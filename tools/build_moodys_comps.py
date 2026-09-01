#!/usr/bin/env python3
"""Build Moody's CRE sale comps from the live TRANSACTION_SOLD pull.

    python3 tools/build_moodys_comps.py build/moodys_comps_raw.txt build/moodys_comps.json

Line: propertyId|address|city|zip|county|CATEGORY/SUB|acres|yearBuilt|bldgSF|price|closeDate|pricePerSF|priceSource|buyer|photoPath

Two things to keep straight:
  * `dateAdded` is the ONLY date filter Moody's honours in comps mode, and it is when
    Moody's PUBLISHED the comp, not when the sale closed. Closing dates therefore run
    earlier than the report window, so every card states its own closing date.
  * `buildings[0].grossSF` is sometimes the LOT area rather than a building (223 N
    Applegate St came back as 71,874 SF, which is exactly its 1.65 acres). When gross
    SF is within 1% of acres x 43,560 it is dropped and the derived $/SF with it.
  * priceSource ESTIMATION means Moody's estimated the consideration; say so on the card.
"""
import json, re, sys

IN, OUT = sys.argv[1], sys.argv[2]
CDN = "https://img-resized-cache.catylist.com/l1/OG"

SC_KEYS = ["id","address","city","state","zip","county","type","isLand","marketingName","size","lotSize",
           "saleDate","salePrice","pricePerSF","capRate","saleType","saleConditions","tenant","yearBuilt",
           "submarket","contact","office","mlsNum","source","costarUrl","mlsUrl","mapUrl","photoUrl","notes",
           "moodysUrl","crexiUrl"]
def rec(d): return {k: d.get(k, False if k=="isLand" else "") for k in SC_KEYS}
def mapurl(a,c): return "https://www.google.com/maps/search/?q=" + '+'.join(re.sub(r'[^A-Za-z0-9 ]',' ',(a+' '+c+' MS')).split())

TYPE = {'LAND':'Land','RETAIL':'Retail','OFFICE':'Office','INDUSTRIAL':'Industrial',
        'MULTIFAMILY':'Multifamily','FARM_RANCH':'Farm/Ranch','HOSPITALITY':'Hospitality',
        'SPECIAL_PURPOSE':'Special Purpose','MIXED_USE':'Mixed Use','FLEX':'Flex'}

out, i = [], 0
for line in open(IN):
    line = line.rstrip('\n')
    if not line or line.startswith('#'): continue
    p = (line.split('|') + ['']*15)[:15]
    pid, addr, city, zp, cty, cat, ac, yb, bsf, price, dt, psf, src, buyer, photo = p
    i += 1
    catmain, _, sub = cat.partition('/')
    ty = TYPE.get(catmain, catmain.title())
    acres = float(ac) if ac else 0.0
    gross = float(bsf) if bsf else 0.0
    lot_sf = acres * 43560
    if gross and lot_sf and abs(gross - lot_sf) / lot_sf < 0.01:
        gross, psf = 0.0, ''            # that "building" is the parcel
    notes = []
    if sub: notes.append(sub.replace('_', ' ').title())
    if buyer: notes.append('Buyer: ' + buyer)
    if dt: notes.append('Closed ' + dt)
    notes.append('Published to Moody\'s between Aug 24 and Aug 31; the closing date above is the transaction date')
    if src == 'ESTIMATION':
        notes.append('Consideration estimated by Moody\'s, not a disclosed contract price')
    out.append(rec(dict(
        id=f"mdc{i}", address=addr, city=city, state='MS', zip=zp,
        county=(cty + ' County') if cty else '', type=ty, isLand=(ty == 'Land'),
        size=(f"{int(gross):,} SF" if gross else ''),
        lotSize=(f"{acres:g} AC" if acres else ''),
        saleDate=dt, salePrice=(f"${int(price):,}" if price else ''),
        pricePerSF=(f"{float(psf):.2f}" if psf and float(psf) else ''),
        yearBuilt=yb, source='moodys',
        moodysUrl='https://members.moodyscre.com/property/' + pid,
        mapUrl=mapurl(addr, city), photoUrl=(CDN + photo) if photo else '',
        notes=' · '.join(notes))))

json.dump(dict(forSale=[], forLease=[], saleComps=out, leaseComps=[]),
          open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('saleComps', len(out), '| with photo', sum(1 for r in out if r['photoUrl']),
      '| with price', sum(1 for r in out if r['salePrice']))
