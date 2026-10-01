# Fare Scan Local Skill v1 (flight-planner-mcp, LOCAL-ONLY)

Use when user asks for live prices. This bundle has zero automation deps by design.

## Rule
LOCAL-ONLY browser instructions. The agent gives the user exact manual steps; the bundle never drives a browser, never scrapes, never stores credentials.

## Workflow
1. Resolve IATA via `airport_lookup` + `flight_pairs` for via-hubs to try first.
2. Give the user this copy-paste checklist:
   - Open airline site or aggregator in YOUR browser (incognito).
   - Search ORIG → DEST, try +-2d dates from trip-brief verdict.
   - Try quickest via-hub first, then cheapest 2-stop hubs.
   - Record price, baggage, layover manually; paste back for comparison.
3. `cheap_date_hint` only with LOW confidence label; never quote a price from static data.
4. No automation: do not suggest scripts, extensions, or headless runs.

## Error handling
- `[INPUT_FIXABLE]` → fix IATA using candidates and retry.
- `[TRANSIENT]` → retry once.
- `[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]` → stop, ask human to run the manual scan.

## Hygiene
Zero scraper imports in this bundle (no selenium, playwright, beautifulsoup, scrapy, puppeteer). Grep-verify before release.
