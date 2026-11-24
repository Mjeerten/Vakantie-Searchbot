/* Travel Desk view (#travel). Reads and writes only the travel_* collections of the Agent Hub database.
   All database text is set with textContent (it was written by the bot from travel sites). */
(() => {
  const $ = (id) => document.getElementById(id);
  const isTv = () => /^#travel(\/|$)/.test(location.hash);
  const el = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v; else if (k === "text") e.textContent = v; else if (k === "style") e.setAttribute("style", v);
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e;
  };
  const eur = (n) => (n == null || isNaN(n)) ? "–" : "€" + Math.round(n).toLocaleString("en-GB");
  const safe = (u) => (typeof u === "string" && u.startsWith("https://")) ? u : null;
  const day = (d) => d ? new Date(d.slice(0, 10) + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "";
  const when = (iso) => { if (!iso) return "never"; const d = new Date(iso); if (isNaN(d)) return "–"; const t = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); return d.toDateString() === new Date().toDateString() ? "today " + t : d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) + " " + t; };
  let toastT; const toast = (t) => { const e = $("tvToast"); e.textContent = t; e.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => e.hidden = true, 2600); };

  const S = { db: null, cfg: null, cfgVer: 0, trips: [], plans: [], pkgs: [], runs: [], connected: false };
  const SEG = [["flight", "Flight", "var(--amber)"], ["bag", "Bag", "var(--dim)"], ["stays", "Stays", "var(--cyan)"], ["transport", "Trains", "#b394ff"], ["food", "Food", "var(--good)"], ["activities", "Activities", "#ff7eb6"], ["local", "Local transport", "var(--muted)"]];
  const INTERESTS = [["city", "City, food & nightlife"], ["culture", "Culture & temples"], ["nature", "Nature & views"], ["beach", "Beach & relaxing"]];
  const COUNTRIES = ["Japan", "China", "Vietnam", "Thailand", "Zuid-Korea"];
  const AIRPORTS = ["AMS", "BRU", "DUS", "EIN", "RTM"];
  const PKG = ["Japan", "China", "Vietnam", "Thailand", "Zuid-Korea", "Taiwan", "Indonesie", "Maleisie", "Cambodja"];
  const label = (c) => ({ "Zuid-Korea": "South Korea", Indonesie: "Indonesia", Maleisie: "Malaysia", Cambodja: "Cambodia" }[c] || c);

  /* next scheduled check: the routine looks at 08:17, 12:17, 16:17 and 20:17 Amsterdam time and searches when asked or when the last search is 3 h old (every slot: Google allows only a few flight checks per run) */
  function nextSearch(c) {
    if (!c) return "–";
    if (c.status === "running") return "running now";
    const due = c.runRequested || !c.lastRunAt ? Date.now() : Date.parse(c.lastRunAt) + 3 * 36e5;
    const now = new Date(Math.max(Date.now(), due));
    for (let i = 0; i < 9; i++) {
      for (const h of [8, 12, 16, 20]) {
        const d = new Date(now); d.setDate(now.getDate() + i);
        const ams = new Date(d.toLocaleString("en-US", { timeZone: "Europe/Amsterdam" }));
        const off = d - ams;
        const slot = new Date(ams.getFullYear(), ams.getMonth(), ams.getDate(), h, 17, 0).getTime() + off;
        if (slot >= now.getTime()) return when(new Date(slot).toISOString());
      }
    }
    return "–";
  }

  function verdict(total) {
    const max = S.cfg?.budgetMaxPP ?? 2500, min = S.cfg?.budgetMinPP ?? 1500;
    if (total <= min) return ["good", "top deal", "ok"];
    if (total <= max) return ["good", "within budget", "ok"];
    if (total <= max * 1.15) return ["warn", eur(total - max) + " over budget", "over"];
    return ["bad", eur(total - max) + " over budget", "far"];
  }

  function spark(hist) {
    if (!hist || hist.length < 2) return null;
    const v = hist.map((h) => h.totalPP), lo = Math.min(...v), hi = Math.max(...v), w = 200, h = 26, p = 3;
    const x = (i) => p + i * (w - 2 * p) / (v.length - 1), y = (n) => hi === lo ? h / 2 : p + (hi - n) * (h - 2 * p) / (hi - lo);
    const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`); svg.setAttribute("class", "tv-spark"); svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img"); svg.setAttribute("aria-label", `Price history, ${eur(v[0])} to ${eur(v.at(-1))}`);
    const pts = v.map((n, i) => `${x(i)},${y(n)}`).join(" ");
    const a = document.createElementNS(ns, "polygon"); a.setAttribute("points", `${x(0)},${h} ${pts} ${x(v.length - 1)},${h}`); a.setAttribute("fill", "rgba(98,210,232,.12)");
    const l = document.createElementNS(ns, "polyline"); l.setAttribute("points", pts); l.setAttribute("fill", "none"); l.setAttribute("stroke", "#62d2e8"); l.setAttribute("stroke-width", "1.5"); l.setAttribute("vector-effect", "non-scaling-stroke");
    const d = document.createElementNS(ns, "circle"); d.setAttribute("cx", x(v.length - 1)); d.setAttribute("cy", y(v.at(-1))); d.setAttribute("r", "2.5"); d.setAttribute("fill", "#ffb34a");
    svg.append(a, l, d); return svg;
  }

  function renderTop() {
    const c = S.cfg;
    $("tvLed").className = "led " + (S.connected ? "on" : "off");
    $("tvDbState").textContent = S.db === null ? "Offline" : S.connected ? "Live" : "Connecting";
    $("tvWindow").textContent = c ? `${day(c.windowStart)} – ${day(c.windowEnd)}` : "–";
    $("tvLast").textContent = c ? (c.status === "running" ? "running" : when(c.lastRunAt)) : "–";
    $("tvNext").textContent = nextSearch(c);
    const run = $("tvRunBtn");
    run.disabled = !S.db || !c || c.runRequested || c.status === "running";
    run.textContent = c?.status === "running" ? "Searching…" : c?.runRequested ? "Search queued" : "Search now";
    $("tvSettingsBtn").disabled = !S.db || !c;
  }

  function renderReadouts() {
    const list = S.trips.filter((t) => t.best).sort((a, b) => a.best.totalPP - b.best.totalPP);
    const b = list[0], c = S.cfg;
    $("tvBest").textContent = b ? eur(b.best.totalPP) : "–";
    $("tvBestS").textContent = b ? `${b.name} · ${day(b.best.depart)} – ${day(b.best.return)}` : (c?.lastSummary || "Waiting for the first search");
    $("tvBudget").textContent = c ? `${eur(c.budgetMinPP)}–${eur(c.budgetMaxPP).replace("€", "")}` : "–";
    const fl = list.map((t) => t.best.flight).filter((f) => f && f.pricePP).sort((a, b) => a.pricePP - b.pricePP)[0];
    $("tvFlight").textContent = fl ? eur(fl.pricePP) : "–";
    $("tvFlightS").textContent = fl ? `from ${fl.origin} · ${(fl.airlines || []).join(" / ")}${fl.cached ? " · cached fare" : ""}` : "return, per person";
    $("tvRoutes").textContent = String(S.plans.length);
  }

  function tripCard(t) {
    const b = t.best, parts = b.parts || {}, sum = Object.values(parts).reduce((a, n) => a + (n || 0), 0) || 1;
    const [chipCls, vtext, pctCls] = verdict(b.totalPP);
    const fl = b.flight || {};
    const route = el("div", { class: "tv-route" });
    (b.stays || []).forEach((s, i) => { if (i) route.append(el("i", { text: "→" })); route.append(el("span", { text: s.city }), el("small", { text: ` ${s.nights}n` })); });
    const bar = el("div", { class: "tv-bar", role: "img", "aria-label": "Cost breakdown" }), leg = el("div", { class: "tv-legend" });
    for (const [k, name, col] of SEG) { const v = parts[k] || 0; if (!v) continue; bar.append(el("span", { style: `width:${v / sum * 100}%;background:${col}`, title: `${name} ${eur(v)}` })); leg.append(el("span", {}, el("i", { style: `background:${col}` }), `${name} ${eur(v)}`)); }
    const meta = el("div", { class: "dmeta" },
      el("span", { class: "chip " + chipCls, text: vtext }),
      el("span", { class: "chip", text: `${day(b.depart)} → ${day(b.return)} · ${b.days} days` }),
      el("span", { class: "chip cyan", text: `${fl.origin || "?"} · ${(fl.airlines || []).join(" / ") || "?"}` }),
      fl.cached ? el("span", { class: "chip", text: "cached fare" }) : el("span", { class: "chip amber", text: fl.checkedAt ? "Google fare · " + when(fl.checkedAt) : "live fare" }));
    const flags = el("div", { class: "flags" }, (b.flags || []).map((f) => el("span", { class: "chip warn", text: f })));
    const items = el("ul");
    const fdesc = [fl.type, fl.out && (fl.out.stops != null ? (fl.out.stops ? fl.out.stops + " stop" + (fl.out.stops > 1 ? "s" : "") : "direct") : null), fl.out && (fl.out.duration || (fl.out.hours ? fl.out.hours + " h" : null))].filter(Boolean).join(" · ");
    items.append(el("li", {}, el("b", { text: `Flight ${eur(fl.pricePP)}` }), " " + fdesc + (fl.google ? ` · Google now ${eur(fl.google.pricePP)}` : "")));
    for (const s of (b.stays || [])) items.append(el("li", {}, el("b", { text: `${s.city} ${s.nights} nights ${eur(s.pricePP)}` }), " " + (s.pick ? `${s.pick.name} · ${s.pick.score10 != null ? s.pick.score10 + "/10" : (s.pick.rating ?? "?") + "★"} (${s.pick.reviews ?? "?"} reviews) · ${eur(s.pick.nightlyEur)}/night for 2${s.pick.kind ? " · " + s.pick.kind.split(/ (Free cancellation|We have|Breakfast)/)[0] : ""}${s.pick.cheaperVia ? " · cheaper on another site via Google Hotels (Booking " + eur(s.pick.bookingTotal) + ")" : s.source ? " · " + s.source : ""}` : "estimated, no hotel price found")));
    for (const l of (b.legs || [])) items.append(el("li", {}, el("b", { text: `${l.from} → ${l.to} ${eur(l.pricePP)}` }), l.known ? " train/bus" : " estimate"));
    const why = S.plans.find((p) => p.id === t.planId)?.why;
    const acts = el("div", { class: "dact" });
    const seen = new Set();
    for (const u of [...(fl.urls || []), fl.google?.url]) { const s = safe(u); if (s && !seen.has(s)) { seen.add(s); acts.append(el("a", { class: "btn sm", href: s, target: "_blank", rel: "noopener", text: s.includes("aviasales") ? "Flight ↗" : "Google Flights ↗" })); } }
    for (const s of (b.stays || [])) { const u = safe(s.pick?.url) || safe(s.url); if (u) acts.append(el("a", { class: "btn sm", href: u, target: "_blank", rel: "noopener", text: (s.pick?.url ? "Stay " : "Hotels ") + s.city + " ↗" })); }
    const nums = el("div", { class: "dnums" },
      el("div", { class: "row big" }, el("span", { text: "Per person" }), el("b", { text: eur(b.totalPP) })),
      el("div", { class: "row" }, el("span", { text: "For two" }), el("b", { text: eur(b.totalPP * 2) })),
      el("div", { class: "row" }, el("span", { text: `${b.days} days, per day` }), el("b", { text: eur(Math.round(b.totalPP / (b.days || 1))) })),
      el("div", { class: "row" }, el("span", { text: "Flight" }), el("b", { text: eur(parts.flight) })),
      el("div", { class: "row" }, el("span", { text: "Stays" }), el("b", { text: eur(parts.stays) })),
      el("div", { class: "row" }, el("span", { text: "Food + fun" }), el("b", { text: eur((parts.food || 0) + (parts.activities || 0)) })),
      t.bestEver && t.bestEver.totalPP < b.totalPP ? el("div", { class: "row profit" }, el("span", { text: "Lowest seen" }), el("b", { text: eur(t.bestEver.totalPP) })) : null,
      spark(t.history),
      el("div", { class: "row" }, el("span", { text: "Updated" }), el("b", { text: when(t.updatedAt) })));
    return el("article", { class: "deal", style: `--hue:${chipCls === "good" ? "var(--good)" : chipCls === "warn" ? "var(--amber)" : "var(--bad)"}` },
      el("div", { class: "disc" }, el("div", { class: "pct " + pctCls, text: eur(b.totalPP) }), el("div", { class: "lbl", text: "all-in p.p." })),
      el("div", { class: "dbody" },
        el("span", { class: "dtitle", text: `${t.name}` }),
        meta, route, bar, leg,
        why ? el("p", { class: "dwhy", text: why }) : null,
        t.lastNote ? el("p", { class: "dwhy", text: "Last search: " + t.lastNote }) : null,
        flags.childElementCount ? flags : null,
        el("details", { class: "tv-more" }, el("summary", { text: "Breakdown" }), items),
        acts),
      nums);
  }

  function renderFeed() {
    const box = $("tvFeed"); box.replaceChildren();
    const list = S.trips.filter((t) => t.best).sort((a, b) => a.best.totalPP - b.best.totalPP);
    if (!list.length) {
      box.append(el("div", { class: "empty" }, el("strong", { text: S.db === null ? "Database offline" : "No trips priced yet" }),
        el("p", { text: S.db === null ? "Open the Agent Hub on claude.ai while signed in." : "Atlas prices every route once a day. Press Search now to queue a search; it starts at the next check (08:17, 12:17, 16:17 or 20:17)." })));
      return;
    }
    /* Japan is the first choice: its trips always come first, the rest below an "Other trips" divider */
    /* Japan: trips within budget first. 16 days is the owner's sweet spot; a longer trip ranks higher only when each
       extra day costs less than EUR 40 p.p. (so "a bit longer for not much more"). Over budget: by price. */
    const maxB = S.cfg?.budgetMaxPP || 2500, fits = (t) => t.best.totalPP <= maxB;
    const score = (t) => t.best.totalPP - 40 * ((t.best.days || 16) - 16);
    /* Japan: one card per route family (golden, via Kanazawa, golden + Kanazawa), the cheapest of both directions */
    const fam = (t) => String(t.planId || t.id || "").replace(/-rev$/, ""), famBest = new Map();
    for (const t of list.filter((t) => t.country === "Japan")) { const k = fam(t), c = famBest.get(k); if (!c || t.best.totalPP < c.best.totalPP) famBest.set(k, t); }
    const ORDER = ["jp-classic", "jp-golden", "jp-kanazawa", "jp-golden-kanazawa"], rank = (t) => { const i = ORDER.indexOf(fam(t)); return i < 0 ? 99 : i; };
    const jp = [...famBest.values()].sort((a, b) => rank(a) - rank(b) || score(a) - score(b)), rest = list.filter((t) => t.country !== "Japan");
    for (const t of jp) box.append(tripCard(t));
    if (jp.length && rest.length) box.append(el("div", { class: "tv-divider", text: "Other trips" }));
    for (const t of rest) box.append(tripCard(t));
  }

  function renderPackages() {
    const box = $("tvPkgWrap"); box.replaceChildren();
    const rows = [];
    for (const p of S.pkgs) for (const d of (p.departures || [])) rows.push({ p, d });
    rows.sort((a, b) => (a.d.allInPP ?? a.d.price) - (b.d.allInPP ?? b.d.price));
    const seen = new Set(), top = rows.filter((r) => !seen.has(r.p.url) && seen.add(r.p.url)).slice(0, 14);
    if (!top.length) { box.append(el("div", { class: "empty" }, el("strong", { text: "No package tours yet" }), el("p", { text: "Journaway and other tour operators are checked during the daily search." }))); return; }
    const tb = el("tbody");
    for (const { p, d } of top) {
      const u = safe(p.url), all = d.allInPP ?? d.price, [cls, vt] = verdict(all);
      tb.append(el("tr", {},
        el("td", { class: "sum" }, u ? el("a", { href: u, target: "_blank", rel: "noopener", text: p.title }) : p.title, el("div", { style: "color:var(--dim);font:11px/1.4 var(--f-mono)", text: (p.source || "Journaway") + (p.twoForOne ? " · 2-for-1: listed price is for 2, halved" : "") })),
        el("td", { text: `${day(d.from)} → ${day(d.to)} · ${d.days} d` }),
        el("td", { text: d.airport || "–" }),
        el("td", { class: "num", text: eur(d.price) }),
        el("td", { class: "num" }, el("b", { text: eur(all) })),
        el("td", {}, el("span", { class: "chip " + cls, text: vt }))));
    }
    box.append(el("div", { class: "log" }, el("table", {},
      el("thead", {}, el("tr", {}, ["Trip", "Dates", "From", "Tour p.p.", "All-in p.p.", ""].map((h) => el("th", { text: h })))), tb)));
  }

  function renderRoutes() {
    const box = $("tvBay"); box.replaceChildren();
    if (!S.plans.length) { box.append(el("div", { class: "empty" }, el("strong", { text: "No routes yet" }), el("p", { text: "Atlas picks routes from your settings at the next search." }))); return; }
    for (const p of [...S.plans].sort((a, b) => (a.priority ?? 9) - (b.priority ?? 9))) {
      const t = S.trips.find((x) => x.planId === p.id);
      box.append(el("div", { class: "agent" },
        el("div", { class: "agent-top" }, el("div", {}, el("h3", { text: label(p.country) }), el("div", { class: "aname", text: p.name })),
          el("span", { class: "status" }, el("span", { class: "chip " + (t?.best ? verdict(t.best.totalPP)[0] : ""), text: t?.best ? eur(t.best.totalPP) : t?.groundOnly ? eur(t.groundOnly.totalExFlightPP) + " + flight" : "not priced" }))),
        el("div", { class: "tv-route" }, (p.stops || []).flatMap((s, i) => [i ? el("i", { text: "→" }) : null, el("span", { text: s.city }), el("small", { text: ` ${s.nights}n` })])),
        el("p", { class: "why", text: p.why || "" }),
        el("div", { class: "specs" },
          el("div", {}, el("div", { class: "k", text: "Nights" }), el("div", { class: "v", text: String(p.nights ?? "–") })),
          el("div", {}, el("div", { class: "k", text: "Fly in" }), el("div", { class: "v", text: p.flyIn || "–" })),
          el("div", {}, el("div", { class: "k", text: "Fly out" }), el("div", { class: "v", text: p.flyOut || "–" })))));
    }
  }

  function renderLog() {
    const box = $("tvLogWrap"); box.replaceChildren();
    if (!S.runs.length) { box.append(el("div", { class: "empty" }, el("strong", { text: "No searches yet" }))); return; }
    const tb = el("tbody");
    for (const r of S.runs) tb.append(el("tr", {}, el("td", { text: when(r.at) }), el("td", { class: "note", text: r.summary || "" }), el("td", { text: r.googleBlocked ? "Google blocked part" : "ok" })));
    box.append(el("div", { class: "log" }, el("table", {}, el("thead", {}, el("tr", {}, ["When", "Result", "Sources"].map((h) => el("th", { text: h })))), tb)));
  }

  function renderAll() { renderTop(); renderReadouts(); renderFeed(); renderPackages(); renderRoutes(); renderLog(); }

  /* ---------- settings drawer ---------- */
  function checks(boxId, options, selected, lab = (x) => x) {
    const box = $(boxId); box.replaceChildren();
    for (const o of options) { const v = Array.isArray(o) ? o[0] : o, t = Array.isArray(o) ? o[1] : lab(o);
      const c = el("input", { type: "checkbox", id: `${boxId}-${v}`, value: v, checked: (selected || []).includes(v) });
      box.append(el("label", { for: `${boxId}-${v}` }, c, t)); }
  }
  const picked = (boxId) => [...$(boxId).querySelectorAll("input:checked")].map((i) => i.value);
  function openSettings() {
    const c = S.cfg || {};
    $("tvStart").value = c.windowStart || ""; $("tvEnd").value = c.windowEnd || ""; $("tvMinDays").value = c.minDays ?? 11;
    $("tvPace").value = c.pace || "relaxed-medium"; $("tvBMin").value = c.budgetMinPP ?? 1500; $("tvBMax").value = c.budgetMaxPP ?? 2500;
    checks("tvInterests", INTERESTS, c.interests || ["city", "culture", "nature"]);
    checks("tvCountries", COUNTRIES, c.countries || ["Japan", "Vietnam", "Thailand"], label);
    checks("tvAirports", AIRPORTS, c.airports || AIRPORTS);
    checks("tvPkgCountries", PKG, c.packageCountries || ["Japan"], label);
    const jp = (c.perDay || {}).Japan || {};
    $("tvFood").value = jp.foodPerDay ?? 30; $("tvAct").value = jp.activitiesPerDay ?? 12; $("tvHours").value = c.comfortHours ?? 18;
    $("tvWishes").value = c.wishes || ""; $("tvFormErr").hidden = true;
    $("tvScrim").hidden = false; $("tvDrawer").hidden = false; $("tvStart").focus();
  }
  function closeSettings() { $("tvScrim").hidden = true; $("tvDrawer").hidden = true; }
  async function saveSettings(e) {
    e.preventDefault();
    const err = $("tvFormErr"), num = (id) => Number($(id).value);
    const body = {
      windowStart: $("tvStart").value, windowEnd: $("tvEnd").value, minDays: num("tvMinDays"), pace: $("tvPace").value,
      budgetMinPP: num("tvBMin"), budgetMaxPP: num("tvBMax"), interests: picked("tvInterests"), countries: picked("tvCountries"),
      airports: picked("tvAirports"), packageCountries: picked("tvPkgCountries"), comfortHours: num("tvHours"),
      perDay: { ...(S.cfg?.perDay || {}), Japan: { foodPerDay: num("tvFood"), activitiesPerDay: num("tvAct") } },
      wishes: $("tvWishes").value.slice(0, 1500), replan: true, settingsChangedAt: new Date().toISOString(),
    };
    const bad = !body.windowStart || !body.windowEnd || body.windowEnd <= body.windowStart ? "Pick a leave date before the home-by date."
      : body.budgetMaxPP < body.budgetMinPP ? "The budget's upper limit is below the lower limit."
      : !body.interests.length ? "Pick at least one interest." : !body.countries.length ? "Pick at least one destination."
      : !body.airports.length ? "Pick at least one departure airport." : null;
    if (bad) { err.textContent = bad; err.hidden = false; return; }
    $("tvSaveBtn").disabled = true;
    try { await S.db.doc("travel_config/settings").update(body); closeSettings(); toast("Saved. Atlas re-plans at the next search."); }
    catch (x) { err.textContent = "Couldn't save that (" + (x.code || "error") + "). Try again in a moment."; err.hidden = false; }
    $("tvSaveBtn").disabled = false;
  }

  /* ---------- wiring ---------- */
  $("tvSettingsBtn").addEventListener("click", openSettings);
  $("tvCancelBtn").addEventListener("click", closeSettings);
  $("tvScrim").addEventListener("click", closeSettings);
  $("tvForm").addEventListener("submit", saveSettings);
  $("tvRunBtn").addEventListener("click", async () => {
    if (!S.db) return; $("tvRunBtn").disabled = true;
    try { await S.db.doc("travel_config/settings").update({ runRequested: true, requestedAt: new Date().toISOString() }); toast("Search queued. Atlas starts at the next check."); }
    catch (x) { $("tvRunBtn").disabled = false; toast("Couldn't queue the search (" + (x.code || "error") + ")."); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !isTv()) return;
    if (!$("tvDrawer").hidden) return closeSettings();
    location.hash = "";
  });
  $("tvBack").addEventListener("click", (e) => { e.preventDefault(); location.hash = ""; });

  renderAll();
  (async () => {
    let db = null; try { db = window.claude?.use ? await window.claude.use("db") : null; } catch (x) { db = null; }
    S.db = db; if (!db) { renderAll(); return; }
    const rows = (q) => q.docs.map((d) => ({ id: d.id, ...d.data() }));
    const timer = setTimeout(() => { if (!S.connected) { $("tvDbState").textContent = "Not reachable yet"; } }, 10000);
    db.doc("travel_config/settings").onSnapshot((d) => { S.cfg = d.exists ? d.data() : null; if (!d.metadata.fromCache) { S.connected = true; clearTimeout(timer); } renderAll(); }, () => { clearTimeout(timer); renderAll(); });
    db.collection("travel_trips").onSnapshot((q) => { S.trips = rows(q).map((t) => ({ planId: t.id, ...t })); renderAll(); }, () => {});
    db.collection("travel_plans").onSnapshot((q) => { S.plans = rows(q); renderAll(); }, () => {});
    db.collection("travel_packages").onSnapshot((q) => { S.pkgs = rows(q); renderPackages(); }, () => {});
    db.collection("travel_runs").orderBy("at", "desc").limit(8).onSnapshot((q) => { S.runs = rows(q); renderLog(); }, () => {});
    setInterval(renderTop, 60000);
  })();
})();
