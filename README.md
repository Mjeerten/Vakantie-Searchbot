# Vakantiebot

Dagelijkse cloud-bot die een reis voor 2 personen zoekt (23 jul - 13 aug 2027, Japan of Zuidoost-Azie, budget ~EUR 1.500-2.500 p.p.).

- Hub (routes aanpassen, resultaten, pakketreizen): https://claude.ai/artifact/G4yp1AbQWcquzh8z47GUby (bron: `hub/index.html`)
- `scan.md` - instructies voor elke run (de geplande taak leest dit bestand)
- `run.py` - rekent elke route door: vluchten + hotels + treinen + eten/uitjes per persoon
- `flights.py` - Google Flights (publieke resultatenpagina)
- `hotels.js` - Google Hotels (headless browser)
- `journaway.js` - Journaway pakketreizen met vertrekdata en prijzen
- `save.py` - zet resultaten om naar hub-documenten en een pushmelding
- `costs.json` - schattingen voor treinen, eten, uitjes en bagage (vrij aan te passen)

Alleen lezen: de bot boekt of reserveert nooit iets.
