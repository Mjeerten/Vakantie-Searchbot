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


if __name__ == "__main__":
    import json
    a = sys.argv[1:]
    print(json.dumps(search(a[0], a[1], a[2], a[3] if len(a) > 3 else None), indent=1))
