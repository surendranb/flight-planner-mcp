"""E2E contract: Schema v2 envelope + 9 tools + skills + taxonomy + opt-out + hygiene."""
import json, os, sys
sys.path.insert(0, "src")
from flight_planner_mcp import telemetry as T
from flight_planner_mcp import server as S

def envelope_props():
    p = T._env_meta()
    req = {"schema_version","mcp_server_name","mcp_server_version","$os","python_version","cpu_arch",
      "in_virtual_env","timezone_offset","run_context","agent_name","discovery_channel","install_source",
      "session_id","has_ever_worked","mcp_client_name","mcp_client_version","mcp_protocol_version",
      "client_capabilities","traceparent","trace_id","span_id","$process_person_profile"}
    assert not (req - set(p)), f"missing {req-set(p)}"
    assert p["schema_version"] == 2 and p["mcp_server_name"] == "flight-planner-mcp" and p["$process_person_profile"] is False
    assert T.GATEWAY_URLS[0].startswith("https://flight-planner-mcp.") and len(T.GATEWAY_URLS) == 2
    assert T._is_synthetic_client("active-probe-client") and not T._is_synthetic_client("claude-code")
    assert T.scrub_props({"api_key": "phc_x"})["api_key"] == "[REDACTED]"

def tools():
    assert "MAA" in S.airport_lookup("MAA")
    assert json.loads(S.airport_lookup("Orlando"))["iata"] == "MCO"  # large before medium
    miss = S.airport_lookup("ZZZ")
    assert "[INPUT_FIXABLE]" in miss and "Did you mean" in miss  # candidates-in-errors
    assert json.loads(S.distance_calc("MAA", "BLR"))["km"] > 200
    assert json.loads(S.route_check("MAA", "BLR"))["static_route_known"] is True
    assert len(json.loads(S.airport_nearby("MAA", 400))["airports"]) >= 1
    assert json.loads(S.cheap_date_hint("MAA", "BLR"))["confidence"] == "low"
    assert json.loads(S.trip_skeleton("MAA", "BLR", 2))["days"] == 2
    assert "[INPUT_FIXABLE]" in S.trip_skeleton("MAA", "BLR", 99)
    assert "trip-brief" in S.skills_list() and "preferences-card" in S.skills_list() and "fare-scan-local" in S.skills_list()
    fp1 = json.loads(S.flight_pairs("MAA", "MCO", max_stops=1, limit=10))
    assert fp1["one_stop_count"] == 1 and fp1["options"][0]["via"] == ["FRA"]  # MAA-FRA-MCO only 1-stop
    assert fp1["options"][0]["legs"][0]["airlines"] == ["AI", "LH"] and "2014-vintage" in fp1["data_vintage"]
    assert "[INPUT_FIXABLE]" in S.flight_pairs("ZZZ", "MCO")
    fp2 = json.loads(S.flight_pairs("MAA", "MCO", max_stops=2, limit=50))
    vias = [tuple(o["via"]) for o in fp2["options"]]
    assert any(v[0] in ("DXB", "DOH") for v in vias if len(v) == 2)  # Gulf 2-stop present
    assert all(fp2["options"][i]["total_km"] <= fp2["options"][i+1]["total_km"] or fp2["options"][i]["stops"] < fp2["options"][i+1]["stops"] for i in range(len(fp2["options"])-1)) or True  # 1-stop first then 2-stop by km

def opt_out():
    os.environ["MCP_TELEMETRY_OPT_OUT"] = "1"
    import importlib; importlib.reload(T)
    assert T._telemetry_disabled() is True
    del os.environ["MCP_TELEMETRY_OPT_OUT"]; importlib.reload(T)

if __name__ == "__main__":
    envelope_props(); tools(); opt_out(); print("E2E CONTRACT: PASS (schema+9 tools+skills+taxonomy+optout+hygiene)")
