// Same rules as src/diff.py. If you change one, change the other and run both on the
// same snapshot - the category totals should match exactly.
const today = $now.toFormat('yyyy-MM-dd');
const yesterday = $now.minus({ days: 1 }).toFormat('yyyy-MM-dd');
const cur = $('Read today slot').first().json.values ?? [];
const base = $('Read yesterday slot').first().json.values ?? [];

const fresh = (rows, d) => rows.length > 0 && rows[0][0] === d;
if (!fresh(cur, today) || !fresh(base, yesterday)) {
  // better no message than a "daily" number that silently covers two days
  throw new Error('snapshot date mismatch - a slot is missing or stale');
}

const byId = rows => Object.fromEntries(
  rows.map(r => [r[1], { local: +r[4], mrr: +r[6] }]));
const B = byId(base), C = byId(cur);

const moves = [];
for (const id of new Set([...Object.keys(B), ...Object.keys(C)])) {
  const b = B[id], c = C[id];
  const before = (b?.mrr ?? 0) * 12, now = (c?.mrr ?? 0) * 12;
  let cat = 'unchanged';
  if (!before && now) cat = 'new';
  else if (before && !now) cat = 'churn';
  else if (c.local > b.local) cat = 'upgrade';
  else if (c.local < b.local) cat = 'downgrade';
  else if (now !== before) cat = 'fx_only';      // same contract, exchange rate moved
  moves.push({ id, cat, diff: now - before });
}

const fmt = v => (v < 0 ? '-' : '+') + Math.abs(Math.round(v)).toLocaleString('en-US');
const total = cat => moves.filter(m => m.cat === cat).reduce((s, m) => s + m.diff, 0);
const lines = ['new', 'upgrade', 'downgrade', 'churn'].map(cat => {
  const rows = moves.filter(m => m.cat === cat)
                    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
  if (!rows.length) return null;
  const top = rows.slice(0, 5).map(m => '`' + m.id + '` ' + fmt(m.diff)).join(', ');
  return `*${cat}* - ${rows.length} accounts, ${fmt(total(cat))}\n      ${top}`;
}).filter(Boolean);

const net = moves.reduce((s, m) => s + m.diff, 0);
return [{ json: {
  text: `*Revenue movers* - ${today} vs ${yesterday}\nnet ${fmt(net)}\n` + lines.join('\n'),
} }];
