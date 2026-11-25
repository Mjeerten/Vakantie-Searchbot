#!/usr/bin/env python3
"""Hourly flight scanner for GitHub Actions: Google Flights checks only (no hotels, no Claude).

Usage: python3 scan_flights.py <search_config.json> <previous flight_checks.json> <out.json>
Picks the routes with planner.py, then checks flights Japan first (every departure day, the other ticket type,
the other airports) and the other countries after that. It stops at the first Google rate limit.
Output: {"updatedAt", "blocked", "queries", "plans": {planId: [checks]}, "coverage": {planId: [done, total]}}
Atlas (scan.md) reads this file with run.py --checks=<file>.
"""
import datetime as dt
import json
import sys

import flights
import planner
import run


def main():
    cfg_path, prev_path, out_path = sys.argv[1:4]
    cfg = json.load(open(cfg_path))
    try:
        prev = json.load(open(prev_path))
    except Exception:
        prev = {}
    airports = cfg["airports"]
    states = []
    for p in sorted(planner.plan(cfg), key=lambda p: p.get("priority", 9)):
        nights, variants = run.date_variants(p, cfg)
        old = [c for c in (prev.get("plans") or {}).get(p["id"], [])
               if run._age_h(c.get("checkedAt", "")) <= run.FRESH_H and (run.D(c["return"]) - run.D(c["depart"])).days == nights + 1]
        states.append({"plan": p, "nights": nights, "variants": variants, "tp": [], "checks": old, "tried": set()})
    import os
    if os.environ.get("GOOGLE_BUDGET"):
        cfg["googleQueryBudget"] = int(os.environ["GOOGLE_BUDGET"])
    budget = run.Budget(int(cfg.get("googleQueryBudget", 10)))
    run.google_round(states, airports, budget, float(cfg.get("googlePauseSec", 25)), log=lambda m: print(m, flush=True))
    out = {"updatedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "blocked": flights.BLOCKED,
           "queries": int(cfg.get("googleQueryBudget", 10)) - budget.left, "plans": {}, "coverage": {}}
    for st in states:
        st["tried"] = set()
        out["plans"][st["plan"]["id"]] = sorted(st["checks"], key=lambda c: c["checkedAt"])[-250:]
        out["coverage"][st["plan"]["id"]] = list(run.coverage(st, airports))
    json.dump(out, open(out_path, "w"), indent=1, ensure_ascii=False)
    for k, v in out["coverage"].items():
        best = min((c["pricePP"] for c in out["plans"][k] if c.get("pricePP")), default=None)
        print(f"{k}: {v[0]}/{v[1]} core options, cheapest EUR {best}")
    print("blocked" if flights.BLOCKED else "ok", "queries", out["queries"])


if __name__ == "__main__":
    main()
