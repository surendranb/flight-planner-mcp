"""Build latest-available-snapshot US fare baseline from BTS DB1B Market bulk zips. Stdlib only.

Usage:
    python3 scripts/build_fares.py /tmp/bts/market_2025_1.zip /tmp/bts/market_2025_2.zip

Reads TranStats PREZIP DB1B Market CSVs (Origin_and_Destination_Survey_DB1BMarket_*.csv),
true directional O&D, passenger-weighted fare quantiles per ORIG-DEST:
    - drops BulkFare != 0 and MktFare <= 0 (zero-fare / bulk artifacts)
    - keeps MktGeoType == '2' (domestic US markets; grounded: JFK-MCO/ATL-MCO rows carry '2')
    - suppresses routes with n < 50 sampled tickets (emits nothing, not a guess)

Output (packaged data dir, same pattern as airports.json/routes.json):
    src/flight_planner_mcp/data/fares-us-rolling.json   {vintage, months, route_count, routes:{...}}
    src/flight_planner_mcp/data/fares-VINTAGE.txt       one-line vintage stamp
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

MIN_N = 50  # suppression floor: sampled tickets per directional route
DATA_OUT = Path(__file__).resolve().parent.parent / "src" / "flight_planner_mcp" / "data"

# TranStats short names, e.g. Origin_and_Destination_Survey_DB1BMarket_2025_1.csv -> 2025-Q1
def _label(csv_name: str) -> str:
    stem = Path(csv_name).stem.replace("Origin_and_Destination_Survey_DB1BMarket_", "")
    y, q = stem.split("_")[:2]
    return f"{y}-Q{q}"


def _wquant(sorted_fares: list[int], cum: list[int], total: int, q: float) -> int:
    target = total * q
    lo, hi = 0, len(sorted_fares) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cum[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return sorted_fares[lo]


def main(zips: list[str]) -> None:
    fares: dict[tuple[str, str], Counter] = {}
    carriers: dict[tuple[str, str], Counter] = {}
    months: list[str] = []
    rows_seen = rows_kept = 0
    for zp in zips:
        z = zipfile.ZipFile(zp)
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        months.append(_label(csv_name))
        with z.open(csv_name) as f:
            r = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
            hdr = [c.strip('"') for c in next(r)]
            io_, id_, it_, ib_, ip_, im_, ig_ = (hdr.index(c) for c in
                ("Origin", "Dest", "TkCarrier", "BulkFare", "Passengers", "MktFare", "MktGeoType"))
            for row in r:
                rows_seen += 1
                if row[ig_] != "2":
                    continue
                try:
                    if float(row[ib_]) != 0:
                        continue
                    fare = float(row[im_])
                    pax = int(float(row[ip_]))
                except (ValueError, IndexError):
                    continue
                if fare <= 0 or pax <= 0:
                    continue
                o, d = row[io_].strip().upper(), row[id_].strip().upper()
                if len(o) != 3 or len(d) != 3:
                    continue
                key = (o, d)
                fares.setdefault(key, Counter())[int(round(fare))] += pax
                carriers.setdefault(key, Counter())[row[it_].strip().upper() or "?"] += pax
                rows_kept += 1
    months = sorted(set(months))
    vintage = f"DB1B Market {', '.join(months)} (10% ticket sample, USD, passenger-weighted)"
    routes: dict[str, dict] = {}
    for (o, d), fc in fares.items():
        n = sum(fc.values())
        if n < MIN_N:
            continue  # suppress: emit nothing, not a guess
        sf = sorted(fc)
        cum, run = [], 0
        for v in sf:
            run += fc[v]
            cum.append(run)
        cc = carriers[(o, d)]
        top = [{"code": c, "share": round(v / n, 3)} for c, v in cc.most_common(3)]
        routes[f"{o}-{d}"] = {"median": _wquant(sf, cum, n, 0.5),
            "p25": _wquant(sf, cum, n, 0.25), "p75": _wquant(sf, cum, n, 0.75),
            "n": n, "carriers": top}
    out = {"vintage": vintage, "months": months, "route_count": len(routes), "routes": routes}
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    p = DATA_OUT / "fares-us-rolling.json"
    p.write_text(json.dumps(out), encoding="utf-8")
    (DATA_OUT / "fares-VINTAGE.txt").write_text(vintage + "\n", encoding="utf-8")
    kb = p.stat().st_size / 1024
    print(f"months={months} rows_seen={rows_seen} rows_kept={rows_kept} "
          f"routes={len(routes)} file={kb:.0f}KB vintage='{vintage}'")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: build_fares.py <db1b-market-zip> [<db1b-market-zip> ...]")
    main(sys.argv[1:])
