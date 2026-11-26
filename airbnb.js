#!/usr/bin/env node
// Airbnb public search results reader (read-only, no login, no booking).
// Usage: node airbnb.js "<city>" <checkin> <checkout> <lat> <lng> <radiusMiles>
// Searches a box around the city centre (so every result is in a good area), entire places and private rooms only,
// 2 adults. Prints one JSON line in the same shape as booking.js: {hotels:[{name, total, nightlyEur, score10, rating,
// reviews, kind, miles, url, src}], blocked, url}. Totals are Airbnb's own "€X for N nights" (fees included).
const { chromium } = require('playwright');

(async () => {
  const [city, ci, co, lat, lng, rmi] = process.argv.slice(2);
  const nights = Math.round((new Date(co) - new Date(ci)) / 864e5);
  const dLat = (+rmi * 1.609) / 111, dLng = dLat / Math.cos(+lat * Math.PI / 180);
  const q = new URLSearchParams({ checkin: ci, checkout: co, adults: '2', currency: 'EUR', locale: 'en',
    price_filter_num_nights: String(nights), search_by_map: 'true', search_type: 'filter_change',
    ne_lat: (+lat + dLat).toFixed(4), ne_lng: (+lng + dLng).toFixed(4), sw_lat: (+lat - dLat).toFixed(4), sw_lng: (+lng - dLng).toFixed(4) });
  q.append('room_types[]', 'Entire home/apt'); q.append('room_types[]', 'Private room');
  const url = process.env.AB_URL || 'https://www.airbnb.com/s/' + encodeURIComponent(city + '--Japan') + '/homes?' + q.toString();
  const out = { hotels: [], blocked: false, url, nights };
  let b;
  try {
    b = await chromium.launch();
    const c = await b.newContext({ locale: 'en-GB', viewport: { width: 1300, height: 2400 },
      userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36' });
    const p = await c.newPage();
    let cards = [];
    for (let page = 0; page < 2; page++) {
      if (page === 0) await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
      else {
        const nx = p.locator('a[aria-label="Next"]').first();
        if (!(await nx.count())) break;
        await nx.click(); await p.waitForTimeout(4000);
      }
      try { await p.waitForSelector('[data-testid="card-container"]', { timeout: 30000 }); }
      catch (e) { if (!page) { out.blocked = true; out.error = 'no result cards (blocked or no results)'; } break; }
      await p.mouse.wheel(0, 6000); await p.waitForTimeout(2500);
      cards = cards.concat(await p.$$eval('[data-testid="card-container"]', els => els.map(e => {
        const a = e.querySelector('a[href*="/rooms/"]');
        return { text: e.innerText.replace(/\n+/g, ' | '), href: a ? a.getAttribute('href') : '' };
      })));
    }
    const seen = new Set();
    for (const k of cards) {
      const id = (k.href.match(/\/rooms\/(\d+)/) || [])[1];
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const parts = k.text.split(' | ').map(s => s.trim());
      const tot = k.text.match(/€\s?([\d.,]+) for \d+ nights/);
      const rv = k.text.match(/([\d.]+) out of 5 average rating,\s*([\d,]+) reviews?/);
      if (!tot || !rv) continue;  // new listings without reviews are skipped
      const total = parseInt(tot[1].replace(/[.,]/g, ''), 10);
      const typ = parts.find(s => / in /.test(s) && !/rating/.test(s)) || '';
      const ri = parts.findIndex(s => /^\d(\.\d+)? \(\d[\d,]*\)$/.test(s));
      const title = (ri >= 0 && parts[ri + 1]) || typ;
      const beds = (k.text.match(/\b\d+ (?:double|queen|king|single|twin)? ?beds?\b|\b\d+ bedrooms?\b|Studio/gi) || []).filter((x, i, a) => a.indexOf(x) === i).join(', ');
      const entire = /^(Rental unit|Apartment|Condo|Home|House|Loft|Serviced apartment|Townhouse|Guesthouse|Vacation home|Tiny home)\b/i.test(typ);
      out.hotels.push({ name: title.slice(0, 80) + ' (Airbnb)', total, nightlyEur: Math.round(total / nights), score10: +(+rv[1] * 2).toFixed(1),
        rating: +rv[1], reviews: parseInt(rv[2].replace(/,/g, ''), 10),
        kind: (entire ? 'Entire place: ' : 'Private room: ') + typ + (beds ? ' - ' + beds : ''), miles: null,
        url: `https://www.airbnb.com/rooms/${id}?check_in=${ci}&check_out=${co}&adults=2&currency=EUR`, src: 'airbnb' });
    }
    out.hotels.sort((a, b) => a.total - b.total);
  } catch (e) {
    out.error = String(e).slice(0, 160);
  } finally {
    if (b) await b.close();
  }
  console.log(JSON.stringify(out));
})();
