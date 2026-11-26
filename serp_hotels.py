#!/usr/bin/env python3
"""Hotel re-check for the booked golden route through SerpApi's Google Hotels API (owner's wish, Nov 2026).
Runs in the GitHub workflow "hotel-checks"; the key comes from the repository secret SERPAPI_KEY (never stored here).
Usage: python3 serp_hotels.py <out.json> [--dry-run] [--pages N] [--details N]

Owner's criteria: private room for 2 (no dorms, shared bathroom fine, any beds), hotels / hostels / ryokan /
guesthouses only (no vacation rentals), price first but a nice location: the daily train/metro cost of staying
far out is added to the price, so a central hotel wins when the outskirts saving is eaten by transport.
Reasonably good reviews. Never below 5 searches left on the account. Japan only (never China).
"""
import json
import math
import os
import subprocess
import sys
import urllib.parse

API = "https://serpapi.com/search.json"
KEEP_LEFT, RUN_CAP = 5, 40

# the golden route as booked (dates from costs.json ownerStays), with where the fun is
CITIES = {
    "Tokyo": {"q": "hotels in Taito, Tokyo, Japan", "hubs": [(35.6812, 139.7671), (35.7138, 139.7773), (35.6896, 139.7006),
                                           (35.6580, 139.7016), (35.7148, 139.7967)]},  # Tokyo st, Ueno, Shinjuku, Shibuya, Asakusa
    "Kanazawa": {"q": "hotels in Kanazawa, Ishikawa, Japan", "hubs": [(36.5781, 136.6480), (36.5613, 136.6562)]},  # station, Korinbo/Kenrokuen
    "Kyoto": {"q": "hotels in Kyoto, Japan", "hubs": [(35.0036, 135.7681), (34.9858, 135.7588)]},  # Kawaramachi/Gion, Kyoto st
    "Koyasan": {"q": "shukubo temple lodging in Koyasan, Wakayama, Japan", "hubs": [(34.2131, 135.5836)]},  # Okunoin/centre
    "Osaka": {"q": "hotels in Osaka, Japan", "hubs": [(34.6687, 135.5013), (34.7025, 135.4959), (34.7334, 135.5001)]},  # Namba, Umeda, Shin-Osaka
}
AVOID = ["capsule", "dorm", "bunk", "pod", "cabin", "love hotel", "male only", "female only", "women only"]
# metro day cost p.p. in yen for a walk-away distance: within 1.2 km of a hub you walk most days
JPY_PER_EUR = 162


def call(url):
    p = subprocess.run(["curl", "-s", "-m", "150", url], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"error": "bad response: " + p.stdout[:120]}


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def transport_jpy(dist_km, city):
    """Extra metro/train cost per person per day for staying this far from where you go every day."""
    if city == "Koyasan":
        return 0 if dist_km < 2.5 else 600  # the town is small; the bus covers it
    if dist_km <= 1.2:
        return 0
    if dist_km <= 3:
        return 360  # ~2 short rides
    if dist_km <= 6:
        return 500
    return 800


def stays():
    own = json.load(open("costs.json"))["ownerStays"]["jp-golden"]
    import datetime as dt
    for city, s in own.items():
        ci = dt.date.fromisoformat(s["checkin"])
        yield city, s["checkin"], (ci + dt.timedelta(days=int(s["nights"]))).isoformat(), int(s["nights"]), s["pick"]


def params(key, city, ci, co, token=None):
    q = {"engine": "google_hotels", "q": CITIES[city]["q"], "check_in_date": ci, "check_out_date": co,
         "adults": 2, "currency": "EUR", "gl": "nl", "hl": "en", "sort_by": 3, "rating": 7, "api_key": key}
    if token:
        q["next_page_token"] = token
    return q


def candidate(p, city, nights):
    gps = p.get("gps_coordinates") or {}
    tot = ((p.get("total_rate") or {}).get("extracted_lowest")
           or ((p.get("rate_per_night") or {}).get("extracted_lowest") or 0) * nights)
    if not tot or not gps:
        return None
    pos = (gps.get("latitude"), gps.get("longitude"))
    d = min(km(pos, h) for h in CITIES[city]["hubs"])
    tj = transport_jpy(d, city)
    extra = round(tj * nights * 2 / JPY_PER_EUR)  # 2 people, every day of the stay
    return {"name": p.get("name"), "type": p.get("type"), "total": round(tot), "nightlyEur": round(tot / nights),
            "rating": p.get("overall_rating"), "reviews": p.get("reviews"), "locationRating": p.get("location_rating"),
            "hotelClass": p.get("extracted_hotel_class"), "kmToCentre": round(d, 1), "transportPPday": round(tj / JPY_PER_EUR, 1),
            "effectiveTotal": round(tot) + extra, "link": p.get("link"), "token": p.get("property_token"),
            "amenities": (p.get("amenities") or [])[:8], "nearby": [n.get("name") for n in (p.get("nearby_places") or [])][:3]}


def good(c):
    text = (c["name"] or "").lower() + " " + (c.get("type") or "").lower()
    if c["kmToCentre"] > 12:  # Google sometimes mixes in hotels near the searcher instead of the city
        return False
    return ((c.get("type") or "hotel").lower() != "vacation rental" and not any(w in text for w in AVOID)
            and (c.get("rating") or 0) >= 3.9 and (c.get("reviews") or 0) >= 50
            and (c.get("locationRating") is None or c["locationRating"] >= 3.0))


def main():
    out = sys.argv[1]
    dry = "--dry-run" in sys.argv
    pages = int(sys.argv[sys.argv.index("--pages") + 1]) if "--pages" in sys.argv else 2
    ndet = int(sys.argv[sys.argv.index("--details") + 1]) if "--details" in sys.argv else 3
    only = sys.argv[sys.argv.index("--cities") + 1].split(",") if "--cities" in sys.argv and sys.argv[sys.argv.index("--cities") + 1] else None
    key = os.environ.get("SERPAPI_KEY") or ("DRY" if dry else None)
    if not key:
        print("SerpApi: no key, skipped")
        return
    if dry:
        for city, ci, co, n, _ in stays():
            print(city, API + "?" + urllib.parse.urlencode(params("KEY", city, ci, co)))
        print(f"would use at most {len(CITIES) * (pages + ndet)} searches (cap {RUN_CAP}, keep {KEEP_LEFT})")
        return
    acc = call("https://serpapi.com/account.json?" + urllib.parse.urlencode({"api_key": key}))  # free
    left = acc.get("total_searches_left", acc.get("plan_searches_left"))
    print(f"SerpApi: {left} searches left on the account", flush=True)
    if left is None:
        print("account check failed:", str(acc.get("error"))[:120])
        return
    used, res = 0, {}

    def can():
        return used < RUN_CAP and left - used > KEEP_LEFT

    for city, ci, co, n, cur in stays():
        if only and city not in only:
            continue
        found, token = {}, None
        for _ in range(pages):
            if not can():
                break
            d = call(API + "?" + urllib.parse.urlencode(params(key, city, ci, co, token)))
            used += 1
            for p in d.get("properties") or []:
                c = candidate(p, city, n)
                if c and c["name"] not in found:
                    found[c["name"]] = c
            print(f"{city}: page -> {len(d.get('properties') or [])} properties {d.get('error') or ''}", flush=True)
            token = (d.get("serpapi_pagination") or {}).get("next_page_token")
            if not token:
                break
        ok = sorted((c for c in found.values() if good(c)), key=lambda c: c["effectiveTotal"])
        top = ok[:6]
        for c in top[:ndet]:
            if not can() or not c.get("token"):
                continue
            q = params(key, city, ci, co)
            q["property_token"] = c["token"]
            d = call(API + "?" + urllib.parse.urlencode(q))
            used += 1
            pr = [{"source": x.get("source"), "total": (x.get("total_rate") or {}).get("extracted_lowest"),
                   "link": x.get("link"), "official": bool(x.get("official"))}
                  for x in (d.get("prices") or []) + (d.get("featured_prices") or []) if x.get("source")]
            c["prices"] = sorted([x for x in pr if x["total"]], key=lambda x: x["total"])[:5]
            c["address"] = d.get("address")
            c["checkIn"] = d.get("check_in_time")
            c["excludedAmenities"] = (d.get("excluded_amenities") or [])[:5]
        res[city] = {"checkin": ci, "checkout": co, "nights": n, "seen": len(found), "qualifying": len(ok),
                     "current": {"name": cur["name"], "total": cur["total"]}, "top": top}
        for c in top:
            print(f"  {city} EUR {c['total']} (eff {c['effectiveTotal']}) {c['name']} | {c['rating']}* {c['reviews']} rev | "
                  f"{c['kmToCentre']} km | {c.get('type')} | {[(x['source'], x['total']) for x in c.get('prices', [])][:3]}", flush=True)
    json.dump({"searchesUsed": used, "leftBefore": left, "cities": res}, open(out, "w"), indent=1, ensure_ascii=False)
    print(f"done: {used} searches used, {left - used} left", flush=True)


if __name__ == "__main__":
    main()
