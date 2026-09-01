#!/usr/bin/env python3
"""Build Crexi records from the for-sale (and, when available, for-lease) card pulls.

    python3 tools/build_crexi.py build/crexi_sale_raw.txt build/crexi.json [build/crexi_lease_raw.txt]

Input line: assetId~daysOnMarket~price~address~city~zip~spec~yearBuilt~photoPath

Crexi's "Time Period -> 7 days" filter does NOT mean newly listed (2026-08-25: it
returned a listing 139 days on market). Use **Listing timeline -> Custom** with an
explicit date range instead -- verified 2026-09-01, where every one of 48 results
came back between 2 and 8 days on market for an Aug 24-31 range. `listDate` here is
derived from each property page's own days-on-market, not from the filter.
"""
import json, re, sys, datetime

SALE_IN, OUT = sys.argv[1], sys.argv[2]
LEASE_IN = sys.argv[3] if len(sys.argv) > 3 else None
EXPORT_DATE = datetime.date(2026, 9, 1)
# Sale photos hang off /assets/, lease photos off /lease-assets/; the raw files carry
# whichever prefix the card had, so only the common part is prepended here.
IMGBASE = "https://crexi.com/images/format=auto,width=620,height=400,fit=cover/"

FS_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","price","pricePerSF",
           "pricePerUnit","capRate","size","lotSize","units","yearBuilt","zoning","tenant","contact","office",
           "phone","flags","alsoForLease","listDate","domLabel","source","mlsNum","costarUrl","moodysUrl",
           "crexiUrl","mlsUrl","mapUrl","photoUrl","notes"]
FL_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","askingRate","leaseType",
           "size","avail","lotSize","yearBuilt","zoning","tenant","contact","office","phone","availDate",
           "alsoForSale","listDate","domLabel","source","mlsNum","costarUrl","moodysUrl","crexiUrl","mlsUrl",
           "mapUrl","photoUrl","notes"]

def rec(keys,d): return {k: d.get(k, False if k=="isLand" else "") for k in keys}
def mapurl(a,c): return "https://www.google.com/maps/search/?q=" + '+'.join(re.sub(r'[^A-Za-z0-9 ]',' ',(a+' '+c+' MS')).split())

COUNTY = {"Natchez":"Adams","Hattiesburg":"Forrest","Jackson":"Hinds","Myrtle":"Union","Meridian":"Lauderdale",
 "Clarksdale":"Coahoma","Oxford":"Lafayette","Long Beach":"Harrison","Columbia":"Marion","Mccomb":"Pike",
 "Clinton":"Hinds","Saltillo":"Lee","Corinth":"Alcorn","Holcomb":"Grenada","Tupelo":"Lee","Carthage":"Leake",
 "Ridgeland":"Madison","Olive Branch":"DeSoto","Laurel":"Jones","Starkville":"Oktibbeha","Kosciusko":"Attala",
 "Gulfport":"Harrison","Forest":"Scott","Vicksburg":"Warren","Terry":"Hinds","Biloxi":"Harrison",
 "Hazlehurst":"Copiah","Madison":"Madison","Magee":"Simpson","Magnolia":"Pike"}

TYPES = ["Retail","Office","Industrial","Land","Multifamily","Mixed Use","Hospitality","Flex","Special Purpose"]

def classify(spec):
    s = spec.lower()
    for t in TYPES:
        if t.lower() in s: return t
    if 'restaurant' in s or 'storefront' in s: return 'Retail'
    if 'warehouse' in s or 'showroom' in s: return 'Industrial'
    if 'commercial' in s: return 'Commercial'
    return ''

def build(path, keys, kind, start=0):
    out, i = [], start
    for line in open(path):
        line = line.rstrip('\n')
        if not line or line.startswith('#'): continue
        p = (line.split('~') + ['']*9)[:9]
        aid, dom, price, addr, city, zp, spec, yb, photo = p
        if kind == 'sale' and photo and not photo.startswith(('assets/', 'lease-assets/')):
            photo = 'assets/' + photo
        i += 1
        ld = ''
        if dom.strip().isdigit():
            ld = (EXPORT_DATE - datetime.timedelta(days=int(dom))).isoformat()
        ty = classify(spec)
        m = re.search(r'([\d,]+)\s*(?:SqFt|SF)\b', spec)
        size = (m.group(1) + ' SF') if m else ''
        m = re.search(r'([\d.]+)\s*(?:acres|AC)\b', spec, re.I)
        lot = (m.group(1) + ' AC') if m else ''
        # numeric only: the dashboard appends the % sign
        m = re.search(r'([\d.]+)\s*%\s*CAP', spec, re.I)
        cap = m.group(1) if m else ''
        m = re.search(r'(\d+)\s*Units?\b', spec, re.I)
        units = m.group(1) if m else ''
        notes = [spec]
        if not photo:
            # Crexi serves a generic map graphic when a listing has no photo of its own;
            # that placeholder is dropped at capture time, so a blank here is a real gap.
            notes.append('No photo available on Crexi')
        if not ld:
            notes.append('Days on market not published for this listing')
        d = dict(address=addr, city=city, state='MS', zip=zp,
                 county=(COUNTY.get(city,'') + ' County') if COUNTY.get(city) else '',
                 type=ty, isLand=(ty == 'Land'), size=size, lotSize=lot, units=units,
                 yearBuilt=yb, listDate=ld, domLabel=('' if ld else 'N/A'), source='crexi',
                 crexiUrl=('https://www.crexi.com/lease/properties/' + aid) if kind == 'lease'
                          else ('https://www.crexi.com/properties/' + aid),
                 mapUrl=mapurl(addr, city),
                 photoUrl=(IMGBASE + photo) if photo else '',
                 notes=' · '.join(notes))
        if kind == 'sale':
            unpriced = price.lower().startswith('unpriced') or 'bid' in price.lower()
            if unpriced:
                notes.append('Price not published on Crexi' if 'bid' not in price.lower()
                             else 'Offered at auction - starting bid not published')
                d['notes'] = ' · '.join(notes)
            out.append(rec(keys, dict(d, id=f"cx{i}", price=('' if unpriced else price), capRate=cap)))
        else:
            # Crexi prints the rate with its own unit: "$9.50/SF/YR", "$1.33/SF/MO",
            # "$6-$12/SF/YR". Split the number from the unit so the renderer does not
            # relabel a monthly rate as annual.
            m = re.match(r'\$?([\d.,]+(?:\s*-\s*\$?[\d.,]+)?)\s*/?\s*SF\s*/\s*(YR|MO)', price, re.I)
            if m:
                rate = m.group(1).replace('$', '')
                unit = '$/SF/Year' if m.group(2).upper() == 'YR' else '$/SF/Month'
            else:
                rate, unit = price.lstrip('$'), ('Negotiable' if not price.strip('$ ') else '')
            out.append(rec(keys, dict(d, id=f"cxl{i}", askingRate=rate, leaseType=unit)))
    return out

forSale = build(SALE_IN, FS_KEYS, 'sale')
forLease = build(LEASE_IN, FL_KEYS, 'lease') if LEASE_IN else []
json.dump(dict(forSale=forSale, forLease=forLease, saleComps=[], leaseComps=[]),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('forSale', len(forSale), 'forLease', len(forLease))
print('with photo:', sum(1 for r in forSale+forLease if r['photoUrl']), '/', len(forSale)+len(forLease))
print('with listDate:', sum(1 for r in forSale+forLease if r['listDate']))
print('untyped:', [r['address'] for r in forSale+forLease if not r['type']])
