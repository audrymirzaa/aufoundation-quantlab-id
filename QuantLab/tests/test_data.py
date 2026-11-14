import pandas as pd
import pytest

from engine import data


def test_prices_to_returns():
    prices = pd.Series([100.0, 110.0, 99.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    returns = data.prices_to_returns(prices)
    assert returns.iloc[0, 0] == pytest.approx(0.10)
    assert returns.iloc[1, 0] == pytest.approx(-0.10)


def test_periodic_returns_daily():
    prices = pd.DataFrame(
        {"X": [100.0, 110.0, 121.0]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
    )
    returns = data.periodic_returns(prices, "D")
    assert len(returns) == 2
    assert returns.iloc[0, 0] == pytest.approx(0.10)
    assert returns.iloc[1, 0] == pytest.approx(0.10)


def test_periodic_returns_weekly_compounds():
    prices = pd.DataFrame(
        {"X": [100.0, 110.0, 121.0, 133.1, 146.41, 161.051]},
        index=pd.to_datetime(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08", "2024-01-12"]
        ),
    )
    returns = data.periodic_returns(prices, "W")
    assert len(returns) == 1
    assert returns.iloc[0, 0] == pytest.approx(0.21)


def test_periodic_returns_monthly_compounds():
    prices = pd.DataFrame(
        {"X": [100.0, 110.0, 121.0, 133.1, 161.051]},
        index=pd.to_datetime(
            ["2024-01-01", "2024-01-15", "2024-01-31", "2024-02-15", "2024-02-29"]
        ),
    )
    returns = data.periodic_returns(prices, "M")
    assert len(returns) == 1
    assert returns.iloc[0, 0] == pytest.approx(0.331)


def test_returns_from_changes_daily():
    changes = pd.Series([1.5, -0.37])
    returns = data.returns_from_changes(changes, "D")
    assert returns.iloc[0, 0] == pytest.approx(0.015)
    assert returns.iloc[1, 0] == pytest.approx(-0.0037)


def test_returns_from_changes_rejects_resample():
    with pytest.raises(ValueError):
        data.returns_from_changes(pd.Series([1.5]), "W", source_period="D")


def test_returns_from_changes_monthly_source():
    returns = data.returns_from_changes(pd.Series([1.5]), "M", source_period="M")
    assert returns.iloc[0, 0] == pytest.approx(0.015)


def test_detect_frequency():
    daily = pd.date_range("2024-01-01", periods=10, freq="D")
    weekly = pd.date_range("2024-01-01", periods=10, freq="7D")
    monthly = pd.date_range("2024-01-01", periods=10, freq="MS")
    assert data.detect_frequency(daily) == "D"
    assert data.detect_frequency(weekly) == "W"
    assert data.detect_frequency(monthly) == "M"


def test_align_series_inner():
    a = pd.Series([0.1, 0.2, 0.3], index=[1, 2, 3])
    b = pd.Series([0.4, 0.5], index=[2, 3])
    aligned = data.align_series({"a": a, "b": b})
    assert list(aligned.index) == [2, 3]
    assert list(aligned.columns) == ["a", "b"]


def test_validate_prices_flags_negative_and_duplicate():
    index = pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-03"])
    prices = pd.Series([100.0, -5.0, 110.0], index=index)
    report = data.validate_prices(prices)
    codes = {issue.code for issue in report.issues}
    assert "error_non_positive" in codes
    assert report.ok is False


def test_validate_returns_flags_extreme_and_constant():
    returns = pd.DataFrame({"a": [0.01, 0.40, 0.02], "b": [0.01, 0.01, 0.01]})
    report = data.validate_returns(returns)
    codes = {issue.code for issue in report.issues}
    assert "warning_extreme" in codes
    assert "warning_constant" in codes


def test_normalize_ticker_idx_and_index():
    assert data.normalize_ticker("bbca") == "BBCA.JK"
    assert data.normalize_ticker("^JKSE") == "^JKSE"
    assert data.normalize_ticker("BBCA.JK") == "BBCA.JK"
    assert data.normalize_ticker("AAPL", market="US") == "AAPL"
