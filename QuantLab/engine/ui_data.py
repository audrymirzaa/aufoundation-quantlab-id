from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from .formats import RESAMPLE_RULE, PERIOD_LABEL, annualize_return, format_percent, normalize_period
from .metrics import AssetMetrics

FIELD_LABELS = {
    "return": "Return %",
    "change": "Change %",
    "close": "Close",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "volume": "Volume",
}
FIELD_ORDER = ["return", "change", "close", "open", "high", "low", "volume"]

PERIOD_ORDER = {"D": 0, "W": 1, "M": 2}


def allowed_periods(source_period: str) -> list[str]:
    source = normalize_period(source_period)
    return [period for period in ("D", "W", "M") if PERIOD_ORDER[period] >= PERIOD_ORDER[source]]


def dataset_code_from_filename(filename: str) -> str:
    lower = filename.lower()
    known = {
        "indofood": "INDF",
        "mds retailing": "LPPF",
        "antam": "ANTM",
        "bank central asia": "BBCA",
        "bank negara indonesia": "BBNI",
        "bank rakyat": "BBRI",
        "telkom": "TLKM",
    }
    for keyword, code in known.items():
        if keyword in lower:
            return code
    if "composite" in lower or "ihsg" in lower:
        return "IHSG"
    stem = Path(filename).stem
    stem = re.sub(r"\(.*?\)", " ", stem)
    for junk in ("Stock Price History", "Historical Data", "Data Historis"):
        stem = stem.replace(junk, " ")
    tokens = [token for token in re.split(r"[^A-Za-z0-9]+", stem) if token]
    if not tokens:
        return "ASSET"
    return tokens[0].upper()


def resample_price_frame(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    normalized = normalize_period(period)
    if normalized == "D":
        return frame.copy()
    rule = RESAMPLE_RULE[normalized]
    aggregation: dict[str, str] = {}
    for column in frame.columns:
        if column.endswith("_open"):
            aggregation[column] = "first"
        elif column.endswith("_high"):
            aggregation[column] = "max"
        elif column.endswith("_low"):
            aggregation[column] = "min"
        elif column.endswith("_volume"):
            aggregation[column] = "sum"
        elif column.endswith("_change"):
            continue
        else:
            aggregation[column] = "last"
    if not aggregation:
        return frame.iloc[0:0]
    return frame.resample(rule).agg(aggregation)


def build_display_frame(
    returns: pd.DataFrame,
    frames: Mapping[str, pd.DataFrame],
    fields: Sequence[str],
    change_labels: Mapping[str, bool] | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    change_labels = change_labels or {}
    index = pd.DatetimeIndex(returns.index)
    output = pd.DataFrame({"Tanggal": index})
    percent_columns: list[str] = []
    volume_columns: list[str] = []
    for instrument in returns.columns:
        frame = frames.get(instrument)
        for field in fields:
            if field not in FIELD_LABELS:
                continue
            label = FIELD_LABELS[field]
            series = None
            if field == "return":
                series = returns[instrument]
                if change_labels.get(instrument):
                    label = "Change %"
            elif field == "change":
                if frame is not None:
                    series = frame.get(f"{instrument}_change")
            elif field == "close":
                if frame is not None:
                    series = frame.get(instrument)
            else:
                if frame is not None:
                    series = frame.get(f"{instrument}_{field}")
            if series is None:
                continue
            column_name = f"{instrument} {label}"
            if column_name in output.columns:
                continue
            output[column_name] = pd.Series(series).reindex(index).to_numpy()
            if field in ("return", "change"):
                percent_columns.append(column_name)
            if field == "volume":
                volume_columns.append(column_name)
    return output, percent_columns, volume_columns


def format_number(value: float | None, decimals: int = 2, locale: str = "id") -> str:
    if value is None:
        return "N/A"
    try:
        if pd.isna(value):
            return "N/A"
    except (TypeError, ValueError):
        return "N/A"
    text = f"{value:,.{decimals}f}"
    if locale == "id":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text


def metrics_table(
    results: Mapping[str, AssetMetrics],
    *,
    annualized: bool = False,
    locale: str = "id",
    decimals: int = 2,
) -> pd.DataFrame:
    rows = []
    for name, result in results.items():
        er_market = annualize_return(result.er_market, result.period) if annualized else result.er_market
        erp = annualize_return(result.erp, result.period) if annualized else result.erp
        capm_value = result.capm_annual if annualized else result.capm
        mean_value = result.mean_annual if annualized else result.mean_return
        alpha_value = result.alpha_annual if annualized else result.alpha
        if alpha_value is None:
            verdict = "N/A"
        elif alpha_value > 0:
            verdict = "Outperform"
        else:
            verdict = "Underperform"
        rows.append(
            {
                "Saham": name,
                "n": result.n,
                "Beta": format_number(result.beta, 3, locale),
                "Kategori Beta": result.beta_category,
                "E(Rm)": format_percent(er_market, decimals, locale),
                "ERP": format_percent(erp, decimals, locale),
                "CAPM": format_percent(capm_value, decimals, locale),
                "Avg Return": format_percent(mean_value, decimals, locale),
                "Alpha": format_percent(alpha_value, decimals, locale),
                "Putusan": verdict,
            }
        )
    return pd.DataFrame(rows)


def risk_table(
    results: Mapping[str, AssetMetrics],
    *,
    locale: str = "id",
    decimals: int = 2,
) -> pd.DataFrame:
    rows = []
    for name, result in results.items():
        if result.cv is None:
            cv_text = "N/A"
            status = "Tidak valid (mean <= 0)" if not result.cv_valid else "Tidak tersedia"
        else:
            cv_text = format_number(result.cv, 2, locale)
            if result.legacy and not result.cv_valid:
                status = "Legacy: negatif, bukan ukuran efisiensi"
            elif result.cv_valid:
                status = "Valid"
            else:
                status = "Perlu dicek"
        rows.append(
            {
                "Saham": name,
                "SD Periode": format_percent(result.sd, decimals, locale),
                "SD Annual": format_percent(result.sd_annual, decimals, locale),
                "CV": cv_text,
                "Status CV": status,
                "Beta": format_number(result.beta, 3, locale),
            }
        )
    return pd.DataFrame(rows)


def correlation_table(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.corr().round(4)


def medians_display(medians: pd.DataFrame, locale: str = "id", decimals: int = 2) -> pd.DataFrame:
    if medians.empty:
        return medians
    output = medians.copy()
    for column in ("roe_median", "pbv_median", "cr_median"):
        if column not in output.columns:
            continue
        if column == "roe_median":
            output[column] = output[column].map(lambda value: format_percent(value, decimals, locale))
        else:
            output[column] = output[column].map(lambda value: format_number(value, decimals, locale))
    output = output.rename(
        columns={
            "sector": "Sektor",
            "roe_median": "ROE Median",
            "pbv_median": "PBV Median",
            "cr_median": "CR Median",
            "n": "Peer",
            "enough_peers": "Peer Cukup",
        }
    )
    return output


def quadrant_display(frame: pd.DataFrame, locale: str = "id", decimals: int = 2) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    for column in ("ROE", "ROE Median", "Alpha"):
        if column in output.columns:
            output[column] = output[column].map(lambda value: format_percent(value, decimals, locale))
    for column in ("PBV", "PBV Median", "CR", "CR Median"):
        if column in output.columns:
            output[column] = output[column].map(lambda value: format_number(value, decimals, locale))
    return output


def frames_to_excel(
    sheets: Mapping[str, pd.DataFrame],
    percent_columns: Mapping[str, Sequence[str]] | None = None,
) -> bytes:
    percent_columns = percent_columns or {}
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            safe_name = sheet_name[:31]
            pd.DataFrame(frame).to_excel(writer, sheet_name=safe_name, index=False)
            worksheet = writer.sheets[safe_name]
            for column_index, column in enumerate(frame.columns, start=1):
                if column == "Tanggal":
                    for row in range(2, len(frame) + 2):
                        worksheet.cell(row=row, column=column_index).number_format = "yyyy-mm-dd"
                if column in percent_columns.get(sheet_name, []):
                    for row in range(2, len(frame) + 2):
                        worksheet.cell(row=row, column=column_index).number_format = "0.00%"
    return buffer.getvalue()


def source_note(source_period: str, target_period: str, mode: str) -> str:
    source_label = PERIOD_LABEL[normalize_period(source_period)]
    target_label = PERIOD_LABEL[normalize_period(target_period)]
    if normalize_period(source_period) != normalize_period(target_period):
        return f"Sumber {source_label}, analisa {target_label}: return dihitung dari harga."
    if mode == "change":
        return f"Sumber {source_label}: memakai kolom Change % dari file."
    return f"Sumber {source_label}: return dihitung dari harga."


def merge_datasets(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged.update(incoming)
    return merged
