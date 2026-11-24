#!/usr/bin/env node
// Google Flights public results page in a real browser (read-only). Handles round trip and multi-city.
// Usage: node gflights.js "<url>"   (url built by flights.py tfs_url)
// Prints one JSON line: {labels:[aria-label strings with prices], status, blocked, error}
const { chromium } = require('playwright');

(async () => {
  const url = process.argv[2];
  const out = { labels: [], blocked: false, error: null };
  let b;
  try {
    b = await chromium.launch();
    const c = await b.newContext({ locale: 'en-GB', viewport: { width: 1300, height: 2200 } });
    await c.addCookies([{ name: 'CONSENT', value: 'YES+', domain: '.google.com', path: '/' }]);
    const p = await c.newPage();
    p.on('response', r => { if (r.status() === 429 || /\/sorry\//.test(r.url())) out.blocked = true; });
    const r = await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    out.status = r ? r.status() : null;
    try { await p.waitForSelector('[aria-label^="From "][aria-label*="euros"]', { timeout: 60000 }); }
    catch (e) { out.error = out.blocked ? 'Google rate limit (429)' : 'no prices on page'; }
    await p.waitForTimeout(1500);
    out.labels = await p.$$eval('[aria-label^="From "][aria-label*="euros"]', els => els.map(e => e.getAttribute('aria-label')));
    if (out.labels.length) { out.blocked = false; out.error = null; }
  } catch (e) {
    out.error = String(e).slice(0, 160);
  } finally {
    if (b) await b.close();
  }
  console.log(JSON.stringify(out));
})();
