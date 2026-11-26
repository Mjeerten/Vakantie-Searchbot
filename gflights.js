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
    if (!out.error) {
      // Sort by price (default is "top flights") and open the full list, so cheap but less "convenient" options count too
      try {
        const price = p.locator('[aria-label^="Price, Not selected"]').first();
        if (await price.count()) { await price.click(); await p.waitForTimeout(4000); out.sorted = 'price'; }
        for (let i = 0; i < 3; i++) {
          const more = p.locator('[aria-label*="more flights" i]').first();
          if (!(await more.count())) break;
          await more.click(); await p.waitForTimeout(3000);
        }
      } catch (e) { out.note = 'sort/expand failed: ' + String(e).slice(0, 80); }
    }
    out.labels = await p.$$eval('[aria-label^="From "][aria-label*="euros"]', els => els.map(e => e.getAttribute('aria-label')));
    if (out.labels.length) { out.blocked = false; out.error = null; }
    // Booking mode (control bot): click through like a person, outbound -> cheapest return (-> next leg) -> the
    // "Booking options" page, and read the real total there. Usage: node gflights.js "<url>" book "<text in the row>"
    if (process.argv[3] === 'book' && out.labels.length) {
      const want = process.argv[4] || '';
      const book = { steps: [] };
      try {
        for (let step = 0; step < 3; step++) {
          const rows = p.locator('[aria-label^="From "][aria-label*="euros"]');
          const n = await rows.count();
          if (!n) break;
          let idx = 0;
          if (step === 0 && want) {
            const labs = await rows.evaluateAll(els => els.map(e => e.getAttribute('aria-label')));
            const parts = want.split('|');
            const i = labs.findIndex(l => parts.every(x => l.includes(x)));
            if (i < 0) { book.error = 'flight not on the page any more'; break; }
            idx = i;
          }
          book.steps.push((await rows.nth(idx).getAttribute('aria-label')).slice(0, 220));
          await rows.nth(idx).click();
          await p.waitForTimeout(6000);
          if (await p.getByText('Booking options').count()) break;
          // next leg: sort by price again, then the cheapest is first
          try { const pr = p.locator('[aria-label^="Price, Not selected"]').first(); if (await pr.count()) { await pr.click(); await p.waitForTimeout(3000); } } catch (e) {}
        }
        const txt = await p.evaluate(() => document.body.innerText);
        const tot = txt.match(/€\s?([0-9.,]+)\s*\n?\s*Lowest total price/);
        book.totalPP = tot ? +tot[1].replace(/[.,]/g, '') : null;
        book.options = [...txt.matchAll(/Book with ([^\n]+?)\s*(?:Airline)?\s*\n+\s*€\s?([0-9.,]+)/g)].slice(0, 4).map(m => ({ site: m[1].trim(), pricePP: +m[2].replace(/[.,]/g, '') }));
        const bag = txt.match(/1st checked bag:?\s*([^\n]+)/);
        book.bag = bag ? bag[1].trim() : null;
        book.different = /different airport/i.test(txt);
        book.url = p.url();
      } catch (e) { book.error = String(e).slice(0, 120); }
      out.book = book;
    }
  } catch (e) {
    out.error = String(e).slice(0, 160);
  } finally {
    if (b) await b.close();
  }
  console.log(JSON.stringify(out));
})();
