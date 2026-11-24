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
        return {"origin": origin, "type": "retour" + (f" {fin} (+ trein terug naar {plan['stops'][0]['city']})" if back else ""),
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
    return {"origin": origin, "type": "open-jaw (2x enkele reis)", "pricePP": p, "backTrainPP": 0, "compare": p,
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


def evaluate(plan, cfg, budget, fx, do_hotels, pause):
    country = plan.get("country", "default")
    rules = country_costs(country, cfg)
    nights, variants = date_variants(plan, cfg)
    out = {"planId": plan["id"], "name": plan.get("name"), "country": country, "nights": nights, "variants": [], "notes": []}
    if not variants:
        out["notes"].append("Route past niet in de periode (te veel nachten).")
        return out
    airports = cfg.get("airports") or ["AMS", "BRU", "DUS", "EIN", "RTM"]
    # 1) first airport for every date variant
    for v in variants:
        f = flight_option(airports[0], plan, v, budget, pause)
        v["flights"] = [f] if f else []
    priced = [v for v in variants if v["flights"] and v["flights"][0].get("compare")]
    if not priced:
        out["variants"] = variants
        out["notes"].append("Geen vluchtprijzen gevonden" + (" (Google blokkeerde de cloud)" if flights.BLOCKED else ""))
        return out
    best = min(priced, key=lambda v: v["flights"][0]["compare"])
    # 2) the other airports only for the best date, then open jaw from the first airport
    for ap in airports[1:]:
        f = flight_option(ap, plan, best, budget, pause)
        if f:
            best["flights"].append(f)
    if plan.get("flyOut") and plan["flyOut"] != plan["flyIn"]:
        f = flight_option(airports[0], plan, best, budget, pause, mode="oj")
        if f:
            best["flights"].append(f)
    fl = min((f for f in best["flights"] if f and f.get("compare")), key=lambda f: f["compare"])
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
    verdict = "topdeal" if total <= bmin else "binnen budget" if total <= bmax else f"€{total - bmax} boven budget"
    est_flags = []
    if bag:
        est_flags.append("ruimbagage geschat (check of het ticket een koffer bevat)")
    if any(s.get("estimated") for s in stays):
        est_flags.append("sommige verblijven geschat (geen prijs gevonden)")
    if any(not l["known"] for l in legs):
        est_flags.append("onbekend treintraject geschat")
    if fl["type"].startswith("open-jaw"):
        est_flags.append("open-jaw als 2 enkele reizen; een multi-city ticket is vaak goedkoper")
    out.update({"variants": variants, "best": {
        "depart": best["depart"], "return": best["return"], "days": days, "flight": fl, "stays": stays, "legs": legs,
        "parts": parts, "totalPP": total, "totalFor2": total * 2, "verdict": verdict, "flags": est_flags}})
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
    fx = usd_to_eur()
    budget = Budget(int(cfg.get("googleQueryBudget", 16)))
    pause = float(cfg.get("googlePauseSec", 12))
    res = {"runAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "usdToEur": fx, "plans": [], "packages": []}
    for p in plans:
        res["plans"].append(evaluate(p, cfg, budget, fx, "--no-hotels" not in flags, pause))
    res["googleBlocked"] = flights.BLOCKED
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


if __name__ == "__main__":
    main()
