from pathlib import Path

from engine import assistant, universe


def codes(rows):
    return [row["code"] for row in rows]


def test_universe_is_complete():
    stats = universe.stats()
    assert stats["count"] >= 976
    assert stats["banks"] == 48
    assert stats["plantation"] >= 25


def test_sawit_returns_all_plantation():
    rows, broad = assistant.universe_suggestions("semua saham sawit di indonesia")
    assert broad is True
    assert len(rows) == 27
    assert all(row["subsector"] == "Plantation" for row in rows)
    assert {"AALI", "LSIP", "SIMP", "DSNG", "TBLA", "SSMS"} <= set(codes(rows))


def test_all_banks_are_returned():
    rows, broad = assistant.universe_suggestions("seluruh ticker perbankan")
    assert broad is True
    assert len(rows) == 48
    assert all(row["subsector"] == "Banks" for row in rows)
    assert {"BBCA", "BBRI", "BMRI", "BBNI", "BRIS", "BANK", "MCOR"} <= set(codes(rows))


def test_bank_syariah_is_filtered():
    rows, _ = assistant.universe_suggestions("bank syariah")
    assert {"BANK", "BRIS", "BTPS", "PNBS"} == set(codes(rows))
    assert all(row["subsector"] == "Banks" for row in rows)


def test_exact_code():
    rows, _ = assistant.universe_suggestions("BBCA")
    assert rows[0]["code"] == "BBCA"
    assert rows[0]["name"].startswith("Bank Central Asia")


def test_no_match():
    rows, _ = assistant.universe_suggestions("perusahaan roket antariksa")
    assert rows == []


def test_missing_file_returns_empty(tmp_path: Path):
    assert universe.load_universe(tmp_path / "tidak-ada.csv") == []


def test_merge_details_unknown():
    merged = universe.merge_details([{"code": "ZZZZ"}, {"code": "BBCA"}])
    assert merged[0]["known"] is False
    assert "verifikasi" in merged[0]["reason"].lower()
    assert merged[1]["known"] is True
    assert merged[1]["sector"] == "Financials"


def test_broad_selection_keeps_every_candidate():
    candidates, _ = assistant.universe_suggestions("semua bank")
    qwen = [{"code": "BBCA"}, {"code": "BBRI"}, {"code": "BMRI"}]
    final, ignored = assistant.select_suggestions("semua bank", qwen, candidates)
    assert len(final) == len(candidates) == 48
    assert ignored == []


def test_sector_query_keeps_all_without_broad_word():
    candidates, broad = assistant.universe_suggestions("carikan ticker bank")
    assert broad is False
    qwen = [{"code": "BBCA"}, {"code": "BBRI"}, {"code": "BMRI"}]
    final, _ = assistant.select_suggestions("carikan ticker bank", qwen, candidates)
    assert len(final) == len(candidates) == 48


def test_selection_drops_foreign_code():
    candidates, _ = assistant.universe_suggestions("BBCA")
    final, ignored = assistant.select_suggestions("BBCA", [{"code": "BBCA"}, {"code": "ZZZZ"}], candidates)
    assert codes(final) == ["BBCA"]
    assert ignored == ["ZZZZ"]


def test_cement_group_is_complete():
    rows, _ = assistant.universe_suggestions("semen")
    assert {"SMGR", "INTP", "SMBR", "SMCB"} == set(codes(rows))
    assert all(row["subsector"] == "Cement" for row in rows)


def test_copy_prompt_contains_candidates():
    candidates, _ = assistant.universe_suggestions("sawit")
    prompt = assistant.build_copy_prompt("sawit", candidates)
    assert "AALI|" in prompt
    assert "HANYA dari kandidat" in prompt
    assert "tickers" in prompt


def test_system_prompt_without_candidates():
    prompt = assistant.system_prompt()
    assert "Tidak ada kandidat" in prompt
    assert "tickers" in prompt
