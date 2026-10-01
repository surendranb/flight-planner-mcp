# RELEASE GATE — flight-planner-mcp v0.1.0 (independent harness only)

Status: PREPARED 2026-10-01 — NOT PASSED. Builder does not self-pass; an independent harness runs every step below and pastes real output.

## Zero-sum funding (max 2, no ties)
1. Static pair engine + trip-brief verdict (funded). Kills: live-price scraping, fare-history job.
2. Schema v2 telemetry + edge relay (funded). Kills: custom analytics dashboard, per-user tracking.
3. Dual-registry bridges + dynamic skills (deprioritized: ships as-is, no new registry work). Kills: PyPI/npm badges, studio subsite page.

## Task 1 — install via uvx (numeric: exit 0, version 0.1.0 shown)
```bash
uvx --from flight-planner-mcp flight-planner-mcp --help 2>&1 | head -5
npx -y flight-planner-mcp --help 2>&1 | head -5
```
Pass: both print help with exit 0.

## Task 2 — airport_lookup Orlando (numeric: iata == MCO)
Run via MCP inspector or:
```bash
uv run python -c "import sys; sys.path.insert(0,'src'); from flight_planner_mcp import server as S; import json; print(S.airport_lookup('Orlando'))"
```
Pass: JSON contains `"iata": "MCO"` (large-airport rank before medium).

## Task 3 — flight_pairs MAA-MCO (numeric: 1-stop via FRA + Gulf 2-stop)
```bash
uv run python -c "import sys,json; sys.path.insert(0,'src'); from flight_planner_mcp import server as S; fp1=json.loads(S.flight_pairs('MAA','MCO',max_stops=1,limit=10)); print('ONE:',fp1['one_stop_count'],fp1['options'][0]['via'],fp1['options'][0]['legs'][0]['airlines']); fp2=json.loads(S.flight_pairs('MAA','MCO',max_stops=2,limit=50)); print('GULF:',[v for v in [tuple(o['via']) for o in fp2['options']] if len(v)==2 and v[0] in ('DXB','DOH')][:3])"
```
Pass: `ONE: 1 ['FRA'] ['AI','LH']`; GULF non-empty (e.g. ('DXB','MAN')).

## Task 4 — trip_skeleton MAA-MCO-14 (numeric: days == 14)
```bash
uv run python -c "import sys,json; sys.path.insert(0,'src'); from flight_planner_mcp import server as S; s=json.loads(S.trip_skeleton('MAA','MCO',14)); print(s['route'],s['days'],s['km'])"
```
Pass: `MAA->MCO 14 14996.9` (km ±50 допускает data rebuild).

## Task 5 — edge relay /health (numeric: HTTP 200, status ok)
```bash
curl -s https://flight-planner-mcp.builditwithai.xyz/health
curl -s https://flight-planner-mcp-install-telemetry.reachsuren.workers.dev/health
```
Pass: both return `{"status":"ok","server":"flight-planner-mcp","gateway_version":"2",...}`.

## Task 6 — telemetry capture (numeric: ≥1 tool_executed row per task within 10 min)
Credential never in repo: `security find-generic-password -s PostHog-PAT -w` (Keychain) → `$POSTHOG_PAT`.
```bash
curl -s -H "Authorization: Bearer $POSTHOG_PAT" -H "Content-Type: application/json" \
  https://us.i.posthog.com/api/projects/489528/query -d '{
  "query": {"kind": "HogQLQuery", "query": "SELECT properties.tool_name, properties.status, count() FROM events WHERE event = '\''tool_executed'\'' AND properties.mcp_server_name = '\''flight-planner-mcp'\'' AND properties.mcp_client_name NOT ILIKE '\''%fuzz%'\'' AND properties.mcp_client_name NOT ILIKE '\''%test%'\'' AND properties.mcp_client_name NOT ILIKE '\''%probe%'\'' AND properties.mcp_client_name NOT ILIKE '\''%monitor%'\'' AND timestamp > now() - INTERVAL 1 DAY GROUP BY properties.tool_name, properties.status ORDER BY count() DESC LIMIT 20"}
}' | head -c 2000
```
Pass: rows for airport_lookup, flight_pairs, trip_skeleton with status success; zero rows with synthetic client names.
Schema check: every row carries schema_version=2, mcp_server_version=0.1.0, $process_person_profile=false.

## Task 7 — hygiene (numeric: 0 hits each)
```bash
grep -rniE "^\s*(import|from)\s+(selenium|playwright|bs4|beautifulsoup|scrapy|puppeteer|requests-html)" src scripts worker || echo OK_ZERO_SCRAPER_IMPORTS
grep -rE "phc_[A-Za-z0-9]{10,}" src worker npm || echo OK_ZERO_PLAINTEXT_KEYS
uv run python tests/test_e2e_contract.py
```
Pass: both OK lines + `E2E CONTRACT: PASS`.

## Task 8 — browser-lane fare evidence (numeric: 8/8 fields present, scan age <=6h)
The bundle never drives a browser and stores no live prices. Any price verdict must attach a fresh manual fare scan (fare-scan-local checklist) with exactly these 8 fields, else the trip-brief FAIL-CLOSED sentence fires:
1. route (e.g. MAA->MCO via FRA) 2. date (YYYY-MM-DD) 3. fare (amount + currency) 4. timestamp (UTC ISO-8601) 5. page URL 6. screenshot path 7. baseline-band comparison (scanned fare vs fare_baseline p25–p75 + vintage) 8. latency (page-load ms or manual-scan minutes).
Freshness: scan timestamp <=6 hours old at verdict time; older scans are quoted as inference only, never crowned.
Pass: verdict cites all 8 fields + age <=6h; without a scan the exact fail-closed sentence is present and no winner is named. No live prices committed to repo; Task 7 grep stays clean.

## Gate verdict
Independent harness pastes outputs for Tasks 1–8. Any numeric mismatch = FAIL, file issue, no release. Builder signature: backend-engineer 2026-10-01 (prepared, not passed).
