from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from .formats import RESAMPLE_RULE, annualization_factor, normalize_period


@dataclass
class Issue:
    code: str
    message: str
    count: int = 1


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.code.startswith("error") for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.__dict__ for issue in self.issues]}


def _as_frame(prices: pd.Series | pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(prices).astype(float)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame.index.name = "date"
    return frame


def prices_to_returns(prices: pd.Series | pd.DataFrame) -> pd.DataFrame:
    frame = _as_frame(prices)
    returns = frame.pct_change(fill_method=None)
    return returns.dropna(how="all")


def periodic_returns(prices: pd.Series | pd.DataFrame, period: str = "D") -> pd.DataFrame:
    frame = _as_frame(prices)
    normalized = normalize_period(period)
    if normalized == "D":
        returns = frame.pct_change(fill_method=None)
    else:
        resampled = frame.resample(RESAMPLE_RULE[normalized]).last()
        returns = resampled.pct_change(fill_method=None)
    return returns.dropna(how="all")


def change_percent_to_decimal(changes: pd.Series | pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(changes).astype(float)
    return frame / 100.0


def returns_from_changes(
    changes: pd.Series | pd.DataFrame,
    period: str = "D",
    source_period: str | None = None,
) -> pd.DataFrame:
    target = normalize_period(period)
    source = normalize_period(source_period or period)
    if source != target:
        raise ValueError(
            "Change % hanya bisa dipakai bila periode sumber sama dengan periode analisis. "
            "Untuk resample ke mingguan/bulanan, gunakan kolom harga."
        )
    return change_percent_to_decimal(changes)


def detect_frequency(index: pd.Index) -> str:
    dates = pd.DatetimeIndex(index).drop_duplicates().sort_values()
    if len(dates) < 3:
        return "D"
    gaps = pd.Series(dates).diff().dt.days.dropna()
    if gaps.empty:
        return "D"
    median = float(gaps.median())
    if median <= 3:
        return "D"
    if median <= 10:
        return "W"
    if 25 <= median <= 35:
        return "M"
    if median < 20:
        return "W"
    return "M"


def build_return_frame(prices: dict[str, pd.Series], period: str = "D") -> pd.DataFrame:
    frames = {name: periodic_returns(series, period).iloc[:, 0] for name, series in prices.items()}
    return align_series(frames)


def align_series(frames: dict[str, pd.Series], how: Literal["inner", "outer"] = "inner") -> pd.DataFrame:
    if not frames:
        raise ValueError("Tidak ada data untuk digabung.")
    combined = pd.concat(frames, axis=1, join=how)
    combined.columns = list(frames)
    return combined.dropna(how="any")


def missing_dates(index: pd.Index, benchmark_index: pd.Index) -> list[pd.Timestamp]:
    asset_dates = set(pd.DatetimeIndex(index))
    benchmark_dates = set(pd.DatetimeIndex(benchmark_index))
    return sorted(benchmark_dates - asset_dates)


def validate_prices(prices: pd.Series | pd.DataFrame) -> ValidationReport:
    report = ValidationReport()
    frame = pd.DataFrame(prices).astype(float)
    if frame.empty:
        report.issues.append(Issue("error_empty", "Data harga kosong."))
        return report
    if frame.isna().any().any():
        report.issues.append(Issue("warning_missing", "Ada harga kosong.", int(frame.isna().sum().sum())))
    non_positive = int((frame <= 0).sum().sum())
    if non_positive:
        report.issues.append(Issue("error_non_positive", "Harga harus lebih besar dari nol.", non_positive))
    if frame.index.duplicated().any():
        report.issues.append(Issue("warning_duplicate", "Tanggal duplikat.", int(frame.index.duplicated().sum())))
    returns = frame.pct_change(fill_method=None)
    extreme = int((returns.abs() > 0.50).sum().sum())
    if extreme:
        report.issues.append(Issue("warning_extreme", "Perubahan harga di atas 50%; cek split/dividen.", extreme))
    if frame.shape[0] < 2:
        report.issues.append(Issue("error_short", "Butuh minimal dua baris harga."))
    return report


def validate_returns(returns: pd.Series | pd.DataFrame) -> ValidationReport:
    report = ValidationReport()
    frame = pd.DataFrame(returns).astype(float)
    if frame.empty:
        report.issues.append(Issue("error_empty", "Data return kosong."))
        return report
    missing = int(frame.isna().sum().sum())
    if missing:
        report.issues.append(Issue("warning_missing", "Ada return kosong.", missing))
    extreme = int((frame.abs() > 0.35).sum().sum())
    if extreme:
        report.issues.append(Issue("warning_extreme", "Return di luar +/-35%; cek data.", extreme))
    for column in frame.columns:
        series = frame[column].dropna()
        if len(series) > 1 and float(series.var(ddof=1)) == 0.0:
            report.issues.append(Issue("warning_constant", f"Return {column} konstan; beta/SD tidak bermakna."))
    if frame.shape[0] < 2:
        report.issues.append(Issue("error_short", "Butuh minimal dua observasi return."))
    return report


def normalize_ticker(ticker: str, market: str = "IDX") -> str:
    cleaned = ticker.strip().upper()
    if market.upper() != "IDX":
        return cleaned
    if cleaned.startswith("^") or "." in cleaned:
        return cleaned
    return f"{cleaned}.JK"


def fetch_prices(
    tickers: list[str],
    start: str | None = None,
    end: str | None = None,
    *,
    market: str = "IDX",
    auto_adjust: bool = True,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError("yfinance belum terpasang. Jalankan: uv pip install -r requirements.txt") from exc
    symbols = [normalize_ticker(ticker, market) for ticker in tickers]
    raw = yf.download(
        symbols,
        start=start,
        end=end,
        auto_adjust=auto_adjust,
        progress=False,
        group_by="column",
        threads=False,
    )
    if raw is None or raw.empty:
        raise ValueError("yfinance tidak mengembalikan data. Cek koneksi dan kode ticker.")
    if isinstance(raw.columns, pd.MultiIndex):
        level_zero = raw.columns.get_level_values(0)
        if "Close" in level_zero:
            close = raw["Close"]
        else:
            close = raw.xs("Close", axis=1, level=1)
    else:
        close = raw[["Close"]].copy()
        close.columns = symbols[:1]
    close.index = pd.to_datetime(close.index)
    if getattr(close.index, "tz", None) is not None:
        close.index = close.index.tz_localize(None)
    close.index.name = "date"
    rename = {symbol: original for symbol, original in zip(symbols, tickers)}
    close = close.rename(columns=rename)
    close = close.sort_index()
    return close


def save_cache(prices: pd.DataFrame, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(destination)
    return destination


def load_cache(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    return frame.astype(float)


def annualization_note(period: str) -> str:
    return f"Faktor annualisasi {normalize_period(period)} = {annualization_factor(period)}"
