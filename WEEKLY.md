# Section 6 — Weekly Runbook

Live dashboard: **https://purple-hill-0cd2cb610.7.azurestaticapps.net/**
Meeting: **Wednesdays.** The meeting date is the `MEETINGS` key, e.g. `20260902` → "September 2, 2026".

The window is the **8 days ending the Tuesday before the meeting** (2026-08-26 used Aug 17–24).
Confirm the window with Jo if it matters; she sets it. Anything that also appeared in the
previous week's report gets a note **"Also appeared in the <date> report"** rather than being
dropped — she chose labelled repeats over silent gaps.

---

## 0. Start from GitHub, not the local file

```bash
git clone https://github.com/joespina/ucr-sales-meeting.git /tmp/work/repo   # NOT the mounted folder
cd /tmp/work/repo && mkdir -p build
grep -o '"2026[0-9]\{4\}"' index.html | sort -u        # which meetings exist
```

Jo's local `/Users/joespina/Claude/Projects/UCR Sales Meeting Project/index.html` **goes stale**
— on 2026-08-25 it was three weeks behind and missing two whole meetings. Building on it would
have deleted them. GitHub is the source of truth. Write the finished file back to her disk at
the end so the two converge.

`git push` does **not** work from a Cowork sandbox (the proxy strips credentials — it is not an
auth problem, so do not go hunting for tokens). Deploy via the browser: see step 6.

---

## 1. CoStar — four PDFs

Jo drops them in `CoStar Exports/`. Identify each by content, not filename.

```bash
for f in "CoStar Exports"/*.pdf; do pdftotext -layout "$f" "build/$(basename "$f" .pdf).txt"; done
grep -c "Asking Price" build/*for_Sale*.txt        # 0 == wrong export template, see below
python3 tools/parse_costar.py build/<forSale>.txt  build/cs_sale.json
python3 tools/parse_costar.py build/<forLease>.txt build/cs_lease.json
python3 tools/build_costar.py build/cs_sale.json build/cs_lease.json build/costar.json [build/cs_comps.json]
```

**Check the template.** Two different CoStar reports produce similar filenames. The thin one
(property attributes only) parses cleanly and yields a plausible record count but has **no
prices, cap rates, broker contacts or list dates** — that is what arrived on 2026-08-26. Ingest
it anyway, but ask Jo to re-export from the listing view.

A **missing** Sale/Lease Comps PDF means zero matching transactions that week. Do not chase her for it.

Comps are hand-entered into `build/cs_comps.json`:

```json
{"saleComps":[{"id":"csc1","address":"225 Pinola Dr SE","city":"Magee","state":"MS","zip":"39111",
  "county":"Simpson County","type":"Retail","size":"2,550 SF","lotSize":"1.10 AC",
  "saleDate":"2026-08-19","salePrice":"","saleType":"Investment","yearBuilt":"1990",
  "contact":"Dylan Silber (631) 478-3382","office":"Silber Investment Properties, LTD",
  "source":"costar","notes":"Closed Aug 19, 2026 · Sale price not disclosed · …"}],
 "leaseComps":[]}
```

CoStar photos are **permanently unavailable** — its CDN requires a signed token and returns 403.
Leave `photoUrl` empty; CoStar is the one source exempt from the photo rule.

---

## 2, 3, 4. Moody's, MLS, Crexi — all via Jo's logged-in browser

Every snippet, filter and trap is in **[tools/browser_pulls.md](tools/browser_pulls.md)**. Read it
first; it will save you an hour. Never enter credentials — if a login screen appears, stop and
ask Jo to sign in.

Write each source to `build/moodys.json`, `build/mls.json`, `build/crexi.json` using the field
schemas in [tools/browser_pulls.md](tools/browser_pulls.md#record-schemas).

---

## 5. Merge, check, apply

```bash
python3 tools/merge_all.py build/records_20260902.json \
        build/costar.json build/mls.json build/moodys.json build/crexi.json
python3 tools/near_dupes.py build/records_20260902.json      # eyeball, add ALIASES if needed
python3 tools/apply_block.py 20260902 "September 2, 2026" build/records_20260902.json
./tools/validate.sh 20260902
node -e "const h=require('fs').readFileSync('index.html','utf8');
  [...h.matchAll(/<script>([\s\S]*?)<\/script>/g)].forEach((b,i)=>{new Function(b[1]);console.log('script',i,'OK')})"
```

`validate.sh` blocks on: missing address/source, `flmls` instead of `mls`, a listing with neither
`listDate` nor `domLabel` (which renders a false "New"), a non-CoStar source without its
click-through URL, a missing photo outside CoStar, residential language in notes, and duplicate
addresses or ids. It warns on rates whose magnitude contradicts their unit — that is how source
data-entry errors reach the meeting.

Then verify every image actually loads. A dead photo URL passes validation but shows a broken card:

```bash
python3 - <<'PY'
import json, urllib.request
d = json.load(open('build/records_20260902.json'))
urls = sorted({r['photoUrl'] for a in d for r in d[a] if r.get('photoUrl')})
bad = []
for u in urls:
    try: c = urllib.request.urlopen(urllib.request.Request(u, method='HEAD',
             headers={'User-Agent':'Mozilla/5.0'}), timeout=25).status
    except Exception as e: c = str(e)[:40]
    if c != 200: bad.append((u[-50:], c))
print(len(urls), 'photo urls; non-200:', bad or 'none')
PY
```

---

## 6. Deploy

`git commit` locally for history, then push through the browser (the sandbox proxy blocks `git push`):

1. `cp index.html /mnt/user-data/outputs/index.html`
2. Open `https://github.com/joespina/ucr-sales-meeting/upload/main`
3. `find` the file input ("Choose your files"), then `file_upload` that path — this reads the exact
   bytes off disk. **Never** retype file content or base64 through `javascript_tool`: it silently
   drops characters and corrupts large payloads.
4. Fill the commit message and description. **Re-screenshot before clicking** — the window resizes
   between calls and stale coordinates miss the fields silently. Confirm "Commit directly to `main`".
5. Verify: Actions run green, then

```bash
curl -s -o /tmp/live.html https://raw.githubusercontent.com/joespina/ucr-sales-meeting/main/index.html
diff <(shasum -a 256 /tmp/live.html | cut -d' ' -f1) <(shasum -a 256 index.html | cut -d' ' -f1) \
  && echo "byte-for-byte identical"
```

6. Hard-reload the live site and confirm the new meeting is selected with the right counts.
7. Write the file back to Jo's disk with `device_commit_files`.

---

## Standing rules — these came from Micah and Jo, do not quietly relax them

- **No residential, in any array, from any source.** Verify property type **per record**; the
  URL filter has been wrong before. MLS `PropertyType` `A` and `B` are both suspect — `B`
  ("Lots & Acreage") is mostly residential building lots and is excluded. See
  [tools/browser_pulls.md](tools/browser_pulls.md#mls-united-flexmls).
- **Photos on every source except CoStar.** Moody's is the one most often missed.
- **One card per property.** Merge across sources; consolidate multiple suites at one address
  into a single card with a size/rate range.
- **Every non-CoStar listing links to its source.** Populate `mlsUrl` / `crexiUrl` / `moodysUrl`
  at pull time. CoStar deliberately has no link.
- **`listDate` drives Days on Market** — never store a `dom` integer. No list date available?
  Set `domLabel` (e.g. `"N/A"`), or the card claims to be new.
- **Never invent a figure.** No asking price means "not published" on the card, not a blank that
  reads as free. Keep source errors as published and flag them in `notes`.
- **Pending listings** go in with `flags: "Under Contract"` and must never read as available.
- **Verify what a supplied link actually filters for** before ingesting it. On 2026-08-25 three of
  four links were mislabelled — a "Closed Comps" link that returned only Active listings, and a
  "Comps" link that returned active inventory. Decode the filter, run it, check the status
  distribution of what came back.
