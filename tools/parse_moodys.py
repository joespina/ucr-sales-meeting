#!/usr/bin/env python3
"""Parse a Moody's CRE "For Sale and Lease" PDF text export into structured entries.

    pdftotext -layout "Moodys_for_Sale_and_Lease.pdf" moodys.txt
    python3 tools/parse_moodys.py moodys.txt build/moodys_pdf.json

Blocks are separated by form feeds; each page starts "<Category> For <Sale|Lease>".
One listing can span several pages, so pages are grouped by Listing ID.
The layout is three columns: key/value, key/value, and a free-text Description
column on the right, so key/value extraction is anchored on a known key list.
"""
import re, json, sys

KEYS = [
 "Suite","Sublease","Total Available Space","Min Div/Max Contig","Asking Rate","Monthly Rate",
 "Lease Type","Expenses","Possession","Show Instructions","Vacant","Available Date","Days On Market",
 "Date Listed","Last Modified","Listing ID","Parking Spaces","Asking Price","Listing Price Per SF",
 "List Price Per Acre","Cap Rate (Actual)","Investment","Electric Service","Clear Height",
 "Ceiling Height","Dock High Doors","Grade Level Doors","Water","Sanitary Sewer","Natural Gas",
 "Building Class","Property Type","Sub Type","Zoning","Building Status","Building Size","Land Size",
 "Number of Buildings","Floors","Year Built","Year Built/Renovated","Primary Construction",
 "Occupancy Type","Parcels","Legal Owner","Submarket","County","In Opportunity Zone","Signage",
 "Tenancy","Frontage","Traffic Count","Load Type","Rail Service","Sprinklers","Column Spacing",
]
_ALT = '|'.join(re.escape(k) for k in sorted(KEYS, key=len, reverse=True))
# A key whose own value is blank is followed directly by the NEXT key on the same
# line ("Asking Rate<spaces>Listing ID<spaces>45539826"). Without the negative
# lookahead the empty key swallows the next key as its value and that listing is
# lost entirely -- two Moody's listings vanished this way on 2026-09-01.
KEYRE = re.compile(r'(?:^|\s{2,})(' + _ALT + r')\s{2,}(?!(?:' + _ALT + r')\s{2,})(\S.*?)(?=\s{3,}|$)')
ADDR = re.compile(r'^([^,]+),\s*([^,]+),\s*(MS),\s*(\d{5})\s*$')
# Some listings publish no street at all (Byhalia outparcels, 2026-09-01) and the
# line collapses to "City, MS, ZIP". Match those too and leave the street blank;
# the caller falls back to the marketing name.
ADDR2 = re.compile(r'^([^,]+),\s*(MS),\s*(\d{5})\s*$')

def pages(path):
    return open(path, encoding='utf-8', errors='replace').read().split('\f')

def parse(path):
    out, order = {}, []
    for pg in pages(path):
        lines = pg.split('\n')
        kv = {}
        for ln in lines:
            for k, v in KEYRE.findall(ln):
                v = v.strip()
                if v and v != '-':
                    kv.setdefault(k, v)
        lid = kv.get('Listing ID')
        if not lid:
            continue
        if lid not in out:
            hdr = next((l.strip() for l in lines if l.strip()), '')
            addr = ''
            marketing = ''
            for i, l in enumerate(lines):
                m = ADDR.match(l.strip()); m2 = None if m else ADDR2.match(l.strip())
                if m or m2:
                    if m:
                        addr = m.group(1).strip(); city = m.group(2).strip(); zp = m.group(4)
                    else:
                        addr = ''; city = m2.group(1).strip(); zp = m2.group(3)
                    # marketing name is the first non-empty line above the "Prepared on" line
                    for j in range(i-1, -1, -1):
                        s = lines[j].strip()
                        if s and 'Prepared on' not in s and 'NAI UCR' not in s and s != hdr:
                            marketing = re.split(r'\s{2,}', s)[0].strip()
                            # the right-hand "Office: General For Lease" column can sit a
                            # single space away from the marketing name, so strip it by shape
                            marketing = re.sub(r'\s*[A-Z][A-Za-z /&-]*:\s*[A-Za-z][A-Za-z /&-]*\s+For\s+(?:Sale|Lease)\s*$', '', marketing)
                            marketing = re.sub(r'\s+(?:For\s+(?:Sale|Lease)|Sublease)\s*$', '', marketing)
                            marketing = re.sub(r'\s*(?:\u2026|\.\.\.)$', '', marketing).strip()
                            break
                    break
            else:
                city = zp = ''
            # the right-hand tail of the title line carries "Office: General For Lease"
            sub = ''
            for l in lines:
                m = re.search(r'\s{3,}([A-Za-z][A-Za-z /&\-]*?:\s*[A-Za-z][A-Za-z /&\-]*?)\s+For\s+(Sale|Lease)\s*$', l.rstrip())
                if m:
                    sub = m.group(1).strip(); break
            deal = 'Sale' if hdr.endswith('For Sale') else ('Lease' if hdr.endswith('For Lease') else '')
            out[lid] = dict(listingId=lid, header=hdr, deal=deal, marketing=marketing,
                            address=addr, city=city, zip=zp, subtypeLabel=sub, kv=kv,
                            desc=[], contacts=[])
            order.append(lid)
        else:
            for k, v in kv.items():
                out[lid]['kv'].setdefault(k, v)
        # description column: text right of column ~135
        for ln in lines:
            tail = ln[132:].strip() if len(ln) > 132 else ''
            if tail and 'Copyright Catylist' not in tail and 'assume any liability' not in tail \
               and not KEYRE.search('  ' + tail) and 'Prepared on' not in tail \
               and 'NAI UCR' not in tail and 'Katherine Drive' not in tail \
               and not re.match(r'^(?:ste|suite)\b', tail, re.I) and 'Flowood, MS 39232' not in tail:
                out[lid]['desc'].append(tail)
        # contacts block
        try:
            ci = next(i for i, l in enumerate(lines) if l.strip().startswith('Contact'))
        except StopIteration:
            ci = None
        if ci is not None:
            for l in lines[ci:ci+12]:
                s = l.strip()
                if 'Copyright' in s or not s:
                    continue
                out[lid]['contacts'].append(re.split(r'\s{3,}', s))
    return [out[k] for k in order]

if __name__ == '__main__':
    rows = parse(sys.argv[1])
    for r in rows:
        d = ' '.join(r['desc'])
        d = re.sub(r'\s+', ' ', d).strip()
        r['desc'] = d[:600]
    json.dump(rows, open(sys.argv[2], 'w'), indent=1)
    print('listings:', len(rows))
    print('deals:', {d: sum(1 for r in rows if r['deal'] == d) for d in ('Sale', 'Lease', '')})
    miss = [r['listingId'] for r in rows if not r['address']]
    print('missing address:', miss or 'none')
