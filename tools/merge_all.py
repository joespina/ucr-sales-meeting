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
    # 2026-09-02: same property, different spelling across sources
    ("531 central avenue", "laurel"): ("531 central ave", "laurel"),
    ("347 devereux drive", "natchez"): ("347 devereaux dr", "natchez"),
    ("4432 north gloster street", "tupelo"): ("4432 n gloster st", "tupelo"),
    ("112 riley drive", "jackson"): ("112 riley dr", "jackson"),
    ("11376 three rivers road", "gulfport"): ("11376 three rivers rd", "gulfport"),
    ("15075 us 49", "gulfport"): ("15075 highway 49", "gulfport"),
    ("903 s locust street", "mccomb"): ("903 s locust st", "mccomb"),
    ("2438 highway 98 east", "columbia"): ("2438 highway 98 e", "columbia"),
    ("1329 ms13", "columbia"): ("1329 hwy 13 n", "columbia"),
    ("5000 hwy 80 e", "pearl"): ("5000 highway 80 e", "pearl"),
    ("braswell rd", "hattiesburg"): ("103 braswell rd", "hattiesburg"),
    # 2026-09-08: CoStar abbreviates, Moody's spells it out
    ("3405 pemberton square", "vicksburg"): ("3405 pemberton sq", "vicksburg"),
    ("409 virlilia rd", "canton"): ("409 virilia rd", "canton"),
    # 2026-09-08: Crexi vs MLS/CoStar spellings
    ("650 north oak avenue", "ruleville"): ("650 n oak avenue", "ruleville"),
    ("650 north oak avenue units", "ruleville"): ("650 n oak unit a avenue", "ruleville"),
    # norm() strips the hyphen without inserting a space, so key on the joined form
    ("34033405 pemberton square boulevard", "vicksburg"): ("3405 pemberton sq", "vicksburg"),
    # Crexi lists the 44.5-acre Starkville tract on Bardwell Road; CoStar calls it
    # Blackjack Rd. Same listing - "44.5 Acres At the Gates of Mississippi State".
    ("bardwell road", "starkville"): ("blackjack rd", "starkville"),   # verified: Crexi's
    # page for the 44.5-acre tract names both roads (corner parcel)
    ("1313 carterville road", "petal"): ("1313 carterville rd", "petal"),
    ("2005 old richton road", "petal"): ("2005 old richton rd", "petal"),
    ("1224 east fortification street", "jackson"): ("1224 e fortification st", "jackson"),
    ("128 east commerce street", "aberdeen"): ("128 e commerce st", "aberdeen"),
    # 2026-09-15: same property, different spelling across sources. Each verified by
    # matching price AND size, not by address resemblance alone.
    ("906 6th avenue", "picayune"): ("906 sixth ave", "picayune"),          # MLS -> CoStar/Crexi, both $575,000
    ("4194 hwy 589", "sumrall"): ("4194 ms589", "sumrall"),                 # Crexi -> CoStar, both 25.5 AC unpriced
    ("0 tchulahoma rd", "hernando"): ("tchulahoma rd", "hernando"),         # Crexi -> CoStar, both 58 AC unpriced
    ("country club rd", "hattiesburg"): ("0 country club road", "hattiesburg"),  # Moody's -> Crexi, both $79,990
    ("111 mable st", "hattiesburg"): ("111 mable street", "hattiesburg"),   # Crexi -> Moody's, both $189,900
    ("3100 us 80", "pearl"): ("3100 hwy 80 e", "pearl"),                    # Crexi -> CoStar, Harbor Freight
    ("801 ridgewood road", "ridgeland"): ("801 ridgewood rd", "ridgeland"), # Crexi -> CoStar, Staybridge $11.3M
    ("2022 us72", "corinth"): ("2022 highway 72 e", "corinth"),             # Moody's/Crexi -> CoStar, both $2,711,864
    # 9008 McLaurin is listed twice on Crexi and once on MLS; the city is spelled
    # three ways. All three carry $699,000 / 14,000 SF.
    ("9008 mclaurin st", "bay st louis"): ("9008 mclaurin street", "bay st louis"),
    ("9008 mclaurin street", "bay saint louis"): ("9008 mclaurin street", "bay st louis"),
    # CoStar prices the Southaven Hwy 51 tract as "Part of 3-Property Portfolio" at the
    # same $700,000 Crexi quotes for the 8-lot package at Hwy 51 & Dorchester Dr.
    ("us51 hwy n", "southaven"): ("hwy 51 dorchester dr", "southaven"),
    # leases
    ("2446 caffey street", "hernando"): ("2446 caffey st", "hernando"),
    ("272 calhoun station parkway", "madison"): ("272 calhoun station pkwy", "madison"),
    ("207 commonwealth blvd 102", "oxford"): ("207 commonwealth blvd", "oxford"),
    ("1315 24th street", "mccomb"): ("1315 24th st", "mccomb"),
    ("116 west main street", "louisville"): ("116 w main st", "louisville"),
    ("4400 hardy st", "hattiesburg"): ("4400 hardy street", "hattiesburg"),
    ("100 106 business park drive", "ridgeland"): ("100 business park dr", "ridgeland"),
    ("5 shenandoah drive", "hattiesburg"): ("9 shenandoah dr", "hattiesburg"),
    ("321 2nd street", "columbia"): ("321 2nd st", "columbia"),
    ("1010 s 17th ave", "hattiesburg"): ("1010 s 17th avenue", "hattiesburg"),
    # 2026-09-08 Crexi lease spellings
    ("3420 goodman rd w", "horn lake"): ("3420 goodman rd", "horn lake"),
    ("1220 north shore parkway", "brandon"): ("1220 n shore pkwy", "brandon"),
    ("176 east center street", "hernando"): ("176180 e center st", "hernando"),
    ("3506 washington avenue", "gulfport"): ("3506 washington ave", "gulfport"),
    ("1881 nail road", "horn lake"): ("1881 nail rd w", "horn lake"),
    ("4300 b west railroad street", "gulfport"): ("4300 b w railroad street", "gulfport"),
    ("325 hwy 51", "ridgeland"): ("325 highway 51", "ridgeland"),
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

    # A record can arrive from a source with no list date (domLabel "N/A") and then
    # be filled in by a later source that has one. Leaving the label behind renders a
    # real list date as "N/A" -- 661 Sunnybrook Rd did exactly that on 2026-09-02.
    for a in ("forSale", "forLease"):
        for r in out[a]:
            if r.get("listDate") and r.get("domLabel") == "N/A":
                r["domLabel"] = ""

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
