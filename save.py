#!/usr/bin/env python3
"""Turn run.py results into hub database documents (one JSON file per document) and a push line.

Usage: python3 save.py <results.json> <dbdir> <outdir> <nowIso> [plans.json]
  dbdir  : where ArtifactData list wrote the current docs (<dbdir>/travel_trips/<id>.json ...), may be empty
  outdir : writes travel_trips/<planId>.json, travel_packages/<slug>.json, travel_plans/<id>.json,
           travel_runs/<id>.json and summary.json
Collections live in the Agent Hub database next to Flipdeck's; this script only ever writes travel_* collections.

summary.json: {lastSummary, push (string or null), writes:[{op, collection, doc_id, file_path, if_version}]}
"""
import glob
import json
import os
import re
import sys

res_path, dbdir, outdir, now = sys.argv[1:5]
plans_path = sys.argv[5] if len(sys.argv) > 5 else None
T, P, RU, PL = "travel_trips", "travel_packages", "travel_runs", "travel_plans"
res = json.load(open(res_path))


try:
    VERS = json.load(open(os.path.join(dbdir, "versions.json")))
except Exception:
    VERS = {}


def load_existing(coll):
    out = {}
    for f in glob.glob(os.path.join(dbdir, coll, "*.json")):
        d = json.load(open(f))
        doc_id = os.path.splitext(os.path.basename(f))[0]
        ver = d.get("version") if isinstance(d, dict) else None
        body = d.get("data") if isinstance(d, dict) and isinstance(d.get("data"), dict) else d
        out[doc_id] = (body, ver or VERS.get(coll + "/" + doc_id))
    return out


trips_old = load_existing(T)
pk_old = load_existing(P)
pl_old = load_existing(PL)
writes, pushes, summ = [], [], []


def put(coll, doc_id, body, old):
    os.makedirs(os.path.join(outdir, coll), exist_ok=True)
    fp = os.path.join(outdir, coll, doc_id + ".json")
    json.dump(body, open(fp, "w"), ensure_ascii=False)
    w = {"op": "set", "collection": coll, "doc_id": doc_id, "file_path": os.path.abspath(fp)}
    if old and old[1]:
        w["if_version"] = old[1]
    writes.append(w)


bmax = None
for p in res["plans"]:
    b = p.get("best")
    old = trips_old.get(p["planId"])
    prev = old[0] if old else {}
    if not b:
        summ.append(f"{p['name']}: {'; '.join(p.get('notes') or ['no price'])}")
        # keep the last good result (if any), add the note, the flight checks and the costs without flight
        doc = dict(prev) if prev else {"planId": p["planId"], "name": p["name"], "country": p["country"]}
        doc["lastNote"] = "; ".join(p.get("notes") or [])
        doc["lastTriedAt"] = now
        doc["flightChecks"] = p.get("flightChecks") or []
        doc["groundOnly"] = p.get("groundOnly")
        put(T, p["planId"], doc, old)
        continue
    hist = (prev.get("history") or [])[-59:] + [{"at": now, "totalPP": b["totalPP"], "flightPP": b["flight"]["pricePP"]}]
    best_ever = prev.get("bestEver")
    improved = best_ever is None or b["totalPP"] < best_ever["totalPP"]
    if improved:
        best_ever = {"totalPP": b["totalPP"], "at": now, "depart": b["depart"]}
    doc = {"planId": p["planId"], "name": p["name"], "country": p["country"], "updatedAt": now,
           "best": b, "history": hist, "bestEver": best_ever, "lastNote": None,
           "flightChecks": p.get("flightChecks") or [], "groundOnly": None}
    put(T, p["planId"], doc, old)
    summ.append(f"{p['name']} €{b['totalPP']}")
    # push rule: within budget and new best (or first result), or a drop of >= 75 versus last run
    last = (prev.get("history") or [{}])[-1].get("totalPP")
    drop = last - b["totalPP"] if last else 0
    within = b["verdict"] in ("within budget", "top deal")
    if within and (improved or drop >= 75):
        pushes.append(f"{p['name']} {b['days']}d €{b['totalPP']} p.p. ({b['verdict']}) {b['depart'][5:]}→{b['return'][5:]} vlucht {b['flight']['origin']} {'/'.join(b['flight']['airlines'])}")

seen = set()
for r in res.get("packages", []):
    if r.get("error") or not r.get("url"):
        continue
    doc_id = re.sub(r"[^a-z0-9-]", "", r["url"].rstrip("/").split("/")[-1].lower())[:120] or "pkg"
    if doc_id in seen:
        continue
    seen.add(doc_id)
    old = pk_old.get(doc_id)
    doc = {**r, "source": r.get("source") or "Journaway", "updatedAt": now}
    prev_min = (old[0].get("minAllInPP") if old else None)
    allin = min((d["allInPP"] for d in r.get("departures", [])), default=None)
    doc["minAllInPP"] = allin
    put(P, doc_id, doc, old)
    if allin and allin <= 2500 and (prev_min is None or allin < prev_min - 50):
        pushes.append(f"Pakket {r['title'][:60]} €{allin} p.p. incl. eten")

# packages that no longer show up in the window: drop them so the hub stays current
for doc_id, old in pk_old.items():
    if doc_id not in seen and res.get("packages"):
        w = {"op": "delete", "collection": P, "doc_id": doc_id}
        if old[1]:
            w["if_version"] = old[1]
        writes.append(w)

if plans_path:
    new_ids = set()
    for p in json.load(open(plans_path)):
        new_ids.add(p["id"])
        put(PL, p["id"], {**p, "updatedAt": now}, pl_old.get(p["id"]))
    for doc_id, old in pl_old.items():
        if doc_id not in new_ids:
            w = {"op": "delete", "collection": PL, "doc_id": doc_id}
            if old[1]:
                w["if_version"] = old[1]
            writes.append(w)
        # results of a dropped plan go too
    for doc_id, old in trips_old.items():
        if doc_id not in new_ids:
            w = {"op": "delete", "collection": T, "doc_id": doc_id}
            if old[1]:
                w["if_version"] = old[1]
            writes.append(w)

pk_best = min(((d["allInPP"], r["title"]) for r in res.get("packages", []) for d in r.get("departures", [])), default=None)
if pk_best:
    summ.append(f"package from €{pk_best[0]}")
if res.get("googleBlocked"):
    summ.append("Google blocked part of the search")
line = " · ".join(summ)[:300]
run_id = now.replace(":", "-")
put(RU, run_id, {"at": now, "summary": line, "googleBlocked": res.get("googleBlocked"), "pushes": pushes}, None)
push = None
if pushes:
    push = "VAKANTIE: " + pushes[0] + (f" (+{len(pushes) - 1} meer)" if len(pushes) > 1 else "")
json.dump({"lastSummary": line, "push": push[:200] if push else None, "writes": writes},
          open(os.path.join(outdir, "summary.json"), "w"), ensure_ascii=False, indent=1)
print(line)
print("PUSH:", push)
print("writes:", len(writes))
