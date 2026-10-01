# Trip Brief Skill v1 (flight-planner-mcp, static-only)

Use for any origin → destination planning question. No live fares, no booking.

## Workflow
1. `airport_lookup` to resolve both cities to IATA (recognition beats recall; use candidates in errors).
2. `flight_pairs` with max_stops=2, limit=10. Server ranks by total_km; model does no math.
3. `fare_baseline` for ORIG → DEST: cite median + p25/p75 + vintage in the verdict; on `[TOO_THIN]` say so plainly and never substitute a guess.
4. `distance_calc` for km + approx_hours (server-computed).
5. `cheap_date_hint` only with LOW confidence label; never quote prices.
6. `trip_skeleton` for day plan + best-effort METAR/TAF + FAA snapshot.

## FAIL-CLOSED price rule (no live data here, so no price winner without proof)
This bundle holds no live fares. Never crown a cheapest flight or quote a price from static pairs or baseline medians.
- With a fresh fare scan attached (fare-scan-local checklist filled in: route, date, fare, timestamp, page URL, screenshot path, baseline-band comparison, latency; scan under 6 hours old): compare scanned fares against the baseline band, then crown a winner. Tag every scanned number with its timestamp and page URL; tag every baseline-derived number inference.
- Without one: return flight pairs + baseline band only, then write this exact sentence: "I cannot crown a winner — no fresh scan attached; run the 5-minute fare check in fare-scan-local and paste the result back." Never name a winner in this branch.
- Every inferred number carries the word inference next to it, every time. No exceptions.

## Bucket verdict (+-2d window)
 trip-brief always returns three buckets from static pairs:
- cheapest: shortest total_km 2-stop option (fewest km ≈ lowest fuel cost proxy).
- quickest: shortest total_km 1-stop option, or direct static pair if route_check true.
- sweet-spot: 1-stop via large hub (FRA/DXB/DOH class) balancing km vs stops.
State verdict as: cheapest = <via>, quickest = <via>, sweet-spot = <via> with km cited.
Append fare line: baseline median $M (p25–p75 $A–$B, n=N sampled tickets, <vintage>) or `too-thin, no baseline`.
For dates: advise user to check +-2d around target on a live fare site; static hint only.

## Error handling
- `[INPUT_FIXABLE]` → fix args using candidates in error and retry.
- `[TRANSIENT]` → retry once after 2s.
- `[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]` → stop, ask for network/GitHub help.

## Example
User: "Chennai to Orlando 14 days?" → lookup MAA, MCO → flight_pairs MAA/MCO → verdict: quickest via FRA (1-stop), cheapest via Gulf 2-stop → trip_skeleton MAA/MCO/14.
