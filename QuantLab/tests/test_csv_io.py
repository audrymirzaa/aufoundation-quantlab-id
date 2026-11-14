from pathlib import Path

import pandas as pd
import pytest

from engine import csv_io

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_number_id_locale():
    assert csv_io.parse_number("6.850", decimal=",", thousands=".") == 6850.0
    assert csv_io.parse_number("1,50%", decimal=",", thousands=".") == pytest.approx(1.5)
    assert csv_io.parse_number("12,3M", decimal=",", thousands=".") == pytest.approx(12_300_000)
    assert csv_io.parse_number("(1,23)", decimal=",", thousands=".") == pytest.approx(-1.23)
    assert csv_io.parse_number("-", decimal=",", thousands=".") is None


def test_parse_number_us_locale():
    assert csv_io.parse_number("12,300,000", decimal=".", thousands=",") == 12_300_000
    assert csv_io.parse_number("1.50%", decimal=".", thousands=",") == pytest.approx(1.5)
    assert csv_io.parse_number("-0.37", decimal=".", thousands=",") == pytest.approx(-0.37)
    assert csv_io.parse_number("N/A") is None


def test_read_id_csv_detection():
    parsed = csv_io.read_csv(FIXTURES / "investing_id.csv")
    assert parsed.detection.delimiter == ";"
    assert parsed.detection.decimal == ","
    assert parsed.detection.thousands == "."
    assert parsed.detection.date_format in {"%d/%m/%Y", "%d/%m/%y"}
    assert list(parsed.frame.columns) == ["Tanggal", "Terakhir", "Pembukaan", "Tertinggi", "Terendah", "Vol.", "Perubahan%"]


def test_read_us_csv_detection():
    parsed = csv_io.read_csv(FIXTURES / "investing_us.csv")
    assert parsed.detection.delimiter == ","
    assert parsed.detection.decimal == "."
    assert parsed.detection.thousands == ","
    assert parsed.detection.date_format == "%m/%d/%Y"


def test_suggest_mapping_id_headers():
    parsed = csv_io.read_csv(FIXTURES / "investing_id.csv")
    suggested = csv_io.suggest_mapping(parsed)
    assert suggested["date_column"] == "Tanggal"
    assert suggested["price_column"] == "Terakhir"
    assert suggested["change_column"] == "Perubahan%"
    assert suggested["volume_column"] == "Vol."
    assert "error" not in " ".join(suggested["warnings"]).lower()


def test_apply_mapping_converts_dates_prices_and_percent():
    parsed, mapping, frame = csv_io.parse_price_csv(FIXTURES / "investing_id.csv", "BBCA")
    assert frame.index[0] == pd.Timestamp("2024-01-02")
    assert frame.index.is_monotonic_increasing
    assert frame.loc["2024-01-02", "BBCA"] == pytest.approx(6850.0)
    assert frame.loc["2024-01-02", "BBCA_change"] == pytest.approx(0.015)
    assert frame.loc["2024-01-02", "BBCA_volume"] == pytest.approx(12_300_000)
    assert mapping.columns[0].kind == "date"


def test_apply_mapping_us_dates():
    parsed, mapping, frame = csv_io.parse_price_csv(FIXTURES / "investing_us.csv", "TEST")
    assert frame.index[0] == pd.Timestamp("2024-01-02")
    assert frame.loc["2024-01-02", "TEST"] == pytest.approx(6850.0)
    assert frame.loc["2024-01-02", "TEST_change"] == pytest.approx(0.015)


def test_no_change_column_is_not_invented():
    parsed = csv_io.read_csv(FIXTURES / "no_change.csv")
    suggested = csv_io.suggest_mapping(parsed)
    assert suggested["change_column"] is None
    assert suggested["price_column"] == "Price"


def test_monthly_dates_detected():
    parsed = csv_io.read_csv(FIXTURES / "monthly.csv")
    assert parsed.detection.date_format == "%Y-%m-%d"
    _, _, frame = csv_io.parse_price_csv(FIXTURES / "monthly.csv", "MONTHLY")
    assert frame.index[0] == pd.Timestamp("2024-01-31")
    assert frame.index[-1] == pd.Timestamp("2024-07-31")


def test_duplicate_dates_keep_last_row():
    text = "Date;Price\n02/01/2024;100\n02/01/2024;110\n03/01/2024;120\n"
    parsed = csv_io.read_csv(text)
    mapping = csv_io.Mapping(
        instrument="X",
        columns=[
            csv_io.ColumnSpec(source="Date", target="date", kind="date"),
            csv_io.ColumnSpec(source="Price", target="X", kind="price"),
        ],
    )
    frame = csv_io.apply_mapping(parsed, mapping)
    assert len(frame) == 2
    assert frame.loc["2024-01-02", "X"] == pytest.approx(110.0)


def test_blank_rows_are_dropped():
    text = "Date;Price\n02/01/2024;100\n;\n03/01/2024;110\n"
    parsed = csv_io.read_csv(text)
    assert len(parsed.frame) == 2
