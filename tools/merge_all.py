#!/usr/bin/env python3
"""Merge per-source record files into one records JSON for a meeting block.

    python3 tools/merge_all.py build/records_20260902.json \
        build/costar.json build/mls.json build/moodys.json build/crexi.json

Source order matters: the FIRST file to contribute a given address owns the
record's id and address spelling; later sources fill blank fields and append
their token to `source`. Put CoStar first (richest building attributes), then
MLS, then Moody's -- that ordering was validated on 2026-08-26.

Dedup is by normalised (address, city) within each array. Two records for the
same property must never both appear: the dashboard shows one card per row and
duplicates read as double-counted inventory.
"""
import json, re, sys, os

ARRAYS = ("forSale", "forLease", "saleComps", "leaseComps")

def norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", str(x or "").lower())).strip()

# Same property, different spelling across sources. Add to this as you find them;
# a missed alias produces two near-identical cards, which is how "100 - 104
# Business Park Dr" and "100 Business Park Dr" nearly shipped twice.
ALIASES = {
    ("100 104 business park dr", "ridgeland"): ("100 business park dr", "ridgeland"),
    ("100 106 business park dr", "ridgeland"): ("100 business park dr", "ridgeland"),
}

def akey(addr, city):
    k = (norm(addr), norm(city))
    return ALIASES.get(k, k)

def merge(out_path, sources):
    out = {a: [] for a in ARRAYS}
    index = {a: {} for a in ARRAYS}
    merged = []

    for path in sources:
        if not os.path.exists(path):
            print("skip (missing):", path); continue
        data = json.load(open(path, encoding="utf-8"))
        for a in ARRAYS:
            for r in data.get(a, []):
                key = akey(r.get("address"), r.get("city"))
                if key in index[a]:
                    tgt = index[a][key]
                    seen, toks = set(), []
                    for s in (tgt.get("source", "") + "," + r.get("source", "")).split(","):
                        if s and s not in seen: seen.add(s); toks.append(s)
                    for k, v in r.items():
                        if k in ("id", "source", "notes"): continue
                        if not tgt.get(k) and v: tgt[k] = v
                    tgt["source"] = ",".join(toks)
                    if r.get("notes") and r["notes"] not in tgt.get("notes", ""):
                        tgt["notes"] = (tgt.get("notes", "") + " · " if tgt.get("notes") else "") + r["notes"]
                    merged.append((a, tgt["id"], r.get("id"), tgt["address"], tgt["source"]))
                else:
                    rec = dict(r)
                    out[a].append(rec)
                    index[a][key] = rec

    # newest first, so the top of each tab is this week's freshest activity
    out["forSale"].sort(key=lambda r: r.get("listDate", ""), reverse=True)
    out["forLease"].sort(key=lambda r: r.get("listDate", ""), reverse=True)
    out["saleComps"].sort(key=lambda r: r.get("saleDate", ""), reverse=True)
    out["leaseComps"].sort(key=lambda r: r.get("signDate", ""), reverse=True)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("counts:", {a: len(out[a]) for a in ARRAYS})
    print("cross-source merges:", len(merged))
    for x in merged: print("  merged", x)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(__doc__)
    merge(sys.argv[1], sys.argv[2:])
