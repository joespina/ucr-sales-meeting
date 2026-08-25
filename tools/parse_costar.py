#!/usr/bin/env python3
"""Parse a CoStar text export into structured entries.

    pdftotext -layout "CoStar for Sale Report.pdf" sale.txt
    python3 tools/parse_costar.py sale.txt build/sale.json

Two gotchas encoded here, both found the hard way on 2026-08-26:
  * An entry's location line can have its submarket TRUNCATED with an ellipsis
    ("... Submar\u2026"). Requiring the full word "Submarket" silently drops entries.
  * Split the title at the LAST " - ", not the first. The address itself can
    contain one ("100 - 104 Business Park Dr - 100-104 Business Park"); splitting
    at the first yields address "100", which then fails to dedupe against the
    same property from another source.
One entry spans several PDF pages, so blocks are grouped by entry number.
"""
import re, json, sys

HDR = re.compile(r'^\s{1,4}(\d+)\s{2,}(\S.*?)\s*$')
LOC = re.compile(r'^\s*(.+?),\s*(Mississippi|MS)\s+(\d{5})\s*(?:\(([^)]*)\))?\s*(?:-\s*(.*?)\s*Submar\S*)?\s{2,}(\S.*?)\s*$')

def blocks(path):
    lines = open(path).read().split('\n')
    hits = []
    for i, l in enumerate(lines):
        m = HDR.match(l)
        if not m: continue
        if i+1 >= len(lines): continue
        lm = LOC.match(lines[i+1])
        if not lm: continue
        hits.append((i, m.group(1), m.group(2), lm))
    out = {}
    for j, (i, num, title, lm) in enumerate(hits):
        end = hits[j+1][0] if j+1 < len(hits) else len(lines)
        body = '\n'.join(lines[i:end])
        if num not in out:
            out[num] = dict(num=num, title=title, city=lm.group(1).strip(),
                            zip=lm.group(3), county=(lm.group(4) or '').strip(),
                            submarket=(lm.group(5) or '').strip(), ptype=lm.group(6).strip(),
                            body=body)
        else:
            out[num]['body'] += '\n' + body
    return [out[k] for k in sorted(out, key=lambda x: int(x))]

def kvpairs(body):
    """Property Summary style two-column key/value lines."""
    kv = {}
    for seg in re.findall(r'Property Summary\n(.*?)(?=\n\s*(?:Amenities|Available Spaces|Market Conditions|Contacts)\b|\Z)', body, re.S):
        for line in seg.split('\n'):
            if not line.strip(): continue
            # two columns separated by 3+ spaces; each column "Label   Value"
            parts = re.split(r'\s{3,}', line.strip())
            i = 0
            while i + 1 < len(parts):
                k, v = parts[i].strip(), parts[i+1].strip()
                if k and v and not k[0].isdigit(): kv.setdefault(k, v)
                i += 2
            if len(parts) == 1:
                pass
    return kv

def spaces(body):
    rows = []
    for seg in re.findall(r'Rent/SF/Year\s+Occupancy\s+Term\n(.*?)(?=\n\s*\n\s*\n|\Z)', body, re.S):
        for line in seg.split('\n'):
            s = line.strip()
            if not s or s.startswith('2026 CoStar'): continue
            p = re.split(r'\s{2,}', s)
            if len(p) >= 6: rows.append(p)
    return rows

def amenities(body):
    m = re.search(r'Amenities\n\s*(.*?)\n', body)
    if not m: return ''
    a = m.group(1).strip()
    return '' if a.lower().startswith('no data') else a

if __name__ == '__main__':
    path = sys.argv[1]
    bs = blocks(path)
    print('entries:', len(bs), '->', [b['num'] for b in bs])
    for b in bs:
        b['kv'] = kvpairs(b['body']); b['spaces'] = spaces(b['body']); b['amen'] = amenities(b['body'])
        b.pop('body')
    json.dump(bs, open(sys.argv[2],'w'), indent=1)
    ks = {}
    for b in bs:
        for k in b['kv']: ks[k] = ks.get(k,0)+1
    print('field frequency:', dict(sorted(ks.items(), key=lambda x:-x[1])))
