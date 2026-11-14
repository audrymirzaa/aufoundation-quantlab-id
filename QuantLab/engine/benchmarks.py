from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from . import csv_io
from .metrics import AssetMetrics, classify_quadrant

FUNDAMENTAL_COLUMNS = ["ticker", "sector", "roe", "pbv", "cr", "as_of"]
METRIC_COLUMNS = ["roe", "pbv", "cr"]

HEADER_ALIASES = {
    "ticker": {"ticker", "kode", "saham", "code", "symbol", "emiten"},
    "sector": {"sector", "sektor", "industri", "industry"},
    "roe": {"roe", "returnonequity", "returnonequitiy"},
    "pbv": {"pbv", "pb", "pricebookvalue", "pricebook"},
    "cr": {"cr", "currentratio", "rasiolancar", "current"},
    "name": {"name", "nama", "perusahaan", "company"},
}


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    for column in frame.columns:
        normalized = _norm_header(column)
        for canonical, aliases in HEADER_ALIASES.items():
            if normalized in aliases:
                mapping[column] = canonical
                break
    renamed = frame.rename(columns=mapping)
    return renamed.loc[:, ~renamed.columns.duplicated()]


def load_fundamentals(
    data: Any,
    *,
    roe_percent: bool = True,
    decimal: str | None = None,
    thousands: str | None = None,
) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        frame = data.copy()
        dec = decimal or "."
        thou = thousands or ","
    else:
        parsed = csv_io.read_csv(data, decimal=decimal, thousands=thousands)
        frame = parsed.frame.copy()
        dec = parsed.detection.decimal
        thou = parsed.detection.thousands
    frame = _canonical_columns(frame)
    for required in ("ticker", "sector"):
        if required not in frame.columns:
            raise ValueError(f"Kolom wajib '{required}' tidak ditemukan. Kolom tersedia: {list(frame.columns)}")
    for column in METRIC_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
        frame[column] = frame[column].map(lambda value: csv_io.parse_number(value, decimal=dec, thousands=thou))
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "name" not in frame.columns:
        frame["name"] = ""
    if "as_of" not in frame.columns:
        frame["as_of"] = ""
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["sector"] = frame["sector"].astype(str).str.strip()
    frame["as_of"] = frame["as_of"].astype(str).str.strip()
    frame = frame[frame["ticker"].ne("") & frame["ticker"].ne("NAN")]
    frame = frame[frame["sector"].ne("") & frame["sector"].ne("NAN")]
    if frame["roe"].notna().any() and roe_percent:
        frame["roe"] = frame["roe"] / 100.0
    frame = frame.drop_duplicates(subset=["ticker"], keep="last")
    columns = ["ticker", "sector", "roe", "pbv", "cr", "as_of", "name"]
    return frame[columns].reset_index(drop=True)


def _normalize_fundamental_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = FUNDAMENTAL_COLUMNS + ["name"]
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=columns)
    output = frame.copy()
    for column in columns:
        if column not in output.columns:
            output[column] = None
    output["ticker"] = output["ticker"].astype(str).str.strip().str.upper()
    for column in ("roe", "pbv", "cr"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    for column in ("sector", "as_of", "name"):
        output[column] = output[column].astype(str).str.strip().replace({"nan": "", "None": ""})
    output = output[output["ticker"].ne("") & output["ticker"].ne("NAN")]
    return output[columns].drop_duplicates(subset=["ticker"], keep="last").reset_index(drop=True)


def merge_fundamentals(
    existing: pd.DataFrame | None,
    incoming: pd.DataFrame | None,
    *,
    overwrite: bool = False,
) -> pd.DataFrame:
    base = _normalize_fundamental_frame(existing)
    fresh = _normalize_fundamental_frame(incoming)
    if fresh.empty:
        return base
    rows = base.to_dict("records")
    index = {row["ticker"]: position for position, row in enumerate(rows)}
    for fresh_row in fresh.to_dict("records"):
        code = fresh_row["ticker"]
        if code not in index:
            rows.append(fresh_row)
            index[code] = len(rows) - 1
            continue
        row = rows[index[code]]
        changed = False
        for metric in METRIC_COLUMNS:
            value = fresh_row.get(metric)
            if pd.isna(value):
                continue
            if overwrite or pd.isna(row.get(metric)):
                row[metric] = value
                changed = True
        if not row.get("sector") and fresh_row.get("sector"):
            row["sector"] = fresh_row["sector"]
        if not row.get("name") and fresh_row.get("name"):
            row["name"] = fresh_row["name"]
        if changed or not row.get("as_of"):
            row["as_of"] = fresh_row.get("as_of") or row.get("as_of", "")
    return pd.DataFrame(rows, columns=FUNDAMENTAL_COLUMNS + ["name"]).reset_index(drop=True)


def sector_medians(fundamentals: pd.DataFrame, min_peers: int = 2) -> pd.DataFrame:
    empty = pd.DataFrame(
        columns=["sector", "roe_median", "pbv_median", "cr_median", "n", "enough_peers"]
    )
    if fundamentals.empty:
        return empty
    grouped = fundamentals.groupby("sector")
    medians = grouped[["roe", "pbv", "cr"]].median().rename(
        columns={"roe": "roe_median", "pbv": "pbv_median", "cr": "cr_median"}
    )
    counts = grouped["ticker"].nunique().rename("n")
    result = medians.join(counts).reset_index()
    result["enough_peers"] = result["n"] >= min_peers
    return result[["sector", "roe_median", "pbv_median", "cr_median", "n", "enough_peers"]]


def classify_fundamentals(
    fundamentals: pd.DataFrame,
    medians: pd.DataFrame,
    min_peers: int = 2,
) -> pd.DataFrame:
    if fundamentals.empty:
        return fundamentals.assign(
            roe_vs=pd.Series(dtype="object"),
            pbv_vs=pd.Series(dtype="object"),
            cr_vs=pd.Series(dtype="object"),
            score=pd.Series(dtype="float"),
            comparisons=pd.Series(dtype="float"),
            peer_n=pd.Series(dtype="float"),
            fundamental_above=pd.Series(dtype="object"),
            notes=pd.Series(dtype="object"),
        )
    merged = fundamentals.merge(medians, on="sector", how="left")
    rows = []
    for _, row in merged.iterrows():
        score = 0
        comparisons = 0
        verdicts: dict[str, str] = {}
        rules = {
            "roe": (True, row.get("roe"), row.get("roe_median")),
            "pbv": (False, row.get("pbv"), row.get("pbv_median")),
            "cr": (True, row.get("cr"), row.get("cr_median")),
        }
        for metric, (higher_is_better, value, median) in rules.items():
            if pd.isna(value) or pd.isna(median):
                verdicts[f"{metric}_vs"] = "N/A"
                continue
            comparisons += 1
            if metric == "cr":
                better = value >= median
            elif higher_is_better:
                better = value > median
            else:
                better = value < median
            if better:
                score += 1
            verdicts[f"{metric}_vs"] = "Di atas median" if better else "Di bawah median"
        peer_n = row.get("n")
        enough = pd.notna(peer_n) and peer_n >= min_peers
        if not enough or comparisons == 0:
            above = None
        else:
            threshold = comparisons // 2 + 1
            above = score >= threshold
        notes = []
        if not enough:
            notes.append(f"Butuh minimal {min_peers} peer satu sektor")
        if comparisons < 3:
            notes.append(f"Data fundamental {comparisons}/3")
        rows.append(
            {
                **row.to_dict(),
                **verdicts,
                "score": score,
                "comparisons": comparisons,
                "peer_n": peer_n,
                "fundamental_above": above,
                "notes": "; ".join(notes),
            }
        )
    return pd.DataFrame(rows)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def quadrant_table(
    fundamentals: pd.DataFrame,
    medians: pd.DataFrame,
    results: Mapping[str, AssetMetrics],
    min_peers: int = 2,
) -> pd.DataFrame:
    if fundamentals.empty:
        return pd.DataFrame()
    classified = classify_fundamentals(fundamentals, medians, min_peers)
    rows = []
    for _, row in classified.iterrows():
        ticker = str(row["ticker"]).upper()
        result = results.get(ticker)
        alpha = result.alpha if result is not None else None
        raw_above = row["fundamental_above"]
        above = None if _is_missing(raw_above) else bool(raw_above)
        if above is None:
            quadrant = {
                "quadrant": "Tidak tersedia",
                "business": "Data belum cukup",
                "market": "Tidak dapat dinilai",
                "action": "Lengkapi data",
            }
        elif result is None:
            quadrant = {
                "quadrant": "Tidak tersedia",
                "business": "Fundamental ada",
                "market": "Data return tidak ada",
                "action": "Muat data harga",
            }
        else:
            quadrant = classify_quadrant(bool(above), alpha)
        rows.append(
            {
                "Ticker": ticker,
                "Sektor": row["sector"],
                "ROE": row.get("roe"),
                "PBV": row.get("pbv"),
                "CR": row.get("cr"),
                "ROE Median": row.get("roe_median"),
                "PBV Median": row.get("pbv_median"),
                "CR Median": row.get("cr_median"),
                "Peer": row.get("peer_n"),
                "Skor": row.get("score"),
                "Fundamental": "Di atas median" if above is True else ("Di bawah median" if above is False else "N/A"),
                "Alpha": alpha,
                "Kuadran": quadrant["quadrant"],
                "Aksi": quadrant["action"],
                "Catatan": row.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def template_fundamentals(tickers: list[str], sector_map: Mapping[str, str] | None = None) -> pd.DataFrame:
    sector_map = sector_map or {}
    upper_map = {str(key).upper(): value for key, value in sector_map.items()}
    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    rows = []
    for ticker in tickers:
        code = str(ticker).upper()
        rows.append(
            {
                "ticker": code,
                "sector": upper_map.get(code, ""),
                "roe": None,
                "pbv": None,
                "cr": None,
                "as_of": today,
            }
        )
    return pd.DataFrame(rows, columns=FUNDAMENTAL_COLUMNS)


def load_sector_map(path: str | Path) -> dict[str, str]:
    source = Path(path)
    if not source.exists():
        return {}
    frame = pd.read_csv(source)
    frame = _canonical_columns(frame)
    if "ticker" not in frame.columns or "sector" not in frame.columns:
        return {}
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["sector"] = frame["sector"].astype(str).str.strip()
    return dict(zip(frame["ticker"], frame["sector"]))


def save_fundamentals(frame: pd.DataFrame, path: str | Path, roe_percent: bool = True) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    for column in FUNDAMENTAL_COLUMNS:
        if column not in output.columns:
            output[column] = None
    if roe_percent and "roe" in output.columns:
        output["roe"] = output["roe"] * 100.0
    if "name" in output.columns:
        columns = FUNDAMENTAL_COLUMNS + ["name"]
    else:
        columns = FUNDAMENTAL_COLUMNS
    output = output[columns]
    output.to_csv(destination, index=False)
    return destination
