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

# A page break puts a form feed in front of the entry number, and \s eats it: with
# "\f" plus four spaces the old ^\s{1,4} no longer matched and the entry silently
# merged into the previous one, so its fields were attributed to the wrong property
# (found 2026-09-01: 106 Riverview Dr rendered 120 Saint Charles Ave's size).
# Form feeds are stripped from every line before matching.
HDR = re.compile(r'^\s{1,4}(\d+)\s{2,}(\S.*?)\s*$')
LOC = re.compile(r'^\s*(.+?),\s*(Mississippi|MS)\s+(\d{5})\s*(?:\(([^)]*)\))?\s*(?:-\s*(.*?)\s*Submar\S*)?\s{2,}(\S.*?)\s*$')

def blocks(path):
    lines = [l.lstrip('\f') for l in open(path).read().split('\n')]
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

HEADINGS = ("Property Summary", "For Sale Summary", "For Lease Summary", "Property Details",
            "Amenities", "Available Spaces", "Market Conditions", "Contacts", "Unit Mix",
            "Transportation", "Sale History", "Tenants", "Land Details")
# Sections whose key/value pairs we want. "For Sale Summary" and "For Lease Summary" only
# exist in CoStar's *listing* export; the thinner property export has neither, which is
# exactly how you tell the two templates apart (see feedback-costar-missing-reports).
WANTED = ("Property Summary", "For Sale Summary", "For Lease Summary", "Property Details",
          "Land Details")
SECT = re.compile(r'^[ \t]*(' + '|'.join(HEADINGS) + r')[ \t]*$', re.M)

def sections(body):
    """Split a block into {heading: text} using the known section headings."""
    out, hits = {}, list(SECT.finditer(body))
    for i, m in enumerate(hits):
        end = hits[i+1].start() if i+1 < len(hits) else len(body)
        out.setdefault(m.group(1), '')
        out[m.group(1)] += body[m.end():end]
    return out

def kvpairs(body):
    """Two-column 'Label   Value' pairs from every wanted section."""
    kv = {}
    secs = sections(body)
    for name in WANTED:
        for line in secs.get(name, '').split('\n'):
            if not line.strip() or line.strip().startswith('2026 CoStar'):
                continue
            parts = re.split(r'\s{3,}', line.strip())
            i = 0
            while i + 1 < len(parts):
                k, v = parts[i].strip(), parts[i+1].strip()
                if k and v and not k[0].isdigit():
                    kv.setdefault(k, v)
                i += 2
    return kv

def owner(body):
    """Recorded/True Owner from the Contacts table, best available."""
    sec = sections(body).get('Contacts', '')
    best = ''
    for line in sec.split('\n'):
        m = re.match(r'\s*(Recorded Owner|True Owner)\s{2,}(\S.*?)(?:\s{2,}|$)', line)
        if m:
            if m.group(1) == 'True Owner':
                return m.group(2).strip()
            best = best or m.group(2).strip()
    return best

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
        b['kv'] = kvpairs(b['body']); b['spaces'] = spaces(b['body']); b['amen'] = amenities(b['body']); b['owner'] = owner(b['body'])
        b.pop('body')
    json.dump(bs, open(sys.argv[2],'w'), indent=1)
    ks = {}
    for b in bs:
        for k in b['kv']: ks[k] = ks.get(k,0)+1
    print('field frequency:', dict(sorted(ks.items(), key=lambda x:-x[1])))
