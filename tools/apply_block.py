#!/usr/bin/env python3
"""Rewrite (or create) one MEETINGS["YYYYMMDD"] block in index.html from a records JSON.

    python3 tools/apply_block.py 20260902 "September 2, 2026" build/records_20260902.json \
        [index.html] [build/coverage_20260902.html]

The optional last argument is a small HTML fragment describing what this week's pull
reached and what it did not; it renders as a banner above the tabs. Always write one
when a source was partly or wholly unavailable -- a silent gap reads as "no activity".

The records JSON is {"forSale":[...], "forLease":[...], "saleComps":[...], "leaseComps":[...]}.
Idempotent: run it as many times as you like, it replaces the block in place.
"""
import json, sys, os

ARRAYS = ("forSale", "forLease", "saleComps", "leaseComps")

def main(key, label, src, html="index.html", coverage=None):
    data = json.load(open(src, encoding="utf-8"))
    cov = ""
    if coverage and os.path.exists(coverage):
        cov = "    coverage: " + json.dumps(
            " ".join(open(coverage, encoding="utf-8").read().split()), ensure_ascii=False) + ",\n"
    def arr(name):
        rows = data.get(name, [])
        if not rows:
            return f"    {name}: [\n    ]"
        body = ",\n".join("    " + json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows)
        return f"    {name}: [\n{body}\n    ]"

    block = (f'  "{key}": {{\n    label: "{label}",\n' + cov
             + ",\n".join(arr(n) for n in ARRAYS) + "\n  }")

    s = open(html, encoding="utf-8").read()
    marker = f'  "{key}": {{'
    end = s.index("\n};", s.index("const MEETINGS = {"))

    if marker in s:                                  # replace an existing block
        start = s.index(marker)
        s = s[:start] + block + s[end:]
    else:                                            # append a new block
        head = s[:end].rstrip()
        assert head.endswith("}"), "unexpected shape at end of MEETINGS"
        cut = head.rfind("\n  }")
        s = s[:cut] + "\n  },\n" + block + s[end:]

    open(html, "w", encoding="utf-8").write(s)
    print("applied", key, {k: len(data.get(k, [])) for k in ARRAYS})

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3],
         sys.argv[4] if len(sys.argv) > 4 else "index.html",
         sys.argv[5] if len(sys.argv) > 5 else None)
