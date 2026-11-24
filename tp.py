#!/usr/bin/env python3
"""Travelpayouts / Aviasales Data API client (cached fares found by Aviasales users in the last days).

The API token is injected by the session's network proxy into requests to api.travelpayouts.com
(header X-Access-Token), so this script never handles the key itself.

CLI test: python3 tp.py AMS TYO 2027-07-23 2027-08-13 [OSA]
"""
import json
import subprocess
import sys
import urllib.parse

API = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
STATUS = {"ok": True, "error": None, "calls": 0}


def _get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    STATUS["calls"] += 1
    p = subprocess.run(["curl", "-s", "--max-time", "30", "-w", "\n%{http_code}", url], capture_output=True, text=True)
    body, _, code = p.stdout.rpartition("\n")
    if code.strip() != "200":
        STATUS["ok"] = False
        STATUS["error"] = f"HTTP {code.strip()} {body[:60].strip()}"
        return []
    try:
        d = json.loads(body)
    except ValueError:
        STATUS["ok"] = False
        STATUS["error"] = "not JSON"
        return []
    if not d.get("success", True):
        STATUS["error"] = str(d.get("error"))[:120]
        return []
    return d.get("data") or []


def _months(start, end):
    a, b = start[:7], end[:7]
    out = [a]
    if b != a:
        out.append(b)
    return out


def _norm(x, one_way):
    link = x.get("link") or ""
    return {
        "src": "travelpayouts",
        "pricePP": int(round(x["price"])),
        "airline": x.get("airline"),
        "flight": x.get("flight_number"),
        "from": x.get("origin_airport") or x.get("origin"),
        "to": x.get("destination_airport") or x.get("destination"),
        "depart": (x.get("departure_at") or "")[:16],
        "return": None if one_way else (x.get("return_at") or "")[:16],
        "stopsOut": x.get("transfers"),
        "stopsBack": None if one_way else x.get("return_transfers"),
        "hoursOut": round((x.get("duration_to") or x.get("duration") or 0) / 60, 1) or None,
        "hoursBack": None if one_way else (round((x.get("duration_back") or 0) / 60, 1) or None),
        "url": ("https://www.aviasales.com" + link) if link.startswith("/") else None,
        "cached": True,
    }


def round_trips(origin, dest, start, end, min_nights=0, max_nights=99):
    """All cached round trips origin->dest leaving >= start and back <= end."""
    seen, out = set(), []
    for dm in _months(start, end):
        for rm in _months(start, end):
            if rm < dm:
                continue
            rows = _get({"origin": origin, "destination": dest, "departure_at": dm, "return_at": rm,
                         "currency": "eur", "sorting": "price", "one_way": "false", "limit": 1000})
            for x in rows:
                o = _norm(x, False)
                d0, r0 = o["depart"][:10], (o["return"] or "")[:10]
                if not (start <= d0 and r0 and r0 <= end):
                    continue
                import datetime as dt
                n = (dt.date.fromisoformat(r0) - dt.date.fromisoformat(d0)).days
                if not (min_nights <= n <= max_nights):
                    continue
                k = (o["depart"], o["return"], o["airline"], o["pricePP"])
                if k not in seen:
                    seen.add(k)
                    out.append(o)
    out.sort(key=lambda o: o["pricePP"])
    return out


def one_ways(origin, dest, start, end):
    seen, out = set(), []
    for dm in _months(start, end):
        for x in _get({"origin": origin, "destination": dest, "departure_at": dm, "currency": "eur",
                       "sorting": "price", "one_way": "true", "limit": 1000}):
            o = _norm(x, True)
            if start <= o["depart"][:10] <= end:
                k = (o["depart"], o["airline"], o["pricePP"])
                if k not in seen:
                    seen.add(k)
                    out.append(o)
    out.sort(key=lambda o: o["pricePP"])
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    rt = round_trips(a[0], a[1], a[2], a[3])
    print("round trips:", len(rt), STATUS)
    for o in rt[:8]:
        print(o)
    if len(a) > 4:
        ow = one_ways(a[0], a[1], a[2], a[3])
        back = one_ways(a[4], a[0], a[2], a[3])
        print("one-way out:", len(ow), "back:", len(back))
        for o in (ow[:3] + back[:3]):
            print(o)
