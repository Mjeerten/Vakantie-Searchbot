#!/usr/bin/env python3
"""Control bot: re-opens the links in results.json and checks that the prices are really there.

Usage: python3 verify.py results.json [--top=N] [--no-hotels] [--checks=flight_checks.json]

For each plan (highest priority first, up to N, default all):
- flight: opens the stored Google Flights link again (sorted by price, the full list), looks for the SAME
  airline and departure time, and records what Google shows now. A changed price replaces the stored one
  (total updated); a fare that is gone is flagged.
- stays: searches Booking.com again for the picked hotel by name and dates (Booking blocks its hotel pages
  for bots, the search page works), Airbnb again in the same map box (matched by room id), Google Hotels
  again by city. A changed total replaces the stored one.
Every checked item gets `verify: {status, storedPP|storedTotal, seen..., at}` with status
"confirmed" (same price, +-2 EUR), "changed" (other price, now used) or "not found" (kept, flagged).
Read-only: no login, no booking, no forms.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flights  # noqa: E402
import run  # noqa: E402

NOW = lambda: dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
TOL = 2


def _node(args, timeout=170):
    try:
        p = subprocess.run(["node"] + args, capture_output=True, text=True, timeout=timeout, cwd=HERE)
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {"error": str(e)[:120]}


def _dep_key(o):
    """'Tuesday, July 27 9:40 PM' -> '9:40 PM' (the time; the date is in the link)."""
    m = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", (o or {}).get("departs") or "")
    return m.group(1) if m else None


FL_CACHE = {}
SHARED = []  # checks from the GitHub scanner (--checks=flight_checks.json)


def verify_flight(fl):
    url = (fl.get("urls") or [None])[0]
    if fl.get("src") != "google" or not url:
        return None
    if url not in FL_CACHE:
        r = _node([os.path.join(HERE, "gflights.js"), url])
        import html as _h
        body = " ".join('aria-label="' + _h.escape(l, quote=True) + '"' for l in r.get("labels", []))
        FL_CACHE[url] = {"offers": flights.parse(body), "error": r.get("error"), "sorted": r.get("sorted")}
        time.sleep(15)
    res = FL_CACHE[url]
    v = {"at": NOW(), "storedPP": fl["pricePP"], "url": url}
    if not res["offers"]:
        # Google throttles this server's IP now and then: use a newer check of the SAME flight by the
        # GitHub scanner (other IPs, every 20 min) if there is one
        g = [c for c in SHARED if c.get("pricePP") and c.get("origin") == fl.get("origin") and c.get("depart") == fl.get("depart")
             and c.get("return") == fl.get("return") and c.get("airline") == (fl.get("out") or {}).get("airline")
             and _dep_key(c.get("out")) == _dep_key(fl.get("out")) and c.get("checkedAt", "") > fl.get("checkedAt", "")]
        if g:
            c = max(g, key=lambda c: c["checkedAt"])
            v.update(seenPP=c["pricePP"], via="GitHub scan " + c["checkedAt"],
                     status="confirmed" if abs(c["pricePP"] - fl["pricePP"]) <= TOL else "changed")
            return v
        v.update(status="not checked", note=res["error"] or "Google showed no prices (throttled?)")
        return v
    out = fl.get("out") or {}
    air, dep = (out.get("airline") or (fl.get("airlines") or [""])[0]), _dep_key(out)
    same = [o for o in res["offers"] if o.get("airline") == air and _dep_key(o) == dep]
    v["cheapestNowPP"] = min(o["pricePP"] for o in res["offers"])
    if not same:
        v.update(status="not found", note=f"{air} departing {dep} is no longer listed; cheapest on the page now €{v['cheapestNowPP']}")
        return v
    seen = min(o["pricePP"] for o in same)
    v["seenPP"] = seen
    v["status"] = "confirmed" if abs(seen - fl["pricePP"]) <= TOL else "changed"
    return v


def _search_stays(pick, city, ci, co):
    src = pick.get("src")
    if src == "booking":
        r = _node([os.path.join(HERE, "booking.js"), pick["name"], ci, co])
        hits = [h for h in r.get("hotels", []) if run.same_hotel(h["name"], pick["name"])]
    elif src == "airbnb":
        rid = re.search(r"/rooms/(\d+)", pick.get("url") or "")
        lat, lng = run.CENTRES.get(city, (None, None))
        if not (rid and lat):
            return None, "no room id"
        r = _node([os.path.join(HERE, "airbnb.js"), city, ci, co, str(lat), str(lng), str(run.BIG_CITIES.get(city, 3))])
        hits = [h for h in r.get("hotels", []) if f"/rooms/{rid.group(1)}" in (h.get("url") or "")]
    else:  # Google Hotels (also the price from Agoda/Trip.com/... it compares)
        r = _node([os.path.join(HERE, "hotels.js"), city, ci, co])
        hits = [h for h in r.get("hotels", []) if run.same_hotel(h["name"], pick["name"])]
    if r.get("error") and not hits:
        return None, r["error"]
    return hits, None


def verify_stay(sv):
    pick = sv.get("pick")
    if not pick or sv.get("estimated") or not pick.get("total"):
        return None
    ci = sv["checkin"]
    co = (dt.date.fromisoformat(ci) + dt.timedelta(days=int(sv["nights"]))).isoformat()
    hits, err = _search_stays(pick, sv.get("city"), ci, co)
    v = {"at": NOW(), "storedTotal": pick["total"], "site": pick.get("src")}
    if hits is None:
        v.update(status="not checked", note=err)
    elif not hits:
        v.update(status="not found", note="not in the search results again (sold out or filtered)")
    else:
        seen = min(h["total"] for h in hits)
        v.update(seenTotal=seen, status="confirmed" if abs(seen - pick["total"]) <= TOL else "changed")
    return v


def apply(best, kind, item, v):
    """Update the plan totals when a verified price differs."""
    if not v or v.get("status") != "changed":
        return
    if kind == "flight":
        d = v["seenPP"] - item["pricePP"]
        item["pricePP"] += d
        item["compare"] = item.get("compare", 0) + d
        item["effective"] = item.get("effective", 0) + d
        best["parts"]["flight"] += d
    else:
        old_pp = item["pricePP"]
        item["pick"]["total"] = v["seenTotal"]
        item["pick"]["nightlyEur"] = round(v["seenTotal"] / int(item["nights"]))
        item["pricePP"] = round(v["seenTotal"] / 2)
        d = item["pricePP"] - old_pp
        best["parts"]["stays"] += d
    best["totalPP"] = sum(best["parts"].values())
    best["totalFor2"] = best["totalPP"] * 2


def main():
    path = sys.argv[1]
    top = next((int(a.split("=")[1]) for a in sys.argv[2:] if a.startswith("--top=")), 99)
    hotels = "--no-hotels" not in sys.argv
    chk = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--checks=")), None)
    if chk and os.path.exists(chk):
        SHARED.extend(c for cs in (json.load(open(chk)).get("plans") or {}).values() for c in cs)
    res = json.load(open(path))
    plans = [p for p in res["plans"] if p.get("best")]
    plans.sort(key=lambda p: p.get("priority", 9))
    stay_cache, n = {}, {"confirmed": 0, "changed": 0, "not found": 0, "not checked": 0}
    for p in plans[:top]:
        b = p["best"]
        fl = b.get("flight")
        lines = []
        if fl:
            v = verify_flight(fl)
            if v:
                apply(b, "flight", fl, v)
                fl["verify"] = v
                n[v["status"]] += 1
                lines.append(f"flight {v['status']} (stored €{v['storedPP']}" + (f", now €{v['seenPP']}" if 'seenPP' in v else "") + ")")
                if v["status"] == "not found":
                    b.setdefault("flags", []).append("control bot: " + v["note"])
        if hotels:
            for sv in b.get("stays") or []:
                key = (sv.get("city"), sv.get("checkin"), (sv.get("pick") or {}).get("name"))
                if key not in stay_cache:
                    stay_cache[key] = verify_stay(sv)
                v = stay_cache[key]
                if not v:
                    continue
                v = dict(v)
                apply(b, "stay", sv, v)
                sv["verify"] = v
                n[v["status"]] += 1
                lines.append(f"{sv['city']} {v['status']}" + (f" (€{v['storedTotal']}→€{v['seenTotal']})" if v["status"] == "changed" else ""))
        b["verifiedAt"] = NOW()
        print(f"{p.get('name')}: €{b['totalPP']} p.p. | " + "; ".join(lines), flush=True)
    res["verify"] = {"at": NOW(), "counts": n}
    json.dump(res, open(path, "w"), indent=1)
    print("VERIFY " + ", ".join(f"{k} {v}" for k, v in n.items()))


if __name__ == "__main__":
    main()
