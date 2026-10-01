"""Build full OurAirports bundle (~9k rows) + trimmed OpenFlights routes. Stdlib only, no keys."""
from __future__ import annotations
import csv, io, json, urllib.request
from pathlib import Path

AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
ROUTES_DAT = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
OUT = Path(__file__).resolve().parent.parent / "src" / "flight_planner_mcp" / "data"

def get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    csv_text = get(AIRPORTS_CSV)
    airports, seen = [], set()
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("type") not in ("large_airport", "medium_airport"):
            continue
        iata = (row.get("iata_code") or "").strip().upper()
        if not iata or iata in seen:
            continue
        try:
            lat, lon = float(row["latitude_deg"]), float(row["longitude_deg"])
        except (ValueError, KeyError):
            continue
        ident = (row.get("ident") or "").strip().upper()
        seen.add(iata)
        airports.append({"iata": iata, "icao": ident or iata,
            "name": (row.get("name") or iata).strip(), "city": (row.get("municipality") or "").strip() or iata,
            "country": (row.get("iso_country") or "").strip(), "lat": round(lat, 4), "lon": round(lon, 4),
            "size": "large" if row["type"] == "large_airport" else "medium"})
    airports.sort(key=lambda a: a["iata"])
    valid = {a["iata"] for a in airports} | {a["icao"] for a in airports}
    icao2iata = {}
    for a in airports:
        icao2iata.setdefault(a["icao"], a["iata"])
    pairs: dict[tuple[str, str], set[str]] = {}
    for line in get(ROUTES_DAT).splitlines():
        p = [c.strip() for c in line.split(",")]
        if len(p) < 8:
            continue
        al, s, d = (p[0] or "?").strip().upper(), p[2].strip().upper(), p[4].strip().upper()
        if s not in valid or d not in valid:
            continue
        s, d = icao2iata.get(s, s), icao2iata.get(d, d)
        if s == d:
            continue
        pairs.setdefault((s, d), set()).add(al or "?")
    norm = [{"from": s, "to": d, "airlines": sorted(v)} for (s, d), v in sorted(pairs.items())]
    (OUT / "airports.json").write_text(json.dumps(airports), encoding="utf-8")
    (OUT / "routes.json").write_text(json.dumps(norm), encoding="utf-8")
    ap = (OUT / "airports.json").stat().st_size / 1024
    rt = (OUT / "routes.json").stat().st_size / 1024
    print(f"airports={len(airports)} ({ap:.0f}KB) routes={len(norm)} ({rt:.0f}KB)")
    print("sources: OurAirports CC0 airports.csv (large+medium, IATA only); OpenFlights routes.dat 2014-vintage static fallback, date disclosed in route_check note.")

if __name__ == "__main__":
    main()
