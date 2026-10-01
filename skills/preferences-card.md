# Preferences Card Skill v1 (flight-planner-mcp)

Use to capture traveler preferences once, reuse across briefs. Stored by the model in conversation; no server state.

## Card fields
- home_airport: IATA (e.g. MAA)
- cabin: economy | premium | business (default economy)
- max_stops: 1 | 2 (default 2)
- avoid_red-eye: yes | no
- airline_alliances: Star Alliance | oneworld | SkyTeam | none
- date_flex_days: 0 | 2 (default 2 for +-2d scan)
- budget_note: free text, never a price promise

## Workflow
1. Ask for home_airport via `airport_lookup` (validate IATA).
2. Fill card with defaults for missing fields; state assumptions.
3. Pass max_stops into `flight_pairs`; pass days into `trip_skeleton`.
4. Reuse card for follow-ups without re-asking.

## Error handling
- `[INPUT_FIXABLE]` → fix IATA using candidates and retry.
- `[TRANSIENT]` → retry once.
- `[ENVIRONMENT_FIXABLE: STOP & ASK HUMAN]` → stop, ask human.

## Example
User: "I fly from Chennai, max 1 stop" → card {home_airport: MAA, max_stops: 1} → flight_pairs MAA/MCO max_stops=1.
