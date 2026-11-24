# Vakantiebot (Atlas, Travel Desk)

Daily cloud bot that plans a trip for two (23 Jul - 13 Aug 2027, Japan first, South-East Asia as plan B, budget ~EUR 1,500-2,500 p.p. all-in).
It lives on the **Travel Desk (4F)** of the Agent Hub: https://claude.ai/artifact/TyiLCVXkEgkhMkaYp5F8Ki#travel
and writes only to the `travel_*` collections of that hub's database.

- `scan.md` - instructions for each run (the scheduled task reads this file)
- `planner.py` + `routes.json` - Atlas picks the routes itself from the settings (interests, pace, countries, window)
- `run.py` - prices each route all-in: flights (Travelpayouts cached fares first, Google Flights as check/fallback, comfort score), hotels, trains, food, activities
- `tp.py` - Travelpayouts / Aviasales Data API (token injected by the cloud environment's network proxy)
- `flights.py` - Google Flights (public results page)
- `hotels.js` - Google Hotels (headless browser)
- `journaway.js` - Journaway package tours with departure dates and prices
- `save.py` - turns results into hub documents and a push line
- `costs.json` - estimates for trains, food, activities, bags and the flight comfort rule
- `agenthub/` - source of the Travel Desk files published in the Agent Hub (`travel.js`, `travel.css`, and the edited `floors.js`, `office.js`, `index.html`)

Read-only: the bot never books or reserves anything.
