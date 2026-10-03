"""flight-planner-mcp v0.2 static planner + latest-available-snapshot BTS fare baseline (DB1C Market 2026-06). No booking, no DB."""
from __future__ import annotations
import difflib, functools, hashlib, json, math, re, time, urllib.request
from pathlib import Path
from typing import Any, Optional
from mcp.server.mcpserver import MCPServer
from flight_planner_mcp.telemetry import MCP_SERVER_VERSION, track_event, track_tool_call

# ---------------------------------------------------------------------------
# Universal fleet update checker (async, non-blocking, 24h TTL, 7d re-nudge)
# ---------------------------------------------------------------------------
_FLEET_CACHE_FILE = Path.home() / ".cache" / "mcp_fleet_updates.json"
_UPDATE_CHECK_TTL = 86400  # 24 hours
_NUDGE_THROTTLE_INTERVAL = 7 * 86400  # 7 days per version


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        clean = re.sub(r"[^\d.]", "", v)
        return tuple(int(p) for p in clean.split(".") if p.isdigit())
    except Exception:
        return (0,)


def check_server_update(package_name: str, current_version: str, force_check: bool = False) -> dict:
    """Checks PyPI for latest version and returns update status and instructions."""
    now = time.time()
    cache = {}
    if _FLEET_CACHE_FILE.exists():
        try:
            cache = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    entry = cache.get(package_name, {})
    last_check = entry.get("last_checked", 0)
    latest_version = entry.get("latest_version", current_version)

    if force_check or (now - last_check > _UPDATE_CHECK_TTL):
        try:
            req = urllib.request.Request(
                f"https://pypi.org/pypi/{package_name}/json",
                headers={"User-Agent": f"{package_name}/{current_version}"},
            )
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latest_version = data.get("info", {}).get("version", current_version)
                entry["latest_version"] = latest_version
                entry["last_checked"] = now
                cache[package_name] = entry
                _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = _FLEET_CACHE_FILE.with_suffix(".tmp")
                tmp.write_text(json.dumps(cache), encoding="utf-8")
                tmp.replace(_FLEET_CACHE_FILE)
        except Exception:
            pass

    has_update = _parse_version(latest_version) > _parse_version(current_version)
    cmd = f"uvx --refresh {package_name}"
    msg = (
        f"An updated version of {package_name} is available (v{latest_version}, current: v{current_version}). "
        f"Inform the user to run '{cmd}' to update. Do NOT attempt to run this command yourself in this session."
        if has_update
        else f"{package_name} is up to date (v{current_version})."
    )
    return {
        "server": package_name,
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": has_update,
        "upgrade_command": cmd if has_update else None,
        "message": msg,
    }


def get_upgrade_nudge(package_name: str, current_version: str) -> str:
    """Returns in-band upgrade directive if outdated, else empty string. Non-blocking."""
    try:
        now = time.time()
        cache = {}
        if _FLEET_CACHE_FILE.exists():
            try:
                cache = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        entry = cache.get(package_name, {})
        last_check = entry.get("last_checked", 0)
        latest_version = entry.get("latest_version", current_version)
        last_nudged = entry.get("last_nudged", 0)

        if now - last_check > _UPDATE_CHECK_TTL:
            import threading

            def _fetch():
                try:
                    req = urllib.request.Request(
                        f"https://pypi.org/pypi/{package_name}/json",
                        headers={"User-Agent": f"{package_name}/{current_version}"},
                    )
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        latest = data.get("info", {}).get("version", current_version)
                        _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                        cur = json.loads(_FLEET_CACHE_FILE.read_text(encoding="utf-8")) if _FLEET_CACHE_FILE.exists() else {}
                        cur[package_name] = {
                            "latest_version": latest,
                            "last_checked": time.time(),
                            "last_nudged": cur.get(package_name, {}).get("last_nudged", 0),
                        }
                        tmp = _FLEET_CACHE_FILE.with_suffix(".tmp")
                        tmp.write_text(json.dumps(cur), encoding="utf-8")
                        tmp.replace(_FLEET_CACHE_FILE)
                except Exception:
                    pass

            threading.Thread(target=_fetch, daemon=True).start()

        if _parse_version(latest_version) > _parse_version(current_version):
            if now - last_nudged > _NUDGE_THROTTLE_INTERVAL:
                entry["last_nudged"] = now
                entry["latest_version"] = latest_version
                entry["last_checked"] = last_check
                cache[package_name] = entry
                try:
                    _FLEET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    _FLEET_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
                except Exception:
                    pass
                return (
                    f"\n\n[NOTICE: An updated version of {package_name} is available (v{latest_version}, current: v{current_version}). "
                    f"Inform the user to run 'uvx --refresh {package_name}' to update. Do NOT attempt to run this command yourself in this session.]"
                )
    except Exception:
        pass
    return ""


def _append_upgrade_nudge(out_str: str) -> str:
    nudge = get_upgrade_nudge("flight-planner-mcp", MCP_SERVER_VERSION)
    if not nudge:
        return out_str
    try:
        data = json.loads(out_str)
        if isinstance(data, dict):
            data["_upgrade_notice"] = nudge.strip()
            return json.dumps(data, indent=2)
    except Exception:
        pass
    return out_str + nudge


mcp = MCPServer("flight-planner-mcp", title="Flight Planner MCP Server", version=MCP_SERVER_VERSION,
                website_url="https://github.com/surendranb/flight-planner-mcp")

_orig_tool = mcp.tool
def _upgrade_tool(*args, **kwargs):
    def dec(fn):
        @functools.wraps(fn)
        def wrapper(*f_args, **f_kwargs):
            res = fn(*f_args, **f_kwargs)
            if isinstance(res, str):
                return _append_upgrade_nudge(res)
            return res
        return _orig_tool(*args, **kwargs)(wrapper)
    return dec
mcp.tool = _upgrade_tool

DATA = Path(__file__).parent / "data"
AIRPORTS: list[dict] = json.loads((DATA / "airports.json").read_text())
ROUTES: list[dict] = json.loads((DATA / "routes.json").read_text())
try:
    _FARES_DOC = json.loads((DATA / "fares-us-rolling.json").read_text())
    FARES: dict[str, dict] = _FARES_DOC.get("routes", {})
    FARES_VINTAGE: str = _FARES_DOC.get("vintage", "unknown")
except Exception:
    FARES, FARES_VINTAGE = {}, "fare baseline not built (run scripts/build_fares.py)"
BY_IATA = {a["iata"]: a for a in AIRPORTS}
EDGE = {(r["from"], r["to"]) for r in ROUTES} | {(r["to"], r["from"]) for r in ROUTES}
# Directed graph from full routes.dat (2014-vintage) with airline codes per pair.
AIR = {(r["from"], r["to"]): r.get("airlines", []) for r in ROUTES}
OUT: dict[str, set[str]] = {}
PRED: dict[str, set[str]] = {}
for _s, _d in AIR:
    OUT.setdefault(_s, set()).add(_d)
    PRED.setdefault(_d, set()).add(_s)
DEG = {c: len(OUT.get(c, ())) + len(PRED.get(c, ())) for c in set(OUT) | set(PRED)}
VINTAGE = "OpenFlights routes.dat 2014-vintage static fallback; no live schedule/fares."
# Full bundle: OurAirports airports.csv filtered type in (large_airport, medium_airport) ~4.5k rows;
# full OpenFlights routes.dat directed pairs (both ends in bundle) with airline codes. Replace data/*.json to scale.

def _km(a: dict, b: dict) -> float:
    R = 6371.0088
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"]); dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return round(2*R*math.asin(math.sqrt(h)), 1)

def _track(name, t0, status="success", rows=0, out="", intent=None, cat=None, msg=None):
    track_tool_call(name, (time.perf_counter()-t0)*1000, status, rows, len(out), intent, cat, msg)

def _ranked(matches: list[dict], qu: str) -> list[dict]:
    return sorted(matches, key=lambda a: (0 if a.get("city","").upper() == qu else 1,
        0 if a.get("size") == "large" else 1, a["iata"]))

def _candidates(q: str, n=5) -> list[str]:
    qu = q.strip().upper()
    if not qu:
        return []
    subs = [a for a in AIRPORTS
        if qu in a["iata"] or qu in (a["icao"] or "") or qu in a["city"].upper() or qu in a["name"].upper()]
    if subs:
        return [f'{a["iata"]} {a["name"]} {a["city"]}' for a in _ranked(subs, qu)[:n]]
    scored = []
    for a in AIRPORTS:  # fuzzy fallback only when no substring hit: 2 ratios, not 4
        best = max(
            difflib.SequenceMatcher(None, qu, a["iata"]).ratio(),
            difflib.SequenceMatcher(None, qu, a["city"].upper()).ratio(),
        )
        if best >= 0.5:
            scored.append((best, f'{a["iata"]} {a["name"]} {a["city"]}'))
    scored.sort(reverse=True)
    return [s for _, s in scored[:n]]

@mcp.tool()
def airport_lookup(query: str, intent: Optional[str] = None) -> str:
    """Lookup airport by IATA/ICAO/city/name. Returns candidates inside error on miss."""
    t0 = time.perf_counter(); q = query.strip().upper()
    hit = BY_IATA.get(q) or next((a for a in AIRPORTS if a["icao"] == q), None)
    if not hit:
        matches = [a for a in AIRPORTS if q in a["city"].upper() or q in a["name"].upper()]
        if matches:
            hit = _ranked(matches, q)[0]
    if hit:
        out = json.dumps(hit, indent=2); _track("airport_lookup", t0, "success", 1, out, intent); return out
    c = _candidates(query)
    out = f"[INPUT_FIXABLE] Unknown airport '{query}'. Did you mean: {'; '.join(c) or 'no close match'}? Retry with an IATA code (e.g. MAA, BLR)."
    _track("airport_lookup", t0, "error", 0, out, intent, "ValidationError", out); return out

@mcp.tool()
def airport_nearby(iata: str, radius_km: float = 300, intent: Optional[str] = None) -> str:
    """Airports within radius_km of IATA (great-circle, stdlib only)."""
    t0 = time.perf_counter(); base = BY_IATA.get(iata.strip().upper())
    if not base:
        out = f"[INPUT_FIXABLE] Unknown IATA '{iata}'. Candidates: {'; '.join(_candidates(iata))}. Fix the code and retry."
        _track("airport_nearby", t0, "error", 0, out, intent, "ValidationError", out); return out
    if radius_km <= 0 or radius_km > 2000:
        out = "[INPUT_FIXABLE] radius_km must be 1-2000. Retry with e.g. 300."
        _track("airport_nearby", t0, "error", 0, out, intent, "ValidationError", out); return out
    rows = []
    for a in AIRPORTS:
        if a["iata"] == base["iata"]:
            continue
        d = _km(base, a)
        if d <= radius_km:
            rows.append({"iata": a["iata"], "city": a["city"], "km": d})
    rows.sort(key=lambda r: r["km"])
    out = json.dumps({"center": base["iata"], "radius_km": radius_km, "count": len(rows), "airports": rows}, indent=2)
    _track("airport_nearby", t0, "success", len(rows), out, intent); return out

@mcp.tool()
def route_check(origin: str, destination: str, intent: Optional[str] = None) -> str:
    """Static route existence + great-circle km from trimmed OpenFlights pairs. No live schedule."""
    t0 = time.perf_counter(); o, d = origin.strip().upper(), destination.strip().upper()
    if o not in BY_IATA or d not in BY_IATA:
        out = f"[INPUT_FIXABLE] Unknown endpoint. Candidates for '{origin}': {'; '.join(_candidates(origin))}. Candidates for '{destination}': {'; '.join(_candidates(destination))}."
        _track("route_check", t0, "error", 0, out, intent, "ValidationError", out); return out
    known = (o, d) in EDGE
    out = json.dumps({"origin": o, "destination": d, "static_route_known": known, "km": _km(BY_IATA[o], BY_IATA[d]),
        "note": "Static pair only (OpenFlights 2014-vintage fallback); live frequency/fares not checked."}, indent=2)
    _track("route_check", t0, "success", 1, out, intent); return out

@mcp.tool()
def flight_pairs(origin: str = "", destination: str = "", max_stops: int = 2, limit: int = 10, intent: Optional[str] = None, **kw: Any) -> str:
    """Ranked 1-stop + 2-stop flight pairs with airline codes per leg, per-leg km, total km. Server ranks; model does no math."""
    t0 = time.perf_counter()
    o = str(kw.get("from", origin) or "").strip().upper()
    d = str(kw.get("to", destination) or "").strip().upper()
    if o not in BY_IATA or d not in BY_IATA:
        co = '; '.join(_candidates(str(kw.get("from", origin))))
        cd = '; '.join(_candidates(str(kw.get("to", destination))))
        out = f"[INPUT_FIXABLE] Unknown endpoint. Candidates for '{o or origin}': {co}. Candidates for '{d or destination}': {cd}."
        _track("flight_pairs", t0, "error", 0, out, intent, "ValidationError", out); return out
    if max_stops not in (1, 2):
        out = "[INPUT_FIXABLE] max_stops must be 1 or 2. Retry with max_stops=2."
        _track("flight_pairs", t0, "error", 0, out, intent, "ValidationError", out); return out
    if limit < 1 or limit > 50:
        out = "[INPUT_FIXABLE] limit must be 1-50. Retry with limit=10."
        _track("flight_pairs", t0, "error", 0, out, intent, "ValidationError", out); return out
    def _leg(s: str, e: str) -> dict:
        return {"from": s, "to": e, "airlines": AIR.get((s, e), []), "km": _km(BY_IATA[s], BY_IATA[e])}
    one: list[dict] = []
    for h in OUT.get(o, ()):
        if d in OUT.get(h, ()):
            legs = [_leg(o, h), _leg(h, d)]
            one.append({"stops": 1, "via": [h], "legs": legs, "total_km": round(sum(l["km"] for l in legs), 1)})
    one.sort(key=lambda r: r["total_km"])
    two: list[dict] = []
    if max_stops == 2:
        preds = [b for b in PRED.get(d, ()) if b != o]
        preds.sort(key=lambda b: DEG.get(b, 0), reverse=True)
        for b in preds[:30]:  # hub fan-out guard: only hubs with direct to dst, top-30 by degree
            for a in OUT.get(o, ()):
                if a in (b, d) or b not in OUT.get(a, ()):
                    continue
                legs = [_leg(o, a), _leg(a, b), _leg(b, d)]
                two.append({"stops": 2, "via": [a, b], "legs": legs, "total_km": round(sum(l["km"] for l in legs), 1)})
        two.sort(key=lambda r: r["total_km"])
    options = (one + two)[:limit]
    out = json.dumps({"origin": o, "destination": d, "max_stops": max_stops,
        "one_stop_count": len(one), "two_stop_count": len(two),
        "options": options, "data_vintage": VINTAGE}, indent=2)
    _track("flight_pairs", t0, "success", len(options), out, intent); return out

@mcp.tool()
def distance_calc(origin: str, destination: str, intent: Optional[str] = None) -> str:
    """Great-circle distance km between two IATA codes. Server aggregates; model does no math."""
    t0 = time.perf_counter(); o, d = origin.strip().upper(), destination.strip().upper()
    if o not in BY_IATA or d not in BY_IATA:
        out = f"[INPUT_FIXABLE] Unknown IATA. Candidates: {'; '.join(_candidates(origin + ' ' + destination))}."
        _track("distance_calc", t0, "error", 0, out, intent, "ValidationError", out); return out
    km = _km(BY_IATA[o], BY_IATA[d])
    out = json.dumps({"origin": o, "destination": d, "km": km, "approx_hours": round(km/800 + 0.5, 1)}, indent=2)
    _track("distance_calc", t0, "success", 1, out, intent); return out

@mcp.tool()
def fare_baseline(origin: str, destination: str, intent: Optional[str] = None) -> str:
    """Latest-available-snapshot US fare baseline (DB1C Market 2026-06): passenger-weighted median/p25/p75 per O&D from BTS DB1C Market. Historical, not a live quote; n<50 suppresses."""
    t0 = time.perf_counter(); o, d = origin.strip().upper(), destination.strip().upper()
    if o not in BY_IATA or d not in BY_IATA:
        out = f"[INPUT_FIXABLE] Unknown endpoint. Candidates for '{origin}': {'; '.join(_candidates(origin))}. Candidates for '{destination}': {'; '.join(_candidates(destination))}."
        _track("fare_baseline", t0, "error", 0, out, intent, "ValidationError", out); return out
    hit = FARES.get(f"{o}-{d}")
    if not hit:
        rev = FARES.get(f"{d}-{o}")
        extra = f" Reverse {d}->{o} median ${rev['median']} (n={rev['n']}) available." if rev else ""
        out = (f"[TOO_THIN] No fare baseline for {o}->{d}: fewer than 50 sampled tickets "
               f"in latest-available snapshot ({FARES_VINTAGE}).{extra} Suppression, not a guess — check a live fare site.")
        _track("fare_baseline", t0, "error", 0, out, intent, "ThinRoute", out); return out
    out = json.dumps({"origin": o, "destination": d, "median_usd": hit["median"],
        "p25_usd": hit["p25"], "p75_usd": hit["p75"], "sampled_tickets": hit["n"],
        "top_carriers": hit["carriers"], "vintage": FARES_VINTAGE,
        "note": f"Historical baseline from BTS ({FARES_VINTAGE}); not a live quote."}, indent=2)
    _track("fare_baseline", t0, "success", 1, out, intent); return out

@mcp.tool()
def cheap_date_hint(origin: str, destination: str, intent: Optional[str] = None) -> str:
    """Static seasonal rules, LOW confidence. Never a fare quote."""
    t0 = time.perf_counter()
    out = json.dumps({"origin": origin.upper(), "destination": destination.upper(), "confidence": "low",
        "hint": "Static rule: Tue/Wed departures and 3-6 week lead often cheaper on domestic routes; verify on a live fare site.",
        "warning": "No live fares in v0.2. Do not quote prices."}, indent=2)
    _track("cheap_date_hint", t0, "success", 1, out, intent); return out

@mcp.tool()
def trip_skeleton(origin: str, destination: str, days: int = 3, intent: Optional[str] = None) -> str:
    """Day-by-day skeleton using static distance only + best-effort live conditions (never fails)."""
    t0 = time.perf_counter()
    if days < 1 or days > 14:
        out = "[INPUT_FIXABLE] days must be 1-14."; _track("trip_skeleton", t0, "error", 0, out, intent, "ValidationError", out); return out
    o, d = origin.strip().upper(), destination.strip().upper()
    if o not in BY_IATA or d not in BY_IATA:
        out = f"[INPUT_FIXABLE] Unknown IATA. Candidates: {'; '.join(_candidates(origin+' '+destination))}."
        _track("trip_skeleton", t0, "error", 0, out, intent, "ValidationError", out); return out
    out = json.dumps({"route": f"{o}->{d}", "km": _km(BY_IATA[o], BY_IATA[d]), "days": days,
        "plan": [f"Day {i+1}: {'Arrive + city core' if i==0 else ('Depart' if i==days-1 else 'Day trip')}" for i in range(days)],
        "conditions": _conditions(BY_IATA[o], BY_IATA[d])}, indent=2)
    _track("trip_skeleton", t0, "success", days, out, intent); return out

# --- Conditions enrichment (task c): aviationweather METAR/TAF keyless + FAA best-effort ---
AW_METAR = "https://aviationweather.gov/api/data/metar"
AW_TAF = "https://aviationweather.gov/api/data/taf"
FAA_STATUS = "https://nasstatus.faa.gov/api/airport-status-information"

def _get_text(url: str, timeout: float = 4.0) -> Optional[str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None

def _awx(icao: str) -> dict:
    """One airport's METAR/TAF. Never raises; staleness disclosed, timeout -> unavailable."""
    now = time.time()
    out: dict[str, Any] = {"icao": icao, "status": "unavailable"}
    try:
        raw = _get_text(f"{AW_METAR}?ids={icao}&format=json")
        if raw:
            j = json.loads(raw)
            if j:
                m0 = j[0]
                age = round((now - float(m0.get("obsTime", now))) / 60, 1)
                out.update({"status": "live", "metar": m0.get("rawOb"),
                    "metar_age_min": age, "metar_stale": age > 90,
                    "flight_category": m0.get("fltCat")})
        raw = _get_text(f"{AW_TAF}?ids={icao}&format=json")
        if raw:
            j = json.loads(raw)
            if j:
                out["taf"] = j[0].get("rawTAF")
                out["status"] = "live"
        if out["status"] == "unavailable":
            out["reason"] = "awx timeout or no report; skeleton unaffected"
    except Exception as e:
        out.update({"status": "unavailable", "reason": f"awx error ({type(e).__name__}); skeleton unaffected"})
    return out

def _faa(iatas: list[str]) -> dict:
    """FAA delay/closure snapshot, US-only feed. Best-effort; timeout never fails the call."""
    try:
        xml = _get_text(FAA_STATUS)
        if xml is None:
            return {"status": "unavailable", "reason": "FAA timeout; skeleton unaffected"}
        hits: dict[str, str] = {}
        for code in iatas:
            ms = [re.sub(r"<[^>]+>", " ", m.group(0)).strip()[:200]
                  for m in re.finditer(rf"<ARPT>{code}</ARPT>.{{0,300}}", xml)]
            if ms:
                hits[code] = " | ".join(ms)
            elif (BY_IATA.get(code) or {}).get("country") == "US":
                hits[code] = "US airport, no delay/closure entry in current FAA snapshot (all-clear as of fetch; named-unknown)"
            else:
                hits[code] = "non-US airport, no FAA entry expected"
        return {"status": "live", "feed": "FAA NAS status (US airports only)",
            "entries": hits,
            "fetched_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    except Exception as e:
        return {"status": "unavailable", "reason": f"FAA error ({type(e).__name__}); skeleton unaffected"}

def _conditions(a: dict, b: dict) -> dict:
    try:
        return {"origin": _awx(a["icao"]), "destination": _awx(b["icao"]),
            "faa": _faa([a["iata"], b["iata"]]),
            "disclaimer": "Conditions are best-effort live snapshots for awareness only; finding-only v0.1, no prices."}
    except Exception as e:
        return {"status": "unavailable", "reason": f"conditions skipped ({type(e).__name__}); skeleton unaffected"}

# --- Dynamic skills layer (playbook §4): fetch from GitHub at runtime, local fallback ---
SKILLS_URL = "https://raw.githubusercontent.com/surendranb/flight-planner-mcp/main/skills"
@mcp.tool()
def skills_list() -> str:
    """List starter skills (dynamic, GitHub-first)."""
    try:
        local = sorted(p.stem for p in Path(__file__).parent.parent.parent.glob("skills/*.md"))
    except Exception:
        local = []
    names = local or ["trip-brief"]
    track_event("skill_read", {"action": "skills_list", "count": len(names)})
    return json.dumps({"skills": names, "source": "github+local"}, indent=2)

@mcp.tool()
def skill_read(name: str) -> str:
    """Fetch SKILL.md by name from GitHub, fallback to local file."""
    t0 = time.perf_counter()
    safe = "".join(c for c in name if c.isalnum() or c in ("_", "-"))
    if not safe:
        out = "[INPUT_FIXABLE] Empty skill name. Call skills_list first."; _track("skill_read", t0, "error", 0, out, None, "ValidationError", out); return out
    try:
        with urllib.request.urlopen(f"{SKILLS_URL}/{safe}.md", timeout=5) as r:
            text = r.read().decode("utf-8", "replace")
        _track("skill_read", t0, "success", 1, text); return text
    except Exception:
        p = Path(__file__).parent.parent.parent / "skills" / f"{safe}.md"
        if p.exists():
            text = p.read_text(encoding="utf-8"); _track("skill_read", t0, "success", 1, text); return text
        out = f"[INPUT_FIXABLE] Unknown skill '{name}'. Candidates: call skills_list. If network is blocked: [TRANSIENT] retry, or [ENVIRONMENT_FIXABLE: STOP & ASK HUMAN] if GitHub is unreachable from this host."
        _track("skill_read", t0, "error", 0, out, None, "NotFoundError", out); return out

@mcp.tool()
def check_for_updates() -> str:
    """Check PyPI for newer versions of flight-planner-mcp and get upgrade instructions."""
    res = check_server_update("flight-planner-mcp", MCP_SERVER_VERSION, force_check=True)
    return json.dumps(res, indent=2)

def main():
    mcp.run()
if __name__ == "__main__":
    main()
