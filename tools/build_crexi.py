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

# Positional: sale_raw out [lease_raw]. Options: --page FILE, --lease-page FILE, --date YYYY-MM-DD
_args, _opts, _k = [], {}, None
for _a in sys.argv[1:]:
    if _k: _opts[_k] = _a; _k = None
    elif _a.startswith('--'): _k = _a[2:]
    else: _args.append(_a)
SALE_IN, OUT = _args[0], _args[1]
LEASE_IN = _args[2] if len(_args) > 2 else None
# The date the days-on-market figures were READ off the property pages. It was a hardcoded
# constant (2026-09-22) -- the same forgotten-constant trap parse_costar's footer date fixed.
if 'date' in _opts:
    EXPORT_DATE = datetime.date.fromisoformat(_opts['date'])
else:
    EXPORT_DATE = datetime.date.today()
    print('WARNING: --date not given; days on market read as of', EXPORT_DATE.isoformat())
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
 "Hazlehurst":"Copiah","Madison":"Madison","Magee":"Simpson","Magnolia":"Pike",
 # added 2026-09-29
 "Pearl":"Rankin","Brandon":"Rankin","Flowood":"Rankin","Richland":"Rankin","Florence":"Rankin",
 "Ripley":"Tippah","Walnut":"Tippah","Greenville":"Washington","Leland":"Washington",
 "Brookhaven":"Lincoln","Vancleave":"Jackson","Pascagoula":"Jackson","Gautier":"Jackson",
 "Moss Point":"Jackson","Ocean Springs":"Jackson","Southaven":"DeSoto","Hernando":"DeSoto",
 "Horn Lake":"DeSoto","Canton":"Madison","Shannon":"Lee","Prentiss":"Jefferson Davis",
 "Picayune":"Pearl River","Carriere":"Pearl River","Lexington":"Holmes","Grenada":"Grenada",
 "Bay Saint Louis":"Hancock","Waveland":"Hancock","Columbus":"Lowndes","Byram":"Hinds"}

TYPES = ["Retail","Office","Industrial","Land","Multifamily","Mixed Use","Hospitality","Flex","Special Purpose",
         "Self Storage","Mobile Home Park","Senior Living"]

# assetId -> (type, sub type, building SF, lease type). Crexi's RESULT CARD often carries
# no property type at all -- 11 of 44 on 2026-09-22 came through untyped, because the card
# text is just the address. The property PAGE always has it, under "Property Type" (sale)
# or "Building Details / Property Type" (lease). Read it there and record it here rather
# than inferring a type from a marketing name.
PAGE_FIX = {
 "2681064": ("Retail", "QSR/Fast Food", "", ""),
 "2681055": ("Industrial", "Warehouse", "", ""),
 "2681068": ("Office", "Medical Office, Traditional Office", "", ""),
 "2681075": ("Land", "", "", ""),
 "2681066": ("Office", "Traditional Office", "5,032", ""),
 "2711678": ("Office", "Special Purpose", "", ""),
 "1155782": ("Office", "Traditional Office, Executive Office", "1,120", "Full Service"),
 "1245660": ("Office", "Traditional Office, Medical Office", "9,326", "NNN"),
 "1245662": ("Industrial", "Warehouse", "5,455", "NNN"),
 "1245670": ("Industrial", "Warehouse", "4,800", "NNN"),
 "1245676": ("Retail", "", "100,861", "NNN"),
}

# Per-property facts read off each Crexi PROPERTY PAGE in the same pull (see
# tools/browser_pulls.md): id|type|subtype|SF|acres|zoning|agent|firm (sale) and
# id|type|subtype|buildingSF|leaseType|agent|firm|rate|desc (lease). The result card alone
# is not enough -- 11 of 44 cards were untyped on 2026-09-22.
def _strip_initials(name):
    """Crexi renders a broker with no headshot as an initials avatar, and the page text reads
    "SC Scott Cote", "CM Charles McGee". Drop the avatar when it is exactly the initials."""
    m = re.match(r'^([A-Z]{2,3}) (.+)$', name or '')
    if m and ''.join(w[0] for w in m.group(2).split()[:len(m.group(1))]).upper() == m.group(1):
        return m.group(2)
    return name

def _load_page(path, kind):
    out = {}
    if not path: return out
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'): continue
        p = (line.split('|') + [''] * 9)[:9]
        if kind == 'sale':
            aid, ty, sub, sf, ac, zon, ag, firm = p[:8]; lt = ''
        else:
            aid, ty, sub, sf, lt, ag, firm = p[:7]; ac = zon = ''
        ty = re.sub(r'\s+Class\s+[A-D]\b', '', ty)
        sub = re.sub(r'\s*\(\+\d+\)', '', sub).strip()
        first = re.sub(r'\s*\(\+\d+\)', '', ty).split(',')[0].strip()
        out[aid] = dict(type=first, types=re.sub(r'\s*\(\+\d+\)', '', ty).strip(), sub=sub,
                        sf=sf.strip(), ac=ac.strip(), zoning=zon.strip().rstrip(','),
                        agent=_strip_initials(re.sub(r'\s+\d{3}[.-]\d{3}[.-]\d{4}$', '', ag.strip())),
                        firm=firm.strip(), lease_type=lt.strip())
    return out
PAGE = _load_page(_opts.get('page'), 'sale')
PAGE.update(_load_page(_opts.get('lease-page'), 'lease'))

# Standing rule: no residential in any array. Crexi is not commercial-only; every drop is
# recorded by asset id with the words that decided it.
DROP = {
 "2715046": "217 Rogers Cir, Brookhaven - 'Single Family Rental Portfolio', eight rental houses",
 "2715215": "Belmont Estates Dr, Gautier - '99 lots on 45 acres ... approved platted lots', zoned Single Family",
 "2715214": "Lickskillet Rd, Biloxi - 'The perfect setting for a beautiful subdivision'",
 "2720669": "N Livingston Rd & Hwy 463, Madison - '81 acres of residential development land', zoned REA low density",
 "2720999": "1 Hillcrest Farm Rd, Carriere - '10 contiguous lots ... build a private estate or build multiple homes'",
 "2721548": "Barnes Rd, Florence (23 AC) - lakefront tract split from a larger parcel, 'a stunning homesite'",
 "2721572": "Barnes Rd, Florence (10.2 AC) - lakefront tract split from a larger parcel, 'a stunning homesite'",
}
# Address corrections, by asset id, with the evidence.
ADDR_FIX = {
 "1263167": ("8930 Lorraine Road, Lot B", "Crexi publishes the street as \"8930 Lorraine Road Lot: B B\""),
 "2720583": ("US Highway 49 (7.1 AC tract)", "Crexi publishes the street as \"7.1 Acres U S Highway 49\""),
 "2720582": ("US Highway 49 & Old Pearson Rd", "Crexi publishes the street as \"U S Highway 49\"; the listing "
             "places the 2.87 acres at U.S. Highway 49 and Old Pearson Rd"),
 "2720712": ("717 Highway 80 E", "Crexi files this at 717 US 80, Jackson, MS 39110, but the listing places it on "
             "Hwy 80 between Sutherland and the outlet mall entrance, which is Pearl; Crexi listed 717 Highway 80 E, "
             "Pearl for lease in the September 23 report", "Pearl", "39208"),
 "2716460": ("Larue Rd", "Crexi files this 18-acre parcel (APN 0-34-25-010.050) at 16701 Larue Road, the "
             "address of the adjoining 36.6-acre tract (APN 0-34-25-010.075, listed separately); shown "
             "as Larue Rd, as Moody's publishes it"),
}
NOTE = {
 "2712632": "Business-only sale of two Denny's franchise restaurants; the real estate is not included "
            "and Crexi does not disclose the locations",
 "2716147": "Crexi publishes the acreage as 77,340, which is the lot in square feet (1.78 AC)",
 "2721715": "The listing describes a 4.63\u00b1 acre mixed-use (MX) development site",
 "1261133": "Crexi shows the rate as undisclosed, but the listing text reads \"$5,750 per month on a "
            "full-service basis\" for the \u00b12,300 SF upstairs suite",
}
LOT_FIX = {"2721715": "4.63 AC"}

# Hattiesburg ZIP 39402 straddles Forrest and Lamar counties, so the city map guesses wrong
# for west Hattiesburg: 6051 US-98 (Oak Leaf Plaza, beside Turtle Creek Mall) and 3239 Oak
# Grove went out as Forrest County on 2026-09-29. Every CoStar/Moody's record on US-98 or Oak
# Grove Rd in 39402 since July says Lamar. In a split ZIP, no guess: an id-level fix or blank.
SPLIT_ZIPS = {("Hattiesburg", "39402")}
COUNTY_FIX = {
 "2696375": "Lamar",     # 6051 US-98 -- CoStar/Moody's: 6341, 6504, 6690, 7127 US-98 are Lamar
 "2721715": "Lamar",     # 3239 Oak Grove -- CoStar: 2006 and 2008 Oak Grove Rd are Lamar
 "2715151": "Forrest",   # 10 Gateway Dr -- CoStar, Sep 23 report
 "2715093": "Forrest",   # 48 Rawls Springs Loop Rd -- CoStar, Sep 23 report
 "1258580": "Forrest",   # same property, lease listing
}
def _county(aid, city, zp):
    if aid in COUNTY_FIX: return COUNTY_FIX[aid] + ' County'
    if (city, zp) in SPLIT_ZIPS: return ''
    return (COUNTY.get(city, '') + ' County') if COUNTY.get(city) else ''

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
        if aid in DROP:
            DROPPED.append('%s: %s' % (aid, DROP[aid])); continue
        pg = PAGE.get(aid, {})
        # The card's spec text repeats the street and the "street, City, MS zip" line when a
        # listing has no marketing name ("0 Ellis Avenue 0 Ellis Avenue, Jackson, MS 39209").
        _spec = spec
        for junk in (addr + ', ' + city + ', MS ' + zp, addr + ', ' + city + ', MS, ' + zp):
            _spec = _spec.replace(junk, ' ')
        _spec = re.sub(r'\b' + re.escape(addr) + r'\b', ' ', _spec) if addr and len(addr) > 6 else _spec
        spec = re.sub(r'\s+', ' ', _spec).strip(' ,|')
        extra_notes = []
        if aid in ADDR_FIX:
            _fx = ADDR_FIX[aid]
            addr, why = _fx[0], _fx[1]; extra_notes.append(why)
            if len(_fx) > 2: city, zp = _fx[2], _fx[3]      # the city/zip Crexi published was wrong too
        if aid in NOTE: extra_notes.append(NOTE[aid])
        if kind == 'sale' and photo and not photo.startswith(('assets/', 'lease-assets/')):
            photo = 'assets/' + photo
        i += 1
        ld = ''
        if dom.strip().isdigit():
            ld = (EXPORT_DATE - datetime.timedelta(days=int(dom))).isoformat()
        ty = classify(spec)
        fix = PAGE_FIX.get(aid)
        if fix and fix[0]: ty = fix[0]
        if pg.get('type'): ty = pg['type']
        m = re.search(r'([\d,]+)\s*(?:SqFt|SF)\b', spec)
        size = (m.group(1) + ' SF') if m else ''
        m = re.search(r'([\d.]+)\s*(?:acres|AC)\b', spec, re.I)
        lot = (m.group(1) + ' AC') if m else ''
        # On a LAND listing Crexi's square footage is the PARCEL, not a building.
        # Cold Spgs Rd, Moss Point published "Land,Mixed Use,Special Purpose | 887,460 SF"
        # on 2026-09-15 and it landed in `size`, so the card claimed an 887,460 SF
        # building on a bare tract. Move it to lotSize, in acres.
        if ty == 'Land' and size and not lot:
            _sf = float(size.replace(',', '').replace(' SF', ''))
            lot = ('%.2f AC' % (_sf / 43560)) if _sf > 5000 else ''
            size = ''
        elif ty == 'Land' and size and lot:
            size = ''
        # numeric only: the dashboard appends the % sign
        m = re.search(r'([\d.]+)\s*%\s*CAP', spec, re.I)
        cap = m.group(1) if m else ''
        m = re.search(r'(\d+)\s*Units?\b', spec, re.I)
        units = m.group(1) if m else ''
        if fix:
            if fix[2] and not size: size = fix[2] + ' SF'
        if re.match(r'0+ SF$', size or ''): size = ''     # "Office | 0 SF" (411 S State St, Clarksdale)
        if pg.get('sf') and not size and pg['sf'].replace(',', '').isdigit() and int(pg['sf'].replace(',', '')) > 0:
            size = pg['sf'] + ' SF'
        if aid in LOT_FIX and not lot: lot = LOT_FIX[aid]
        if pg.get('ac') and not lot:
            try:
                _ac = float(pg['ac'].replace(',', ''))
                if _ac > 1000: _ac = _ac / 43560      # published as SF (Comfort Suites, 77,340)
                lot = ('%.2f AC' % _ac) if _ac else ''
            except ValueError: pass
        if ty == 'Land' and size:
            # On a Land listing the page's square footage is the lot or an ancillary house
            # (5447 Hwy 80 E: a 1,840 SF 1949 residence on 9.13 AC). Keep it out of `size`,
            # and only mention it when it is NOT simply the lot restated in SF.
            _s = float(size.replace(',', '').replace(' SF', ''))
            _l = re.match(r'([\d.]+)', lot or '')
            _lsf = float(_l.group(1)) * 43560 if _l else 0
            if not (_lsf and abs(_s - _lsf) / _lsf < 0.05):
                extra_notes.append('Crexi lists %s of building area%s on this land listing'
                                   % (size, (' (built %s)' % yb) if yb else ''))
            size = ''
        if ty == 'Land' and yb:
            # The year built on a Land listing is the ancillary house's, not the offering's.
            if not any('building area' in n for n in extra_notes):
                extra_notes.append('Crexi lists a year built of %s on this land listing' % yb)
            yb = ''
        notes = [spec] if spec else []
        if pg.get('types') and ',' in pg['types']: notes.append('Crexi property types: ' + pg['types'])
        if pg.get('sub'): notes.append('Crexi sub type: ' + pg['sub'])
        elif fix and fix[1]: notes.append('Crexi sub type: ' + fix[1])
        if pg.get('lease_type'): notes.append('Lease type: ' + pg['lease_type'])
        notes.extend(extra_notes)
        if not photo:
            # Crexi serves a generic map graphic when a listing has no photo of its own;
            # that placeholder is dropped at capture time, so a blank here is a real gap.
            notes.append('No photo available on Crexi')
        if not ld:
            notes.append('Days on market not published for this listing')
        d = dict(address=addr, city=city, state='MS', zip=zp,
                 zoning=pg.get('zoning', ''), contact=pg.get('agent', ''), office=pg.get('firm', ''),
                 county=_county(aid, city, zp),
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
            flags = ''
            _pn = re.match(r'\$([\d,]+)$', price.strip())
            _sz = re.match(r'([\d,]+) SF', size or '')
            if _pn and _sz and ty != 'Land':
                _ppsf = float(_pn.group(1).replace(',', '')) / float(_sz.group(1).replace(',', ''))
                if _ppsf < 1.0:
                    # 2214-A Green St, Tupelo: "$12,500" on 50,000 SF of warehouse (2026-09-29).
                    notes.append('Crexi publishes a $%s sale price on %s, which is $%.2f/SF and reads '
                                 'as a monthly rent rather than a sale price; confirm with the listing '
                                 'broker before quoting it' % (_pn.group(1), size, _ppsf))
                    d['notes'] = ' · '.join(notes); flags = 'Check price'
            out.append(rec(keys, dict(d, id=f"cx{i}", price=('' if unpriced else price), capRate=cap,
                                      flags=flags)))
        else:
            # Crexi prints the rate with its own unit: "$9.50/SF/YR", "$1.33/SF/MO",
            # "$6-$12/SF/YR". Split the number from the unit so the renderer does not
            # relabel a monthly rate as annual.
            m = re.match(r'\$?([\d.,]+(?:\s*-\s*\$?[\d.,]+)?)\s*/?\s*SF\s*/\s*(YR|MO)', price, re.I)
            if m:
                rate = m.group(1).replace('$', '')
                unit = '$/SF/Year' if m.group(2).upper() == 'YR' else '$/SF/Month'
                # Crexi's published UNIT is wrong often enough to check the magnitude.
                # 325 Hwy 51 was "$2,300/SF/MO" on 2026-09-08 (Moody's had the same
                # suite at $2,300 a month); 5910 U.S. 49 was "$1,200/SF/YR" on a
                # 1,239 SF retail suite on 2026-09-15. Anything at or above $200/SF
                # is not a per-square-foot rate; say so rather than print it.
                _lo = re.match(r'([\d,.]+)', rate)
                if _lo and float(_lo.group(1).replace(',', '')) >= 200:
                    rate = ('$%s — Crexi publishes this as $/SF/%s, which is not a '
                            'credible per-square-foot rate; confirm the unit with the '
                            'listing broker' % (rate, m.group(2).upper()))
                    unit = ''
            else:
                rate, unit = price.lstrip('$'), ('Negotiable' if not price.strip('$ ') else '')
            if fix and fix[3] and not unit:
                unit = fix[3]
            elif fix and fix[3] and unit and fix[3] not in d['notes']:
                d['notes'] = d['notes'] + ' · Lease type: ' + fix[3]
            out.append(rec(keys, dict(d, id=f"cxl{i}", askingRate=rate, leaseType=unit)))
    return out

DROPPED = []
forSale = build(SALE_IN, FS_KEYS, 'sale')
forLease = build(LEASE_IN, FL_KEYS, 'lease') if LEASE_IN else []

# One card per property: Crexi files separate suites in one building as separate lease
# listings with the suite glued onto the street ("2318 Pass Road 7c", "2318 Pass Road 3",
# 2026-09-29). Group on the street with a trailing suite token removed; only collapse a
# group that really has more than one member.
_SUITE = re.compile(r'^(\d[\w-]*\s+.+?\b(?:Road|Rd|Street|St|Drive|Dr|Avenue|Ave|Boulevard|Blvd|Parkway|Pkwy|Highway|Hwy|Lane|Ln|Way|Plaza|Plz))\s*,?\s*(?:Suite\s+|Ste\s+|Unit\s+|#)?([A-Z0-9]{1,4})$', re.I)
def _consolidate(rows):
    groups = {}
    for r in rows:
        m = _SUITE.match(r['address'])
        base = m.group(1) if m else r['address']
        groups.setdefault((base.lower(), r['city'].lower()), []).append((r, m))
    out = []
    for (base, _c), g in groups.items():
        if len(g) == 1:
            out.append(g[0][0]); continue
        r = dict(g[0][0]); r['address'] = g[0][1].group(1) if g[0][1] else r['address']
        sizes = sorted(int(x[0]['size'].replace(',', '').replace(' SF', '')) for x in g if x[0]['size'])
        if sizes: r['size'] = ('{:,} SF'.format(sizes[0]) if sizes[0] == sizes[-1]
                               else '{:,} - {:,} SF'.format(sizes[0], sizes[-1]))
        suites = ', '.join(x[1].group(2).upper() for x in g if x[1])
        r['notes'] = r['notes'] + ' · %d suites listed separately on Crexi (%s), consolidated into one card' % (len(g), suites)
        r['crexiUrl'] = g[0][0]['crexiUrl']
        out.append(r)
    return out
forLease = _consolidate(forLease)
json.dump(dict(forSale=forSale, forLease=forLease, saleComps=[], leaseComps=[]),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('forSale', len(forSale), 'forLease', len(forLease))
print('with photo:', sum(1 for r in forSale+forLease if r['photoUrl']), '/', len(forSale)+len(forLease))
print('with listDate:', sum(1 for r in forSale+forLease if r['listDate']))
print('untyped:', [r['address'] for r in forSale+forLease if not r['type']])
print('read as of:', EXPORT_DATE.isoformat())
if DROPPED:
    print('DROPPED as residential (%d):' % len(DROPPED))
    for x in DROPPED: print('   -', x)
