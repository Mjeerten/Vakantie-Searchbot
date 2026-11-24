// Google Hotels price reader (public results page, read-only, headless browser).
// Usage: node hotels.js "<city>" <checkin YYYY-MM-DD> <checkout YYYY-MM-DD> [usdToEur]
// Prints one JSON object: {city, checkin, checkout, url, blocked, currency, hotels:[{name, nightly, nightlyEur, rating, reviews, kind, deal}]}
// Prices are Google's nightly price for one room for 2 adults (Google's default).
const { chromium } = require('playwright');

const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const pretty = d => { const [y, m, day] = d.split('-').map(Number); return `${MONTHS[m - 1]} ${day} ${y}`; };

function parse(text, usdToEur) {
  const lines = text.split('\n').map(s => s.trim()).filter(Boolean);
  const out = [];
  const badge = /^(DEAL|GREAT DEAL|GREAT PRICE|Sponsored|Ad|LOW PRICE|View prices|·)$/i;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(\$|€|US\$)\s?([0-9][0-9.,]*)$/);
    if (!m) continue;
    let j = i - 1;
    while (j >= 0 && badge.test(lines[j])) j--;
    const name = lines[j];
    if (!name || name.length > 90 || /results|filters|Sort by|Price|Under/i.test(name)) continue;
    let rating = null, reviews = null, kind = null, deal = null;
    for (let k = i + 1; k < Math.min(lines.length, i + 20); k++) {
      const l = lines[k];
      if (/^(\$|€|US\$)\s?[0-9]/.test(l)) break; // next card
      if (rating === null && /^[1-5]\.\d$/.test(l)) rating = Number(l);
      else if (reviews === null && /^\([0-9.,]+K?\)$/.test(l)) {
        const v = l.slice(1, -1); reviews = v.endsWith('K') ? Math.round(parseFloat(v) * 1000) : Number(v.replace(/[.,]/g, ''));
      } else if (!kind && /(star hotel|hostel|capsule|apartment|guest ?house|inn|ryokan|resort|homestay|villa|bed & breakfast|hotel)$/i.test(l) && l.length < 40) kind = l;
      else if (!deal && /less than usual/i.test(l)) deal = l;
    }
    const nightly = Number(m[2].replace(/,/g, ''));
    const isUsd = m[1] !== '€';
    out.push({ name, nightly, currency: isUsd ? 'USD' : 'EUR', nightlyEur: Math.round(isUsd ? nightly * usdToEur : nightly), rating, reviews, kind, deal });
  }
  const seen = new Set();
  return out.filter(h => !seen.has(h.name) && seen.add(h.name));
}

(async () => {
  const [city, checkin, checkout, fx] = process.argv.slice(2);
  const usdToEur = Number(fx || 0.92);
  const url = 'https://www.google.com/travel/search?hl=en&gl=nl&curr=EUR&q=' +
    encodeURIComponent(`${city} hotels ${pretty(checkin)} to ${pretty(checkout)}`);
  const res = { city, checkin, checkout, url, blocked: false, hotels: [], error: null };
  const b = await chromium.launch();
  try {
    const ctx = await b.newContext({ locale: 'en-GB', timezoneId: 'Europe/Amsterdam' });
    const p = await ctx.newPage();
    const r = await p.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
    const text = await p.innerText('body');
    if (r.status() === 429 || /unusual traffic/i.test(text)) { res.blocked = true; res.error = 'Google rate limit'; }
    else {
      const ins = await p.$$eval('input', els => els.map(e => (e.getAttribute('aria-label') || '') + '=' + e.value));
      res.datesShown = ins.filter(s => /^Check/i.test(s));
      res.hotels = parse(text, usdToEur);
      if (!res.hotels.length) res.error = 'no prices on page';
    }
  } catch (e) { res.error = String(e).slice(0, 200); }
  await b.close();
  console.log(JSON.stringify(res));
})();
