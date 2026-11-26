#!/usr/bin/env python3
"""Google Flights price reader (public results page, read-only).

Usage as a module: search(origin, dest, date, ret=None) -> dict
CLI test:  python3 flights.py AMS TYO 2027-07-24 [2027-08-11]

Prices are per person (1 adult searched), in EUR, economy, any number of stops.
Google sometimes rate-limits cloud IPs (HTTP 429). Then the result has
blocked=True and the caller should stop asking Google for this run.
"""
import html
import re
import subprocess
import sys
import time
import urllib.parse

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
LABEL = re.compile(r'aria-label="(From [0-9][^"]*?euros[^"]*)"')
BLOCKED = False
EMPTY_STREAK = 0   # Google's quiet throttle: page loads but results never do


def url_for(origin, dest, date, ret=None):
    if ret:
        q = f"flights from {origin} to {dest} {date} to {ret}"
    else:
        q = f"flights from {origin} to {dest} on {date} one way"
    return "https://www.google.com/travel/flights?hl=en&gl=nl&curr=EUR&q=" + urllib.parse.quote_plus(q)


def _get(url):
    p = subprocess.run(
        ["curl", "-s", "-L", "--max-time", "30", "-A", UA, "-H", "Cookie: CONSENT=YES+",
         "-w", "\n%{http_code}", url],
        capture_output=True, text=True)
    body, _, code = p.stdout.rpartition("\n")
    return code.strip(), body


def parse(body):
    offers, seen = [], set()
    for raw in LABEL.findall(body):
        lab = html.unescape(raw).replace(" ", " ").replace("\xa0", " ")
        m = re.match(r"From ([0-9,]+) euros", lab)
        if not m:
            continue
        price = int(m.group(1).replace(",", ""))
        stops = 0 if "Nonstop" in lab else int((re.search(r"(\d+) stops? flight", lab) or [0, 0])[1])
        airline = (re.search(r"flight with ([^.]+)\.", lab) or [None, "?"])[1]
        dur = (re.search(r"Total duration ([^.]+)\.", lab) or [None, "?"])[1]
        leave = (re.search(r"Leaves (.+?) at (.+?) on (.+?) and arrives at (.+?) at (.+?) on (.+?)\.", lab))
        lay = re.findall(r"layover at ([^.]+?)(?: in [^.]+)?\.", lab)
        key = (price, airline, leave.group(2) if leave else "")
        if key in seen:
            continue
        seen.add(key)
        offers.append({
            "pricePP": price, "airline": airline.strip(), "stops": stops, "duration": dur,
            "from": leave.group(1) if leave else None, "departs": f"{leave.group(3)} {leave.group(2)}" if leave else None,
            "to": leave.group(4) if leave else None, "arrives": f"{leave.group(6)} {leave.group(5)}" if leave else None,
            "layovers": lay[:3],
            # "is a 1 hr 35 min layover" / "is a 55 min layover" / "10 hr 5 min overnight layover"
            "layoverMins": [int(h or 0) * 60 + int(mi or 0) for h, mi in
                            re.findall(r"(?:(\d+) hr)?\s*(?:(\d+) min)?\s+(?:overnight )?layover at", lab) if h or mi],
            # Google marks itineraries on separate tickets ("Self transfer", "Separate tickets booked together"):
            # a missed connection there is your own problem, so those are skipped
            "selfTransfer": bool(re.search(r"self[- ]transfer|separate tickets", lab, re.I)),
            # Google says e.g. "Change of airport" / "airport change" / "transfer to Heathrow"; a layover naming two airports counts too
            "airportChange": bool(re.search(r"change (of )?airports?|airport change|different airport|transfer to", lab, re.I))
                             or any(len(re.findall(r"Airport", x)) > 1 for x in lay),
        })
    offers.sort(key=lambda o: o["pricePP"])
    return offers


def search(origin, dest, date, ret=None, retry_wait=45):
    """One Google Flights search. Returns {url, offers, blocked, error}."""
    global BLOCKED
    url = url_for(origin, dest, date, ret)
    res = {"origin": origin, "dest": dest, "date": date, "ret": ret, "url": url,
           "offers": [], "blocked": False, "error": None}
    if BLOCKED:
        res["blocked"] = True
        return res
    for attempt in range(2):
        code, body = _get(url)
        if code == "200" and "unusual traffic" not in body:
            res["offers"] = parse(body)[:6]
            if res["offers"]:
                return res
            res["error"] = "no prices on page"
            if attempt == 1:
                return res
            time.sleep(15)
            continue
        if attempt == 0:
            time.sleep(retry_wait)
    BLOCKED = True
    res["blocked"] = True
    res["error"] = f"HTTP {code} (Google rate limit)"
    return res


# ---- tfs links (the URL format the Google Flights page itself uses), rendered in a real browser ----
import base64
import json as _json
import os as _os


def _v(n):
    o = b""
    while True:
        b, n = n & 0x7F, n >> 7
        if n:
            o += bytes([b | 0x80])
        else:
            return o + bytes([b])


def _ld(num, data):
    return _v((num << 3) | 2) + _v(len(data)) + data


HOME_AIRPORTS = {"schiphol": "AMS", "amsterdam": "AMS", "brussels": "BRU", "zaventem": "BRU", "sseldorf": "DUS",
                 "eindhoven": "EIN", "rotterdam": "RTM", "charleroi": "CRL", "cologne": "CGN", "weeze": "NRN"}


def home_code(name):
    n = (name or "").lower()
    return next((c for k, c in HOME_AIRPORTS.items() if k in n), None)


def tfs_url(legs):
    """legs: [(date, from, to), ...]. 2 legs mirrored = round trip, otherwise multi-city. 1 adult, economy, EUR."""
    rt = len(legs) == 2 and legs[0][1] == legs[1][2] and legs[0][2] == legs[1][1]
    trip = 1 if rt else (2 if len(legs) == 1 else 3)
    # "AMS,BRU,DUS" = any of these airports (Google then also mixes them: out from DUS, home to AMS)
    ap = lambda field, codes: b"".join(_ld(field, _ld(2, x.strip().encode())) for x in codes.split(","))
    m = b"".join(_ld(3, _ld(2, d.encode()) + ap(13, a) + ap(14, z)) for d, a, z in legs)
    m += _v(8 << 3) + _v(1) + _v(9 << 3) + _v(1) + _v(19 << 3) + _v(trip)
    t = base64.urlsafe_b64encode(m).decode().rstrip("=")
    return f"https://www.google.com/travel/flights/search?tfs={t}&hl=en&gl=nl&curr=EUR"


def search_legs(legs):
    """Round trip or multi-city search in a browser. Returns {url, offers, blocked, error}.
    Offer price is the whole-trip total per person; out-leg details come from the label."""
    global BLOCKED, EMPTY_STREAK
    url = tfs_url(legs)
    res = {"legs": legs, "url": url, "offers": [], "blocked": False, "error": None}
    if BLOCKED:
        res["blocked"] = True
        return res
    p = subprocess.run(["node", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "gflights.js"), url],
                       capture_output=True, text=True, timeout=150)
    try:
        r = _json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        res["error"] = "gflights.js failed: " + (p.stderr or "")[-120:]
        return res
    body = " ".join('aria-label="' + html.escape(l, quote=True) + '"' for l in r.get("labels", []))
    res["offers"] = parse(body)[:6]
    if not res["offers"]:
        res["error"] = r.get("error") or "no prices on page"
        EMPTY_STREAK += 1
        if r.get("blocked") or EMPTY_STREAK >= 2:
            BLOCKED = True
            res["blocked"] = True
            if not r.get("blocked"):
                res["error"] = "Google throttle (results never loaded twice in a row)"
    else:
        EMPTY_STREAK = 0
    return res


if __name__ == "__main__":
    import json
    a = sys.argv[1:]
    print(json.dumps(search(a[0], a[1], a[2], a[3] if len(a) > 3 else None), indent=1))
