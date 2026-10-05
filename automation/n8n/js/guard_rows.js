// A half-empty extract would look like mass churn tomorrow, so stop here instead.
const MIN_ROWS = 100;
const rows = $input.all().map(i => i.json);
if (rows.length < MIN_ROWS) {
  throw new Error(`only ${rows.length} rows (< ${MIN_ROWS}) - snapshot skipped, old slot kept`);
}

const today = $now.toFormat('yyyy-MM-dd');
const slot = 'day_' + $now.toFormat('dd');
// first column = snapshot date, so the diff job can tell a fresh slot from last month's
const values = rows.map(r => [today, r.account_id, r.plan_tier, r.currency,
                              r.local_monthly, r.fx_rate, r.monthly_revenue]);
return [{ json: { slot, today, values, count: rows.length } }];
