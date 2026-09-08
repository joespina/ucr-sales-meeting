#!/usr/bin/env python3
"""Label listings that also appeared in the previous week's block.

    python3 tools/mark_repeats.py build/records_20260909.json index.html 20260902 "September 2, 2026"

Jo's standing choice is **labelled repeats over silent gaps**: a property that was in last
week's report is not dropped, it is carried with a note saying so. WEEKLY.md has said this
since 2026-08-26 but nothing implemented it, and the 2026-09-09 build shipped 16 unlabelled
repeats before a re-check caught it. Run this after merge_all and before apply_block.
"""
import json, re, subprocess, sys, os

RECORDS, HTML, PREV_KEY, PREV_LABEL = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
ARRAYS = ("forSale", "forLease", "saleComps", "leaseComps")
HERE = os.path.dirname(os.path.abspath(__file__))

def norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", str(x or "").lower())).strip()

# pull the previous block straight out of index.html so this needs no extra input file
js = subprocess.run(["python3", os.path.join(HERE, "extract_meetings.py"), HTML],
                    capture_output=True, text=True, check=True).stdout
# the extracted MEETINGS blob is megabytes -- `node -e` blows the argv limit, write a file
tmp = "/tmp/_prev_block.json"
js += "\nrequire('fs').writeFileSync(%r, JSON.stringify(MEETINGS[%r]||null));\n" % (tmp, PREV_KEY)
script = "/tmp/_mark_repeats.js"
open(script, "w").write(js)
subprocess.run(["node", script], check=True, capture_output=True, text=True)
prev = json.load(open(tmp))
if not prev:
    print("no previous block %s in %s -- nothing to mark" % (PREV_KEY, HTML)); sys.exit(0)

data = json.load(open(RECORDS, encoding="utf-8"))
NOTE = "Also appeared in the %s report" % PREV_LABEL
marked = []
for a in ARRAYS:
    seen = {(norm(r.get("address")), norm(r.get("city"))) for r in prev.get(a, [])}
    for r in data.get(a, []):
        if (norm(r.get("address")), norm(r.get("city"))) in seen:
            if NOTE not in (r.get("notes") or ""):
                r["notes"] = (r["notes"] + " · " if r.get("notes") else "") + NOTE
            marked.append((a, r["id"], r["address"], r["city"]))

json.dump(data, open(RECORDS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("marked %d repeat(s) from %s" % (len(marked), PREV_LABEL))
for m in marked: print("  ", m)
