#!/usr/bin/env python3
"""Vakantiebot daily search: flights + stays + day costs per route plan, plus Journaway packages.

Usage:
  python3 run.py <config.json> <plans.json> <out.json> [--no-packages] [--no-hotels]

config.json : the hub doc config/settings (plain fields)
plans.json  : list of hub plan docs (each with an "id")
out.json    : results written here (also a short summary on stdout)

Only reads public result pages. Never books, logs in or fills in forms.
"""
import datetime as dt
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import flights
import tp

HERE = os.path.dirname(os.path.abspath(__file__))
COSTS = json.load(open(os.path.join(HERE, "costs.json")))
D = dt.date.fromisoformat


def unwrap(x):
    """ArtifactData files may wrap the fields; accept {data:{...}} or {fields:{...}}."""
    if isinstance(x, dict):
        for k in ("data", "fields", "document"):
            if isinstance(x.get(k), dict) and len(x) <= 4:
                return x[k]
    return x


def usd_to_eur():
    try:
        with urllib.request.urlopen("https://api.frankfurter.app/latest?from=USD&to=EUR", timeout=15) as r:
            return json.load(r)["rates"]["EUR"]
    except Exception:
        return 0.92


def leg_cost(a, b):
    legs = COSTS["legs"]
    for k in (f"{a}>{b}", f"{b}>{a}"):
        if k in legs:
            return legs[k], True
    return COSTS["unknownLegEstimate"], False


def country_costs(country, cfg):
    base = dict(COSTS["countries"].get(country, COSTS["countries"]["default"]))
    over = (cfg.get("perDay") or {}).get(country) or {}
    base.update({k: v for k, v in over.items() if isinstance(v, (int, float))})
    return base


def date_variants(plan, cfg, maxn=8):
    """Depart day D (overnight flight), check in D+1, fly home on the last checkout day."""
    nights = sum(int(s["nights"]) for s in plan["stops"])
    start, end = D(cfg["windowStart"]), D(cfg["windowEnd"])
    last_depart = end - dt.timedelta(days=nights + 1)
    if last_depart < start:
        return nights, []
    span = (last_depart - start).days
    # every possible departure day, evenly thinned to maxn (Google checks rotate through them over the runs)
    picks = sorted({round(i * span / (maxn - 1)) for i in range(maxn)}) if span >= maxn else list(range(span + 1))
    if plan.get("fixedDepart"):
        picks = [(D(plan["fixedDepart"]) - start).days]
    out = []
    for p in picks[:maxn]:
        dep = start + dt.timedelta(days=p)
        out.append({"depart": dep.isoformat(), "checkin": (dep + dt.timedelta(days=1)).isoformat(),
                    "return": (dep + dt.timedelta(days=nights + 1)).isoformat(), "days": nights + 2})
    return nights, out


class Budget:
    def __init__(self, n):
        self.left = n

    def take(self):
        if self.left <= 0 or flights.BLOCKED:
            return False
        self.left -= 1
        return True


FRESH_H = 48     # a Google check is used for the total up to this age
RECHECK_H = 20   # after this age it is queued again


def _age_h(iso):
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600
    except Exception:
        return 1e9


def prev_checks(dbdir, plan_id, nights):
    """Google flight checks saved by earlier runs (travel_trips/<id>.json), still fresh and for this trip length."""
    if not dbdir:
        return []
    try:
        d = unwrap(json.load(open(os.path.join(dbdir, "travel_trips", plan_id + ".json"))))
    except Exception:
        return []
    out = []
    for c in d.get("flightChecks") or []:
        try:
            n = (D(c["return"]) - D(c["depart"])).days
        except Exception:
            continue
        if n == nights + 1 and c.get("pricePP") and _age_h(c.get("checkedAt", "")) <= FRESH_H:
            out.append(c)
    return out


def next_check(st, airports):
    """Next (origin, depart, mode) to check on Google for this plan, or None when everything is fresh.
    Open-jaw routes check both a multi-city ticket ("mc") and a return to the arrival city plus the train back ("rt")."""
    p = st["plan"]
    modes = ["mc", "rt"] if (p.get("flyOut") or p["flyIn"]) != p["flyIn"] else ["rt"]
    recent = {(c["origin"], c["depart"], c["mode"]) for c in st["checks"] if not c.get("manual") and _age_h(c["checkedAt"]) < RECHECK_H} | st["tried"]
    dates = []
    if st["tp"]:
        t = min(st["tp"], key=lambda c: c["compare"])
        for m in modes:
            if (t["origin"], t["depart"], m) not in recent:
                return t["origin"], t["depart"], m
        dates.append(t["depart"])
    vs = st["variants"]
    order = [vs[len(vs) // 2]] + [v for i, v in enumerate(vs) if i != len(vs) // 2]
    dates += [v["depart"] for v in order]
    # flights are most of the cost: first find the cheapest day (every possible departure day from the main airport),
    # then try the other ticket type and the other airports on that day; stays are priced on the winning dates
    for d in dates:
        if (airports[0], d, modes[0]) not in recent:
            return airports[0], d, modes[0]
    priced = [c for c in st["checks"] if c.get("pricePP")]
    if priced:
        b = min(priced, key=lambda c: c["pricePP"] + c.get("backTrainPP", 0))
        bestd, bestm = b["depart"], b["mode"]
    else:
        bestd, bestm = dates[0], modes[0]
    for m in modes:
        if (airports[0], bestd, m) not in recent:
            return airports[0], bestd, m
    for ap in airports[1:]:
        if (ap, bestd, bestm) not in recent:
            return ap, bestd, bestm
    # finally the runner-up days from the other airports
    for ap in airports[1:]:
        for d in dates:
            if (ap, d, bestm) not in recent:
                return ap, d, bestm
    return None



def coverage(st, airports):
    """Core flight options for a route: every departure day from the main airport, the other ticket type on the
    cheapest day, and the other airports on that day. Returns (checked, total)."""
    p = st["plan"]
    modes = ["mc", "rt"] if (p.get("flyOut") or p["flyIn"]) != p["flyIn"] else ["rt"]
    fresh = {(c["origin"], c["depart"], c["mode"]) for c in st["checks"] if not c.get("manual") and _age_h(c.get("checkedAt", "")) <= FRESH_H} | st["tried"]
    dates = [v["depart"] for v in st["variants"]]
    if not dates:
        return 0, 0
    priced = [c for c in st["checks"] if c.get("pricePP")]
    b = min(priced, key=lambda c: c["pricePP"] + c.get("backTrainPP", 0)) if priced else None
    bestd, bestm = (b["depart"], b["mode"]) if b else (dates[len(dates) // 2], modes[0])
    core = {(airports[0], d, modes[0]) for d in dates} | {(airports[0], bestd, m) for m in modes} | {(a, bestd, bestm) for a in airports[1:]}
    return len(core & fresh), len(core)


def google_round(states, airports, budget, pause, log=print):
    """Google checks: Japan routes first until their core options are covered, then every route round robin."""
    def loop(group, core_only):
        progress = True
        while progress and budget.left > 0 and not flights.BLOCKED:
            progress = False
            for st in group:
                if not st["variants"] or budget.left <= 0 or flights.BLOCKED:
                    continue
                if core_only:
                    done, tot = coverage(st, airports)
                    if done >= tot:
                        continue
                nx = next_check(st, airports)
                if not nx:
                    continue
                budget.take()
                st["tried"].add(nx)
                c = run_check(st["plan"], st["nights"], *nx)
                log(f"google {st['plan']['id']} {' '.join(nx)}: " + (f"EUR {c['pricePP']}" if c.get("pricePP") else c.get("error") or "?"))
                if c.get("pricePP"):
                    st["checks"] = [x for x in st["checks"] if (x["origin"], x["depart"], x["mode"]) != nx] + [c]
                progress = True
                time.sleep(pause)
    japan = [st for st in states if st["plan"].get("country") == "Japan"]
    loop(japan, True)
    loop(states, False)


def shared_checks(path, plan_id, nights):
    """Checks from the GitHub flight scanner (flight_checks.json on the flight-data branch)."""
    if not path:
        return []
    try:
        d = json.load(open(path)).get("plans", {}).get(plan_id) or []
    except Exception:
        return []
    return [c for c in d if c.get("pricePP") and _age_h(c.get("checkedAt", "")) <= FRESH_H
            and (D(c["return"]) - D(c["depart"])).days == nights + 1]


def manual_checks(cfg, plan_id, nights):
    """Fares the owner saw on Google Flights from the Netherlands (settings.manualFlights). Google shows
    different fares per country, so these can beat what the bot sees from its servers. Valid 14 days."""
    out = []
    for m in cfg.get("manualFlights") or []:
        try:
            if m.get("plan") != plan_id or (D(m["return"]) - D(m["depart"])).days != nights + 1 or _age_h(m["seenAt"]) > 14 * 24:
                continue
            out.append({"origin": m.get("origin", "AMS"), "depart": m["depart"], "return": m["return"], "mode": m.get("mode", "mc"),
                        "checkedAt": m["seenAt"], "url": m.get("url", ""), "pricePP": int(m["pricePP"]), "airline": m.get("airline", "?"),
                        "manual": True, "out": {"airline": m.get("airline", "?"), "stops": m.get("stops"), "layovers": m.get("layovers", []),
                                                "pricePP": int(m["pricePP"]), "airportChange": False, "note": m.get("note", ""),
                                                "duration": m.get("duration"), "departs": m.get("departs"), "arrives": m.get("arrives")}})
        except Exception:
            continue
    return out


def merge_checks(*lists):
    best = {}
    for c in [c for l in lists for c in l]:
        k = (c["origin"], c["depart"], c["mode"], bool(c.get("manual")))
        if k not in best or c["checkedAt"] > best[k]["checkedAt"]:
            best[k] = c
    return list(best.values())


def run_check(plan, nights, origin, depart, mode):
    fin, fout = plan["flyIn"], plan.get("flyOut") or plan["flyIn"]
    ret = (D(depart) + dt.timedelta(days=nights + 1)).isoformat()
    home_from = fout if mode == "mc" else fin
    r = flights.search_legs([(depart, origin, fin), (ret, home_from, origin)])
    c = {"origin": origin, "depart": depart, "return": ret, "mode": mode,
         "checkedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "url": r["url"]}
    if mode == "rt" and fin != fout:
        c["backTrainPP"] = leg_cost(plan["stops"][-1]["city"], plan["stops"][0]["city"])[0]
    if r["offers"]:
        # cheapest after the comfort penalty (long or night flights), not just the cheapest
        # never a layover where you must change airports (e.g. land at London City, depart from Heathrow)
        same = [o for o in r["offers"] if not o.get("airportChange")]
        scored = [(comfort({"out": o, "compare": o["pricePP"]})[0], o) for o in (same or r["offers"])]
        scored = [x for x in scored if x[0] is not None] or [(o["pricePP"], o) for o in r["offers"]]
        o = min(scored, key=lambda x: x[0])[1]
        c.update({"pricePP": o["pricePP"], "airline": o["airline"], "out": o, "cheapestPP": min(x["pricePP"] for x in r["offers"])})
    else:
        c["error"] = r["error"]
    return c


def google_cand(plan, c):
    fin, fout = plan["flyIn"], plan.get("flyOut") or plan["flyIn"]
    back = c.get("backTrainPP", 0)
    if c["mode"] == "mc":
        typ = f"multi-city ticket (in {fin}, home from {fout})"
    else:
        typ = "return " + fin + (f" (+ train back to {plan['stops'][0]['city']})" if back else "")
    return {"origin": c["origin"], "src": "google", "type": typ,
            "pricePP": c["pricePP"], "backTrainPP": back, "compare": c["pricePP"] + back, "airlines": [c.get("airline")],
            "out": c.get("out"), "back": None, "depart": c["depart"], "return": c["return"],
            "urls": [c["url"]], "checkedAt": c["checkedAt"], "manual": bool(c.get("manual"))}


BIG_CITIES = {"Tokyo": 4, "Seoul": 4.5, "Bangkok": 4.5, "Osaka": 3, "Kyoto": 2.5, "Ho Chi Minh City": 3, "Hanoi": 2.5,
              "Chongqing": 4, "Chengdu": 3.5, "Beijing": 5, "Shanghai": 4.5, "Xi'an": 3}  # max miles from the centre: stay where the fun is
ALWAYS_AVOID = ["capsule", "cabin", "dorm", "bunk", "male only", "love hotel", "pod "]


def _hotel_search(script, city, checkin, checkout, fx, maxmi=None):
    extra = [str(fx)] if script == "hotels.js" else ([str(round(maxmi * 1609))] if maxmi else [])
    args = ["node", os.path.join(HERE, script), city, checkin, checkout] + extra
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=180)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"hotels": [], "error": f"{script} failed: {e}"[:160]}


def pick_stay(city, checkin, nights, rules, fx, cfg):
    """Cheapest decent private room for 2: Booking.com first (real totals for the stay), Google Hotels as backup."""
    checkout = (D(checkin) + dt.timedelta(days=nights)).isoformat()
    minr = float(cfg.get("minRating") or rules["minRating"])  # out of 5 (Booking score / 2)
    minrev = int(cfg.get("minReviews") or 100)
    avoid = list({w.lower() for w in (cfg.get("avoidWords") or []) + ALWAYS_AVOID})
    maxmi = BIG_CITIES.get(city, 3.5)
    res = {"city": city, "checkin": checkin, "checkout": checkout, "nights": nights}
    # Booking.com and Google Hotels (which compares Agoda, Trip.com, Expedia, Hotels.com and the hotels' own sites) at once
    with ThreadPoolExecutor(2) as ex:
        fb = ex.submit(_hotel_search, "booking.js", city, checkin, checkout, fx, maxmi)
        fg = ex.submit(_hotel_search, "hotels.js", city, checkin, checkout, fx)
        rb, rg = fb.result(), fg.result()

    def good(h):
        return ((h.get("rating") or 0) >= minr and (h.get("reviews") or 0) >= minrev
                and (h.get("miles") is None or h["miles"] <= maxmi)
                and not any(w in (h["name"] + " " + (h.get("kind") or "")).lower() for w in avoid)
                and not re.search(r"(?<!non-)(?<!non )smoking", (h.get("kind") or "").lower()))

    gl = [h for h in rg.get("hotels", []) if h.get("nightlyEur")]
    ok = [dict(h) for h in rb.get("hotels", []) if good(h)]
    for h in ok:
        # same hotel cheaper on another site (via Google Hotels)? then use that price
        m = next((g for g in gl if same_hotel(h["name"], g["name"])), None)
        if m and m["nightlyEur"] * nights < h["total"] - 5:
            h["bookingTotal"] = h["total"]
            h["total"] = m["nightlyEur"] * nights
            h["nightlyEur"] = m["nightlyEur"]
            h["cheaperVia"] = "Google Hotels (another booking site)"
    src = "Booking.com"
    if not ok:
        # Google only: no distance known, so only as a fallback
        ok = [dict(h, total=h["nightlyEur"] * nights) for h in gl if good(h)]
        src = "Google Hotels"
    ok.sort(key=lambda h: h.get("total") or h["nightlyEur"] * nights)
    res.update({"source": src, "url": rb.get("url"), "googleUrl": rg.get("url"), "blocked": rb.get("blocked"),
                "error": rb.get("error") or rg.get("error"), "found": len(rb.get("hotels", [])) + len(gl), "qualifying": len(ok)})
    if ok:
        top = ok[:3]
        res["pick"] = top[0]
        res["alternatives"] = top[1:]
        tot = top[0].get("total") or top[0]["nightlyEur"] * nights
        res["pricePP"] = round(tot / 2)  # room for 2, split in two
        res["medianTop3PP"] = round(statistics.median((h.get("total") or h["nightlyEur"] * nights) for h in top) / 2)
    return res


def same_hotel(a, b):
    """Loose name match between sites ("plat hostel keikyu asakusa karin" ~ "Plat Hostel Keikyu Asakusa Karin")."""
    t = lambda x: {w for w in re.findall(r"[a-z0-9]+", x.lower()) if len(w) > 2 and w not in ("hotel", "hostel", "the", "and", "inn")}
    x, y = t(a), t(b)
    return bool(x and y) and len(x & y) / min(len(x), len(y)) >= 0.6


def hours_of(text):
    """'17 hr 10 min' -> 17.2"""
    import re
    if not text:
        return None
    h = re.search(r"(\d+) hr", text)
    m = re.search(r"(\d+) min", text)
    if not h and not m:
        return None
    return round(int(h.group(1) if h else 0) + int(m.group(1) if m else 0) / 60, 1)


def comfort(f):
    """Effective price: real price + EUR per hour above the comfort limit, per direction. None = too long."""
    lim = COSTS.get("comfort", {}).get("hoursFree", 18)
    per = COSTS.get("comfort", {}).get("eurPerHour", 10)
    hard = COSTS.get("comfort", {}).get("maxHours", 30)
    hs = []
    for leg in ("out", "back"):
        o = f.get(leg) or {}
        h = o.get("hours") or hours_of(o.get("duration"))
        if h:
            hs.append(h)
    flags = []
    pen = 0
    for h in hs:
        if h > hard:
            return None, [f"very long flight ({h:.0f} h)"]
        if h > lim:
            pen += (h - lim) * per
            flags.append(f"long flight ({h:.0f} h)")
    for leg in ("out", "back"):
        a = (f.get(leg) or {}).get("arrives") or ""
        m = re.search(r"(\d+):(\d+) (AM|PM)", a)
        if m:
            hr = int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)
            if hr >= 23 or hr < 6:
                flags.append(f"arrives at night ({leg})")
    base = f.get("compare") or f.get("pricePP")
    return round(base + pen), flags


_TP = {}


def tp_rt(o, d, start, end):
    k = ("rt", o, d)
    if k not in _TP:
        _TP[k] = tp.round_trips(o, d, start, end)
    return _TP[k]


def tp_ow(o, d, start, end):
    k = ("ow", o, d)
    if k not in _TP:
        _TP[k] = tp.one_ways(o, d, start, end)
    return _TP[k]


def tp_reference(airports, dest, start, end):
    """No cached fare fits the exact dates (common far ahead): give the cheapest cached return
    that leaves within 2 weeks of the window, as a price reference note (never used in totals)."""
    lo = (D(start) - dt.timedelta(days=14)).isoformat()
    hi = (D(end) + dt.timedelta(days=14)).isoformat()
    best = None
    for ap in airports:
        k = ("ref", ap, dest)
        if k not in _TP:
            _TP[k] = tp.round_trips(ap, dest, lo, hi, 9, 30)
        for r in _TP[k][:1]:
            if best is None or r["pricePP"] < best["pricePP"]:
                best = r
    if not best:
        return None
    return (f"Price reference (Travelpayouts cache, dates not in your window): {best['from']}-{best['to']} return "
            f"{best['depart'][:10]} to {best['return'][:10]}, EUR {best['pricePP']} p.p. ({best['airline']}). "
            "Few fares are cached this far ahead; exact-date fares appear as summer 2027 gets closer.")


def tp_candidates(plan, nights, cfg, airports):
    """Cheapest cached fares that fit this plan exactly: depart D, home D + nights + 1."""
    if cfg.get("useTravelpayouts") is False:
        return []
    start, end = cfg["windowStart"], cfg["windowEnd"]
    fin, fout = plan["flyIn"], plan.get("flyOut") or plan["flyIn"]
    back_train = leg_cost(plan["stops"][-1]["city"], plan["stops"][0]["city"])[0] if fin != fout else 0
    out = []
    for ap in airports:
        if not tp.STATUS["ok"]:
            break
        for r in tp_rt(ap, fin, start, end):
            n = (D(r["return"][:10]) - D(r["depart"][:10])).days
            if n != nights + 1:
                continue
            out.append({"origin": ap, "src": "travelpayouts", "type": "return " + fin + (f" (+ train back to {plan['stops'][0]['city']})" if back_train else ""),
                        "pricePP": r["pricePP"], "backTrainPP": back_train, "compare": r["pricePP"] + back_train,
                        "airlines": [r["airline"]], "hoursOut": r["hoursOut"], "hoursBack": r["hoursBack"],
                        "out": {"airline": r["airline"], "stops": r["stopsOut"], "departs": r["depart"], "hours": r["hoursOut"]},
                        "back": {"airline": r["airline"], "stops": r["stopsBack"], "departs": r["return"], "hours": r["hoursBack"]},
                        "depart": r["depart"][:10], "return": r["return"][:10], "urls": [r["url"]] if r["url"] else [], "cached": True})
            break  # list is sorted by price: first fitting fare is the cheapest for this airport
        if fin != fout and tp.STATUS["ok"]:
            outs = tp_ow(ap, fin, start, end)
            backs = {}
            for b in tp_ow(fout, ap, start, end):
                backs.setdefault(b["depart"][:10], b)  # cheapest per day (sorted)
            bestoj = None
            for a in outs:
                ret = (D(a["depart"][:10]) + dt.timedelta(days=nights + 1)).isoformat()
                b = backs.get(ret)
                if b and (bestoj is None or a["pricePP"] + b["pricePP"] < bestoj[0]):
                    bestoj = (a["pricePP"] + b["pricePP"], a, b)
            if bestoj:
                p, a, b = bestoj
                out.append({"origin": ap, "src": "travelpayouts", "type": "open jaw (2 one-way tickets)", "pricePP": p, "backTrainPP": 0, "compare": p,
                            "airlines": [a["airline"], b["airline"]], "hoursOut": a["hoursOut"], "hoursBack": b["hoursOut"],
                            "out": {"airline": a["airline"], "stops": a["stopsOut"], "departs": a["depart"], "hours": a["hoursOut"]},
                            "back": {"airline": b["airline"], "stops": b["stopsOut"], "departs": b["depart"], "hours": b["hoursOut"]},
                            "depart": a["depart"][:10], "return": b["depart"][:10],
                            "urls": [u for u in (a["url"], b["url"]) if u], "cached": True})
    return out


def evaluate(plan, cfg, st, do_hotels):
    country = plan.get("country", "default")
    rules = country_costs(country, cfg)
    nights, variants, fx = st["nights"], st["variants"], st.get("fx", 0.92)
    out = {"planId": plan["id"], "name": plan.get("name"), "country": country, "nights": nights, "variants": [],
           "notes": list(st["notes"]), "flightChecks": sorted(st["checks"], key=lambda c: c["checkedAt"])[-30:]}
    if not variants:
        out["notes"].append("Route does not fit the travel window.")
        return out
    # live Google prices win; cached Travelpayouts fares only when no Google check exists yet
    gc = [google_cand(plan, c) for c in st["checks"] if c.get("pricePP")]
    cands, src = (gc, "google") if gc else (list(st["tp"]), "travelpayouts")
    fl = None
    if cands:
        for f in cands:
            f["effective"], f["comfortFlags"] = comfort(f)
        cands = [f for f in cands if f["effective"] is not None] or cands
        fl = min(cands, key=lambda f: f["effective"] if f["effective"] is not None else 1e9)
        dep = D(fl["depart"])
        best = {"depart": fl["depart"], "checkin": (dep + dt.timedelta(days=1)).isoformat(),
                "return": fl["return"], "days": nights + 2}
        variants = [{"depart": c["depart"], "return": c["return"], "origin": c["origin"], "type": c["type"], "pricePP": c["pricePP"],
                     "effective": c["effective"]} for c in sorted(cands, key=lambda c: c["effective"] or 1e9)[:8]]
    else:
        # no flight price yet: still price the stays, trains and day costs for the middle date
        out["notes"].append("No flight price yet: Google limits searches from the cloud, so Atlas checks a few flights per run"
                            + ("" if tp.STATUS["ok"] else f"; Travelpayouts: {tp.STATUS['error']}"))
        mid = variants[len(variants) // 2]
        best = {"depart": mid["depart"], "checkin": mid["checkin"], "return": mid["return"], "days": nights + 2}
        variants = []
    # bags
    bag = 0
    if fl and best["days"] > 10 and not all(a in COSTS["bags"]["usuallyIncluded"] for a in fl["airlines"]):
        bag = COSTS["bags"]["extraBagEstimatePP"]
        if cfg.get("sharedBag"):
            bag = round(bag / 2)  # one suitcase for the two of you
    # 3) stays for the best date
    stays, cursor = [], D(best["checkin"])
    for s in plan["stops"]:
        n = int(s["nights"])
        if do_hotels and not s.get("skipHotel"):
            sv = pick_stay(s.get("hotelCity") or s["city"], cursor.isoformat(), n, rules, fx, {**cfg, **(plan.get("stay") or {})})
        else:
            sv = {"city": s["city"], "nights": n, "checkin": cursor.isoformat()}
        if not sv.get("pricePP"):
            est = int((plan.get("stay") or {}).get("fallbackNightlyRoom") or cfg.get("fallbackNightlyRoom") or 90)
            sv["pricePP"] = round(est * n / 2)
            sv["estimated"] = True
        stays.append(sv)
        cursor += dt.timedelta(days=n)
    # 4) transport between stops
    legs, cities = [], [s["city"] for s in plan["stops"]]
    for a, b in zip(cities, cities[1:]):
        c, known = leg_cost(a, b)
        legs.append({"from": a, "to": b, "pricePP": c, "known": known})
    if (plan.get("flyOut") or plan["flyIn"]) == plan["flyIn"] and plan.get("returnCity") and plan["returnCity"] != cities[-1]:
        c, known = leg_cost(cities[-1], plan["returnCity"])
        legs.append({"from": cities[-1], "to": plan["returnCity"], "pricePP": c, "known": known})
    days = best["days"]
    on_ground = days - 1
    parts = {
        "flight": fl["pricePP"] if fl else 0, "bag": bag,
        "stays": sum(s["pricePP"] for s in stays),
        "transport": sum(l["pricePP"] for l in legs) + (fl or {}).get("backTrainPP", 0) + 2 * rules["airportTransfer"],
        "food": rules["foodPerDay"] * on_ground,
        "activities": rules["activitiesPerDay"] * on_ground,
        "local": rules["localTransportPerDay"] * on_ground,
    }
    total = sum(parts.values())
    bmin, bmax = cfg.get("budgetMinPP", 1500), cfg.get("budgetMaxPP", 2500)
    verdict = "top deal" if total <= bmin else "within budget" if total <= bmax else f"€{total - bmax} over budget"
    est_flags = []
    if bag:
        est_flags.append("checked bag estimated" + (" (1 suitcase shared by 2)" if cfg.get("sharedBag") else "") + " - check if the fare includes a suitcase")
    if any(s.get("estimated") for s in stays):
        est_flags.append("some stays estimated (no hotel price found)")
    if any(not l["known"] for l in legs):
        est_flags.append("unknown train leg estimated")
    if not fl:
        out["groundOnly"] = {"depart": best["depart"], "return": best["return"], "days": days, "stays": stays, "legs": legs,
                             "parts": parts, "totalExFlightPP": total, "flags": est_flags}
        return out
    if fl["type"].startswith("open jaw"):
        est_flags.append("open jaw priced as 2 one-way tickets; a multi-city ticket is often cheaper")
    if fl.get("manual"):
        est_flags.append(f"flight price seen by you on Google Flights (NL) {_age_h(fl['checkedAt']) / 24:.0f} days ago; the bot's servers don't get this fare, check it before booking")
    elif fl.get("checkedAt"):
        est_flags.append(f"flight price checked on Google {_age_h(fl['checkedAt']):.0f} h ago")
    if fl.get("cached"):
        est_flags.append("cached fare (seen by Aviasales users recently), check the live price")
    est_flags += fl.get("comfortFlags") or []
    out.update({"variants": variants, "best": {
        "depart": best["depart"], "return": best["return"], "days": days, "flight": fl, "stays": stays, "legs": legs,
        "parts": parts, "totalPP": total, "totalFor2": total * 2, "verdict": verdict, "flags": est_flags,
        "flightSource": src}})
    return out


def packages(cfg):
    countries = cfg.get("packageCountries") or ["Japan"]
    min_days = int(cfg.get("minDays", 11)) - 1
    try:
        p = subprocess.run(["node", os.path.join(HERE, "journaway.js"), cfg["windowStart"], cfg["windowEnd"], str(min_days), *countries],
                           capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired:
        return [{"error": "journaway.js timeout"}]
    rows = []
    for line in p.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    for r in rows:
        # "2 voor 1" deals: the price shown is for two people together, so halve it for a per-person compare
        two_for_one = bool(r.get("twoForOne")) or bool(re.search(r"2[\s-]*(voor|for|4)[\s-]*1", (r.get("title") or "") + " " + (r.get("url") or ""), re.I))
        if two_for_one:
            r["twoForOne"] = True
        for d in r.get("departures", []):
            if two_for_one and not d.get("halved"):
                d["priceFor2"] = d["price"]
                d["price"] = round(d["price"] / 2)
                d["halved"] = True
                d["note"] = ((d.get("note") or "") + " 2-for-1: price shown is for 2 people, halved here").strip()
            # Journaway includes flights, hotels and listed transport; add food + activities for a fair compare
            c = country_costs(r.get("country", "default"), cfg)
            d["extraPP"] = (c["foodPerDay"] + c["activitiesPerDay"]) * (d["days"] - 1)
            d["allInPP"] = d["price"] + d["extraPP"]
    return rows


def main():
    cfg_path, plans_path, out_path = sys.argv[1:4]
    flags = sys.argv[4:]
    cfg = unwrap(json.load(open(cfg_path)))
    plans = [unwrap(p) for p in json.load(open(plans_path))]
    plans = [p for p in plans if p.get("enabled", True)]
    plans.sort(key=lambda p: p.get("priority", 9))
    if cfg.get("comfortHours"):
        COSTS.setdefault("comfort", {})["hoursFree"] = float(cfg["comfortHours"])
    fx = usd_to_eur()
    budget = Budget(int(cfg.get("googleQueryBudget", 8)))
    pause = float(cfg.get("googlePauseSec", 20))
    dbdir = next((f.split("=", 1)[1] for f in flags if f.startswith("--prev=")), None)
    shared = next((f.split("=", 1)[1] for f in flags if f.startswith("--checks=")), None)
    airports = cfg.get("airports") or ["AMS", "BRU", "DUS", "EIN", "RTM"]
    res = {"runAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "usdToEur": fx, "plans": [], "packages": []}
    # 1) per plan: date variants, cached Travelpayouts fares, earlier Google checks
    states = []
    for p in plans:
        nights, variants = date_variants(p, cfg)
        st = {"plan": p, "nights": nights, "variants": variants, "tp": [], "notes": [], "tried": set(),
              "checks": merge_checks([c for c in prev_checks(dbdir, p["id"], nights) if not c.get("manual")],
                                     shared_checks(shared, p["id"], nights), manual_checks(cfg, p["id"], nights)), "fx": fx}
        if variants:
            st["tp"] = tp_candidates(p, nights, cfg, airports)
            if not st["tp"] and tp.STATUS["ok"] and cfg.get("useTravelpayouts") is not False:
                ref = tp_reference(airports, p["flyIn"], cfg["windowStart"], cfg["windowEnd"])
                if ref:
                    st["notes"].append(ref)
        states.append(st)
    # 2) Google checks: Japan first, then the rest
    google_round(states, airports, budget, pause, log=lambda m: print(m, flush=True))
    # 3) stays, trains, day costs
    for st in states:
        st["tried"] = set()
        r = evaluate(st["plan"], cfg, st, "--no-hotels" not in flags)
        done, tot = coverage(st, airports)
        r["coverage"] = {"done": done, "total": tot}
        if r.get("best") and done < tot:
            r["best"].setdefault("flags", []).append(f"flight scan {done}/{tot} options checked, cheaper dates may still turn up")
        res["plans"].append(r)
    res["googleBlocked"] = flights.BLOCKED
    res["travelpayouts"] = dict(tp.STATUS)
    res["googleQueriesLeft"] = budget.left
    if "--no-packages" not in flags:
        res["packages"] = packages(cfg)
    json.dump(res, open(out_path, "w"), indent=1, ensure_ascii=False)
    for p in res["plans"]:
        b = p.get("best")
        print(f"{p['name']}: " + (f"€{b['totalPP']} p.p. ({b['verdict']}), {b['depart']}→{b['return']}, vlucht €{b['flight']['pricePP']} vanaf {b['flight']['origin']}" if b else "; ".join(p["notes"]) or "geen resultaat"))
    pk = [(d["allInPP"], r["title"], d["from"]) for r in res["packages"] for d in r.get("departures", [])]
    if pk:
        m = min(pk)
        print(f"Goedkoopste pakketreis (incl. eten/uitjes): €{m[0]} p.p. {m[1]} vanaf {m[2]}")
    print("Google geblokkeerd" if flights.BLOCKED else f"Google ok ({budget.left} zoekopdrachten over)")
    print("Travelpayouts:", "ok" if tp.STATUS["ok"] else tp.STATUS["error"], f"({tp.STATUS['calls']} calls)")


if __name__ == "__main__":
    main()
