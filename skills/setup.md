# Setting Up Flight Planner MCP Server

A zero-configuration, privacy-preserving flight routing and planning engine for AI agents with offline airport datasets and rolling BTS fare baselines.

Official Repository: [github.com/surendranb/flight-planner-mcp](https://github.com/surendranb/flight-planner-mcp)

---

## 1. Quickstart (Zero API Keys Required)

`flight-planner-mcp` runs entirely on embedded and offline-accessible open datasets:
- **OurAirports**: 75,000+ global airport coordinates, IATA/ICAO codes, runway lengths, and timezones
- **BTS Rolling Fare Baselines**: Bureau of Transportation Statistics historical fare baselines and seasonal price curves
- **Great Circle Distance & Hub Routing**: 1-stop and 2-stop flight connection calculations

**Zero API keys, zero external credentials, and zero account setup required.**

---

## 2. Client Configuration

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "flight-planner": {
      "command": "uvx",
      "args": ["flight-planner-mcp"]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "flight-planner": {
      "command": "uvx",
      "args": ["flight-planner-mcp"]
    }
  }
}
```

### Command Line / CLI Testing
```bash
uvx flight-planner-mcp
```

---

## 3. Core Tools & Workflow

1. **`airport_lookup(query="SFO")`**:
   Resolve airport codes, coordinates, and details by IATA, ICAO, city, or name.

2. **`route_check(origin="JFK", destination="LHR")`**:
   Check direct route connectivity and distance between two airports.

3. **`flight_pairs(origin="BOS", destination="NRT", max_stops=1)`**:
   Identify optimal routing hubs and layover airports for connecting itineraries.

4. **`fare_baseline(origin="LAX", destination="HNL")`**:
   Query rolling seasonal fare medians and percentiles to benchmark ticket prices.

5. **`trip_skeleton(origin="SEA", destination="CDG", departure_date="2026-06-15")`**:
   Generate an end-to-end trip skeleton with flight routing, layover tolerances, and timezone transitions.

---

## 4. Troubleshooting & Operational Guidance

* **No Booking Functionality**: By design, this server plans routes and validates feasibility without booking tickets or requesting user credit cards.
* **Update Verification**: Call `check_for_updates()` to check PyPI for newer versions and upgrade commands.
* **Dynamic Skills**: Call `skill_read(name='trip-brief')` or `skill_read(name='setup')` for guidance on generating actionable flight briefs.
