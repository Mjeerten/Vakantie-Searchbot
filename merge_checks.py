#!/usr/bin/env python3
"""Merge two flight_checks.json files (e.g. GitHub scanner + another scanner), so neither overwrites the other.
Usage: python3 merge_checks.py <a.json> <b.json> <out.json>
Checks are matched on (origin, depart, return, mode); the newest checkedAt wins. Coverage is recomputed."""
import json
import sys

import planner
import run


def load(p):
    try:
        return json.load(open(p))
    except Exception:
        return {}


def main():
    a, b, out_path = load(sys.argv[1]), load(sys.argv[2]), sys.argv[3]
    plans = {}
    for src in (a, b):
        for pid, checks in (src.get("plans") or {}).items():
            m = plans.setdefault(pid, {})
            for c in checks:
                k = (c.get("query", c.get("origin")), c.get("depart"), c.get("return"), c.get("mode"))
                if k not in m or c.get("checkedAt", "") > m[k].get("checkedAt", ""):
                    m[k] = c
    cfg = json.load(open("search_config.json"))
    out = {"updatedAt": max(a.get("updatedAt", ""), b.get("updatedAt", "")),
           "blocked": bool(b.get("blocked")) if b.get("updatedAt", "") >= a.get("updatedAt", "") else bool(a.get("blocked")),
           "queries": int(a.get("queries") or 0) + int(b.get("queries") or 0), "plans": {}, "coverage": {}}
    all_plans = planner.plan(cfg)
    # routes that fly the same tickets (same arrival/departure city in Japan and the same number of nights, e.g. the
    # golden route and the Kanazawa route reversed) share every flight check: one search counts for all of them
    group = {}
    for p in all_plans:
        g = group.setdefault(run.flight_key(p, cfg), {})
        for k, c in plans.get(p["id"], {}).items():
            if k not in g or c.get("checkedAt", "") > g[k].get("checkedAt", ""):
                g[k] = c
    for p in all_plans:
        nights, variants = run.date_variants(p, cfg)
        checks = sorted(group[run.flight_key(p, cfg)].values(), key=lambda c: c.get("checkedAt", ""))[-250:]
        out["plans"][p["id"]] = checks
        st = {"plan": p, "nights": nights, "variants": variants, "tp": [], "checks": checks, "tried": set()}
        out["coverage"][p["id"]] = list(run.coverage(st, cfg["airports"]))
    json.dump(out, open(out_path, "w"), indent=1, ensure_ascii=False)
    for k, v in out["coverage"].items():
        print(k, v)


if __name__ == "__main__":
    main()
