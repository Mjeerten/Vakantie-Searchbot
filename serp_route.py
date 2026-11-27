#!/usr/bin/env python3
"""One-off flight check for any route through SerpApi Google Flights (run by hand from the "route-check" workflow).
Usage: python3 serp_route.py <from airports, comma> <to> <dep1:ret1,dep2:ret2,...> [adults]
Prints the cheapest round trips per date pair (price is the total for all adults) plus Google's link, and the
booking page (sellers, bag rules) of the overall cheapest. Never below 5 searches left on the account."""
import json
import os
import sys
import urllib.parse

from serp_scan import API, call, left_on_account, offer

KEEP_LEFT, CAP = 5, 12


def main():
    frm, to, pairs = sys.argv[1], sys.argv[2], [p.split(":") for p in sys.argv[3].split(",")]
    adults = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    key = os.environ["SERPAPI_KEY"]
    left, err = left_on_account(key)
    print(f"SerpApi: {left} searches left {err or ''}", flush=True)
    used, best = 0, []
    for dep, ret in pairs:
        if used >= CAP or left - used <= KEEP_LEFT:
            break
        q = {"engine": "google_flights", "currency": "EUR", "gl": "nl", "hl": "en", "adults": adults, "api_key": key,
             "type": 1, "departure_id": frm, "arrival_id": to, "outbound_date": dep, "return_date": ret}
        d = call(API + "?" + urllib.parse.urlencode(q))
        used += 1
        offers = sorted([offer(x) for x in (d.get("best_flights") or []) + (d.get("other_flights") or []) if x.get("price")],
                        key=lambda o: o["pricePP"])
        link = (d.get("search_metadata") or {}).get("google_flights_url")
        lows = (d.get("price_insights") or {}).get("lowest_price")
        print(f"== {dep} -> {ret}: {len(offers)} offers, lowest {lows} | {d.get('error') or ''}\nLINK {link}", flush=True)
        for o in offers[:5]:
            print(f"  EUR {o['pricePP']} total for {adults} | {o['airline']} | {o['from']} {o['departs']} -> {o['arrives']} | stops {o['stops']} {o['layovers']} | {o['duration']}", flush=True)
        if offers:
            best.append((offers[0], q, dep, ret))
    if best and left - used > KEEP_LEFT:
        o, q, dep, ret = min(best, key=lambda b: b[0]["pricePP"])
        d = call(API + "?" + urllib.parse.urlencode(dict(q, departure_token=o["_dep"])))
        used += 1
        back = sorted([offer(x) for x in (d.get("best_flights") or []) + (d.get("other_flights") or []) if x.get("price")],
                      key=lambda b: b["pricePP"])
        for b in back[:3]:
            print(f"  BACK {dep}->{ret} EUR {b['pricePP']} | {b['airline']} | {b['departs']} -> {b['to']} {b['arrives']}", flush=True)
        if back and back[0].get("_book"):
            d = call(API + "?" + urllib.parse.urlencode(dict(q, booking_token=back[0]["_book"])))
            used += 1
            for x in d.get("booking_options") or []:
                t = x.get("together") or {}
                print(f"  BOOK {t.get('book_with')} EUR {t.get('price')} total airline={bool(t.get('airline'))}", flush=True)
            print(f"  BAGS {(d.get('baggage_prices') or {}).get('together')}", flush=True)
            print(f"BOOKLINK {(d.get('search_metadata') or {}).get('google_flights_url')}", flush=True)
    print(f"done: {used} searches used", flush=True)


if __name__ == "__main__":
    main()
