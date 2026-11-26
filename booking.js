#!/usr/bin/env node
// Booking.com public search results reader (read-only, no login, no booking).
// Usage: node booking.js "<city>" <checkin> <checkout> [maxMetresFromCentre]
// Prints one JSON line: {hotels:[{name, total, nightlyEur, score10, rating, reviews, kind, miles, url}], blocked, url}
// Prices are Booking's own totals for the whole stay, 2 adults, 1 room, in EUR, cheapest first, review score 7+.
const { chromium } = require('playwright');

(async () => {
  const [city, ci, co, maxM] = process.argv.slice(2);  // maxM: optional max metres from the centre
  const nights = Math.round((new Date(co) - new Date(ci)) / 864e5);
  const url = 'https://www.booking.com/searchresults.en-gb.html?ss=' + encodeURIComponent(city) +
    `&checkin=${ci}&checkout=${co}&group_adults=2&no_rooms=1&group_children=0&selected_currency=EUR&order=price&nflt=review_score%3D70` + (maxM ? '%3Bdistance%3D' + Math.round(+maxM) : '');
  const out = { hotels: [], blocked: false, url, nights };
  let b;
  try {
    b = await chromium.launch();
    const c = await b.newContext({ locale: 'en-GB', viewport: { width: 1300, height: 2400 },
      userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36' });
    const p = await c.newPage();
    // Booking shows ~25 cards a search (paging repeats them). Search twice, score 7+ and score 8+ (both cheapest
    // first), so well-rated hotels just above the hostels are in the pick too
    let cards = [];
    for (const off of [0, 1]) {
      await p.goto(off ? url.replace('review_score%3D70', 'review_score%3D80') : url, { waitUntil: 'domcontentloaded', timeout: 60000 });
      try { await p.waitForSelector('[data-testid="property-card"]', { timeout: 30000 }); }
      catch (e) { if (!off) { out.blocked = true; out.error = 'no result cards (blocked or no results)'; } break; }
      for (let i = 0; i < 2; i++) { await p.mouse.wheel(0, 8000); await p.waitForTimeout(1500); }
      cards = cards.concat(await readCards(p));
      if (off) await p.waitForTimeout(3000);
    }
    const seen = new Set();
    cards = cards.filter(k => !seen.has(k.name) && seen.add(k.name));
    async function readCards(p) { return p.$$eval('[data-testid="property-card"]', els => els.map(e => {
      const t = s => { const x = e.querySelector(s); return x ? x.innerText.trim() : ''; };
      const a = e.querySelector('a[data-testid="title-link"]');
      const pr = [...e.querySelectorAll('[data-testid="price-and-discounted-price"]')].map(n => n.innerText.trim());
      return { name: t('[data-testid="title"]'), price: pr[pr.length - 1] || '', rate: t('[data-testid="availability-rate-information"]'),
        score: t('[data-testid="review-score"]'), dist: t('[data-testid="distance"]'),
        room: t('[data-testid="recommended-units"]'), href: a ? a.href : '',
        member: /members-only|genius/i.test(e.innerText), orig: ((e.innerText.match(/Original price €\s*([\d.,]+)/) || [])[1]) || '' };
    })); }
    for (const k of cards) {
      const num = x => parseInt(String(x).replace(/[.,]/g, ''), 10);
      const tax = (k.rate.match(/\+\s*€\s*([\d.,]+)\s*taxes/i) || [])[1];
      const total = num((k.price.match(/[\d.,]+/) || [''])[0]) + (tax ? num(tax) : 0);
      const sm = k.score.match(/Scored ([\d.]+)/);
      const rv = k.score.match(/([\d,]+) reviews?/);
      const mi = k.dist.match(/([\d.]+) (miles|km|m)\b/);
      if (!k.name || !total || !sm) continue;
      let miles = null;
      if (mi) miles = mi[2] === 'miles' ? +mi[1] : mi[2] === 'km' ? +mi[1] / 1.609 : +mi[1] / 1609;
      let link = null;
      try { const u = new URL(k.href); if (u.protocol === 'https:' && /(^|\.)booking\.com$/.test(u.hostname)) link = `https://${u.hostname}${u.pathname}?checkin=${ci}&checkout=${co}&group_adults=2&no_rooms=1`; } catch (e) {}
      out.hotels.push({ name: k.name, total, nightlyEur: Math.round(total / nights), score10: +sm[1], rating: +(sm[1] / 2).toFixed(2),
        reviews: rv ? parseInt(rv[1].replace(/,/g, ''), 10) : 0, kind: k.room.replace(/\s+/g, ' ').slice(0, 160),
        miles: miles == null ? null : +miles.toFixed(1), url: link, src: 'booking',
        // members-only (Genius) price: needs a free Booking.com account; publicTotal is the price without one
        memberPrice: k.member || undefined, publicTotal: k.member && k.orig ? num(k.orig) + (tax ? num(tax) : 0) : undefined });
    }
  } catch (e) {
    out.error = String(e).slice(0, 160);
  } finally {
    if (b) await b.close();
  }
  console.log(JSON.stringify(out));
})();
