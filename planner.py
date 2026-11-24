#!/usr/bin/env python3
"""Pick the route plans the bot tests, from the owner's settings and routes.json.

Usage: python3 planner.py <config.json> <plans_out.json>
Settings used: countries, interests (city/culture/nature/beach), pace (relaxed | relaxed-medium | medium | fast),
windowStart, windowEnd, minDays, maxPlans, disabledRoutes (ids the owner switched off).
"""
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def plan(cfg):
    routes = json.load(open(os.path.join(HERE, "routes.json")))["routes"]
    countries = cfg.get("countries") or ["Japan", "Vietnam", "Thailand"]
    interests = set(cfg.get("interests") or ["city", "culture", "nature"])
    pace = cfg.get("pace") or "relaxed-medium"
    off = set(cfg.get("disabledRoutes") or [])
    days_max = (dt.date.fromisoformat(cfg["windowEnd"]) - dt.date.fromisoformat(cfg["windowStart"])).days + 1
    min_days = int(cfg.get("minDays") or 11)
    out = []
    for r in sorted(routes, key=lambda r: r["priority"]):
        if r["country"] not in countries or r["id"] in off or not (interests & set(r["tags"])):
            continue
        stops = []
        for s in r["stops"]:
            n = s["nights"]
            if pace == "relaxed":
                n += s.get("flex", 0)
            elif pace == "medium":
                n = max(1, n - (1 if n >= 4 else 0))
            elif pace == "fast":
                n = max(1, n - (1 if n >= 3 else 0) - (1 if n >= 5 else 0))
            stops.append({"city": s["city"], "nights": n})
        nights = sum(s["nights"] for s in stops)
        # shrink the longest stop until it fits the window (depart day + nights + travel home)
        while nights + 2 > days_max and max(s["nights"] for s in stops) > 2:
            big = max(stops, key=lambda s: s["nights"])
            big["nights"] -= 1
            nights -= 1
        if nights + 2 > days_max or nights + 2 < min_days:
            continue
        base = {"id": r["id"], "name": r["name"], "country": r["country"], "flyIn": r["flyIn"], "flyOut": r["flyOut"],
                "priority": r["priority"], "enabled": True, "stops": stops, "why": r["why"],
                "nights": nights, "days": nights + 2, "tags": r["tags"]}
        out.append(base)
        # longer versions of the favourite routes: as many days as the window allows, and one in between,
        # so the bot can see which length gives the most days for the money
        if r.get("stretch"):
            most = days_max - 2
            for n in sorted({min(nights + 2, most), most} - {nights}):
                if n <= nights:
                    continue
                st = [dict(s) for s in stops]
                big = sorted([s for s in st if s["nights"] >= 3], key=lambda s: -s["nights"]) or st
                i = 0
                for _ in range(n - nights):
                    big[i % len(big)]["nights"] += 1
                    i += 1
                out.append({**base, "id": f"{r['id']}-{n + 2}d", "name": f"{r['name']} ({n + 2} days)", "stops": st,
                            "nights": n, "days": n + 2, "priority": r["priority"] + 0.1 * (n - nights),
                            "why": r["why"] + f" Longer version: {n + 2} days instead of {nights + 2}, extra nights in the big cities."})
    out.sort(key=lambda p: p["priority"])
    jp = [p for p in out if p["country"] == "Japan"]
    rest = [p for p in out if p["country"] != "Japan"]
    keep = int(cfg.get("maxPlans") or 13)
    # other countries: the best route of each country first (up to 3), so every chosen country gets tested
    first, seen = [], set()
    for x in rest:
        if x["country"] not in seen:
            seen.add(x["country"]); first.append(x)
    other = (first + [x for x in rest if x not in first])[:int(cfg.get("maxOtherPlans") or 5)]
    sel = jp[:max(1, keep - len(other))] + other
    return sel[:keep]


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    if isinstance(cfg.get("data"), dict):
        cfg = cfg["data"]
    plans = plan(cfg)
    json.dump(plans, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
    for p in plans:
        print(p["id"], p["nights"], "nights:", " > ".join(f"{s['city']} {s['nights']}" for s in p["stops"]))
