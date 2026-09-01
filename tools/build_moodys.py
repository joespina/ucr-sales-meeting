#!/usr/bin/env python3
"""Build Moody's CRE records from the PDF export plus the live property-id/photo map.

    python3 tools/build_moodys.py build/moodys_pdf.json build/moodys_map.txt build/moodys.json

The PDF export carries the rich per-listing fields; the live pull (see
tools/browser_pulls.md) supplies the property id -- needed for `moodysUrl` -- and the
photo, neither of which appears in the PDF. The map is pipe-delimited:

    idx|dashed-property-id|listingId[/listingId...]|address, city|photo-path

Multiple listed spaces at one property are consolidated into a single card with a
size and rate range, per the standing "one card per property" rule.
"""
import json, re, sys, datetime

PDF_IN, MAP_IN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
CDN = "https://img-resized-cache.catylist.com/l1/OG"
# Properties whose Moody's photo page genuinely shows "Photos (0)" -- verified
# 2026-09-01, not a skipped capture step.
NO_PHOTO_NOTE = "No photo available in Moody's"

FS_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","price","pricePerSF",
           "pricePerUnit","capRate","size","lotSize","units","yearBuilt","zoning","tenant","contact","office",
           "phone","flags","alsoForLease","listDate","domLabel","source","mlsNum","costarUrl","moodysUrl",
           "crexiUrl","mlsUrl","mapUrl","photoUrl","notes"]
FL_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","askingRate","leaseType",
           "size","avail","lotSize","yearBuilt","zoning","tenant","contact","office","phone","availDate",
           "alsoForSale","listDate","domLabel","source","mlsNum","costarUrl","moodysUrl","crexiUrl","mlsUrl",
           "mapUrl","photoUrl","notes"]

def rec(keys, d): return {k: d.get(k, False if k == "isLand" else "") for k in keys}
def norm(x): return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 ]','',str(x or '').lower())).strip()
def mapurl(a,c): return "https://www.google.com/maps/search/?q=" + '+'.join(re.sub(r'[^A-Za-z0-9 ]',' ',(a+' '+c+' MS')).split())

def clean_addr(a, city, zp):
    """Moody's sometimes stores the whole postal line as the street, in caps
    ("716 VETERANS MEMORIAL DR KOSCIUSKO MS 39090"). Strip the repeated city/state/
    zip and title-case it, or it never dedupes against the same property elsewhere."""
    if not a: return a
    a = re.sub(r'[\s,]+MS\s*\d{5}\s*$', '', a.strip(), flags=re.I)
    if city:
        a = re.sub(r'[\s,]+' + re.escape(city) + r'\s*$', '', a, flags=re.I)
    if a.isupper():
        a = ' '.join(w.capitalize() if not re.match(r'^(?:[NSEW]{1,2}|US|MS|I)\d*$', w) else w
                     for w in a.split())
    return a.strip(' ,')

def iso(d):
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', d or '')
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else ''

def sf(v):
    m = re.match(r'([\d,]+)\s*SF', v or '')
    return m.group(1) + ' SF' if m else (v or '')

def acres(v):
    m = re.match(r'([\d.,]+)\s*Acres?', v or '')
    return m.group(1) + ' AC' if m else ''

# --- the property-id / photo map -------------------------------------------------
pid, photo = {}, {}
for line in open(MAP_IN):
    line = line.rstrip('\n')
    if not line or line.startswith('#'): continue
    p = line.split('|')
    ident, img = p[1].replace('-', ''), p[4] if len(p) > 4 else ''
    for lid in p[2].split('/'):
        pid[lid] = ident
        photo[lid] = (CDN + img) if img else ''

rows = json.load(open(PDF_IN))

TYPE = {'Office':'Office','Retail':'Retail','Industrial':'Industrial','Land':'Land',
        'Multifamily':'Multifamily','Multi-Family':'Multifamily','Multi Family':'Multifamily',
        'Flex':'Flex','Hospitality':'Hospitality','Health Care':'Special Purpose',
        'Sports & Entertainment':'Special Purpose','Special Purpose':'Special Purpose',
        'Mixed Use':'Mixed Use','Vacant Land':'Land'}

COMPANY = re.compile(r'(LLC|L\.L\.C|Inc\b|Group|Properties|Realty|Associates|Company|Partners|'
                     r'Advisors|Commercial|Real Estate|Brokerage|CRE|Bank|& Co|Holdings|Team)', re.I)
PERSON  = re.compile(r"^[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'&-]+){1,3}(?:,\s*(?:CCIM|SIOR|MAI|CPM))?$")

def contact_of(r):
    """Moody's prints the brokerage on the "Contact" header line (right column) and
    the agent's name, phone and email on the lines below. Take the company from the
    header when it is there, and the first line that looks like a person's name --
    never letting a company name land in `contact`."""
    office = name = ''
    for parts in r.get('contacts', []):
        for p in parts:
            p = p.strip()
            if not p: continue
            if p.startswith('Contact'):
                continue
            if '@' in p or re.match(r'^[\d()+-][\d ()+-]{6,}$', p):
                continue
            if COMPANY.search(p):
                if not office: office = p
                continue
            if PERSON.match(p) and not name:
                name = p
    # the header line itself: "Contact<spaces><Brokerage>"
    for parts in r.get('contacts', []):
        for p in parts:
            if p.strip().startswith('Contact') and len(p.strip()) > 9 and not office:
                office = p.strip()[7:].strip()
    return name, office

groups = {}
for r in rows:
    addr = clean_addr(r['address'], r['city'], r['zip']) or r['marketing']
    key = (r['deal'] or 'Lease', norm(addr), norm(r['city']))
    groups.setdefault(key, []).append(r)

forSale, forLease = [], []
si = li = 0
for (deal, _a, _c), g in groups.items():
    r0 = g[0]
    kv = r0['kv']
    addr = clean_addr(r0['address'], r0['city'], r0['zip']) or r0['marketing']
    lids = [x['listingId'] for x in g]
    ident = next((pid[l] for l in lids if l in pid), '')
    img = next((photo[l] for l in lids if photo.get(l)), '')
    ptype = TYPE.get(kv.get('Property Type', ''), kv.get('Property Type', ''))
    if not ptype:
        # Land listings carry no "Property Type" row; the page header does ("Land For Sale").
        h = re.sub(r'\s+(?:For (?:Sale|Lease)|Sublease)$', '', r0.get('header', '')).strip()
        ptype = TYPE.get(h, h)
    is_land = ptype == 'Land'
    dates = sorted(iso(x['kv'].get('Date Listed', '')) for x in g if iso(x['kv'].get('Date Listed', '')))
    listDate = dates[-1] if dates else ''

    notes = []
    if len(g) > 1:
        notes.append(f"{len(g)} listings at this property on Moody's, consolidated")
    if not r0['address']:
        notes.append('Street address not published on Moody\'s; shown by listing name')
    if r0.get('subtypeLabel'): notes.append(r0['subtypeLabel'])
    for k, lab in (('Occupancy Type', ''), ('Building Status', 'Building status'),
                   ('Number of Buildings', 'Buildings'), ('Floors', 'Floors'),
                   ('Parking Spaces', 'Parking'), ('In Opportunity Zone', 'Opportunity zone'),
                   ('Parcels', 'Parcel'), ('Legal Owner', 'Owner'), ('Possession', 'Possession')):
        if kv.get(k): notes.append((lab + ': ' + kv[k]) if lab else kv[k])
    if r0.get('desc') and 'contact the agent' not in r0['desc'].lower():
        notes.append(re.sub(r'\s+', ' ', r0['desc'])[:300])
    if not img: notes.append(NO_PHOTO_NOTE)
    contact, office = contact_of(r0)

    common = dict(address=addr, city=r0['city'], state='MS', zip=r0['zip'],
                  county=(kv.get('County', '') + ' County') if kv.get('County') else '',
                  type=ptype, isLand=is_land, marketingName=(r0['marketing'] if r0['address'] else ''),
                  size=sf(kv.get('Building Size', '')), lotSize=acres(kv.get('Land Size', '')),
                  yearBuilt=(kv.get('Year Built') or kv.get('Year Built/Renovated') or '').split('/')[0],
                  zoning=kv.get('Zoning', ''), contact=contact, office=office,
                  listDate=listDate, domLabel=('' if listDate else 'N/A'), source='moodys',
                  moodysUrl=('https://members.moodyscre.com/property/' + ident) if ident else '',
                  mapUrl=mapurl(addr, r0['city']), photoUrl=img)

    if deal == 'Sale':
        si += 1
        price = kv.get('Asking Price', '')
        if price.lower() == 'negotiable':
            price, extra = '', 'Asking price negotiable - call for pricing'
            notes.insert(0, extra)
        forSale.append(rec(FS_KEYS, dict(common, id=f"md{si}", price=price,
            pricePerSF=(kv.get('Listing Price Per SF', '') or '').lstrip('$'),
            capRate=(re.match(r'([\d.]+)', kv.get('Cap Rate (Actual)', '') or '').group(1)
                     if re.match(r'([\d.]+)', kv.get('Cap Rate (Actual)', '') or '') else ''),
            notes=' · '.join(x for x in notes if x))))
    else:
        li += 1
        rates = [x['kv'].get('Asking Rate', '') for x in g if x['kv'].get('Asking Rate')]
        rate, ltype = '', ''
        ann = [re.match(r'\$([\d.,]+)\s*Annual/SF', x) for x in rates]
        ann = [m.group(1) for m in ann if m]
        mon = [re.match(r'\$([\d,]+)\s*Monthly', x) for x in rates]
        mon = [m.group(1) for m in mon if m]
        if ann:
            rate = ann[0] if len(set(ann)) == 1 else f"{min(ann, key=lambda v: float(v.replace(',','')))} - {max(ann, key=lambda v: float(v.replace(',','')))}"
            ltype = '$/SF/Year'
        elif mon:
            rate = mon[0] if len(set(mon)) == 1 else f"{min(mon, key=lambda v: float(v.replace(',','')))} - {max(mon, key=lambda v: float(v.replace(',','')))}"
            ltype = 'monthly rate'
        elif rates and any('egotiable' in x for x in rates):
            ltype = 'Negotiable'
        if not rate and ltype != 'Negotiable':
            notes.insert(0, "Asking rate not published on Moody's")
        lt = kv.get('Lease Type', '')
        if lt and ltype in ('$/SF/Year', 'monthly rate'):
            notes.append('Lease type: ' + lt)
        avail = [sf(x['kv'].get('Total Available Space', '')) or x['kv'].get('Total Available Space', '') for x in g]
        avail = [a for a in avail if a]
        suites = [x['kv'].get('Suite', '') for x in g if x['kv'].get('Suite')]
        suites = [x for x in suites if x.strip()]
        if suites: notes.append('Suite(s): ' + ', '.join(suites))
        forLease.append(rec(FL_KEYS, dict(common, id=f"ml{li}", askingRate=rate,
            leaseType=(ltype or lt or ''), avail=' / '.join(dict.fromkeys(avail)),
            availDate=iso(kv.get('Available Date', '')),
            notes=' · '.join(x for x in notes if x))))

json.dump(dict(forSale=forSale, forLease=forLease, saleComps=[], leaseComps=[]),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('forSale', len(forSale), 'forLease', len(forLease))
print('with photo:', sum(1 for r in forSale + forLease if r['photoUrl']), '/', len(forSale) + len(forLease))
print('with moodysUrl:', sum(1 for r in forSale + forLease if r['moodysUrl']))
print('with price/rate:', sum(1 for r in forSale if r['price']), '/', len(forSale), '|',
      sum(1 for r in forLease if r['askingRate']), '/', len(forLease))
