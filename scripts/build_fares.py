"""Build latest-available-snapshot US fare baseline from BTS DB1B/DB1C Market files.

Usage:
    python3 scripts/build_fares.py /tmp/DB1C.MARKET.202606.16SEP2026.parquet
    python3 scripts/build_fares.py /tmp/bts/market_2025_1.zip /tmp/bts/market_2025_2.zip

Reads TranStats / BTS Market data:
    - DB1C Market (.parquet, .zip, .csv): 40% sample, MktAmount, MktCarrier, MktGeoType=='2'
    - DB1B Market (.zip, .csv): 10% sample, MktFare, TkCarrier, MktGeoType=='2', BulkFare==0
    - Suppresses routes with n < 50 sampled tickets (emits nothing, not a guess)

Output (packaged data dir, same pattern as airports.json/routes.json):
    src/flight_planner_mcp/data/fares-us-rolling.json   {vintage, months, route_count, routes:{...}}
    src/flight_planner_mcp/data/fares-VINTAGE.txt       one-line vintage stamp
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

MIN_N = 50  # suppression floor: sampled tickets per directional route
DATA_OUT = Path(__file__).resolve().parent.parent / "src" / "flight_planner_mcp" / "data"

try:
    import duckdb
except ImportError:
    duckdb = None


def _label_db1b(name: str) -> str:
    stem = Path(name).stem.replace("Origin_and_Destination_Survey_DB1BMarket_", "")
    m = re.search(r"(\d{4})[_-]?[Qq]?(\d)", stem)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    return stem


def _label_db1c(name: str) -> str:
    stem = Path(name).stem
    m = re.search(r"(\d{4})(\d{2})", stem)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return stem


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


def _process_parquet(p: Path, fares: dict, carriers: dict, months: list[str]) -> tuple[int, int, str]:
    if duckdb is None:
        sys.exit("Error: duckdb is required to process .parquet files. Run with: uv run --with duckdb python ...")
    con = duckdb.connect()
    cols = [c[0].lower() for c in con.execute("DESCRIBE SELECT * FROM parquet_scan(?) LIMIT 1", [str(p)]).fetchall()]

    if "rpyear" in cols and "rpmonth" in cols:
        m_rows = con.execute(
            "SELECT DISTINCT RpYear, RpMonth FROM parquet_scan(?) WHERE RpYear IS NOT NULL ORDER BY RpYear, RpMonth",
            [str(p)],
        ).fetchall()
        for y, m in m_rows:
            months.append(f"{y}-{int(m):02d}")
    else:
        months.append(_label_db1c(p.name))

    v_col = "v_yield" if "v_yield" in cols else ("vyield" if "vyield" in cols else None)
    has_v1 = False
    if v_col:
        check = con.execute(f"SELECT 1 FROM parquet_scan(?) WHERE {v_col} = 1 LIMIT 1", [str(p)]).fetchone()
        if check is not None:
            has_v1 = True

    v_filter = f"{v_col} = 1 AND " if has_v1 else ""
    carrier_col = "MktCarrier" if "mktcarrier" in cols else ("TkCarrier" if "tkcarrier" in cols else "RPCarrier")

    q_fares = f"""
    SELECT 
        Origin, Dest,
        CAST(round(MktAmount) AS INT) as fare,
        SUM(CAST(round(COALESCE(Passengers, 1)) AS INT)) as pax
    FROM parquet_scan(?)
    WHERE MktGeoType = 2
      AND {v_filter}MktAmount > 0
      AND COALESCE(Passengers, 1) > 0
      AND length(Origin) = 3
      AND length(Dest) = 3
    GROUP BY Origin, Dest, fare
    """
    q_carriers = f"""
    SELECT 
        Origin, Dest, COALESCE({carrier_col}, '?') as carrier,
        SUM(CAST(round(COALESCE(Passengers, 1)) AS INT)) as pax
    FROM parquet_scan(?)
    WHERE MktGeoType = 2
      AND {v_filter}MktAmount > 0
      AND COALESCE(Passengers, 1) > 0
      AND length(Origin) = 3
      AND length(Dest) = 3
    GROUP BY Origin, Dest, carrier
    """

    t_seen = con.execute("SELECT COUNT(*) FROM parquet_scan(?)", [str(p)]).fetchone()[0]
    t_kept = con.execute(
        f"SELECT COUNT(*) FROM parquet_scan(?) WHERE MktGeoType = 2 AND {v_filter}MktAmount > 0 AND COALESCE(Passengers, 1) > 0 AND length(Origin) = 3 AND length(Dest) = 3",
        [str(p)],
    ).fetchone()[0]

    for o, d, f, pax in con.execute(q_fares, [str(p)]).fetchall():
        fares.setdefault((o, d), Counter())[f] += pax
    for o, d, c, pax in con.execute(q_carriers, [str(p)]).fetchall():
        carriers.setdefault((o, d), Counter())[c] += pax

    return t_seen, t_kept, "db1c"


def _process_csv_stream(f_stream, csv_name: str, fares: dict, carriers: dict, months: list[str]) -> tuple[int, int, str]:
    r = csv.reader(io.TextIOWrapper(f_stream, encoding="utf-8", errors="replace"))
    hdr = [c.strip('"') for c in next(r)]
    hdr_lower = [c.lower() for c in hdr]

    is_db1c = "mktamount" in hdr_lower
    sample_type = "db1c" if is_db1c else "db1b"

    if is_db1c:
        months.append(_label_db1c(csv_name))
        io_ = hdr_lower.index("origin")
        id_ = hdr_lower.index("dest")
        ic_ = hdr_lower.index("mktcarrier") if "mktcarrier" in hdr_lower else (hdr_lower.index("tkcarrier") if "tkcarrier" in hdr_lower else None)
        im_ = hdr_lower.index("mktamount")
        ig_ = hdr_lower.index("mktgeotype")
        ip_ = hdr_lower.index("passengers") if "passengers" in hdr_lower else None
        iv_ = hdr_lower.index("v_yield") if "v_yield" in hdr_lower else (hdr_lower.index("vyield") if "vyield" in hdr_lower else None)

        seen = kept = 0
        for row in r:
            seen += 1
            if row[ig_] != "2":
                continue
            try:
                fare = float(row[im_])
                pax = int(float(row[ip_])) if ip_ is not None and row[ip_] else 1
            except (ValueError, IndexError):
                continue
            if fare <= 0 or pax <= 0:
                continue
            o, d = row[io_].strip().upper(), row[id_].strip().upper()
            if len(o) != 3 or len(d) != 3:
                continue
            key = (o, d)
            fares.setdefault(key, Counter())[int(round(fare))] += pax
            c_code = row[ic_].strip().upper() if ic_ is not None else "?"
            carriers.setdefault(key, Counter())[c_code or "?"] += pax
            kept += 1
        return seen, kept, sample_type
    else:
        months.append(_label_db1b(csv_name))
        io_, id_, it_, ib_, ip_, im_, ig_ = (hdr.index(c) for c in
            ("Origin", "Dest", "TkCarrier", "BulkFare", "Passengers", "MktFare", "MktGeoType"))
        seen = kept = 0
        for row in r:
            seen += 1
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
            kept += 1
        return seen, kept, sample_type


def main(file_paths: list[str]) -> None:
    fares: dict[tuple[str, str], Counter] = {}
    carriers: dict[tuple[str, str], Counter] = {}
    months: list[str] = []
    sample_types: set[str] = set()
    rows_seen = rows_kept = 0

    for fp_str in file_paths:
        p = Path(fp_str)
        if not p.exists():
            sys.exit(f"File not found: {p}")

        if p.suffix.lower() == ".parquet":
            seen, kept, st = _process_parquet(p, fares, carriers, months)
            rows_seen += seen
            rows_kept += kept
            sample_types.add(st)
        elif zipfile.is_zipfile(p):
            z = zipfile.ZipFile(p)
            namelist = z.namelist()
            parquet_names = [n for n in namelist if n.endswith(".parquet")]
            csv_names = [n for n in namelist if n.endswith(".csv")]
            if parquet_names:
                p_name = parquet_names[0]
                with tempfile.TemporaryDirectory() as td:
                    extracted = z.extract(p_name, td)
                    seen, kept, st = _process_parquet(Path(extracted), fares, carriers, months)
                    rows_seen += seen
                    rows_kept += kept
                    sample_types.add(st)
            elif csv_names:
                c_name = csv_names[0]
                with z.open(c_name) as f:
                    seen, kept, st = _process_csv_stream(f, c_name, fares, carriers, months)
                    rows_seen += seen
                    rows_kept += kept
                    sample_types.add(st)
            else:
                sys.exit(f"No .parquet or .csv found in {p}")
        elif p.suffix.lower() == ".csv":
            with open(p, "rb") as f:
                seen, kept, st = _process_csv_stream(f, p.name, fares, carriers, months)
                rows_seen += seen
                rows_kept += kept
                sample_types.add(st)
        else:
            sys.exit(f"Unsupported file format: {p}")

    months = sorted(set(months))
    if "db1c" in sample_types:
        vintage = f"DB1C Market {', '.join(months)} (40% ticket sample, USD, passenger-weighted)"
    else:
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
        routes[f"{o}-{d}"] = {
            "median": _wquant(sf, cum, n, 0.5),
            "p25": _wquant(sf, cum, n, 0.25),
            "p75": _wquant(sf, cum, n, 0.75),
            "n": n,
            "carriers": top,
        }

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
        sys.exit("usage: build_fares.py <market-file> [<market-file> ...]")
    main(sys.argv[1:])
