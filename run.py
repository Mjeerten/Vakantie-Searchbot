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
import statistics
import subprocess
import sys
import time
import urllib.request

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


def date_variants(plan, cfg, maxn=3):
    """Depart day D (overnight flight), check in D+1, fly home on the last checkout day."""
    nights = sum(int(s["nights"]) for s in plan["stops"])
    start, end = D(cfg["windowStart"]), D(cfg["windowEnd"])
    last_depart = end - dt.timedelta(days=nights + 1)
    if last_depart < start:
        return nights, []
    span = (last_depart - start).days
    picks = sorted({0, span // 2, span}) if span else [0]
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


def flight_option(origin, plan, v, budget, pause, mode="rt"):
    """Cheapest flight for one origin and one date variant.
    mode "rt": round trip to flyIn (for an open-jaw route the train back from the last stop is added as backTrainPP).
    mode "oj": open jaw as two one-way tickets (in to flyIn, home from flyOut)."""
    fin, fout = plan["flyIn"], plan.get("flyOut") or plan["flyIn"]
    if mode == "rt" or fin == fout:
        if not budget.take():
            return None
        r = flights.search(origin, fin, v["depart"], v["return"])
        time.sleep(pause)
        if not r["offers"]:
            return {"origin": origin, "error": r["error"], "blocked": r["blocked"], "urls": [r["url"]]}
        o = r["offers"][0]
        back = 0
        if fin != fout:
            back, _ = leg_cost(plan["stops"][-1]["city"], plan["stops"][0]["city"])
        return {"origin": origin, "type": "return " + fin + (f" (+ train back to {plan['stops'][0]['city']})" if back else ""),
                "pricePP": o["pricePP"], "backTrainPP": back, "compare": o["pricePP"] + back,
                "airlines": [o["airline"]], "out": o, "back": None, "urls": [r["url"]]}
    if budget.left < 2 or flights.BLOCKED:
        return None
    budget.take(); a = flights.search(origin, fin, v["depart"]); time.sleep(pause)
    budget.take(); b = flights.search(fout, origin, v["return"]); time.sleep(pause)
    if not a["offers"] or not b["offers"]:
        return {"origin": origin, "error": a["error"] or b["error"], "blocked": a["blocked"] or b["blocked"],
                "urls": [a["url"], b["url"]]}
    p = a["offers"][0]["pricePP"] + b["offers"][0]["pricePP"]
    return {"origin": origin, "type": "open jaw (2 one-way tickets)", "pricePP": p, "backTrainPP": 0, "compare": p,
            "airlines": [a["offers"][0]["airline"], b["offers"][0]["airline"]], "out": a["offers"][0], "back": b["offers"][0],
            "urls": [a["url"], b["url"]]}


def pick_stay(city, checkin, nights, rules, fx, cfg):
    checkout = (D(checkin) + dt.timedelta(days=nights)).isoformat()
    try:
        p = subprocess.run(["node", os.path.join(HERE, "hotels.js"), city, checkin, checkout, str(fx)],
                           capture_output=True, text=True, timeout=150)
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"city": city, "checkin": checkin, "nights": nights, "error": f"hotels.js failed: {e}"[:160]}
    minr = float(cfg.get("minRating") or rules["minRating"])
    minrev = int(cfg.get("minReviews") or 100)
    avoid = [w.lower() for w in (cfg.get("avoidWords") or ["capsule", "cabin", "dorm", "love hotel"])]
    ok = [h for h in r.get("hotels", [])
          if (h.get("rating") or 0) >= minr and (h.get("reviews") or 0) >= minrev
          and not any(w in (h["name"] + " " + (h.get("kind") or "")).lower() for w in avoid)]
    ok.sort(key=lambda h: h["nightlyEur"])
    res = {"city": city, "checkin": checkin, "checkout": checkout, "nights": nights, "url": r.get("url"),
           "blocked": r.get("blocked"), "error": r.get("error"), "found": len(r.get("hotels", [])), "qualifying": len(ok)}
    if ok:
        top = ok[:3]
        res["pick"] = top[0]
        res["alternatives"] = top[1:]
        # price per person for the stay: room for 2, split in two
        res["pricePP"] = round(top[0]["nightlyEur"] * nights / 2)
        res["medianTop3PP"] = round(statistics.median(h["nightlyEur"] for h in top) * nights / 2)
    return res


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
        import re
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


def evaluate(plan, cfg, budget, fx, do_hotels, pause):
    country = plan.get("country", "default")
    rules = country_costs(country, cfg)
    nights, variants = date_variants(plan, cfg)
    out = {"planId": plan["id"], "name": plan.get("name"), "country": country, "nights": nights, "variants": [], "notes": []}
    if not variants:
        out["notes"].append("Route does not fit the travel window.")
        return out
    airports = cfg.get("airports") or ["AMS", "BRU", "DUS", "EIN", "RTM"]
    # 1) Travelpayouts (cached fares for every date) first
    cands = tp_candidates(plan, nights, cfg, airports)
    src = "travelpayouts"
    if not cands:
        # 2) fallback: Google Flights for up to 3 dates (first airport), then other airports for the best date
        src = "google"
        for v in variants:
            f = flight_option(airports[0], plan, v, budget, pause)
            v["flights"] = [f] if f else []
        priced = [v for v in variants if v["flights"] and v["flights"][0].get("compare")]
        if not priced:
            out["variants"] = variants
            out["notes"].append("No flight prices found" + (" (Google blocked the cloud)" if flights.BLOCKED else "")
                                + ("" if tp.STATUS["ok"] else f"; Travelpayouts: {tp.STATUS['error']}"))
            return out
        bestv = min(priced, key=lambda v: comfort(v["flights"][0])[0])
        for ap in airports[1:]:
            f = flight_option(ap, plan, bestv, budget, pause)
            if f:
                bestv["flights"].append(f)
        if plan.get("flyOut") and plan["flyOut"] != plan["flyIn"]:
            f = flight_option(airports[0], plan, bestv, budget, pause, mode="oj")
            if f:
                bestv["flights"].append(f)
        for f in bestv["flights"]:
            if f and f.get("compare"):
                f["depart"], f["return"] = bestv["depart"], bestv["return"]
                cands.append(f)
    for f in cands:
        f["effective"], f["comfortFlags"] = comfort(f)
    cands = [f for f in cands if f["effective"] is not None] or cands
    fl = min(cands, key=lambda f: f["effective"] if f["effective"] is not None else 1e9)
    dep = D(fl["depart"])
    best = {"depart": fl["depart"], "checkin": (dep + dt.timedelta(days=1)).isoformat(),
            "return": fl["return"], "days": nights + 2}
    # Google check of the chosen cached fare (times + live price), when Google still answers
    if src == "travelpayouts" and budget.left > 0 and not flights.BLOCKED and cfg.get("googleConfirm", True):
        fin = plan["flyIn"]
        if budget.take():
            r = flights.search(fl["origin"], fin, fl["depart"], fl["return"])
            time.sleep(pause)
            if r["offers"]:
                fl["google"] = {"pricePP": r["offers"][0]["pricePP"], "airline": r["offers"][0]["airline"],
                                "duration": r["offers"][0]["duration"], "url": r["url"]}
                fl.setdefault("urls", []).append(r["url"])
    variants = [{"depart": c["depart"], "return": c["return"], "origin": c["origin"], "type": c["type"], "pricePP": c["pricePP"],
                 "effective": c["effective"]} for c in sorted(cands, key=lambda c: c["effective"] or 1e9)[:8]]
    # bags
    bag = 0
    if best["days"] > 10 and not all(a in COSTS["bags"]["usuallyIncluded"] for a in fl["airlines"]):
        bag = COSTS["bags"]["extraBagEstimatePP"]
    # 3) stays for the best date
    stays, cursor = [], D(best["checkin"])
    for s in plan["stops"]:
        n = int(s["nights"])
        if do_hotels and not s.get("skipHotel"):
            st = pick_stay(s.get("hotelCity") or s["city"], cursor.isoformat(), n, rules, fx, {**cfg, **(plan.get("stay") or {})})
        else:
            st = {"city": s["city"], "nights": n, "checkin": cursor.isoformat()}
        if not st.get("pricePP"):
            est = int((plan.get("stay") or {}).get("fallbackNightlyRoom") or cfg.get("fallbackNightlyRoom") or 90)
            st["pricePP"] = round(est * n / 2)
            st["estimated"] = True
        stays.append(st)
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
        "flight": fl["pricePP"], "bag": bag,
        "stays": sum(s["pricePP"] for s in stays),
        "transport": sum(l["pricePP"] for l in legs) + fl.get("backTrainPP", 0) + 2 * rules["airportTransfer"],
        "food": rules["foodPerDay"] * on_ground,
        "activities": rules["activitiesPerDay"] * on_ground,
        "local": rules["localTransportPerDay"] * on_ground,
    }
    total = sum(parts.values())
    bmin, bmax = cfg.get("budgetMinPP", 1500), cfg.get("budgetMaxPP", 2500)
    verdict = "top deal" if total <= bmin else "within budget" if total <= bmax else f"€{total - bmax} over budget"
    est_flags = []
    if bag:
        est_flags.append("checked bag estimated (check if the fare includes a suitcase)")
    if any(s.get("estimated") for s in stays):
        est_flags.append("some stays estimated (no hotel price found)")
    if any(not l["known"] for l in legs):
        est_flags.append("unknown train leg estimated")
    if fl["type"].startswith("open"):
        est_flags.append("open jaw priced as 2 one-way tickets; a multi-city ticket is often cheaper")
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
        for d in r.get("departures", []):
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
    budget = Budget(int(cfg.get("googleQueryBudget", 16)))
    pause = float(cfg.get("googlePauseSec", 12))
    res = {"runAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "usdToEur": fx, "plans": [], "packages": []}
    for p in plans:
        res["plans"].append(evaluate(p, cfg, budget, fx, "--no-hotels" not in flags, pause))
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
