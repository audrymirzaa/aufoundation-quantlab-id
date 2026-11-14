from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping as TypingMapping, Sequence

import pandas as pd

SUFFIX_SCALE = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
BLANK_TOKENS = {"", "-", "--", "—", "–", "N/A", "NA", "N/A.", "NAN", "NONE"}

DATE_FORMATS = (
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%m/%d/%y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d, %Y",
    "%d-%b-%Y",
    "%Y%m%d",
)

DAY_FIRST_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y")
MONTH_FIRST_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%b %d, %Y")

PRICE_HINTS = ("price", "last", "close", "terakhir", "penutupan", "harga", "kurs")
CHANGE_HINTS = ("change", "perubahan", "chg", "%")
VOLUME_HINTS = ("vol", "volume")
OPEN_HINTS = ("open", "pembukaan")
HIGH_HINTS = ("high", "tertinggi")
LOW_HINTS = ("low", "terendah")


@dataclass(frozen=True)
class Detection:
    encoding: str = "utf-8"
    delimiter: str = ","
    decimal: str = "."
    thousands: str = ","
    date_format: str | None = None


@dataclass
class ParsedCsv:
    frame: pd.DataFrame
    detection: Detection
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ColumnSpec:
    source: str
    target: str
    kind: str = "numeric"
    percent: bool = False
    scale: float = 1.0


@dataclass
class Mapping:
    instrument: str
    columns: list[ColumnSpec]
    date_format: str | None = None
    decimal: str | None = None
    thousands: str | None = None
    day_first: bool | None = None


def decode_bytes(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def _read_source(source: Any) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, Path):
        return source.read_bytes()
    if isinstance(source, str):
        if "\n" not in source and "\r" not in source and os.path.exists(source):
            return Path(source).read_bytes()
        return source.encode("utf-8")
    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, str):
            return data.encode("utf-8")
        return bytes(data)
    raise TypeError(f"Sumber CSV tidak didukung: {type(source)!r}")


def detect_delimiter(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()][:10]
    if not lines:
        return ","
    sample = "\n".join(lines)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {d: sum(line.count(d) for line in lines[:5]) for d in ",;\t|"}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def detect_decimal(text: str, delimiter: str) -> tuple[str, str]:
    if delimiter == ";":
        return ",", "."
    if delimiter == ",":
        return ".", ","
    comma_decimal = len(re.findall(r"\d,\d", text))
    dot_decimal = len(re.findall(r"\d\.\d", text))
    if comma_decimal > dot_decimal:
        return ",", "."
    return ".", ","


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip().upper() in BLANK_TOKENS


def parse_number(value: Any, decimal: str = ".", thousands: str = ",") -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return None
        return float(value)
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text or text.upper() in BLANK_TOKENS:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    scale = 1.0
    suffix = text[-1:].upper()
    if suffix in SUFFIX_SCALE:
        scale = SUFFIX_SCALE[suffix]
        text = text[:-1]
    if text.endswith("%"):
        text = text[:-1]
    text = text.lstrip("+")
    if text.startswith("-"):
        negative = True
        text = text[1:]
    if thousands and thousands != decimal:
        text = text.replace(thousands, "")
    if decimal and decimal != ".":
        text = text.replace(decimal, ".")
    else:
        text = text.replace(",", "")
    text = text.replace("_", "")
    if not text or text == ".":
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if negative:
        number = -number
    return number * scale


def _parse_ratio(values: Sequence[str], fmt: str) -> float:
    if not values:
        return 0.0
    ok = 0
    for value in values:
        try:
            datetime.strptime(str(value).strip(), fmt)
            ok += 1
        except (ValueError, TypeError):
            continue
    return ok / len(values)


def _day_first_hint(values: Sequence[str]) -> bool | None:
    firsts: list[int] = []
    seconds: list[int] = []
    for value in values:
        match = re.match(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-]\d{2,4}", str(value))
        if not match:
            continue
        firsts.append(int(match.group(1)))
        seconds.append(int(match.group(2)))
    if not firsts:
        return None
    if any(day > 12 for day in firsts):
        return True
    if any(month > 12 for month in seconds):
        return False
    return None


def detect_date_format(
    values: Sequence[Any],
    *,
    decimal: str = ".",
    day_first: bool | None = None,
) -> str | None:
    cleaned = [str(value).strip() for value in values if not _is_blank(value)][:200]
    if not cleaned:
        return None
    scores = {fmt: _parse_ratio(cleaned, fmt) for fmt in DATE_FORMATS}
    best = max(scores.values())
    if best <= 0:
        return None
    top = [fmt for fmt, score in scores.items() if score >= best - 1e-9]
    if len(top) > 1:
        hint = day_first
        if hint is None:
            hint = _day_first_hint(cleaned)
        if hint is None:
            hint = decimal == ","
        preferred = DAY_FIRST_FORMATS if hint else MONTH_FIRST_FORMATS
        for fmt in preferred:
            if fmt in top:
                return fmt
    return top[0]


def detect_date_format_from_frame(frame: pd.DataFrame, decimal: str = ".") -> str | None:
    best_format = None
    best_ratio = 0.0
    for column in frame.columns:
        values = [value for value in frame[column].dropna().tolist() if not _is_blank(value)][:200]
        if not values:
            continue
        fmt = detect_date_format(values, decimal=decimal)
        if not fmt:
            continue
        ratio = _parse_ratio([str(value).strip() for value in values], fmt)
        if ratio > best_ratio:
            best_ratio = ratio
            best_format = fmt
    return best_format if best_ratio >= 0.5 else None


def parse_date_series(series: pd.Series, fmt: str | None = None, day_first: bool = True) -> pd.Series:
    text = series.astype(str).str.strip()
    if fmt:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if parsed.notna().mean() >= 0.5:
            return parsed
    try:
        return pd.to_datetime(text, errors="coerce", dayfirst=day_first, format="mixed")
    except (TypeError, ValueError):
        return pd.to_datetime(text, errors="coerce", dayfirst=day_first)


def _clean_header(name: Any) -> str:
    return str(name).replace("\ufeff", "").strip()


def read_csv(
    source: Any,
    *,
    delimiter: str | None = None,
    decimal: str | None = None,
    thousands: str | None = None,
    date_format: str | None = None,
    encoding: str | None = None,
) -> ParsedCsv:
    data = _read_source(source)
    text, detected_encoding = decode_bytes(data)
    if encoding:
        text = data.decode(encoding)
        detected_encoding = encoding
    warnings: list[str] = []
    detected_delimiter = delimiter or detect_delimiter(text)
    auto_decimal, auto_thousands = detect_decimal(text, detected_delimiter)
    decimal = decimal or auto_decimal
    thousands = thousands or auto_thousands
    frame = pd.read_csv(
        io.StringIO(text),
        sep=detected_delimiter,
        dtype=str,
        skipinitialspace=True,
        engine="python",
        keep_default_na=False,
        na_values=[""],
    )
    frame = frame.dropna(how="all")
    frame.columns = [_clean_header(column) for column in frame.columns]
    frame = frame.loc[:, ~frame.columns.duplicated()]
    keep = [
        column
        for column in frame.columns
        if not (column.lower().startswith("unnamed") and frame[column].isna().all())
    ]
    if len(keep) != len(frame.columns):
        warnings.append("Kolom tanpa nama yang kosong dibuang.")
    frame = frame[keep]
    for column in frame.columns:
        frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)
    frame = frame.dropna(how="all")
    if frame.empty:
        raise ValueError("CSV tidak berisi baris data.")
    detected_date = date_format or detect_date_format_from_frame(frame, decimal=decimal)
    if detected_date is None:
        warnings.append("Format tanggal tidak terdeteksi otomatis; pilih manual.")
    return ParsedCsv(
        frame=frame,
        detection=Detection(
            encoding=detected_encoding,
            delimiter=detected_delimiter,
            decimal=decimal,
            thousands=thousands,
            date_format=detected_date,
        ),
        warnings=warnings,
    )


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9%]+", "", name.lower())


def _find_header(columns: Sequence[str], hints: Sequence[str], exclude: Sequence[str] = ()) -> str | None:
    excluded = set(exclude)
    for column in columns:
        if column in excluded:
            continue
        normalized = _norm_header(column)
        if any(hint in normalized for hint in hints):
            return column
    return None


def _numeric_ratio(series: pd.Series, decimal: str, thousands: str) -> float:
    values = [value for value in series.dropna().tolist() if not _is_blank(value)][:200]
    if not values:
        return 0.0
    ok = sum(1 for value in values if parse_number(value, decimal=decimal, thousands=thousands) is not None)
    return ok / len(values)


def suggest_mapping(parsed: ParsedCsv) -> dict[str, Any]:
    frame = parsed.frame
    decimal = parsed.detection.decimal
    thousands = parsed.detection.thousands
    date_column = None
    best_ratio = 0.0
    for column in frame.columns:
        values = [value for value in frame[column].dropna().tolist() if not _is_blank(value)][:200]
        fmt = detect_date_format(values, decimal=decimal)
        if not fmt:
            continue
        ratio = _parse_ratio([str(value).strip() for value in values], fmt)
        if ratio > best_ratio:
            best_ratio = ratio
            date_column = column
    if best_ratio < 0.6:
        date_column = None

    candidates = [column for column in frame.columns if column != date_column]
    volume_column = _find_header(candidates, VOLUME_HINTS)
    change_column = _find_header(candidates, CHANGE_HINTS)
    price_column = _find_header(candidates, PRICE_HINTS, exclude=[change_column, volume_column])
    open_column = _find_header(candidates, OPEN_HINTS, exclude=[change_column, volume_column])
    high_column = _find_header(candidates, HIGH_HINTS, exclude=[change_column, volume_column])
    low_column = _find_header(candidates, LOW_HINTS, exclude=[change_column, volume_column])

    numeric_columns = [
        column
        for column in candidates
        if _numeric_ratio(frame[column], decimal, thousands) >= 0.8
    ]
    if price_column is None:
        blocked = {change_column, volume_column, open_column, high_column, low_column, date_column}
        price_column = next((column for column in numeric_columns if column not in blocked), None)
        if price_column:
            numeric_columns = [column for column in numeric_columns if column != price_column]

    roles: dict[str, str] = {}
    if date_column:
        roles[date_column] = "date"
    if price_column:
        roles[price_column] = "price"
    if change_column:
        roles[change_column] = "change_percent"
    if volume_column:
        roles[volume_column] = "volume"
    if open_column:
        roles[open_column] = "open"
    if high_column:
        roles[high_column] = "high"
    if low_column:
        roles[low_column] = "low"
    for column in numeric_columns:
        roles.setdefault(column, "numeric")

    warnings: list[str] = []
    if date_column is None:
        warnings.append("Kolom tanggal tidak ditemukan; pilih manual.")
    if price_column is None:
        warnings.append("Kolom harga tidak ditemukan; pilih manual.")

    return {
        "date_column": date_column,
        "price_column": price_column,
        "change_column": change_column,
        "volume_column": volume_column,
        "open_column": open_column,
        "high_column": high_column,
        "low_column": low_column,
        "numeric_columns": numeric_columns,
        "roles": roles,
        "warnings": warnings,
    }


def default_mapping(parsed: ParsedCsv, instrument: str) -> Mapping:
    suggested = suggest_mapping(parsed)
    if suggested["date_column"] is None or suggested["price_column"] is None:
        raise ValueError("Kolom tanggal/harga tidak terdeteksi. Tentukan mapping manual.")
    specs = [
        ColumnSpec(source=suggested["date_column"], target="date", kind="date"),
        ColumnSpec(source=suggested["price_column"], target=instrument, kind="price"),
    ]
    if suggested["change_column"]:
        specs.append(
            ColumnSpec(
                source=suggested["change_column"],
                target=f"{instrument}_change",
                kind="change_percent",
                percent=True,
            )
        )
    for role in ("open", "high", "low"):
        source = suggested.get(f"{role}_column")
        if source:
            specs.append(ColumnSpec(source=source, target=f"{instrument}_{role}", kind=role))
    if suggested["volume_column"]:
        specs.append(ColumnSpec(source=suggested["volume_column"], target=f"{instrument}_volume", kind="volume"))
    return Mapping(instrument=instrument, columns=specs)


def apply_mapping(parsed: ParsedCsv, mapping: Mapping) -> pd.DataFrame:
    frame = parsed.frame
    decimal = mapping.decimal or parsed.detection.decimal
    thousands = mapping.thousands or parsed.detection.thousands
    date_spec = next((spec for spec in mapping.columns if spec.kind == "date"), None)
    if date_spec is None:
        raise ValueError("Mapping harus punya satu kolom dengan kind='date'.")
    if date_spec.source not in frame.columns:
        raise KeyError(f"Kolom tanggal {date_spec.source!r} tidak ada di CSV.")
    day_first = mapping.day_first
    if day_first is None:
        day_first = decimal == ","
    dates = parse_date_series(
        frame[date_spec.source],
        fmt=mapping.date_format or parsed.detection.date_format,
        day_first=day_first,
    )
    valid = dates.notna()
    if valid.sum() < len(frame):
        dropped = int((~valid).sum())
        if dropped == len(frame):
            raise ValueError("Tidak ada tanggal yang bisa dibaca.")
    columns: dict[str, Any] = {}
    for spec in mapping.columns:
        if spec.kind == "date":
            continue
        if spec.source not in frame.columns:
            raise KeyError(f"Kolom {spec.source!r} tidak ada di CSV.")
        values = frame[spec.source].map(
            lambda value: parse_number(value, decimal=decimal, thousands=thousands)
        )
        values = values.astype(float)
        if spec.percent:
            values = values / 100.0
        if spec.scale != 1.0:
            values = values * spec.scale
        columns[spec.target] = values.to_numpy()
    result = pd.DataFrame(columns, index=pd.DatetimeIndex(dates))
    result = result.loc[valid.to_numpy()]
    result.index.name = "date"
    result = result.sort_index()
    result = result[~result.index.duplicated(keep="last")]
    return result


def parse_price_csv(source: Any, instrument: str = "ASSET", **kwargs: Any) -> tuple[ParsedCsv, Mapping, pd.DataFrame]:
    parsed = read_csv(source, **kwargs)
    mapping = default_mapping(parsed, instrument)
    return parsed, mapping, apply_mapping(parsed, mapping)


def detection_report(parsed: ParsedCsv) -> dict[str, Any]:
    return {
        "encoding": parsed.detection.encoding,
        "delimiter": parsed.detection.delimiter,
        "decimal": parsed.detection.decimal,
        "thousands": parsed.detection.thousands,
        "date_format": parsed.detection.date_format,
        "rows": int(parsed.frame.shape[0]),
        "columns": list(parsed.frame.columns),
        "warnings": list(parsed.warnings),
    }
