#!/usr/bin/env python3
"""Japan flight checks through SerpApi's Google Flights API (free plan: 250 searches a month, no Google blocking).
Runs in the GitHub workflow; the key comes from the repository secret SERPAPI_KEY (never stored here).
Usage: python3 serp_scan.py <state.json> <checks_in.json> <checks_out.json> [sweep]

Owner's split of the free searches (max 8 a day, 240 a month, never below 5 left on the account):
- sweep (once, or on request): for every Japan ticket group (routes that fly the same tickets) its 3 cheapest
  days (by the free scanner) as open jaw, plus a round trip on the best day: 24 searches
- every run: re-check the current best flight of each ticket group: golden route groups every 12 h, Koyasan
  every 24 h, classic every 48 h (Kanazawa shares the golden tickets): about 7 a day
- left-over daily searches: confirm a free-scanner fare that is EUR 30+ below the last SerpApi-confirmed one
One search covers all five home airports at once; out from one and home to another is fine (owner's wish).
China gets no SerpApi searches.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse

import planner
import run

API = "https://serpapi.com/search.json"
DAY_CAP, MONTH_CAP, KEEP_LEFT, SWEEP_CAP = 10, 240, 5, 24
REPEAT_H = {1: 12, 2: 24, 3: 48}  # by scanTier: golden, Koyasan, classic


def call(url):
    p = subprocess.run(["curl", "-s", "-m", "150", url], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"error": "bad response: " + p.stdout[:120]}


def left_on_account(key):
    d = call("https://serpapi.com/account.json?" + urllib.parse.urlencode({"api_key": key}))  # free, not counted
    return d.get("total_searches_left", d.get("plan_searches_left")), d.get("error")


def fmt_time(s):
    # "2027-07-27 10:55" -> "Tuesday, July 27 10:55 AM" (the format the rest of the bot reads)
    t = dt.datetime.strptime(s, "%Y-%m-%d %H:%M")
    return f"{t.strftime('%A, %B')} {t.day} {t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def offer(x):
    f = x["flights"]
    airlines = list(dict.fromkeys(s.get("airline") for s in f))
    lay = x.get("layovers") or []
    return {"pricePP": x["price"], "airline": " and ".join(airlines),
            "stops": len(f) - 1, "duration": f"{x.get('total_duration', 0) // 60} hr {x.get('total_duration', 0) % 60} min",
            "from": f[0]["departure_airport"]["name"], "fromId": f[0]["departure_airport"]["id"],
            "departs": fmt_time(f[0]["departure_airport"]["time"]),
            "to": f[-1]["arrival_airport"]["name"], "arrives": fmt_time(f[-1]["arrival_airport"]["time"]),
            "layovers": [l.get("name") for l in lay][:3], "layoverMins": [int(l.get("duration") or 0) for l in lay],
            "selfTransfer": any("separate" in str(e).lower() or "self" in str(e).lower() for e in (x.get("extensions") or [])),
            "airportChange": any(s["departure_airport"]["id"] != p["arrival_airport"]["id"] for p, s in zip(f, f[1:])),
            "toId": f[-1]["arrival_airport"]["id"],
            "_dep": x.get("departure_token"), "_book": x.get("booking_token")}


# SerpApi takes airport codes, not Google's city codes (TYO/OSA gave "no results")
CITY = {"TYO": "HND,NRT", "OSA": "KIX,ITM", "SPK": "CTS", "NGO": "NGO", "FUK": "FUK"}


def params(key, kind, depart, ret, fin, fout, airports):
    ap = ",".join(airports)
    fin, fout = CITY.get(fin, fin), CITY.get(fout, fout)
    q = {"engine": "google_flights", "currency": "EUR", "gl": "nl", "hl": "en", "adults": 1, "api_key": key}
    if kind == "rt":
        q.update(type=1, departure_id=ap, arrival_id=fin, outbound_date=depart, return_date=ret)
    else:
        q.update(type=3, multi_city_json=json.dumps([{"departure_id": ap, "arrival_id": fin, "date": depart},
                                                     {"departure_id": fout, "arrival_id": ap, "date": ret}], separators=(",", ":")))
    return q


def search(key, kind, depart, ret, fin, fout, airports):
    d = call(API + "?" + urllib.parse.urlencode(params(key, kind, depart, ret, fin, fout, airports)))
    offers = [offer(x) for x in (d.get("best_flights") or []) + (d.get("other_flights") or []) if x.get("price")]
    return offers, d.get("error"), (d.get("search_metadata") or {}).get("google_flights_url")


def strip(o):
    return {k: v for k, v in o.items() if not k.startswith("_")}


def booking(key, q, o, airports):
    """Click through like a person, with 2 more searches: this outbound -> cheapest safe way home -> Google's
    booking page ("Book with JAL / BA ..."). Returns the booking page link, its total price and the bag rules."""
    d = call(API + "?" + urllib.parse.urlencode(dict(q, departure_token=o["_dep"])))
    back = [offer(x) for x in (d.get("best_flights") or []) + (d.get("other_flights") or []) if x.get("price")]
    back = [b for b in back if b["toId"] in airports and run.safe_connection(b) and b.get("_book")]
    if not back:
        return {"error": d.get("error") or "no safe way home"}, 1
    b = min(back, key=lambda b: b["pricePP"])
    d = call(API + "?" + urllib.parse.urlencode(dict(q, booking_token=b["_book"])))
    opts = [x.get("together") or x.get("departing") or {} for x in d.get("booking_options") or []]
    opts = [x for x in opts if x.get("price")]
    bags = (d.get("baggage_prices") or {}).get("together") or []
    url = (d.get("search_metadata") or {}).get("google_flights_url")
    print("  booking page:", (url or "")[:90], "| keys", sorted(d.keys())[:12], "| bags", bags, flush=True)
    if not opts:
        return {"error": d.get("error") or "no booking options", "back": strip(b), "pricePP": b["pricePP"]}, 2
    free = [m for m in bags if re.search(r"(\d+|one|1st) free checked bag|free checked bags?", str(m), re.I)]
    return {"bookUrl": url, "pricePP": min(x["price"] for x in opts), "back": strip(b),
            "bookWith": [{"name": x.get("book_with"), "pricePP": x["price"], "airline": bool(x.get("airline"))} for x in opts][:4],
            "bags": bags, "bagsIncluded": bool(free)}, 2


def ident(o):
    return f"{o.get('airline')}|{o.get('departs')}"


def main():
    state_path, in_path, out_path = sys.argv[1:4]
    mode = sys.argv[4] if len(sys.argv) > 4 else ""
    sweep = mode == "sweep"
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        print("SerpApi: no key, skipped")
        return
    cfg = json.load(open("search_config.json"))
    airports = cfg["airports"]
    try:
        state = json.load(open(state_path)).get("serpapi") or {}
    except Exception:
        state = {}
    data = json.load(open(in_path))
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.strftime("%Y-%m-%d")
    if state.get("day") != today:
        state.update(day=today, usedToday=0)
    if state.get("month") != today[:7]:
        state.update(month=today[:7], usedMonth=0)
    left, err = left_on_account(key)
    print(f"SerpApi: {left} searches left on the account, {state.get('usedToday', 0)} used today", flush=True)
    if err or left is None:
        print("SerpApi account check failed: " + str(err)[:120])
        return

    # ticket groups (routes that fly the same tickets), Japan only, owner's order
    plans = [p for p in planner.plan(cfg) if p.get("country") == "Japan"]
    plans.sort(key=lambda p: (p.get("scanTier", 9), p.get("priority", 9)))
    groups = {}
    for p in plans:
        groups.setdefault(run.flight_key(p, cfg), []).append(p)

    def checks_of(ps):
        return [c for p in ps for c in (data.get("plans") or {}).get(p["id"], []) if c.get("pricePP")
                and run._age_h(c.get("checkedAt", "")) <= run.FRESH_H]

    jobs = []  # (why, kind, depart, ret, fin, fout, group plans)
    for gk, ps in groups.items():
        p = ps[0]
        fin, fout = p["flyIn"], p.get("flyOut") or p["flyIn"]
        modes = ["mc", "rt"] if fin != fout else ["rt"]
        cs = checks_of(ps)
        best = min(cs, key=lambda c: c["pricePP"] + c.get("backTrainPP", 0)) if cs else None
        last = (state.get("groups") or {}).get("|".join(map(str, gk))) or {}
        if sweep:
            nights, variants = run.date_variants(p, cfg)
            ret_of = {v["depart"]: v["return"] for v in variants}
            low = {}
            for c in cs:
                ret_of.setdefault(c["depart"], c["return"])
                low[c["depart"]] = min(low.get(c["depart"], 9e9), c["pricePP"] + c.get("backTrainPP", 0))
            days = sorted(low, key=low.get) + [v["depart"] for v in variants if v["depart"] not in low]
            for i, d in enumerate(days[:3]):
                for m in (modes if i == 0 else modes[:1]):
                    jobs.append(("sweep", m, d, ret_of[d], fin, fout if m == "mc" else fin, ps))
        elif mode == "links":
            sp = [c for c in cs if c.get("source") == "serpapi"]
            if sp:
                bs = min(sp, key=lambda c: c["pricePP"] + c.get("backTrainPP", 0))
                jobs.append(("recheck", bs["mode"], bs["depart"], bs["return"], fin, fout if bs["mode"] == "mc" else fin, ps))
        elif best:
            due = run._age_h(last.get("at", "")) >= REPEAT_H.get(p.get("scanTier"), 24)
            serp = [c["pricePP"] + c.get("backTrainPP", 0) for c in cs if c.get("source") == "serpapi"]
            cheaper = serp and best.get("source") != "serpapi" and \
                best["pricePP"] + best.get("backTrainPP", 0) <= min(serp) - 30
            if due or cheaper:
                m = best["mode"]
                jobs.append(("drop" if cheaper and not due else "recheck", m, best["depart"], best["return"], fin,
                             fout if m == "mc" else fin, ps))
    # rechecks first (golden first), then drops; a sweep has its own cap
    jobs.sort(key=lambda j: {"sweep": 0, "recheck": 1, "drop": 2}[j[0]])
    # a sweep / links run has its own budget (searches + 2 per booking page); a normal run the rest of today's
    run_cap = 40 if sweep else 20 if mode == "links" else max(0, DAY_CAP - state.get("usedToday", 0))
    cap = SWEEP_CAP if sweep else run_cap
    cap = min(cap, MONTH_CAP - state.get("usedMonth", 0))
    done, empty, cand = 0, 0, {}
    for why, kind, depart, ret, fin, fout, ps in jobs:
        if done >= cap or left - done <= KEEP_LEFT:
            print("SerpApi: daily/monthly cap or account reserve reached", flush=True)
            break
        offers, err, gurl = search(key, kind, depart, ret, fin, fout, airports)
        done += 1
        state["usedToday"] = state.get("usedToday", 0) + 1
        state["usedMonth"] = state.get("usedMonth", 0) + 1
        empty = 0 if offers else empty + 1
        if empty >= 2:
            print("SerpApi: two empty answers in a row, stopping so no searches are wasted", flush=True)
            break
        safe = [o for o in offers if o["fromId"] in airports and run.safe_connection(o)]
        o = min(safe, key=lambda o: o["pricePP"]) if safe else None
        print(f"SerpApi {why} {kind} {fin}>{fout} {depart}..{ret}: " + (f"EUR {o['pricePP']} {o['fromId']} {o['airline']}" if o else (err or "no safe connection")), flush=True)
        gk = "|".join(map(str, run.flight_key(ps[0], cfg)))
        if o and o.get("_dep"):
            cand.setdefault(gk, []).append((o["pricePP"] + (0 if kind == "mc" or fin == fout else run.leg_cost(ps[0]["stops"][-1]["city"], ps[0]["stops"][0]["city"])[0]),
                                            o, params(key, kind, depart, ret, fin, fout, airports), (depart, ret), ps))
        if o:
            state.setdefault("groups", {})[gk] = {"at": stamp, "pricePP": o["pricePP"], "depart": depart, "mode": kind}
        for p in ps:
            mode = kind if kind == "mc" or fin == fout else "rt"
            c = {"origin": o["fromId"] if o else airports[0], "query": "ALL", "anyHomeAirport": True, "depart": depart,
                 "return": ret, "mode": mode, "checkedAt": stamp, "source": "serpapi",
                 "url": gurl or run.flights.tfs_url([(depart, ",".join(airports), fin), (ret, fout if kind == "mc" else fin, ",".join(airports))])}
            if kind == "rt" and fin != (p.get("flyOut") or p["flyIn"]):
                c["backTrainPP"] = run.leg_cost(p["stops"][-1]["city"], p["stops"][0]["city"])[0]
            if o:
                c.update({"pricePP": o["pricePP"], "airline": o["airline"], "out": strip(o),
                          "cheapestPP": min(x["pricePP"] for x in offers)})
            else:
                c["error"] = err or "no safe connection"
            lst = data.setdefault("plans", {}).setdefault(p["id"], [])
            lst[:] = [x for x in lst if (x.get("query", x.get("origin")), x.get("depart"), x.get("return"), x.get("mode"))
                      != ("ALL", depart, ret, mode)] + [c]
    # booking page for each group's cheapest flight found this run, unless we already have it for that same flight
    links = state.setdefault("links", {})
    for gk, lst in cand.items():
        price, o, q, (depart, ret), ps = min(lst, key=lambda x: x[0])
        old = links.get(gk) or {}
        if old.get("flight") == ident(o) and old.get("depart") == depart and run._age_h(old.get("at", "")) < 72:
            continue
        cap_left = min(run_cap - done, MONTH_CAP - state["usedMonth"], left - done - KEEP_LEFT)
        if cap_left < 2:
            print("SerpApi: no searches left for booking pages this run", flush=True)
            break
        bk, n = booking(key, q, o, airports)
        done += n
        state["usedToday"] += n
        state["usedMonth"] += n
        print(f"SerpApi booking {gk} {depart}: " + (f"EUR {bk['pricePP']} {[x['name'] for x in bk['bookWith']]} bags {bk['bags']}" if bk.get("bookUrl") else str(bk.get("error"))), flush=True)
        if not bk.get("bookUrl"):
            continue
        links[gk] = {"flight": ident(o), "depart": depart, "at": stamp, "pricePP": bk["pricePP"]}
        for p in ps:
            for c in data["plans"].get(p["id"], []):
                if c.get("source") == "serpapi" and c.get("checkedAt") == stamp and c["depart"] == depart and c["return"] == ret \
                        and ident(c.get("out") or {}) == ident(o):
                    c.update(pricePP=bk["pricePP"], searchPricePP=o["pricePP"], bookUrl=bk["bookUrl"], bookWith=bk["bookWith"],
                             bags=bk["bags"], bagsIncluded=bk["bagsIncluded"], back=bk["back"], bookedAt=stamp)
    state["at"] = stamp
    data["serpapi"] = state
    data["updatedAt"] = max(data.get("updatedAt", ""), stamp)
    json.dump(data, open(out_path, "w"), indent=1, ensure_ascii=False)
    print(f"SerpApi: {done} searches this run, {state['usedToday']} today", flush=True)


if __name__ == "__main__":
    main()
