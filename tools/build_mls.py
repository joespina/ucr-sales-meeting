#!/usr/bin/env python3
"""Build MLS United (FlexMLS) records from the three cluster pulls.

    python3 tools/build_mls.py build/mls_raw.txt build/mls_dates.txt build/mls_details.txt build/mls.json

Inputs are the pipe-delimited dumps described in tools/browser_pulls.md.
Only PropertyType E (commercial sale) and F (commercial lease) are accepted, and
only StateOrProvince == 'MS' -- the map bounds reach into LA/AL/TN.

`BuildingAreaTotal` is NOT always a building: on land listings FlexMLS puts the LOT
area there (5754 Us-51 came back as 69,696 SF, which is exactly its 1.6 acres).
LAND_SF below lists the records verified against their own descriptions.
"""
import json, re, sys, datetime

RAW, DATES, DETAILS, OUT = sys.argv[1:5]
MEETING = datetime.date(2026, 9, 2)
BASE = "https://my.flexmls.com/mlsunited/search/idx_links/20210924020458295435000000/listing_detail/"
PHOTO = "https://cdn.photos.sparkplatform.com/"

FS_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","price","pricePerSF",
           "pricePerUnit","capRate","size","lotSize","units","yearBuilt","zoning","tenant","contact","office",
           "phone","flags","alsoForLease","listDate","domLabel","source","mlsNum","costarUrl","moodysUrl",
           "crexiUrl","mlsUrl","mapUrl","photoUrl","notes"]
FL_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","askingRate","leaseType",
           "size","avail","lotSize","yearBuilt","zoning","tenant","contact","office","phone","availDate",
           "alsoForSale","listDate","domLabel","source","mlsNum","costarUrl","moodysUrl","crexiUrl","mlsUrl",
           "mapUrl","photoUrl","notes"]
SC_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","size","lotSize",
           "saleDate","salePrice","pricePerSF","capRate","saleType","saleConditions","tenant","yearBuilt",
           "submarket","contact","office","mlsNum","source","costarUrl","mlsUrl","mapUrl","photoUrl","notes"]

def rec(keys,d): return {k: d.get(k, False if k=="isLand" else "") for k in keys}
def mapurl(a,c): return "https://www.google.com/maps/search/?q=" + '+'.join(re.sub(r'[^A-Za-z0-9 ]',' ',(a+' '+c+' MS')).split())

COUNTY = {"McComb":"Pike","Pearl":"Rankin","Brandon":"Rankin","Pickens":"Holmes","Ruleville":"Sunflower",
 "Southaven":"DeSoto","Rosedale":"Bolivar","Jackson":"Hinds","Biloxi":"Harrison","Picayune":"Pearl River",
 "Gulfport":"Harrison","Wiggins":"Stone","Long Beach":"Harrison","Hattiesburg":"Forrest","Kiln":"Hancock",
 "Pascagoula":"Jackson","Natchez":"Adams","Vicksburg":"Warren","Moss Point":"Jackson","Lucedale":"George",
 "Yazoo City":"Yazoo","Ocean Springs":"Jackson","Clarksdale":"Coahoma"}

# ListingId -> (acres, building SF or '') where BuildingAreaTotal is really the LOT.
# Each one checked against its own listing description.
# ListingId -> dashboard type, where the description contradicts the keyword guess.
TYPE_FIX = {
 "4145662": "Industrial",   # a metal building on 4.5 acres, not a bare parcel
 "4104371": "Commercial",   # "multi use building, gutted and ready for build-out"
 "4152716": "Land",         # commercial parking lot
 "4139275": "Multifamily",  # mobile home park investment
}
LAND_SF = {
 "4160779": ("1.6 AC", ""),      # "1.6 ACRES ON HWY 51 NORTH"
 "4160229": ("1.4 AC", ""),      # "1.4± Acres | C-2 General Commercial"
 "4003595": ("1.0 AC", ""),      # "1 acre of commercial land"
 "4104153": ("2.26 AC", ""),     # "2.26 acre lot zoned C-2"
 "4145662": ("4.5 AC", ""),      # metal building on 4.5 acres; SF field is the lot
 "4160903": ("0.76 AC", "4,000 SF"),  # "all metal building is 4,000 sq ft"
}
TYPE_HINT = [
 (r'\b(warehouse|industrial|manufactur|distribution)\b', 'Industrial'),
 (r'\b(office)\b', 'Office'),
 (r'\b(retail|storefront|restaurant|store|shopping)\b', 'Retail'),
 (r'\b(acre|acres|land|lot|tract|timber|parking lot)\b', 'Land'),
 (r'\b(apartment|multifamily|mobile home park|units)\b', 'Multifamily'),
 (r'\b(church|daycare|fitness|special)\b', 'Special Purpose'),
]

def parse_pipe(path):
    out, section = [], ''
    for line in open(path):
        line = line.rstrip('\n')
        if line.startswith('#'):
            section = line; continue
        if not line.strip(): continue
        out.append((section, line.split('|')))
    return out

dates = {}
for line in open(DATES):
    line = line.rstrip('\n')
    if line.startswith('#') or not line.strip(): continue
    d, ids = line.split('|')
    # closed-comp days are written "C2026-08-28" to keep them apart from list dates;
    # the prefix is a namespace, never part of the value (it rendered as the sale date once)
    closed = d.startswith('C')
    for i in ids.split(','):
        dates[('C' if closed else '') + i.strip()] = d.lstrip('C')

details = {}
for line in open(DETAILS):
    line = line.rstrip('\n')
    if line.startswith('#') or not line.strip(): continue
    p = line.split('|')
    details[p[0]] = (p[1] if len(p) > 1 else '', p[2] if len(p) > 2 else '', p[3] if len(p) > 3 else '')

forSale, forLease, saleComps, leaseComps = [], [], [], []
si = li = ci = 0
skipped = []

for section, p in parse_pipe(RAW):
    lid, key, ptype, status, st, addr, city, zp, price, sf, beds, photo = (p + [''] * 12)[:12]
    if st != 'MS':
        skipped.append((lid, addr, city, st, 'not Mississippi')); continue
    if ptype not in ('E', 'F'):
        skipped.append((lid, addr, city, st, 'PropertyType ' + ptype)); continue
    agent, office, desc = details.get(lid, ('', '', ''))
    d = desc.strip()
    ty = ''
    for pat, t in TYPE_HINT:
        if re.search(pat, d, re.I): ty = t; break
    lot, bsf = LAND_SF.get(lid, ('', None))
    if bsf is None:
        bsf = (f"{int(float(sf)):,} SF" if sf and float(sf) > 0 else '')
    is_land = bool(lot) and not bsf
    if is_land: ty = 'Land'
    if lid in TYPE_FIX:
        ty = TYPE_FIX[lid]
        is_land = (ty == 'Land')
    if not ty: ty = 'Commercial'
    notes = [d[:300]] if d else []
    if lid in LAND_SF:
        notes.append('MLS reports the lot area in its building-size field for this listing; '
                     'shown as land area')
    common = dict(address=addr, city=city, state='MS', zip=zp,
                  county=(COUNTY.get(city, '') + ' County') if COUNTY.get(city) else '',
                  type=ty, isLand=is_land, size=bsf, lotSize=lot,
                  contact=agent, office=office, source='mls', mlsNum=lid,
                  mlsUrl=BASE + key, mapUrl=mapurl(addr, city),
                  photoUrl=(PHOTO + photo) if photo else '')

    if 'CLOSED' in section.upper():
        ci += 1
        # MLS United's IDX feed does NOT publish a sold price. `clusters` has no
        # ClosePrice field at all, and CurrentPrice == ListPrice on closed records
        # (verified 2026-09-01 on 4141839: both 1,275,000, and the detail page shows
        # the same single figure). Putting that number in the Sale Price column would
        # assert a sold price we do not have, which is worse for a comp than a blank.
        # Leave salePrice empty and state the last list price in the notes.
        lp = f"${int(float(price)):,}" if price else ''
        saleComps.append(rec(SC_KEYS, dict(common, id=f"mc{ci}",
            saleDate=dates.get('C' + lid, '') or dates.get(lid, ''),
            salePrice='',
            notes=' · '.join(notes + [
                (f'Last list price {lp} - MLS United does not publish sold prices in its IDX feed, '
                 'so this is NOT the sale price' if lp else
                 'MLS United does not publish sold prices in its IDX feed'),
                'Closed sale reported by MLS United']))))
        continue

    pending = 'PENDING' in section.upper()
    listDate = dates.get(lid, '')
    base = dict(common, flags=('Under Contract' if pending else ''),
                listDate=('' if pending else listDate),
                domLabel=('Under Contract' if pending else ('' if listDate else 'N/A')))
    if pending:
        notes.append('Under contract - went pending between Aug 24 and Aug 31; not available')
    if ptype == 'E':
        si += 1
        forSale.append(rec(FS_KEYS, dict(base, id=f"ms{si}",
            price=(f"${int(float(price)):,}" if price else ''),
            notes=' · '.join(notes))))
    else:
        li += 1
        forLease.append(rec(FL_KEYS, dict(base, id=f"mls{li}",
            askingRate=(f"{int(float(price)):,}" if price else ''),
            leaseType='monthly rate',
            notes=' · '.join(notes + ['Rate is the monthly asking rent as published by MLS United']))))

json.dump(dict(forSale=forSale, forLease=forLease, saleComps=saleComps, leaseComps=leaseComps),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('forSale', len(forSale), 'forLease', len(forLease), 'saleComps', len(saleComps))
print('skipped:', skipped)
print('missing listDate:', [r['mlsNum'] for r in forSale + forLease if not r['listDate'] and r['domLabel'] != 'Under Contract'])
print('missing photo:', [r['mlsNum'] for r in forSale + forLease + saleComps if not r['photoUrl']])
