# flight-planner-mcp (package: `flight-planner-mcp`)

Static flight planner v0.2. 10 tools (airport_lookup, airport_nearby, route_check, distance_calc, fare_baseline rolling BTS median, cheap_date_hint low-confidence, trip_skeleton with METAR/TAF + FAA best-effort, flight_pairs 1-stop + 2-stop ranked, skills_list, skill_read), OurAirports 4,568 airports + 34,824 directed pairs, great-circle stdlib. No booking, no DB, zero paid API, zero secrets in repo.

## Fare baseline (rolling 6 months, BTS DB1B Market)

`data/fares-us-rolling.json` holds passenger-weighted median/p25/p75 per directional US O&D from the last 2 DB1B quarters (10% ticket sample, public domain), built by `scripts/build_fares.py` from TranStats PREZIP bulk files (`https://transtats.bts.gov/PREZIP/Origin_and_Destination_Survey_DB1BMarket_<YYYY>_<Q>.zip`). Zero-fare and bulk-fare artifacts dropped; routes with n<50 sampled tickets are suppressed (tool returns `[TOO_THIN]`, never a guess). `data/fares-VINTAGE.txt` stamps the covered quarters. Raw zips (~100MB/quarter) live outside the repo (`/tmp/bts/`) and are never committed — only the ~3.5MB aggregate ships.

## Refresh (quarterly cron, rolling window self-expiring)

DB1B lags ~1 quarter. Each quarter, download the 2 newest quarters and rebuild; old months fall off automatically, no archive kept.

```cron
# quarterly, 06:00 UTC on the 15th of Jan/Apr/Jul/Oct (after TranStats posts the new quarter)
0 6 15 1,4,7,10 * cd ~/Projects/flight-planner-mcp && python3 scripts/build_fares.py /tmp/bts/market_*.zip && python3 tests/test_e2e_contract.py
```

Manual fallback: if TranStats blocks automated fetch, download the 2 newest `Origin_and_Destination_Survey_DB1BMarket` zips by hand from https://www.transtats.bts.gov/databases.asp (Aviation → Origin and Destination Survey) into `/tmp/bts/` and run the same command. Never fake data: if fewer than 2 quarters are obtainable, ship what exists and stamp the vintage honestly.
