// Pre-deploy quality gate for one MEETINGS block.  Loaded by validate.sh with
// `var MEETINGS` and `const KEY` already defined.  Exits 1 on any hard issue.
const A = ['forSale', 'forLease', 'saleComps', 'leaseComps'];
const m = MEETINGS[KEY];
if (!m) { console.log('FAIL: no meeting block ' + KEY); process.exit(1); }

console.log('meetings in file:', Object.keys(MEETINGS).sort().join(', '));
console.log(KEY, '|', m.label, '|', A.map(k => k + '=' + (m[k] || []).length).join('  '),
            '| total', A.reduce((n, k) => n + (m[k] || []).length, 0));

const bad = [], warn = [];

// ---- residential screen -------------------------------------------------
// Micah's global rule: no residential in any array, from any source.
// This is a text backstop only -- the real defence is checking PropertyType
// per record at pull time (MLS 'A' and 'B' are both suspect; see WEEKLY.md).
const RESI = /\b(single family home|residential lot|build (the|your) home|bedroom home|subdivision lot|sq ft minimum)\b/i;

for (const a of A) for (const r of m[a] || []) {
  const src = String(r.source || '').split(',').filter(Boolean);
  const where = [a, r.id];

  if (!r.address) bad.push([...where, 'no address']);
  if (!src.length) bad.push([...where, 'no source']);
  if (src.includes('flmls')) bad.push([...where, 'source token must be "mls", not "flmls"']);

  // Days on market must be derivable, or explicitly labelled.
  if ((a === 'forSale' || a === 'forLease') && !r.listDate && !r.domLabel)
    bad.push([...where, 'no listDate and no domLabel -> renders a false "New"']);

  // Every non-CoStar source must produce a clickable link.
  if (src.includes('mls')    && !r.mlsUrl)    bad.push([...where, 'mls record without mlsUrl']);
  if (src.includes('crexi')  && !r.crexiUrl)  bad.push([...where, 'crexi record without crexiUrl']);
  if (src.includes('moodys') && !r.moodysUrl) bad.push([...where, 'moodys record without moodysUrl']);

  // Photos: required for every source except CoStar, unless the source has none.
  const nonCostar = src.filter(s => s !== 'costar');
  const noPhotoOk = /No photo available/i.test(r.notes || '');
  if (nonCostar.length && !r.photoUrl && !noPhotoOk)
    bad.push([...where, 'missing photo (source ' + r.source + ')']);

  if (RESI.test(r.notes || '')) bad.push([...where, 'notes read residential -- ' + (r.notes || '').slice(0, 60)]);

  // Soft signals worth a human glance.
  if (a === 'forSale'  && !r.price && !/not published|call for pricing/i.test(r.notes || ''))
    warn.push([...where, 'no price and no explanation']);
  // An empty askingRate is fine -- the renderer shows "Rate Withheld".
  // What matters is a rate whose magnitude contradicts its unit, which is
  // how source data-entry errors reach the meeting. Strip commas first:
  // parseFloat('6,350') is 6, which would fire a false alarm.
  const rate = parseFloat(String(r.askingRate || '').replace(/,/g, ''));
  if (r.leaseType === '$/SF/Year'   && rate > 100) warn.push([...where, 'rate looks like a monthly total, not $/SF/Year: ' + r.askingRate]);
  if (r.leaseType === '$/SF/Month'  && rate > 50)  warn.push([...where, 'rate looks too high for $/SF/Month: ' + r.askingRate]);
  if (r.leaseType === 'monthly rate' && rate < 100) warn.push([...where, 'rate looks like $/SF, not a monthly total: ' + r.askingRate]);
}

// ---- photo coverage by source ------------------------------------------
const bySrc = {};
for (const a of A) for (const r of m[a] || []) for (const s of String(r.source || '').split(',')) {
  if (!s) continue;
  bySrc[s] = bySrc[s] || { n: 0, photos: 0 };
  bySrc[s].n++; if (r.photoUrl) bySrc[s].photos++;
}
console.log('photo coverage:', Object.entries(bySrc)
  .map(([s, v]) => `${s} ${v.photos}/${v.n}`).join('  '), '  (costar is exempt: auth-gated CDN)');

// ---- duplicates --------------------------------------------------------
const norm = x => String(x || '').toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
for (const a of A) {
  const seen = {};
  for (const r of m[a] || []) {
    const k = norm(r.address) + '|' + norm(r.city);
    if (seen[k]) bad.push([a, r.id, 'duplicate address of ' + seen[k] + ' -- merge instead']);
    else seen[k] = r.id;
  }
  const ids = (m[a] || []).map(r => r.id);
  const dup = [...new Set(ids.filter((x, i) => ids.indexOf(x) !== i))];
  if (dup.length) bad.push([a, dup.join(','), 'duplicate id']);
}

if (warn.length) console.log('\nWARNINGS (' + warn.length + ') -- review, not blocking:\n' +
  warn.map(w => '  - ' + w.join(' / ')).join('\n'));
console.log(bad.length ? '\nISSUES (' + bad.length + '):\n' + bad.map(b => '  - ' + b.join(' / ')).join('\n')
                       : '\nCHECKS PASS: no blocking issues');
if (bad.length) process.exit(1);
