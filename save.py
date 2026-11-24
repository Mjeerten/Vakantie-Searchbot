#!/usr/bin/env python3
"""Turn run.py results into hub database documents (one JSON file per document) and a push line.

Usage: python3 save.py <results.json> <dbdir> <outdir> <nowIso>
  dbdir  : where ArtifactData list wrote the current docs (<dbdir>/trips/<id>.json ...), may be empty
  outdir : writes trips/<planId>.json, packages/<slug>.json, runs/<id>.json, summary.json

summary.json: {lastSummary, push (string or null), writes:[{op, collection, doc_id, file_path, if_version}]}
"""
import glob
import json
import os
import re
import sys

res_path, dbdir, outdir, now = sys.argv[1:5]
res = json.load(open(res_path))


def load_existing(coll):
    out = {}
    for f in glob.glob(os.path.join(dbdir, coll, "*.json")):
        d = json.load(open(f))
        doc_id = os.path.splitext(os.path.basename(f))[0]
        ver = d.get("version") if isinstance(d, dict) else None
        body = d.get("data") if isinstance(d, dict) and isinstance(d.get("data"), dict) else d
        out[doc_id] = (body, ver)
    return out


trips_old = load_existing("trips")
pk_old = load_existing("packages")
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
        summ.append(f"{p['name']}: {'; '.join(p.get('notes') or ['geen prijs'])}")
        if prev:  # keep the last good result, add the note
            prev = dict(prev)
            prev["lastNote"] = "; ".join(p.get("notes") or [])
            prev["lastTriedAt"] = now
            put("trips", p["planId"], prev, old)
        continue
    hist = (prev.get("history") or [])[-59:] + [{"at": now, "totalPP": b["totalPP"], "flightPP": b["flight"]["pricePP"]}]
    best_ever = prev.get("bestEver")
    improved = best_ever is None or b["totalPP"] < best_ever["totalPP"]
    if improved:
        best_ever = {"totalPP": b["totalPP"], "at": now, "depart": b["depart"]}
    doc = {"planId": p["planId"], "name": p["name"], "country": p["country"], "updatedAt": now,
           "best": b, "history": hist, "bestEver": best_ever, "lastNote": None}
    put("trips", p["planId"], doc, old)
    summ.append(f"{p['name']} €{b['totalPP']}")
    # push rule: within budget and new best (or first result), or a drop of >= 75 versus last run
    last = (prev.get("history") or [{}])[-1].get("totalPP")
    drop = last - b["totalPP"] if last else 0
    within = b["verdict"] in ("binnen budget", "topdeal")
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
    doc = {**r, "source": "Journaway", "updatedAt": now}
    prev_min = (old[0].get("minAllInPP") if old else None)
    allin = min((d["allInPP"] for d in r.get("departures", [])), default=None)
    doc["minAllInPP"] = allin
    put("packages", doc_id, doc, old)
    if allin and allin <= 2500 and (prev_min is None or allin < prev_min - 50):
        pushes.append(f"Pakket {r['title'][:60]} €{allin} p.p. incl. eten")

# packages that no longer show up in the window: drop them so the hub stays current
for doc_id, old in pk_old.items():
    if doc_id not in seen and res.get("packages"):
        w = {"op": "delete", "collection": "packages", "doc_id": doc_id}
        if old[1]:
            w["if_version"] = old[1]
        writes.append(w)

pk_best = min(((d["allInPP"], r["title"]) for r in res.get("packages", []) for d in r.get("departures", [])), default=None)
if pk_best:
    summ.append(f"pakket vanaf €{pk_best[0]}")
if res.get("googleBlocked"):
    summ.append("Google blokkeerde een deel")
line = " · ".join(summ)[:300]
run_id = now.replace(":", "-")
put("runs", run_id, {"at": now, "summary": line, "googleBlocked": res.get("googleBlocked"), "pushes": pushes}, None)
push = None
if pushes:
    push = "VAKANTIE: " + pushes[0] + (f" (+{len(pushes) - 1} meer)" if len(pushes) > 1 else "")
json.dump({"lastSummary": line, "push": push[:200] if push else None, "writes": writes},
          open(os.path.join(outdir, "summary.json"), "w"), ensure_ascii=False, indent=1)
print(line)
print("PUSH:", push)
print("writes:", len(writes))
