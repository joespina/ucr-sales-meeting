#!/usr/bin/env python3
"""Build CoStar records from parsed For Sale / For Lease exports.

    python3 tools/build_costar.py build/sale.json build/lease.json build/costar.json

Comps come from the two small CoStar comps PDFs and are short enough to hand-enter
straight into the records file -- see WEEKLY.md.

CHECK THE EXPORT TEMPLATE FIRST. If "Asking Price" never appears in the For Sale
text, Jo exported the property-attribute report rather than the listing report and
the cards will have no price, cap rate, broker or list date. Ingest it anyway (the
properties are real) but every record gets domLabel "N/A" and a note saying the
price was not published, so a blank never reads as free. Ask her to re-export.
"""
import json, re, sys

if len(sys.argv) < 4:
    sys.exit(__doc__)
SALE_IN, LEASE_IN, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
COMPS_IN = sys.argv[4] if len(sys.argv) > 4 else None

def norm(x): return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9 ]','',str(x or '').lower())).strip()
def mapurl(a,c): return "https://www.google.com/maps/search/?q=" + '+'.join(re.sub(r'[^A-Za-z0-9 ]',' ',a+' '+c+' MS').split())
def costarurl(a,c): return "https://www.costar.com/properties?q=" + '+'.join(re.sub(r'[^A-Za-z0-9 ]',' ',a+' '+c+' MS').split())

TYPEFIX = {"Manufacturing":"Industrial","Specialty":"Special Purpose","Warehouse":"Industrial",
           "Distribution":"Industrial","Apartments":"Mixed Use"}

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

def split_title(t):
    # Split at the LAST ' - ': the address itself can contain one
    # (e.g. "100 - 104 Business Park Dr - 100-104 Business Park").
    i = t.rfind(' - ')
    if i == -1:
        return t.strip(), ''
    return t[:i].strip(), t[i+3:].strip()

def clean(kv):
    return {k:v for k,v in kv.items() if 'Mississippi' not in k}

def size_of(kv):
    for k in ('RBA (% Leased)','RBA','GLA (% Leased)','GLA','GBA'):
        if kv.get(k):
            m=re.match(r'([\d,]+\s*SF)', kv[k]);  return (m.group(1) if m else kv[k])
    return ''
def leased_of(kv):
    for k in ('RBA (% Leased)','GLA (% Leased)'):
        if kv.get(k):
            m=re.search(r'\(([\d.]+)%\)', kv[k]);  return m.group(1)+'% leased' if m else ''
    return ''
def land_of(kv):
    v=kv.get('Land Area - Gross') or ''
    m=re.match(r'([\d.,]+\s*AC)', v);  return m.group(1) if m else ''

def rent_parts(v):
    """'$16.50 SF/Year/NNN' -> ('16.50','NNN'); '$8.00 - 12.00 SF/Year' -> ('8.00 - 12.00','')"""
    if not v or v.strip().lower()=='withheld': return '',''
    m=re.match(r'\$?([\d.,]+(?:\s*-\s*[\d.,]+)?)\s*SF/Year(?:/(\S+))?', v.strip())
    if not m: return '', ''
    lt=(m.group(2) or '').strip()
    if lt.upper()=='TBD': lt=''
    return m.group(1).replace(' ',' '), lt

def notes_for(b, kv, extra=None):
    n=[]
    if b['ptype'] and b['ptype'] not in ('Land',): n.append(b['ptype'])
    if kv.get('Built/Renovated'): n.append('Built/renovated '+kv['Built/Renovated'])
    if kv.get('Center Type'): n.append(kv['Center Type'])
    l=leased_of(kv)
    if l: n.append(l)
    if kv.get('Tenancy'): n.append(kv['Tenancy']+'-tenant' if kv['Tenancy'] in ('Single','Multiple','Multi') else kv['Tenancy'])
    if kv.get('Units'): n.append(kv['Units']+' residential units above; commercial space offered')
    if kv.get('Proposed Use'): n.append('Proposed use: '+kv['Proposed Use'])
    if kv.get('Current Use'): n.append('Current use: '+kv['Current Use'])
    if kv.get('Topography'): n.append('Topography: '+kv['Topography'])
    if kv.get('Frontage'): n.append('Frontage: '+kv['Frontage'])
    if kv.get('Clear Height'): n.append("Clear height "+kv['Clear Height'])
    if kv.get('Docks'): n.append(kv['Docks']+' docks')
    if kv.get('Drive Ins'): n.append(kv['Drive Ins']+' drive-ins')
    if kv.get('Parking Spaces'): n.append('Parking: '+kv['Parking Spaces'])
    if kv.get('True Owner'): n.append('Owner: '+kv['True Owner'])
    if b.get('amen'): n.append('Amenities: '+b['amen'])
    if b['submarket']: n.append(b['submarket']+' submarket')
    if extra: n.extend(extra)
    return ' · '.join(x for x in n if x)

# ---------- FOR SALE ----------
sale=json.load(open(SALE_IN))
groups={}
for b in sale:
    addr,mk = split_title(b['title'])
    groups.setdefault((norm(addr),norm(b['city'])),[]).append((b,addr,mk))

forSale=[]; i=0
for key,g in groups.items():
    b,addr,mk = g[0]
    kv=clean(b['kv'])
    typ=TYPEFIX.get(b['ptype'], b['ptype'])
    isLand = 'land' in typ.lower()
    extra=[]
    if len(g)>1:
        parcels=[clean(x[0]['kv']).get('Parcel','') for x in g]
        extra.append('%d adjacent parcels in this listing (%s)' % (len(g), ', '.join(p for p in parcels if p)))
    av = kv.get('Available') or kv.get('Commercial Available')
    ar = kv.get('Asking Rent') or kv.get('Commercial Asking Rent')
    alsoLease=''
    if av and ar and ar.lower()!='withheld':
        alsoLease = '%s available at %s' % (av, ar)
    elif av:
        alsoLease = '%s available, rent withheld' % av
    extra.append('Asking price not published in this CoStar export')
    i+=1
    forSale.append(rec(FS_KEYS, dict(
        id=f"cs{i}", address=addr, city=b['city'], state="MS", zip=b['zip'], county=b['county'],
        type=typ, isLand=isLand, marketingName=mk, size=size_of(kv), lotSize=land_of(kv),
        units=kv.get('Units',''), yearBuilt=(kv.get('Built') or '').split('/')[0],
        zoning=kv.get('Zoning',''), alsoForLease=alsoLease, domLabel="N/A", source="costar",
        costarUrl=costarurl(addr,b['city']), mapUrl=mapurl(addr,b['city']),
        notes=notes_for(b,kv,extra))))

# ---------- FOR LEASE ----------
lease=json.load(open(LEASE_IN))
groups={}
for b in lease:
    addr,mk = split_title(b['title'])
    groups.setdefault((norm(addr),norm(b['city'])),[]).append((b,addr,mk))

forLease=[]; i=0
for key,g in groups.items():
    b,addr,mk = g[0]
    kv=clean(b['kv'])
    typ=TYPEFIX.get(b['ptype'], b['ptype'])
    rate,lt = rent_parts(kv.get('Asking Rent') or kv.get('Commercial Asking Rent') or '')
    avs=[clean(x[0]['kv']).get('Available') or clean(x[0]['kv']).get('Commercial Available') or '' for x in g]
    extra=[]
    if len(g)>1:
        sizes=[size_of(clean(x[0]['kv'])) for x in g]
        extra.append('%d buildings at this address (%s)' % (len(g), ', '.join(s for s in sizes if s)))
    rows=[r for x in g for r in x[0]['spaces']]
    if rows:
        extra.append('%d space%s listed' % (len(rows), '' if len(rows)==1 else 's'))
    i+=1
    forLease.append(rec(FL_KEYS, dict(
        id=f"cl{i}", address=addr, city=b['city'], state="MS", zip=b['zip'], county=b['county'],
        type=typ, isLand=False, marketingName=mk, askingRate=rate,
        leaseType=(lt if lt else ("$/SF/Year" if rate else "")),
        size=size_of(kv), avail=' / '.join(a for a in avs if a),
        yearBuilt=(kv.get('Built') or '').split('/')[0], units=kv.get('Units',''),
        domLabel="N/A", source="costar", costarUrl=costarurl(addr,b['city']),
        mapUrl=mapurl(addr,b['city']), notes=notes_for(b,kv,extra))))

# ---------- COMPS ----------
# The Sale Comps and Lease Comps PDFs hold only a handful of entries each, with
# fields (recorded seller, previous sale, cap rate, build-out, landlord) that vary
# too much to parse reliably. Hand-enter them into a small JSON and pass it as the
# optional 4th argument -- see WEEKLY.md for the shape. A MISSING comps PDF means
# zero matching transactions that week, not a skipped export: do not chase Jo for it.
saleComps, leaseComps = [], []
if COMPS_IN:
    _c = json.load(open(COMPS_IN))
    saleComps  = [rec(SC_KEYS, r) for r in _c.get('saleComps', [])]
    leaseComps = [rec(LC_KEYS, r) for r in _c.get('leaseComps', [])]

json.dump(dict(forSale=forSale, forLease=forLease, saleComps=saleComps, leaseComps=leaseComps),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('forSale',len(forSale),'forLease',len(forLease),'saleComps',len(saleComps),'leaseComps',len(leaseComps))
print('with price:', sum(1 for r in forSale if r['price']), '/', len(forSale))
print('with rate :', sum(1 for r in forLease if r['askingRate']), '/', len(forLease))
