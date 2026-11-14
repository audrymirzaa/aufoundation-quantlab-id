import pandas as pd
import pytest

from engine import metrics, ui_data


def test_dataset_code_from_filename():
    assert ui_data.dataset_code_from_filename("Jakarta Stock Exchange Composite Index Historical Data (1).csv") == "IHSG"
    assert ui_data.dataset_code_from_filename("Indofood Stock Price History.csv") == "INDF"
    assert ui_data.dataset_code_from_filename("Antam Stock Price History (2).csv") == "ANTM"
    assert ui_data.dataset_code_from_filename("Mds Retailing Tbk Stock Price History.csv") == "LPPF"


def test_allowed_periods():
    assert ui_data.allowed_periods("D") == ["D", "W", "M"]
    assert ui_data.allowed_periods("W") == ["W", "M"]
    assert ui_data.allowed_periods("M") == ["M"]


def test_resample_price_frame_aggregates_ohlcv():
    frame = pd.DataFrame(
        {
            "X": [100.0, 110.0, 121.0, 133.1, 146.41],
            "X_open": [99.0, 101.0, 111.0, 122.0, 134.0],
            "X_high": [102.0, 112.0, 123.0, 135.0, 148.0],
            "X_low": [98.0, 100.0, 110.0, 121.0, 133.0],
            "X_volume": [10.0, 20.0, 30.0, 40.0, 50.0],
            "X_change": [0.01, 0.02, 0.03, 0.04, 0.05],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )
    result = ui_data.resample_price_frame(frame, "W")
    assert result.loc["2024-01-05", "X"] == pytest.approx(146.41)
    assert result.loc["2024-01-05", "X_open"] == pytest.approx(99.0)
    assert result.loc["2024-01-05", "X_high"] == pytest.approx(148.0)
    assert result.loc["2024-01-05", "X_low"] == pytest.approx(98.0)
    assert result.loc["2024-01-05", "X_volume"] == pytest.approx(150.0)
    assert "X_change" not in result.columns


def test_build_display_frame():
    index = pd.to_datetime(["2024-01-05", "2024-01-12"])
    returns = pd.DataFrame({"X": [0.10, -0.05], "IHSG": [0.02, 0.01]}, index=index)
    frames = {
        "X": pd.DataFrame({"X": [133.1, 126.4], "X_volume": [100.0, 200.0]}, index=index),
        "IHSG": pd.DataFrame({"IHSG": [7000.0, 7070.0]}, index=index),
    }
    display, percent_columns, volume_columns = ui_data.build_display_frame(
        returns,
        frames,
        ["return", "close", "volume"],
        {"X": True},
    )
    assert list(display.columns) == ["Tanggal", "X Change %", "X Close", "X Volume", "IHSG Return %", "IHSG Close"]
    assert percent_columns == ["X Change %", "IHSG Return %"]
    assert volume_columns == ["X Volume"]
    assert display["X Change %"].iloc[0] == pytest.approx(0.10)


def test_metrics_and_risk_tables():
    market = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, 0.00])
    stock = market * 2
    result = metrics.analyze_asset(stock, market, instrument="TEST", period="M", legacy=True)
    capm_frame = ui_data.metrics_table({"TEST": result}, annualized=False, locale="en", decimals=2)
    capm_frame_id = ui_data.metrics_table({"TEST": result}, annualized=False, locale="id", decimals=2)
    risk_frame = ui_data.risk_table({"TEST": result}, locale="id", decimals=2)
    assert capm_frame.loc[0, "Saham"] == "TEST"
    assert capm_frame.loc[0, "Beta"] == "2.000"
    assert capm_frame_id.loc[0, "Beta"] == "2,000"
    assert risk_frame.loc[0, "Saham"] == "TEST"


def test_frames_to_excel_returns_xlsx_bytes():
    frame = pd.DataFrame({"Tanggal": pd.to_datetime(["2024-01-01"]), "X Return %": [0.1]})
    data = ui_data.frames_to_excel({"Grid": frame}, {"Grid": ["X Return %"]})
    assert data[:2] == b"PK"
    assert len(data) > 1000


def test_source_note():
    assert "dihitung dari harga" in ui_data.source_note("D", "M", "change")
    assert "Change %" in ui_data.source_note("M", "M", "change")
    assert "dihitung dari harga" in ui_data.source_note("M", "M", "price")


def test_formatting_handles_missing_values():
    from engine.formats import format_percent

    assert ui_data.format_number(float("nan")) == "N/A"
    assert format_percent(float("nan")) == "N/A"
    assert format_percent(None) == "N/A"


def test_merge_datasets_preserves_existing():
    existing = {"AAAA": {"value": 1}, "BBBB": {"value": 2}}
    incoming = {"BBBB": {"value": 3}, "CCCC": {"value": 4}}
    merged = ui_data.merge_datasets(existing, incoming)
    assert set(merged) == {"AAAA", "BBBB", "CCCC"}
    assert merged["BBBB"]["value"] == 3
    assert existing["BBBB"]["value"] == 2


def test_medians_and_quadrant_display():
    medians = pd.DataFrame(
        {
            "sector": ["Bank"],
            "roe_median": [0.15],
            "pbv_median": [1.2],
            "cr_median": [2.5],
            "n": [3],
            "enough_peers": [True],
        }
    )
    display = ui_data.medians_display(medians, locale="id", decimals=2)
    assert display.loc[0, "ROE Median"] == "15,00%"
    assert display.loc[0, "PBV Median"] == "1,20"
    quadrants = pd.DataFrame(
        {
            "Ticker": ["AAAA"],
            "Sektor": ["Bank"],
            "ROE": [0.15],
            "PBV": [1.2],
            "CR": [2.5],
            "ROE Median": [0.15],
            "PBV Median": [1.2],
            "CR Median": [2.5],
            "Peer": [3],
            "Skor": [3],
            "Fundamental": ["Di atas median"],
            "Alpha": [0.01],
            "Kuadran": ["Kuadran 1: Sweet Spot"],
            "Aksi": ["BUY / CORE ASSET"],
            "Catatan": [""],
        }
    )
    quadrant_display = ui_data.quadrant_display(quadrants, locale="id", decimals=2)
    assert quadrant_display.loc[0, "ROE"] == "15,00%"
    assert quadrant_display.loc[0, "Alpha"] == "1,00%"
