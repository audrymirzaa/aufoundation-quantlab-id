import pandas as pd
import pytest

from engine import benchmarks
from engine.fundamentals import fetch_fundamentals


class FakeTicker:
    def __init__(self, info=None, balance=None, financials=None, error=None):
        self._info = info or {}
        self.balance_sheet = balance
        self.financials = financials
        self._error = error

    def get_info(self):
        if self._error:
            raise self._error
        return self._info


def test_fetch_uses_info_fields():
    symbols = []
    timestamp = int(pd.Timestamp("2026-09-30").timestamp())
    info = {
        "returnOnEquity": 0.185,
        "priceToBook": 2.4,
        "currentRatio": 1.3,
        "mostRecentQuarter": timestamp,
        "longName": "Bank Central Asia Tbk.",
    }

    def factory(symbol):
        symbols.append(symbol)
        return FakeTicker(info=info)

    frame, warnings = fetch_fundamentals(
        ["bbca"],
        sector_lookup={"BBCA": "Financials"},
        ticker_factory=factory,
    )

    assert symbols == ["BBCA.JK"]
    assert frame.loc[0, "ticker"] == "BBCA"
    assert frame.loc[0, "sector"] == "Financials"
    assert frame.loc[0, "name"] == "Bank Central Asia Tbk."
    assert frame.loc[0, "roe"] == pytest.approx(0.185)
    assert frame.loc[0, "pbv"] == pytest.approx(2.4)
    assert frame.loc[0, "cr"] == pytest.approx(1.3)
    assert frame.loc[0, "as_of"] == "2026-09-30"
    assert warnings == []


def test_fetch_falls_back_to_statements():
    info = {
        "marketCap": 1000,
        "currentPrice": 250,
        "bookValue": 100,
        "mostRecentQuarter": int(pd.Timestamp("2026-06-30").timestamp()),
    }
    balance = pd.DataFrame(
        {
            "2025-12-31": [500, 300, 100],
            "2024-12-31": [400, 250, 80],
        },
        index=["Stockholders Equity", "Current Assets", "Current Liabilities"],
    )
    financials = pd.DataFrame(
        {"2025-12-31": [75], "2024-12-31": [60]},
        index=["Net Income"],
    )

    frame, warnings = fetch_fundamentals(
        ["TEST"],
        sector_lookup={"TEST": "Industrials"},
        ticker_factory=lambda symbol: FakeTicker(
            info=info,
            balance=balance,
            financials=financials,
        ),
    )

    assert frame.loc[0, "roe"] == pytest.approx(75 / 500)
    assert frame.loc[0, "pbv"] == pytest.approx(2.5)
    assert frame.loc[0, "cr"] == pytest.approx(3.0)
    assert warnings == []


def test_fetch_continues_when_one_ticker_fails():
    def factory(symbol):
        if symbol == "FAIL.JK":
            return FakeTicker(error=RuntimeError("rate limit"))
        return FakeTicker(info={"returnOnEquity": 0.1, "priceToBook": 1.2, "currentRatio": 2.0})

    frame, warnings = fetch_fundamentals(
        ["FAIL", "OKAY"],
        sector_lookup={"FAIL": "Lainnya", "OKAY": "Lainnya"},
        ticker_factory=factory,
    )

    assert list(frame["ticker"]) == ["FAIL", "OKAY"]
    assert pd.isna(frame.loc[0, "roe"])
    assert frame.loc[1, "roe"] == pytest.approx(0.1)
    assert any("FAIL" in warning and "rate limit" in warning for warning in warnings)


def test_merge_fundamentals_fills_only_missing():
    existing = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "sector": "Financials",
                "roe": 0.20,
                "pbv": 1.5,
                "cr": None,
                "as_of": "2026-01-01",
            }
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "sector": "Financials",
                "roe": 0.10,
                "pbv": 2.0,
                "cr": 3.0,
                "as_of": "2026-11-13",
            }
        ]
    )

    merged = benchmarks.merge_fundamentals(existing, incoming)

    assert merged.loc[0, "roe"] == pytest.approx(0.20)
    assert merged.loc[0, "pbv"] == pytest.approx(1.5)
    assert merged.loc[0, "cr"] == pytest.approx(3.0)
    assert merged.loc[0, "as_of"] == "2026-11-13"


def test_merge_fundamentals_can_overwrite_and_append():
    existing = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "sector": "Financials",
                "roe": 0.20,
                "pbv": 1.5,
                "cr": None,
                "as_of": "2026-01-01",
            }
        ]
    )
    incoming = pd.DataFrame(
        [
            {
                "ticker": "BBCA",
                "sector": "Financials",
                "roe": 0.10,
                "pbv": 2.0,
                "cr": 3.0,
                "as_of": "2026-11-13",
            },
            {
                "ticker": "ANTM",
                "sector": "Basic Materials",
                "roe": 0.15,
                "pbv": 1.1,
                "cr": 2.2,
                "as_of": "2026-11-13",
            },
        ]
    )

    merged = benchmarks.merge_fundamentals(existing, incoming, overwrite=True)

    assert list(merged["ticker"]) == ["BBCA", "ANTM"]
    assert merged.loc[0, "roe"] == pytest.approx(0.10)
    assert merged.loc[0, "pbv"] == pytest.approx(2.0)
    assert merged.loc[1, "cr"] == pytest.approx(2.2)
