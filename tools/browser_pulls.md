# Browser pulls — Moody's, MLS United, Crexi

Everything here runs through Claude in Chrome against **Jo's already-authenticated**
browser. **Never enter credentials.** If a sign-in screen appears, stop and ask her.

`javascript_tool` output truncates around ~800 characters and **blocks strings that look
like query-string or cookie data** — returning a list of hrefs with query strings fails
outright. Emit compact pipe-delimited lines, strip `?…` from URLs, and page through
4–6 records per call.

---

## Moody's CRE

### Active listings

Jo's canonical link (update `dateAdded` each week):

```
https://members.moodyscre.com/search/map@32.72091130637359,-90.01452313448931,7/?bounds=36.741678925950126%2C-81.00573407198932%2C28.510380278335948%2C-99.02331219698931&dateAdded=%7B%22minimum%22%3A%222026-08-17%22%2C%22maximum%22%3A%222026-08-24%22%7D&excludeBrokerManaged=false&listedStatus=AVAILABLE_SALE%2CAVAILABLE_LEASE&locations=%7B%22geographies%22%3A%5B%7B%22regionCode%22%3A%22MS%22%2C%22country%22%3A%7B%22countryCode%22%3A%22USA%22%7D%7D%5D%7D
```

The part that matters is `locations={"geographies":[{"regionCode":"MS",…}]}`. A hand-built
lat/lon `bounds` box is **not** equivalent — one returned 31 properties of which 10 were
Alabama and Louisiana, where the region filter returned 54, all Mississippi. Never use
bounds for state filtering.

### Sale comps — `locations` does NOT work here, use `address`

Adding `locations` to a comps-mode search returns **HTTP 500 every time**, on `_list` and
`_count`, with and without `salePrice`. Comps mode takes a different parameter:

```js
{ listedStatus:["TRANSACTION_SOLD"], saleCompProperty:true,
  salePrice:{minimum:10000}, excludeBrokerManaged:false,
  address:"Mississippi",                                   // a plain STRING, not an object
  dateAdded:{minimum:"2026-08-17", maximum:"2026-08-24"} }
```

`address` alone gives ~3,200 MS sold comps; `dateAdded` narrows it to about a dozen a week.
**Unrecognised date params are silently ignored, not rejected** — `saleDate`, `closeDate` and
`transactionDate` all return the full unfiltered set, which looks like success. Always confirm a
date filter actually changed the count.

Rent Comparables uses `propertySearchMode:true, rentCompProperty:true` — not yet exercised.

### Procedure

1. Navigate, then patch `fetch` to capture the request body:

```js
window.__log=[];const of=window.fetch;
window.fetch=function(u,i){try{const url=(typeof u==='string')?u:(u&&u.url);
  if(url&&url.includes('/properties/_list'))window.__log.push({body:i&&i.body?String(i.body):null})}catch(e){}
  return of.apply(this,arguments)};
```

2. Re-trigger a search so the body is captured — clicking **Table** works for listings; for
   comps, selecting a location from the autocomplete works.
3. Replay for ids: `POST /api/cfra/search/v1/properties/_list?pageSize=100&pageNumber=1&byProperty=true`.
   It returns **ids only**; a `fields=` param exists but silently ignores unknown names, so
   don't guess field names.
4. Fetch each property: `GET /api/cfra/data/v1/property/{id}`. ~54 sequential fetches run fine
   inside one `javascript_tool` call.
5. For listings, keep `listedSpaces` where `availability.status === 'AVAILABLE'` and
   `firstActiveDate` is inside the window.

Setting the location box from JS needs the native setter — a plain `.value =` won't register
with Angular:

```js
const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
setter.call(el,'Mississippi'); el.dispatchEvent(new Event('input',{bubbles:true}));
```

Then click the option whose text is exactly `Mississippi` — the autocomplete also offers
"Mississippi State, MS", "Mississippi County, AR" and similar.

### Field paths

| Field | Path |
|---|---|
| address | `location.address.street.numberMin` + `.name`, `.locality`, `.region`, `.postalCode` |
| county | `location.county` (append " County") |
| type | `category` (`OFFICE`/`RETAIL`/`INDUSTRIAL`/`LAND`/`MULTIFAMILY`/`FARM_RANCH`), detail in `subCategory` |
| lotSize | `lot.totalAcres` |
| yearBuilt | `buildings[0].yearBuilt` — **`buildings` is sometimes a dict of buildings, sometimes one building; handle both** |
| size | `listedSpaces[n].space.size.available`, or `buildings[0].grossSF` for comps |
| asking price | `listedSpaces[n].sale.price.amount` — **`0` means not published**; render "call for pricing", never "$0" |
| comp sale | `listedSpaces[n].sale.transaction` → `.price.amount`, `.closingDate`, `._$soldPricePerSF`, `._$soldSF`, `.buyer.name` |
| lease rate | `listedSpaces[n].lease.askingRent[0].price` → `.amount.minimum/.maximum`, `.period`, `.size`, `.negotiable`; null min+max = Negotiable |
| lease type | `listedSpaces[n].lease.leaseType` (NNN/GROSS/MODIFIED_GROSS/FULL_SERVICE) |
| listDate | `listedSpaces[n].firstActiveDate.$date` (first 10 chars) |
| contact/office | `listedSpaces[n].agents[0].name` / `.company.name` |
| moodysUrl | `https://members.moodyscre.com/property/{id}` |

On an **active** listing `sale.transaction` is a *past* sale — do not mistake it for the asking
price. On a **comp** it is exactly what you want.

### Consolidate multi-space properties

One property routinely carries several listed spaces — 2026-08-26 saw **8 listings on one Canton
gas station** and 4 on 114 Old Runway Rd, Tupelo. Group by `(SALE|LEASE, normalised address, city)`
and emit one card per group with a size range and rate range, noting
`"N listings at this property on Moody's, consolidated"`. Drop exact duplicates.

### Photos — check BOTH places

`property.media` is not the whole story: 1210 Virginia Dr looked photo-less there but its
`/photos` page had 22 (they hang off the listing).

1. `property.media` → filter `type === 'IMAGE'`, sort by `order`, take `[0].url`.
2. Still empty? Open `https://members.moodyscre.com/property/{id}/photos` and read
   `[...document.querySelectorAll('img')].map(i=>i.src).filter(s=>s.includes('/api/images/data/'))`,
   prefer the `/data/lg/` variant, strip the `/api/images/data/{lg|th|md|sm}/` prefix.
3. Public CDN is a prefix swap: **`https://img-resized-cache.catylist.com/l1/OG` + path**. Works for
   both `/media/user_uploads/…` and `/cie-media/…`. Verify 200.
4. A real gap shows **"Photos (0)"** and only the placeholder `11/cie-media/00/15/68/68/64/RAW.JPG`
   (a default avatar — never store it). Note those "No photo available in Moody's" so the photo
   check treats them as accepted exceptions.

---

## MLS United (FlexMLS)

Base: `https://my.flexmls.com/mlsunited/search/idx_links/20210924020458295435000000/`
Always append `&zoom=6&bounds=-91.655273,30.107118,-88.187256,35.046032`, then **filter to
`StateOrProvince === 'MS'` in code** — that box reaches into Louisiana, Alabama and Tennessee.

### The three queries

```
# new / active
clusters?_filter=MlsStatus+Eq+%27Active%27%2C%27Right+of+First+Refusal%27+And+ListingContractDate+Bt+START%2CEND+And+PropertyType+Eq+%27E%27%2C%27F%27
# went under contract in the window
clusters?_filter=MlsStatus+Eq+%27Pending%27+And+PurchaseContractDate+Bt+START%2CEND+And+PropertyType+Eq+%27E%27%2C%27F%27
# closed comps
clusters?_filter=MlsStatus+Eq+%27Closed%27+And+CloseDate+Bt+START%2CEND+And+PropertyType+Eq+%27E%27%2C%27F%27
```

`E` = commercial for sale → `forSale`/`saleComps`. `F` = commercial for lease → `forLease`/`leaseComps`.

### Never use a parenthesised OR clause

The filter the MLS UI produces looks like
`… And (PurchaseContractDate Bt START,END Or StandardStatus Ne 'Pending') And …`.
Against `clusters` that returned **1 record where the split queries returned 28**. The API does
not honour it and fails *quietly* — it looks like a slow week. Always split and merge in code.

### Pinning exact dates

`clusters` does not expose `ListingContractDate`, `CloseDate` or `PurchaseContractDate`, and
`_select=` is ignored. **`ListingKey`'s leading timestamp is the record-creation time, not the
contract date** — one listing had a key dated 7/22 with a contract date inside 8/17–8/24, which
would have rendered a 35-day DOM instead of 8.

Query **one day at a time** (`… ListingContractDate Eq 2026-08-17 …` through `Eq 2026-08-24`),
collect ListingIds per day, and check the per-day counts sum to the range-query total.

### PropertyType `B` is excluded

Jo's saved Active link includes `'B'`. Leave it out. MLS United's `B` is "Lots & Acreage", mixing
commercial land with residential building lots, and the residential ones dominate — sampled
examples were "own a **residential lot** … build the home you've always envisioned" and
"2 acre lot … 2400 sq ft minimum, Lewisburg schools". Including it would have added ~130 records
against the global no-residential rule. If it ever comes back it needs a per-record check.

`BedsTotal` is **not** an exclusion signal — several legitimate commercial records carry it
(a rezoned C1 suite, a former place of worship, C-2 land, a 33,412 SF church).

### Detail pages

`listing_detail/{ListingKey}` gives **agent, office, description and Last Modified only** — no
tables, no county, no zoning, no year built. County comes from a city→county map.

```js
const t=document.body.innerText;
const g=re=>{const m=t.match(re);return m?m[1].trim():''};
const i=t.indexOf('Overview\nDescription');
[t.split('\n').filter(Boolean)[3], g(/List Agent Full Name\s*\n(.+)/),
 g(/List Office Name\s*\n(.+)/), g(/Last Modified\s*\n(.+)/),
 (i>-1?t.slice(i+20,i+300):'').replace(/\s+/g,' ')]
```

Anchor on `'Overview\nDescription'`, not the first `'Description'` — that matches the nav tab and
returns photo filenames. Batch 4–5 listings per `browser_batch` as navigate+extract pairs.

Photos: `StandardFields.Photos[0].Uri640`. `mlsUrl` = `…/listing_detail/{ListingKey}` (the long
numeric key, **not** the human MLS#). Build it at pull time — it went unpopulated for weeks.

---

## Crexi

**Do not trust the saved links, and do not trust the 7-day filter.**

Crexi migrated `/properties` → `/search`, and the redirect **silently drops
`activationPeriod=SevenDays` and `sort=New Listings`**. Worse, hand-built `/search` URLs also lose
the **location** filter — `address_value=Mississippi…` alone yields zero results. Only URLs Crexi
itself generates, or filters set through its UI, hold state.

If results show skeleton loaders forever, **ask Jo to open the tab herself** — that reliably worked
on 2026-08-25 after many Claude-initiated attempts failed. The page is server-rendered, so patching
`fetch` captures only analytics; there is no listings API to replay. Read the DOM.

### The 7-day filter does not mean "newly listed"

Set via the sliders icon → **Listing Information** → **Listing timeline** → Time Period → 7 days,
which stamps `&ListingTimeline_dimension=7%20days&ListingTimeline_block=Time%20Period` and gave 161
Mississippi for-sale results. **But those are not this week's new listings.** Spot-checking the first
card (Chapel Ridge Apartments, Jackson) showed **"139 days on market · Updated 50 days ago"** — and
it is UCR's own listing. Dumping that set into "New Listings This Week" would be worse than an empty
placeholder.

### The correct approach

Each Crexi **property page** exposes real recency in its DOM:

```js
const t=document.body.innerText.replace(/\s+/g,' ');
const i=t.toLowerCase().indexOf('days on market');
t.slice(Math.max(0,i-140), i+80)     // "… $2,750,000 139 days on market Updated 50 days ago …"
```

So: filter loosely in the UI, harvest the cards, then **read each property page and keep only
those whose days-on-market falls inside the window**, deriving `listDate` from it. Verify a couple
of kept records by hand before trusting the batch.

### Reading result cards

Cards are `cui-card` elements (the earlier `closest()`-based selectors returned empty text):

```js
[...document.querySelectorAll('cui-card')].map(el=>{
  const a=el.querySelector('a[href*="/properties/"]');
  const img=el.querySelector('img');
  return {url:(a?a.getAttribute('href'):'').split('?')[0],
          photo:img?(img.getAttribute('src')||'').split('?')[0]:'',
          txt:(el.innerText||'').replace(/\s+/g,' ').trim()};});
```

Text comes through as `For Sale | $2,750,000 | <marketing name> | <description> | <street> |
<city, ST ZIP> | Request Info`. Only ~10 cards render at a time (virtualised) — scroll the
`overflow-auto` pane and accumulate unique hrefs.

**Ask Jo to use "Save Search"** once the Location and Listing timeline filters are right. That makes
the filter state durable instead of something someone re-clicks every week.

Also: filter to Mississippi only, and note in the report when out-of-state listings were excluded.

---

## Record schemas

Field lists live in `tools/build_costar.py` (`FS_KEYS`, `FL_KEYS`, `SC_KEYS`, `LC_KEYS`) — import or
copy them so every source emits the same shape. Notes on the ones that bite:

- `source` — `"costar"` | `"moodys"` | `"crexi"` | `"mls"`, comma-joined when merged. **Always
  `"mls"`, never `"flmls"`.**
- `listDate` — ISO `YYYY-MM-DD`. Drives Days on Market. No `dom` integer, ever.
- `domLabel` — overrides the computed DOM. Use `"N/A"` when there is no list date,
  `"Under Contract"` for pendings.
- `askingRate` + `leaseType` — rate is a number (or range) as a string; `leaseType` carries the
  **unit**: `"$/SF/Year"`, `"$/SF/Month"`, `"monthly rate"`, `"annual rate"`, `"Negotiable"`, or a
  structural type like `"NNN"`/`"MG"`. The renderer picks the displayed unit from it, so getting
  this wrong shows a monthly rent as `$/SF/yr`.
- `size` = building SF, `lotSize` = acreage. Never combine them.
- `isLand` — true for land; the "Land" badge is suppressed when `type` already says Land.
