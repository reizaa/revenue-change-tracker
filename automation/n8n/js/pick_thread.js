// Reply under today's KPI post when it's there; if it isn't (yet), post to the channel.
const msgs = $input.first().json.messages ?? [];
const parent = [...msgs].reverse()
  .find(m => (m.text ?? '').toLowerCase().includes('daily revenue'));
return [{ json: { ...$('Diff + top movers').first().json, thread_ts: parent?.ts ?? '' } }];
