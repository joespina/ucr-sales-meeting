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
# Matching on the address alone loses a repeat the moment an address is CORRECTED:
# "MS 35 N, Forest" became "4006 MS-35, Forest" once Moody's own property record supplied
# the house number, and the listing stopped counting as a repeat although it is the same
# listing (2026-09-22). A source URL or MLS# is the identity that survives that, so match
# on either.
# Match on the address with suffix and direction spelling folded, too: "409 West Oak Street"
# (Crexi, this week) is "409 W Oak St" (CoStar, last week), and "48 Rawls Springs Loop Road"
# is "... Loop Rd". Both were missed on 2026-09-29, three cards in all.
_SUFFIX = {"road": "rd", "drive": "dr", "street": "st", "avenue": "ave", "boulevard": "blvd",
           "highway": "hwy", "parkway": "pkwy", "circle": "cir", "cove": "cv", "court": "ct",
           "lane": "ln", "place": "pl", "north": "n", "south": "s", "east": "e", "west": "w"}
def loose(addr):
    return " ".join(_SUFFIX.get(w, w) for w in norm(addr).split())

def keys_of(r):
    ks = {("addr", norm(r.get("address")), norm(r.get("city"))),
          ("loose", loose(r.get("address")), norm(r.get("city")))}
    for f in ("moodysUrl", "crexiUrl", "mlsUrl"):
        v = str(r.get(f) or "").strip()
        if v: ks.add((f, v))
    if r.get("mlsNum"): ks.add(("mlsNum", str(r["mlsNum"]).strip()))
    return ks

# A repeat cannot have been listed AFTER the report it already appeared in. 903 Wholesale
# Row was in the Sep 23 report listed Jul 31 (Moody's) and came back this week from CoStar and
# Crexi as listed Sep 25 -- the card read "5 days, new" (2026-09-29). When this week's list
# date is later than the previous window's last day, or missing, carry the earlier one and say
# where both came from. The previous window ends two days before the previous meeting.
import datetime
PREV_END = (datetime.date(int(PREV_KEY[:4]), int(PREV_KEY[4:6]), int(PREV_KEY[6:])) - datetime.timedelta(days=2)).isoformat()
carried = []

marked = []
for a in ARRAYS:
    seen, by_key = set(), {}
    for r in prev.get(a, []):
        ks = keys_of(r); seen |= ks
        for k in ks: by_key.setdefault(k, r)
    for r in data.get(a, []):
        hit = keys_of(r) & seen
        if hit:
            if NOTE not in (r.get("notes") or ""):
                r["notes"] = (r["notes"] + " · " if r.get("notes") else "") + NOTE
            marked.append((a, r["id"], r["address"], r["city"]))
            if a in ("forSale", "forLease") and r.get("domLabel") != "Under Contract":
                q = by_key[sorted(hit)[0]]
                pld, cld = str(q.get("listDate") or ""), str(r.get("listDate") or "")
                if pld and pld <= PREV_END and (not cld or cld > PREV_END):
                    r["listDate"], r["domLabel"] = pld, ""
                    msg = ("List date %s carried from the %s report (%s); %s" %
                           (pld, PREV_LABEL, q.get("source", "?"),
                            ("this week's card date, %s (%s), falls after that report's window"
                             % (cld, (r.get("source") or "?").split(",")[0])) if cld
                            else "no list date published this week"))
                    # merge_all's list-date disagreement note says the card uses the first
                    # source's date; after a carry it does not.
                    r["notes"] = r["notes"].replace("; days on market use the first",
                                                    "; days on market use the date carried from the previous report")
                    if msg not in r["notes"]: r["notes"] += " · " + msg
                    carried.append((r["address"], cld or "none", pld))

json.dump(data, open(RECORDS, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("marked %d repeat(s) from %s" % (len(marked), PREV_LABEL))
if carried:
    print("list date carried from the previous report (%d):" % len(carried))
    for c in carried: print("   %s: %s -> %s" % c)
for m in marked: print("  ", m)
