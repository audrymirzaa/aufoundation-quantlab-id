from engine import assistant


def test_catalog_matches_bank():
    results = assistant.catalog_suggestions("carikan ticker bank")
    codes = [item["code"] for item in results]
    assert "BBCA" in codes
    assert "BBRI" in codes
    assert all(item["sector"] == "Financials" for item in results)


def test_catalog_matches_semen():
    results = assistant.catalog_suggestions("saham industri semen")
    codes = [item["code"] for item in results]
    assert {"SMGR", "INTP", "SMCB", "SMBR"} <= set(codes)
    assert all(item["sector"] == "Basic Materials" for item in results)


def test_catalog_no_match():
    assert assistant.catalog_suggestions("perusahaan roket antariksa") == []


def test_normalize_code():
    assert assistant.normalize_code("bbca") == "BBCA"
    assert assistant.normalize_code("BBRI.JK") == "BBRI"
    assert assistant.normalize_code("IDX:TLKM") == "TLKM"
    assert assistant.normalize_code("ABCDE") == ""
    assert assistant.normalize_code("") == ""


def test_parse_fenced_json():
    text = """```json
    {"message":"ok","tickers":[{"code":"bbca.jk","name":"BCA","sector":"Financials","reason":"bank"}]}
    ```"""
    parsed = assistant.parse_ticker_response(text)
    assert parsed["error"] is None
    assert parsed["tickers"][0]["code"] == "BBCA"
    assert parsed["tickers"][0]["known"] is True


def test_parse_list_payload_and_unknown_code():
    text = '[{"ticker":"ZZZZ","alasan":"uji"}, "ANTM"]'
    parsed = assistant.parse_ticker_response(text)
    assert parsed["error"] is None
    codes = [item["code"] for item in parsed["tickers"]]
    assert codes == ["ZZZZ", "ANTM"]
    unknown = next(item for item in parsed["tickers"] if item["code"] == "ZZZZ")
    assert unknown["known"] is False
    assert "verifikasi" in unknown["reason"].lower()


def test_parse_saham_key():
    text = '{"saham":[{"kode":"INDF","sektor":"Consumer Non-Cyclicals"}]}'
    parsed = assistant.parse_ticker_response(text)
    assert parsed["tickers"][0]["code"] == "INDF"
    assert parsed["tickers"][0]["name"].startswith("Indofood Sukses Makmur")


def test_parse_invalid_json():
    parsed = assistant.parse_ticker_response("maaf saya tidak bisa")
    assert parsed["error"] is not None
    assert parsed["tickers"] == []


def test_copy_prompt_contains_schema():
    prompt = assistant.build_copy_prompt("cari semen")
    assert "cari semen" in prompt
    assert '"tickers"' in prompt
    assert "Basic Materials" in prompt


def test_openai_chat_url_variants():
    assert assistant.openai_chat_url("http://localhost:11434") == "http://localhost:11434/v1/chat/completions"
    assert assistant.openai_chat_url("http://localhost:1234/v1") == "http://localhost:1234/v1/chat/completions"
    assert assistant.openai_chat_url("http://localhost:8080/v1/chat/completions") == "http://localhost:8080/v1/chat/completions"


def test_catalog_table():
    frame = assistant.catalog_table(assistant.catalog_suggestions("bank"))
    assert list(frame.columns) == ["Ticker", "Nama", "Sektor", "Subsektor", "Alasan", "Dikenal", "Sumber"]
    assert len(frame) > 0


def test_ask_openai_sends_universe_candidates(monkeypatch):
    captured = {}

    def fake_chat(endpoint, model, messages, **kwargs):
        captured["messages"] = messages
        return '{"message":"ok","tickers":[]}'

    monkeypatch.setattr(assistant, "chat_openai", fake_chat)
    candidates, _ = assistant.universe_suggestions("sawit")
    assistant.ask_openai("http://127.0.0.1:11434/v1", "qwen2.5:3b", "sawit", candidates=candidates)
    system = captured["messages"][0]["content"]
    assert "AALI|" in system
    assert "HANYA dari kandidat" in system
    assert len(captured["messages"]) == 2
