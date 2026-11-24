// Journaway package reader (public pages, read-only, headless browser).
// Usage: node journaway.js <windowStart YYYY-MM-DD> <windowEnd YYYY-MM-DD> <minDays> <country> [country...]
// For each country it opens Journaway's public search page, collects the trip pages it links,
// opens each trip page and reads the departure dates and prices that page itself loads.
// Prints one JSON line per trip: {country, title, url, durationDays, fromPrice, departures:[{from,to,days,airport,price,status}], note}
// Journaway labels prices "p.p." on the page.
const { chromium } = require('playwright');
const [start, end, minDays, ...countries] = process.argv.slice(2);
const MAX_TRIPS_PER_COUNTRY = 10;
// slug words that mark a trip as being in that country (Journaway uses Dutch names in its urls)
const KEYS = { japan: ['japan'], vietnam: ['vietnam'], thailand: ['thailand'], indonesie: ['indonesie', 'bali', 'java', 'lombok'],
  'zuid-korea': ['korea'], taiwan: ['taiwan'], filipijnen: ['filipijnen'], maleisie: ['maleisie', 'borneo'], cambodja: ['cambodja'], laos: ['laos'] };
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ locale: 'nl-NL', timezoneId: 'Europe/Amsterdam' });
  for (const country of countries) {
    let links = [];
    try {
      const p = await ctx.newPage();
      await p.goto(`https://www.journaway.com/nl/zoeken?dType=country&dValue=${encodeURIComponent(country)}`, { waitUntil: 'networkidle', timeout: 90000 });
      links = await p.$$eval('a[href*="/nl/aanbiedingen/"]', as => [...new Set(as.map(a => a.href.split('?')[0]))]);
      const keys = KEYS[country.toLowerCase()] || [country.toLowerCase()];
      links = links.filter(u => keys.some(k => u.split('/aanbiedingen/')[1].includes(k)));
      await p.close();
    } catch (e) { console.log(JSON.stringify({ country, error: 'search page: ' + String(e).slice(0, 120) })); continue; }
    for (const url of links.slice(0, MAX_TRIPS_PER_COUNTRY)) {
      await sleep(2000);
      const p = await ctx.newPage();
      let prices = null;
      p.on('response', async r => { if (r.url().includes('/trip-prices/')) { try { prices = await r.json(); } catch (e) {} } });
      try {
        await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        for (let t = 0; t < 30 && !prices; t++) await sleep(1000);
        const title = (await p.title()).replace(/\s*[|-]\s*journaway.*$/i, '');
        const deps = [];
        for (const m of (prices?.data?.months || [])) for (const a of (m.appointments || [])) {
          const from = a.dateFrom.slice(0, 10), to = a.dateTo.slice(0, 10);
          const days = Math.round((Date.parse(to) - Date.parse(from)) / 864e5) + 1;
          if (from >= start && to <= end && days > Number(minDays) && a.status === 'bookable')
            deps.push({ from, to, days, airport: a.departureAirport, price: a.price, fare: a.fare, note: a.priceNote });
        }
        deps.sort((x, y) => x.price - y.price);
        console.log(JSON.stringify({ country, title, url, fromPrice: prices?.data?.minPrice ?? null, departures: deps.slice(0, 8), priceLabel: 'p.p. (Journaway)' }));
      } catch (e) { console.log(JSON.stringify({ country, url, error: String(e).slice(0, 120) })); }
      await p.close();
    }
  }
  await b.close();
})();
