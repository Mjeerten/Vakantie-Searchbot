#!/usr/bin/env python3
"""Japan flight scan through SearchApi.io (official API returning Google Flights results; no Google blocking).
Usage: python3 sapi_scan.py <in_checks.json> <out_checks.json> [max_credits]
The API key is injected by the session's network proxy (never stored here). Credits are for Japan only.
One search covers all five home airports at once (departure_id=AMS,BRU,DUS,EIN,RTM); searches shared by several
routes (same dates and ticket type) are done once. Order: golden route, Koyasan, classic, Kanazawa (owner's order)."""
import datetime as dt
import json
import subprocess
import sys
import urllib.parse

import planner
import run

API = "https://www.searchapi.io/api/v1/search"


def call(params):
    url = API + "?" + urllib.parse.urlencode(params)
    p = subprocess.run(["curl", "-s", "-m", "150", url], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"error": "bad response: " + p.stdout[:120]}


def hm(mins):
    return f"{int(mins) // 60} hr {int(mins) % 60} min" if mins else None


def fmt_time(a):
    # "2027-07-27" + "10:55" -> "Tuesday, July 27 10:55 AM" (the format comfort() and the Travel Desk read)
    d = dt.date.fromisoformat(a["date"])
    h, m = map(int, a["time"].split(":"))
    return f"{d.strftime('%A, %B')} {d.day} {h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def offer(x):
    f = x["flights"]
    lay = [l.get("name") for l in x.get("layovers") or []]
    return {"pricePP": x["price"], "airline": f[0]["airline"] if len({s["airline"] for s in f}) == 1 else " and ".join(dict.fromkeys(s["airline"] for s in f)),
            "stops": len(f) - 1, "duration": hm(x.get("total_duration")),
            "from": f[0]["departure_airport"]["name"], "fromId": f[0]["departure_airport"]["id"], "departs": fmt_time(f[0]["departure_airport"]),
            "to": f[-1]["arrival_airport"]["name"], "arrives": fmt_time(f[-1]["arrival_airport"]),
            "layovers": lay[:3],
            # a layover where you land at one airport and leave from another (e.g. Narita -> Haneda)
            "airportChange": any(s["departure_airport"]["id"] != p["arrival_airport"]["id"] for p, s in zip(f, f[1:]))}


def search(kind, depart, ret, fin, fout, airports):
    ap = ",".join(airports)
    base = {"engine": "google_flights", "currency": "EUR", "gl": "nl", "hl": "en", "show_cheapest_flights": "true"}
    if kind == "rt":
        q = dict(base, flight_type="round_trip", departure_id=ap, arrival_id=fin, outbound_date=depart, return_date=ret)
    else:
        q = dict(base, flight_type="multi_city", multi_city_json=json.dumps(
            [{"departure_id": ap, "arrival_id": fin, "outbound_date": depart},
             {"departure_id": fout, "arrival_id": ap, "outbound_date": ret}], separators=(",", ":")))
    d = call(q)
    offers = [offer(x) for x in (d.get("best_flights") or []) + (d.get("other_flights") or []) if x.get("price")]
    return offers, d.get("error"), (d.get("search_metadata") or {}).get("request_url")


def main():
    src, out_path = sys.argv[1], sys.argv[2]
    max_credits = int(sys.argv[3]) if len(sys.argv) > 3 else 90
    cfg = json.load(open("search_config.json"))
    airports = cfg["airports"]
    data = json.load(open(src))
    plans = [p for p in planner.plan(cfg) if p.get("country") == "Japan"]
    order = {1: 0, 2: 1, 3: 2, 4: 3}
    plans.sort(key=lambda p: (order.get(p.get("scanTier", 9), 9), p.get("priority", 9)))
    jobs = {}  # (kind, depart, ret, fin, fout) -> [(plan, nights)]
    for p in plans:
        nights, variants = run.date_variants(p, cfg)
        fin, fout = p["flyIn"], p.get("flyOut") or p["flyIn"]
        for v in variants:
            ret = (dt.date.fromisoformat(v["depart"]) + dt.timedelta(days=nights + 1)).isoformat()
            for mode in (["mc", "rt"] if fin != fout else ["rt"]):
                k = ("rt", v["depart"], ret, fin, fin) if mode == "rt" else ("mc", v["depart"], ret, fin, fout)
                jobs.setdefault(k, []).append((p, mode))
    print(f"{len(jobs)} unique searches for {len(plans)} Japan routes; credit cap {max_credits}", flush=True)
    used = 0
    for k, users in jobs.items():
        if used >= max_credits:
            print("credit cap reached", flush=True)
            break
        kind, depart, ret, fin, fout = k
        offers, err, gurl = search(kind, depart, ret, fin, fout, airports)
        used += 1
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        best = {}
        for o in offers:
            if o["fromId"] in airports and not o["airportChange"] and (o["fromId"] not in best or o["pricePP"] < best[o["fromId"]]["pricePP"]):
                best[o["fromId"]] = o
        print(f"{kind} {fin}>{fout} {depart}..{ret}: " + (err or " ".join(f"{a} {o['pricePP']}" for a, o in sorted(best.items(), key=lambda x: x[1]['pricePP']))), flush=True)
        if err and not offers:
            continue
        cheapest = min((o["pricePP"] for o in offers), default=None)
        for p, mode in users:
            lst = data.setdefault("plans", {}).setdefault(p["id"], [])
            for a in airports:
                c = {"origin": a, "depart": depart, "return": ret, "mode": mode, "checkedAt": now, "source": "searchapi", "url": gurl}
                if mode == "rt" and fin != (p.get("flyOut") or p["flyIn"]):
                    c["backTrainPP"] = run.leg_cost(p["stops"][-1]["city"], p["stops"][0]["city"])[0]
                if a in best:
                    o = best[a]
                    c.update({"pricePP": o["pricePP"], "airline": o["airline"], "out": o, "cheapestPP": cheapest})
                else:
                    c["error"] = f"not among the cheapest {len(offers)} options (cheapest from any home airport EUR {cheapest})"
                lst[:] = [x for x in lst if (x.get("origin"), x.get("depart"), x.get("return"), x.get("mode")) != (a, depart, ret, mode)] + [c]
        data["updatedAt"] = now
        json.dump(data, open(out_path, "w"), indent=1, ensure_ascii=False)
    print(f"credits used {used}", flush=True)


if __name__ == "__main__":
    main()
