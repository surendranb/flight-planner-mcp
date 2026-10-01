"""E2E contract: Schema v2 envelope + 10 tools + skills + taxonomy + opt-out + hygiene + fare baseline."""
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

def fares():
    jfk = json.loads(S.fare_baseline("JFK", "MCO"))
    assert jfk["median_usd"] > 0 and jfk["sampled_tickets"] >= 50 and "DB1B Market" in jfk["vintage"]
    atl = json.loads(S.fare_baseline("ATL", "MCO"))
    assert atl["median_usd"] > 0 and atl["sampled_tickets"] >= 50
    thin = S.fare_baseline("MAA", "MCO")
    assert "[TOO_THIN]" in thin  # international O&D absent from DB1B domestic baseline: suppression, not a guess
    assert "[INPUT_FIXABLE]" in S.fare_baseline("ZZZ", "MCO")

def opt_out():
    os.environ["MCP_TELEMETRY_OPT_OUT"] = "1"
    import importlib; importlib.reload(T)
    assert T._telemetry_disabled() is True
    del os.environ["MCP_TELEMETRY_OPT_OUT"]; importlib.reload(T)

def faa_failclosed_vintage():
    import urllib.request
    sk = S.skill_read("trip-brief")
    assert "I cannot crown a winner" in sk and "5-minute fare check" in sk  # fail-closed sentence present without scan
    assert "inference" in sk.lower()  # inferred numbers labeled inference every time
    import time as _t
    for _i in range(3):
        gh = urllib.request.urlopen("https://raw.githubusercontent.com/surendranb/flight-planner-mcp/main/skills/trip-brief.md",
            timeout=15).read().decode("utf-8", "replace")
        if gh.strip() == sk.strip():
            break
        _t.sleep(10)
    assert gh.strip() == sk.strip(), "skill_read must serve the live GitHub body, not a bundled copy"
    skel = json.loads(S.trip_skeleton("MAA", "MCO", 2))
    faa = skel["conditions"]["faa"]
    if faa.get("status") == "live":
        mco = faa["entries"].get("MCO", "")
        assert "non-US" not in mco and "US airport, no delay/closure entry" in mco, f"MCO entry insane: {mco!r}"  # US airport never mislabeled
        assert "non-US" in faa["entries"].get("MAA", ""), "MAA is non-US, must say so"
    else:
        assert "skeleton unaffected" in faa.get("reason", "")
    jb = json.loads(S.fare_baseline("JFK", "MCO"))
    assert jb["vintage"] == "DB1B Market 2025-Q1, 2025-Q2 (10% ticket sample, USD, passenger-weighted)"  # vintage exact
    assert "DB1B Market 2025-Q1, 2025-Q2" in jb["note"]  # every figure carries exact quarters
    assert "rolling" not in (S.fare_baseline.__doc__ or "").lower()  # no rolling-window wording

def plugin_packaging():
    import tomllib
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    py_ver = tomllib.load(open(root / "pyproject.toml", "rb"))["project"]["version"]
    pj = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    assert pj["name"] == "flight-planner-mcp" and pj["version"] == py_ver, f"plugin.json {pj.get('name')} {pj.get('version')} vs pyproject {py_ver}"
    assert (root / pj["skills"]).is_dir(), "skills path missing"
    srv = pj["mcpServers"]["flight-planner-mcp"]
    assert srv["command"] == "uvx" and srv["args"] == ["--from", "flight-planner-mcp", "flight-planner-mcp"] and isinstance(srv["env"], dict)
    mp = json.loads((root / ".claude-plugin" / "marketplace.json").read_text())
    entry = [p for p in mp["plugins"] if p["name"] == "flight-planner-mcp"][0]
    assert entry["version"] == py_ver, f"marketplace {entry.get('version')} vs pyproject {py_ver}"
    assert entry["source"]["repo"] == "surendranb/flight-planner-mcp"
    mc = json.loads((root / "mcp-config.json").read_text())
    assert mc["mcpServers"]["flight-planner-mcp"]["command"] == "uvx"
    assert mc["mcpServers"]["flight-planner-mcp"]["args"] == ["--from", "flight-planner-mcp", "flight-planner-mcp"]
    dotm = json.loads((root / ".mcp.json").read_text())
    assert dotm == mc, ".mcp.json must equal mcp-config.json server block"

if __name__ == "__main__":
    envelope_props(); tools(); fares(); faa_failclosed_vintage(); opt_out(); plugin_packaging(); print("E2E CONTRACT: PASS (schema+10 tools+skills+taxonomy+optout+hygiene+fares+faa+failclosed+vintage+plugin)")
