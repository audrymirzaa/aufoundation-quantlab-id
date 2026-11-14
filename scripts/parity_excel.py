from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import csv_io, metrics


def load_return_table(path: str, market: str | None) -> tuple[pd.DataFrame, str]:
    parsed = csv_io.read_csv(path)
    suggested = csv_io.suggest_mapping(parsed)
    date_column = suggested["date_column"] or parsed.frame.columns[0]
    decimal = parsed.detection.decimal
    thousands = parsed.detection.thousands
    day_first = decimal == ","
    dates = csv_io.parse_date_series(
        parsed.frame[date_column],
        fmt=parsed.detection.date_format,
        day_first=day_first,
    )
    columns: dict[str, pd.Series] = {}
    for column in parsed.frame.columns:
        if column == date_column:
            continue
        values = parsed.frame[column].map(
            lambda value: csv_io.parse_number(value, decimal=decimal, thousands=thousands)
        )
        if values.notna().mean() < 0.8:
            continue
        values = values.astype(float)
        if values.abs().max() > 1.5:
            values = values / 100.0
        columns[column] = values
    frame = pd.DataFrame({name: values.to_numpy() for name, values in columns.items()}, index=pd.DatetimeIndex(dates))
    frame = frame.dropna(how="all").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if market is None:
        market = next(iter(frame.columns))
    elif market not in frame.columns:
        raise KeyError(f"Kolom pasar {market!r} tidak ada. Pilihan: {list(frame.columns)}")
    return frame, market


def format_row(label: str, result: metrics.AssetMetrics) -> str:
    beta = "N/A" if result.beta is None else f"{result.beta:.3f}"
    cv = "N/A" if result.cv is None else f"{result.cv:.2f}"
    return (
        f"{label:14s} n={result.n:3d} beta={beta:>6s} mean={result.mean_return * 100:8.3f}% "
        f"sd={result.sd * 100:8.3f}% cv={cv:>7s} capm={result.capm * 100 if result.capm is not None else float('nan'):8.3f}% "
        f"alpha={result.alpha * 100 if result.alpha is not None else float('nan'):8.3f}%"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Bandingkan hasil engine dengan panel Excel (mode legacy vs corrected).")
    parser.add_argument("csv_path")
    parser.add_argument("--market", default=None, help="Nama kolom benchmark, mis. IHSG")
    parser.add_argument("--rf", type=float, default=0.06, help="Risk-free tahunan, mis. 0.06")
    parser.add_argument("--period", default="D", choices=["D", "W", "M"])
    parser.add_argument("--er-market", type=float, default=None, help="Override E(Rm) periode, mis. -0.008")
    args = parser.parse_args()

    frame, market = load_return_table(args.csv_path, args.market)
    print(f"File       : {args.csv_path}")
    print(f"Obs        : {len(frame)}")
    print(f"Benchmark  : {market}")
    print(f"Periode    : {args.period}")
    print(f"Rf tahunan : {args.rf * 100:.2f}%")
    print()
    for mode, legacy in (("LEGACY (seperti Excel)", True), ("CORRECTED", False)):
        print(mode)
        for column in frame.columns:
            if column == market:
                continue
            pair = pd.concat({"stock": frame[column], "market": frame[market]}, axis=1).dropna()
            result = metrics.analyze_asset(
                pair["stock"],
                pair["market"],
                instrument=column,
                rf_annual=args.rf,
                period=args.period,
                legacy=legacy,
                er_market_override=args.er_market,
            )
            print(format_row(column, result))
        print()


if __name__ == "__main__":
    main()
