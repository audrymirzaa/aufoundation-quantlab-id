from pathlib import Path

import pandas as pd
import pytest

from engine import benchmarks, metrics

FUNDAMENTALS_CSV = """ticker;sector;roe;pbv;cr
AAAA;Bank;15,0;1,2;2,5
BBBB;Bank;12,0;1,8;1,9
CCCC;Bank;18,0;0,9;3,1
DDDD;Barang;20,0;2,0;1,5
"""


def test_load_fundamentals_id_locale():
    frame = benchmarks.load_fundamentals(FUNDAMENTALS_CSV, roe_percent=True)
    assert list(frame["ticker"]) == ["AAAA", "BBBB", "CCCC", "DDDD"]
    assert frame.loc[0, "roe"] == pytest.approx(0.15)
    assert frame.loc[0, "pbv"] == pytest.approx(1.2)
    assert frame.loc[0, "cr"] == pytest.approx(2.5)


def test_load_fundamentals_requires_columns():
    with pytest.raises(ValueError):
        benchmarks.load_fundamentals(pd.DataFrame({"ticker": ["AAAA"], "roe": [0.1]}))


def test_sector_medians():
    frame = benchmarks.load_fundamentals(FUNDAMENTALS_CSV)
    medians = benchmarks.sector_medians(frame)
    bank = medians[medians["sector"] == "Bank"].iloc[0]
    assert bank["roe_median"] == pytest.approx(0.15)
    assert bank["pbv_median"] == pytest.approx(1.2)
    assert bank["cr_median"] == pytest.approx(2.5)
    assert bank["n"] == 3
    assert bool(bank["enough_peers"]) is True
    barang = medians[medians["sector"] == "Barang"].iloc[0]
    assert bool(barang["enough_peers"]) is False


def test_classify_fundamentals_majority_and_missing():
    frame = benchmarks.load_fundamentals(FUNDAMENTALS_CSV)
    medians = benchmarks.sector_medians(frame)
    classified = benchmarks.classify_fundamentals(frame, medians)
    rows = {row["ticker"]: row for _, row in classified.iterrows()}
    assert rows["AAAA"]["score"] == 1
    assert rows["AAAA"]["comparisons"] == 3
    assert rows["AAAA"]["fundamental_above"] is False
    assert rows["CCCC"]["score"] == 3
    assert rows["CCCC"]["fundamental_above"] is True
    assert rows["DDDD"]["fundamental_above"] is None
    assert "peer" in rows["DDDD"]["notes"].lower()


def _results_for(tickers):
    market = pd.Series([0.01, 0.02, 0.03, 0.012, 0.015, 0.011])
    results = {}
    for ticker in tickers:
        stock = market * 2 + 0.01
        results[ticker] = metrics.analyze_asset(
            stock,
            market,
            instrument=ticker,
            rf_annual=0.0,
            period="D",
            legacy=False,
        )
    return results


def test_quadrant_table_maps_fundamental_and_alpha():
    frame = benchmarks.load_fundamentals(FUNDAMENTALS_CSV)
    medians = benchmarks.sector_medians(frame)
    results = _results_for(["AAAA", "CCCC"])
    table = benchmarks.quadrant_table(frame, medians, results)
    rows = {row["Ticker"]: row for _, row in table.iterrows()}
    assert rows["AAAA"]["Kuadran"].startswith("Kuadran 3")
    assert rows["CCCC"]["Kuadran"].startswith("Kuadran 1")
    assert rows["BBBB"]["Kuadran"] == "Tidak tersedia"
    assert rows["DDDD"]["Kuadran"] == "Tidak tersedia"


def test_template_and_save(tmp_path: Path):
    template = benchmarks.template_fundamentals(["indf", "antm"], {"INDF": "Consumer Non-Cyclicals"})
    assert list(template.columns) == benchmarks.FUNDAMENTAL_COLUMNS
    assert template.loc[0, "sector"] == "Consumer Non-Cyclicals"
    assert template.loc[1, "sector"] == ""
    assert template.loc[0, "as_of"]
    destination = tmp_path / "fundamentals.csv"
    benchmarks.save_fundamentals(template, destination)
    assert destination.exists()
    loaded = benchmarks.load_fundamentals(destination, roe_percent=True)
    assert list(loaded["ticker"]) == ["INDF", "ANTM"]


def test_save_fundamentals_roe_roundtrip(tmp_path: Path):
    frame = benchmarks.template_fundamentals(["AAAA"])
    frame.loc[0, "roe"] = 0.15
    destination = tmp_path / "fundamentals.csv"
    benchmarks.save_fundamentals(frame, destination, roe_percent=True)
    loaded = benchmarks.load_fundamentals(destination, roe_percent=True)
    assert loaded.loc[0, "roe"] == pytest.approx(0.15)


def test_load_sector_map(tmp_path: Path):
    path = tmp_path / "sector_map.csv"
    path.write_text("ticker,sector\nINDF,Consumer Non-Cyclicals\n", encoding="utf-8")
    mapping = benchmarks.load_sector_map(path)
    assert mapping == {"INDF": "Consumer Non-Cyclicals"}
