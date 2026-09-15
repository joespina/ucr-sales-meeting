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
MEETING = datetime.date(2026, 9, 16)
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

LC_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","tenant","size",
           "totalSize","signDate","leaseType","term","commenceDate","executionDate","landlord","broker","office",
           "askingRate","yearBuilt","submarket","mlsNum","source","costarUrl","mlsUrl","mapUrl","photoUrl","notes"]

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
 "3186146": "Industrial",   # mini storage + boat storage facility, not a bare parcel
 "4161239": "Mixed Use",    # "waterfront mixed-use commercial & residential", 3-story
 "4157886": "Multifamily",  # The Retreat Apartments, 100% occupied investment sale
 "4145662": "Industrial",   # a metal building on 4.5 acres, not a bare parcel
 "4104371": "Commercial",   # "multi use building, gutted and ready for build-out"
 "4152716": "Land",         # commercial parking lot
 "4139275": "Multifamily",  # mobile home park investment
 "4162227": "Mixed Use",    # "8.2 ACRE MIXED-USE ... with C-2 COMMERCIAL FRONTAGE"
 "4161935": "Special Purpose",  # church campus, multiple buildings
 "4162047": "Land",         # 4.18-5.64 AC development tract, Highland Colony corridor
}
LAND_SF = {
 "4144121": ("4.8 AC", ""),      # "Estimated 4.8 acres of commercial land" - 209,305 SF is the LOT
 "3186146": ("2.4 AC", ""),      # "Approx. 2.4 acres on busy Lemoyne Blvd" - 104,544 SF is the LOT
 "4160779": ("1.6 AC", ""),      # "1.6 ACRES ON HWY 51 NORTH"
 "4160229": ("1.4 AC", ""),      # "1.4± Acres | C-2 General Commercial"
 "4003595": ("1.0 AC", ""),      # "1 acre of commercial land"
 "4104153": ("2.26 AC", ""),     # "2.26 acre lot zoned C-2"
 "4145662": ("4.5 AC", ""),      # metal building on 4.5 acres; SF field is the lot
 "4160903": ("0.76 AC", "4,000 SF"),  # "all metal building is 4,000 sq ft"
 # 2026-09-16 week. FlexMLS put the LOT in BuildingAreaTotal on each of these --
 # the sub-100 values are plainly acres, the zeroes are bare land.
 "4162118": ("2.86 AC", ""),     # "2.86 acre tract on Old Whitfield Road"
 "4162130": ("0.53 AC", ""),     # "0.53 acre C-2 commercial lot on Forest Avenue"
 "4162122": ("0.82 AC", ""),     # "This 0.82 Acre lot is flat, cleared"
 "4162123": ("0.82 AC", ""),     # "This 0.82 Acre lot is flat, cleared"
 "4162097": ("1.36 AC", ""),     # "This 1.36 Acre lot is flat, cleared"
 "4162069": ("0.95 AC", ""),     # "Commercial Lot .95 acres"
 "4161760": ("2.60 AC", ""),     # "Prime 2.60-Acre Commercial Corner Lot"
 "4150284": ("", ""),            # "Recently cleared and ready for development"
 "4162047": ("5.64 AC", ""),     # 245,678 SF is the lot; see the note on this record
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
    lid, key, ptype, status, st, addr, city, zp, price, sf, beds, photo, listprice = (p + [''] * 13)[:13]
    if st != 'MS':
        skipped.append((lid, addr, city, st, 'not Mississippi')); continue
    if ptype not in ('E', 'F'):
        skipped.append((lid, addr, city, st, 'PropertyType ' + ptype)); continue
    agent, office, desc = details.get(lid, ('', '', ''))
    d = desc.strip()
    ty = ''
    # The Land hint matches the bare word "lot", which appears in plenty of
    # descriptions of BUILDINGS ("on a corner lot", "on a .52 acre lot"). Four
    # records with real building sizes were typed Land on 2026-09-15 this way.
    # A record that reports a building size is not land, whatever the prose says.
    _has_bldg = bool(sf) and float(sf or 0) > 100
    for pat, t in TYPE_HINT:
        if t == 'Land' and _has_bldg: continue
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
                  photoUrl=(photo if photo.startswith('http') else (PHOTO + photo)) if photo else '')

    if 'CLOSED' in section.upper():
        # CurrentPrice IS the sale price on a closed MLS record. Established
        # 2026-09-08 by elimination: CurrentPrice diverges from ListPrice ONLY
        # after a listing closes -- 0 of 75 actives listed over three months
        # differ, 0 of 5 pendings differ, and 9 of 13 closed do. MLS United's own
        # IDX detail page renders that figure as the headline price on a Closed
        # listing (4152925: list 299,900, CurrentPrice 263,000, page shows
        # $263,000). This REVERSES the 2026-09-01 conclusion, which was drawn
        # from a single record where the two happened to be equal.
        sp = f"${int(float(price)):,}" if price else ''
        lp = f"${int(float(listprice)):,}" if listprice else ''
        sold_at_ask = (price and listprice and float(price) == float(listprice))
        pnote = []
        if sp and lp and not sold_at_ask:
            pnote.append(f'Closed at {sp} against a {lp} list price')
        elif sp and sold_at_ask:
            pnote.append(f'Closed at the {sp} asking price')
        elif sp:
            pnote.append(f'Closed at {sp}')
        else:
            pnote.append('Sale price not published by MLS United')
        psf = ''
        if price and sf and float(sf) > 0 and lid not in LAND_SF:
            psf = f"{float(price)/float(sf):.2f}"
        cdate = dates.get('C' + lid, '') or dates.get(lid, '')
        if ptype == 'F':
            ci += 1
            leaseComps.append(rec(LC_KEYS, dict(common, id=f"mlc{ci}",
                signDate=cdate, askingRate=(f"{int(float(price)):,}" if price else ''),
                leaseType='monthly rate', broker=agent,
                notes=' \u00b7 '.join(notes + [
                    'Lease closed/completed as reported by MLS United',
                    'Rate is the monthly rent at close as published by MLS United']))))
        else:
            ci += 1
            saleComps.append(rec(SC_KEYS, dict(common, id=f"mc{ci}",
                saleDate=cdate, salePrice=sp, pricePerSF=psf,
                notes=' \u00b7 '.join(notes + pnote + ['Closed sale reported by MLS United']))))
        continue

    pending = 'PENDING' in section.upper()
    listDate = dates.get(lid, '')
    base = dict(common, flags=('Under Contract' if pending else ''),
                listDate=('' if pending else listDate),
                domLabel=('Under Contract' if pending else ('' if listDate else 'N/A')))
    if pending:
        notes.append('Under contract - went pending between Aug 31 and Sep 7; not available')
    if ptype == 'E':
        si += 1
        forSale.append(rec(FS_KEYS, dict(base, id=f"ms{si}",
            price=(f"${int(float(price)):,}" if price else ''),
            notes=' · '.join(notes))))
    else:
        li += 1
        # MLS United publishes one lease figure with no unit attached. It is USUALLY the
        # monthly total, but agents also enter an annual $/SF rate in the same field --
        # 4161218 came through as 25 on a 4,300 SF medical suite (2026-09-08), which is
        # not a credible monthly rent and reads as $25/SF/yr. Rather than pick a unit we
        # cannot confirm, say so on the card: never state a rate we have not verified.
        # A non-numeric askingRate is passed through verbatim by rateText() in index.html.
        amb = bool(price) and float(price) < 100
        if amb:
            rate = f"{float(price):g} — unit not stated by MLS"
            ltype = ''
            rnote = (f'MLS United published this rate as "{float(price):g}" with no unit attached. '
                     'That is too low to be a monthly total for a space this size, so it most '
                     f'likely means ${float(price):g}/SF/year — confirm with the listing agent '
                     'before quoting it.')
        else:
            rate = f"{int(float(price)):,}" if price else ''
            ltype = 'monthly rate'
            rnote = 'Rate is the monthly asking rent as published by MLS United'
        forLease.append(rec(FL_KEYS, dict(base, id=f"mls{li}",
            askingRate=rate, leaseType=ltype,
            notes=' · '.join(notes + [rnote]))))

# ---- consolidate multiple suites at one address into one card -------------------
# Standing rule: one card per property. MLS lists each suite separately -- 168 Cowart
# Street came through as suites 6, 8 and 10 on 2026-09-08, three near-identical rows.
# Group on the address with its trailing suite token stripped; only collapse when a
# group actually has more than one member, so a lone ", Suite B" keeps its label.
def suite_base(addr):
    return re.sub(r',\s*(suite\s+)?[\w-]+\s*$', '', addr, flags=re.I).strip()

def consolidate(rows, rate_key):
    groups = {}
    for r in rows:
        groups.setdefault((suite_base(r['address']).lower(), r['city'].lower()), []).append(r)
    out = []
    for g in groups.values():
        if len(g) == 1:
            out.append(g[0]); continue
        r = dict(g[0])
        r['address'] = suite_base(g[0]['address'])
        def span(vals, fmt):
            n = sorted({int(re.sub(r'[^0-9]', '', v)) for v in vals if re.search(r'\d', v)})
            if not n: return ''
            return fmt.format(n[0]) if len(n) == 1 else (fmt.format(n[0]) + ' - ' + fmt.format(n[-1]))
        r['size'] = span([x['size'] for x in g], '{:,} SF')
        r[rate_key] = span([x[rate_key] for x in g], '{:,}')
        suites = ', '.join(x['address'].split(',')[-1].strip() for x in g if ',' in x['address'])
        r['notes'] = ' \u00b7 '.join([x for x in [g[0]['notes'],
            f'{len(g)} suites listed separately on MLS United at this address ({suites}), '
            'consolidated into one card',
            'MLS#s ' + ', '.join(x['mlsNum'] for x in g)] if x])
        out.append(r)
    return out

forLease = consolidate(forLease, 'askingRate')

json.dump(dict(forSale=forSale, forLease=forLease, saleComps=saleComps, leaseComps=leaseComps),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('forSale', len(forSale), 'forLease', len(forLease), 'saleComps', len(saleComps), 'leaseComps', len(leaseComps))
print('skipped:', skipped)
print('missing listDate:', [r['mlsNum'] for r in forSale + forLease if not r['listDate'] and r['domLabel'] != 'Under Contract'])
print('missing photo:', [r['mlsNum'] for r in forSale + forLease + saleComps if not r['photoUrl']])
