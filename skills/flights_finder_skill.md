# Flights Finder Skill v0.1 (static-only)

Use for airport/route/distance questions. No live fares, no booking.

## Workflow
1. `airport_lookup` to resolve city to IATA (recognition beats recall).
2. `route_check` for static pair existence; `distance_calc` for km (never do math in-head).
3. `cheap_date_hint` only with LOW confidence label; direct user to live fare site for prices.
4. `trip_skeleton` for day plans.

## Error handling
- `[INPUT_FIXABLE]` → fix args using candidates in error and retry.
- `[TRANSIENT]` → retry once.
- `[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]` → stop, ask for network/GitHub help.

## Example
User: "Chennai to Bangalore?" → lookup MAA, BLR → route_check MAA/BLR → distance_calc → skeleton.
