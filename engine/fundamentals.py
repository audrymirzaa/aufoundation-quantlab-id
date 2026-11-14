from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from .data import normalize_ticker
from .universe import normalize_code

ProgressCallback = Callable[[int, int, str], None]
TickerFactory = Callable[[str], Any]

FRAME_COLUMNS = ["ticker", "sector", "roe", "pbv", "cr", "as_of", "name"]
METRIC_COLUMNS = ["roe", "pbv", "cr"]

_EQUITY_ROWS = (
    "Stockholders Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
    "Total Equity",
)
_NET_INCOME_ROWS = (
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income Including Noncontrolling Interests",
)
_CURRENT_ASSETS_ROWS = ("Current Assets",)
_CURRENT_LIABILITIES_ROWS = ("Current Liabilities",)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _first_value(frame: Any, rows: Sequence[str]) -> float | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    for row in rows:
        if row not in frame.index:
            continue
        for value in frame.loc[row].tolist():
            number = _number(value)
            if number is not None:
                return number
    return None


def _first_date(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        if isinstance(value, (int, float)):
            stamp = pd.to_datetime(value, unit="s", errors="coerce", utc=True)
        else:
            stamp = pd.to_datetime(value, errors="coerce", utc=True)
    except (TypeError, ValueError, OverflowError):
        return ""
    if pd.isna(stamp):
        return ""
    return stamp.strftime("%Y-%m-%d")


def _as_of(info: Mapping[str, Any]) -> str:
    for key in ("mostRecentQuarter", "lastFiscalYearEnd", "lastFiscalYearEndDate"):
        text = _first_date(info.get(key))
        if text:
            return text
    return pd.Timestamp.today().strftime("%Y-%m-%d")


def _pbv_from_info(info: Mapping[str, Any]) -> float | None:
    direct = _number(info.get("priceToBook"))
    if direct is not None:
        return direct
    price = _number(info.get("currentPrice"))
    if price is None:
        price = _number(info.get("regularMarketPrice"))
    book = _number(info.get("bookValue"))
    if price and book and price > 0 and book > 0:
        return price / book
    return None


def _load_info(ticker: Any) -> dict[str, Any]:
    getter = getattr(ticker, "get_info", None)
    if callable(getter):
        info = getter()
    else:
        info = getattr(ticker, "info", {})
    return dict(info) if isinstance(info, Mapping) else {}


def _statements(ticker: Any) -> tuple[Any, Any]:
    balance = None
    financials = None
    try:
        balance = ticker.balance_sheet
    except Exception:
        balance = None
    try:
        financials = ticker.financials
    except Exception:
        financials = None
    return balance, financials


def fetch_fundamentals(
    tickers: Sequence[str],
    *,
    sector_lookup: Mapping[str, str] | None = None,
    market: str = "IDX",
    ticker_factory: TickerFactory | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    sector_lookup = sector_lookup or {}
    codes: list[str] = []
    for raw in tickers:
        code = normalize_code(raw)
        if code and code not in codes:
            codes.append(code)
    if not codes:
        return pd.DataFrame(columns=FRAME_COLUMNS), []

    if ticker_factory is None:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError(
                "yfinance belum terpasang. Jalankan: uv pip install -r requirements.txt"
            ) from exc
        ticker_factory = yf.Ticker

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    total = len(codes)
    for index, code in enumerate(codes, start=1):
        if progress:
            progress(index - 1, total, code)
        sector = str(sector_lookup.get(code, "") or "")
        row = {
            "ticker": code,
            "sector": sector,
            "roe": None,
            "pbv": None,
            "cr": None,
            "as_of": pd.Timestamp.today().strftime("%Y-%m-%d"),
            "name": "",
        }
        ticker = None
        info: dict[str, Any] = {}
        info_failed = False
        try:
            ticker = ticker_factory(normalize_ticker(code, market))
            info = _load_info(ticker)
            row["as_of"] = _as_of(info)
            row["name"] = str(info.get("longName") or info.get("shortName") or "").strip()
            row["roe"] = _number(info.get("returnOnEquity"))
            row["pbv"] = _pbv_from_info(info)
            row["cr"] = _number(info.get("currentRatio"))
        except Exception as exc:
            info_failed = True
            warnings.append(f"{code}: {exc}")

        needs_statements = row["roe"] is None or row["pbv"] is None
        if ticker is not None and not info_failed and needs_statements:
            balance, financials = _statements(ticker)
            equity = _first_value(balance, _EQUITY_ROWS)
            if row["roe"] is None:
                net_income = _first_value(financials, _NET_INCOME_ROWS)
                if net_income is not None and equity not in (None, 0):
                    row["roe"] = net_income / equity
            if row["pbv"] is None:
                market_cap = _number(info.get("marketCap"))
                if market_cap is not None and equity not in (None, 0):
                    row["pbv"] = market_cap / equity
            if row["cr"] is None:
                current_assets = _first_value(balance, _CURRENT_ASSETS_ROWS)
                current_liabilities = _first_value(balance, _CURRENT_LIABILITIES_ROWS)
                if current_assets is not None and current_liabilities not in (None, 0):
                    row["cr"] = current_assets / current_liabilities

        rows.append(row)
        if progress:
            progress(index, total, code)

    return pd.DataFrame(rows, columns=FRAME_COLUMNS), warnings
