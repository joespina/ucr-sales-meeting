#!/usr/bin/env python3
"""Report near-duplicate addresses a strict key would miss, so you can add ALIASES.

    python3 tools/near_dupes.py build/records_20260902.json [threshold]

Pairs at >=0.62 similarity within the same city are printed for a human to judge.
Most hits are genuinely different street numbers -- the point is to catch the one
that isn't.
"""
import json, re, sys, difflib

def norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", str(x or "").lower())).strip()

d = json.load(open(sys.argv[1], encoding="utf-8"))
thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.62
found = 0
for a in ("forSale", "forLease", "saleComps", "leaseComps"):
    rows = [(norm(r["address"]), norm(r.get("city")), r["id"], r["address"], r.get("source")) for r in d.get(a, [])]
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            if rows[i][1] != rows[j][1]: continue
            s = difflib.SequenceMatcher(None, rows[i][0], rows[j][0]).ratio()
            if s >= thr:
                found += 1
                print(f"{a:11} {s:.2f}  {rows[i][2]:>6} {rows[i][3]!r} [{rows[i][4]}]  vs  {rows[j][2]:>6} {rows[j][3]!r} [{rows[j][4]}]")
print("no near-duplicates above %.2f" % thr if not found else f"{found} pair(s) to eyeball")
