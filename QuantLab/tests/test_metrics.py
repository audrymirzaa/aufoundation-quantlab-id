from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import csv_io, data, metrics

FIXTURES = Path(__file__).parent / "fixtures"


def test_capm_excel_example():
    value = metrics.capm(0.06, 0.366, -0.008)
    assert value == pytest.approx(0.035112, rel=1e-6)


def test_jensen_excel_example():
    value = metrics.jensen_alpha(0.0041, 0.035112)
    assert value == pytest.approx(-0.031012, rel=1e-6)


def test_rf_period_conversion():
    assert metrics.rf_period_from_annual(0.06, "D") == pytest.approx((1.06 ** (1 / 252)) - 1)
    assert metrics.rf_period_from_annual(0.06, "W") == pytest.approx((1.06 ** (1 / 52)) - 1)
    assert metrics.rf_period_from_annual(0.06, "M") == pytest.approx((1.06 ** (1 / 12)) - 1)
    assert metrics.rf_period_from_annual(0.06, "D") < 0.06


def test_beta_of_doubled_series():
    market = np.array([0.01, -0.02, 0.03, -0.01, 0.02, 0.00])
    stock = market * 2
    assert metrics.beta(stock, market) == pytest.approx(2.0)


def test_beta_matches_polyfit_slope():
    rng = np.random.default_rng(42)
    market = rng.normal(0, 0.01, 200)
    stock = 1.3 * market + rng.normal(0, 0.005, 200)
    slope = np.polyfit(market, stock, 1)[0]
    assert metrics.beta(stock, market) == pytest.approx(slope, rel=1e-9)


def test_beta_none_when_market_constant():
    market = np.array([0.01, 0.01, 0.01, 0.01])
    stock = np.array([0.02, -0.01, 0.03, 0.00])
    assert metrics.beta(stock, market) is None


def test_coefficient_variation_rules():
    assert metrics.coefficient_variation(0.02, 0.01) == pytest.approx(0.5)
    assert metrics.coefficient_variation(-0.02, 0.01) is None
    assert metrics.coefficient_variation(-0.02, 0.01, allow_negative=True) == pytest.approx(-0.5)


def test_annualize_volatility():
    assert metrics.annualize_volatility(0.01, "D") == pytest.approx(0.01 * np.sqrt(252))
    assert metrics.annualize_volatility(0.01, "M") == pytest.approx(0.01 * np.sqrt(12))


def test_beta_category_thresholds():
    assert metrics.beta_category(0.4) == "Defensif"
    assert metrics.beta_category(0.8) == "Sedikit Terpengaruh"
    assert metrics.beta_category(1.1) == "Terpengaruh"
    assert metrics.beta_category(1.3) == "Sangat Berpengaruh"
    assert metrics.beta_category(-0.2) == "Invers"
    assert metrics.beta_category(None) == "Tidak tersedia"


def test_analyze_asset_corrected_converts_rf():
    market = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.00, 0.01, -0.01])
    stock = market * 1.5
    result = metrics.analyze_asset(stock, market, instrument="TEST", rf_annual=0.06, period="D")
    assert result.beta == pytest.approx(1.5)
    assert result.rf_period == pytest.approx((1.06 ** (1 / 252)) - 1)
    assert result.cv is None or result.cv_valid
    assert result.alpha is not None
    assert "Rf tahunan dikonversi" in " ".join(result.notes)


def test_analyze_asset_legacy_keeps_annual_rf():
    market = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.00, 0.01, -0.01])
    stock = market * 1.5
    result = metrics.analyze_asset(stock, market, rf_annual=0.06, period="D", legacy=True)
    assert result.rf_period == pytest.approx(0.06)
    assert result.legacy is True


def test_analyze_asset_legacy_excel_capm():
    market = pd.Series([-0.008] * 8)
    stock = pd.Series([0.0041] * 8)
    result = metrics.analyze_asset(
        stock,
        market,
        rf_annual=0.06,
        period="D",
        legacy=True,
        er_market_override=-0.008,
    )
    assert result.beta is None
    assert result.er_market == pytest.approx(-0.008)


def test_analyze_universe_beta():
    market = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.00, 0.01, -0.01, 0.02, -0.01])
    returns = pd.DataFrame({"IHSG": market, "AAA": market * 2})
    results = metrics.analyze_universe(returns, "IHSG")
    assert results["AAA"].beta == pytest.approx(2.0)


def test_correlation_matrix_perfect():
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0]})
    corr = metrics.correlation_matrix(frame)
    assert corr.loc["a", "b"] == pytest.approx(1.0)


def test_portfolio_stats():
    covariance = np.array([[0.04, 0.006], [0.006, 0.09]])
    result = metrics.portfolio_stats([0.5, 0.5], covariance)
    assert result["variance"] == pytest.approx(0.0355)
    assert result["sd"] == pytest.approx(np.sqrt(0.0355))


def test_classify_quadrant():
    assert metrics.classify_quadrant(True, 0.01)["quadrant"].startswith("Kuadran 1")
    assert metrics.classify_quadrant(True, -0.01)["quadrant"].startswith("Kuadran 2")
    assert metrics.classify_quadrant(False, 0.01)["quadrant"].startswith("Kuadran 3")
    assert metrics.classify_quadrant(False, -0.01)["quadrant"].startswith("Kuadran 4")


def test_real_investing_files_match_excel_panel():
    files = {
        "IHSG": "real_ihsg.csv",
        "INDF": "real_indf.csv",
        "LPPF": "real_lppf.csv",
        "ANTM": "real_antm.csv",
    }
    frames: dict[str, pd.Series] = {}
    for name, filename in files.items():
        _, _, frame = csv_io.parse_price_csv(FIXTURES / "real" / filename, name)
        assert data.detect_frequency(frame.index) == "M"
        frames[name] = frame[f"{name}_change"]
    table = pd.concat(frames, axis=1, join="inner").dropna()
    assert len(table) == 34
    assert table["IHSG"].mean() == pytest.approx(-0.00805, abs=1e-5)

    expected = {
        "INDF": {"beta": 0.3657, "mean": 0.00405, "sd": 0.05951, "cv": 14.68, "capm": 0.03511, "alpha": -0.03106},
        "LPPF": {"beta": 0.3193, "mean": -0.00479, "sd": 0.07975, "cv": -16.66, "capm": 0.03827, "alpha": -0.04306},
        "ANTM": {"beta": 1.0249, "mean": 0.02634, "sd": 0.14289, "cv": 5.42, "capm": -0.00974, "alpha": 0.03608},
    }
    for name, target in expected.items():
        assert metrics.beta(table[name], table["IHSG"]) == pytest.approx(target["beta"], abs=5e-4)
        result = metrics.analyze_asset(
            table[name],
            table["IHSG"],
            instrument=name,
            rf_annual=0.06,
            period="M",
            legacy=True,
        )
        assert result.mean_return == pytest.approx(target["mean"], abs=1e-5)
        assert result.sd == pytest.approx(target["sd"], abs=1e-5)
        assert result.cv == pytest.approx(target["cv"], abs=0.01)
        assert result.capm == pytest.approx(target["capm"], abs=1e-5)
        assert result.alpha == pytest.approx(target["alpha"], abs=1e-5)


def test_corrected_mode_uses_monthly_rf():
    _, _, frame = csv_io.parse_price_csv(FIXTURES / "real" / "real_indf.csv", "INDF")
    _, _, market = csv_io.parse_price_csv(FIXTURES / "real" / "real_ihsg.csv", "IHSG")
    pair = pd.concat(
        {"stock": frame["INDF_change"], "market": market["IHSG_change"]}, axis=1
    ).dropna()
    legacy = metrics.analyze_asset(pair["stock"], pair["market"], period="M", legacy=True)
    corrected = metrics.analyze_asset(pair["stock"], pair["market"], period="M", legacy=False)
    assert legacy.rf_period == pytest.approx(0.06)
    assert corrected.rf_period == pytest.approx((1.06 ** (1 / 12)) - 1)
    assert corrected.capm != pytest.approx(legacy.capm)


def test_price_returns_match_change_column():
    _, _, frame = csv_io.parse_price_csv(FIXTURES / "real" / "real_indf.csv", "INDF")
    price_returns = frame["INDF"].pct_change().dropna()
    change_returns = frame["INDF_change"].iloc[1:]
    assert np.allclose(price_returns.to_numpy(), change_returns.to_numpy(), atol=2e-4)

