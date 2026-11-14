from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

import pandas as pd

from . import universe

SECTOR_ALIASES = universe.SECTOR_ALIASES
MAX_SUGGESTIONS = universe.MAX_CANDIDATES

CATALOG: list[dict[str, Any]] = [
    {"code": "BBCA", "name": "Bank Central Asia", "sector": "Financials", "aliases": ["bca", "bank"]},
    {"code": "BBRI", "name": "Bank Rakyat Indonesia", "sector": "Financials", "aliases": ["bri", "bank"]},
    {"code": "BMRI", "name": "Bank Mandiri", "sector": "Financials", "aliases": ["mandiri", "bank"]},
    {"code": "BBNI", "name": "Bank Negara Indonesia", "sector": "Financials", "aliases": ["bni", "bank"]},
    {"code": "BRIS", "name": "Bank Syariah Indonesia", "sector": "Financials", "aliases": ["bsi", "syariah", "bank"]},
    {"code": "BTPS", "name": "BTPN Syariah", "sector": "Financials", "aliases": ["btpn", "bank"]},
    {"code": "INDF", "name": "Indofood Sukses Makmur", "sector": "Consumer Non-Cyclicals", "aliases": ["indofood", "makanan"]},
    {"code": "ICBP", "name": "Indofood CBP", "sector": "Consumer Non-Cyclicals", "aliases": ["indomie", "makanan"]},
    {"code": "MYOR", "name": "Mayora Indah", "sector": "Consumer Non-Cyclicals", "aliases": ["mayora", "makanan"]},
    {"code": "UNVR", "name": "Unilever Indonesia", "sector": "Consumer Non-Cyclicals", "aliases": ["unilever", "fmcg"]},
    {"code": "AMRT", "name": "Sumber Alfaria Trijaya", "sector": "Consumer Non-Cyclicals", "aliases": ["alfamart", "ritel"]},
    {"code": "CPIN", "name": "Charoen Pokphand Indonesia", "sector": "Consumer Non-Cyclicals", "aliases": ["charoen", "pakan"]},
    {"code": "JPFA", "name": "Japfa Comfeed Indonesia", "sector": "Consumer Non-Cyclicals", "aliases": ["japfa", "pakan"]},
    {"code": "LPPF", "name": "Matahari Department Store", "sector": "Consumer Cyclicals", "aliases": ["matahari", "mds", "ritel"]},
    {"code": "MAPI", "name": "Map Aktif Adiperkasa", "sector": "Consumer Cyclicals", "aliases": ["map", "ritel"]},
    {"code": "ACES", "name": "Aspirasi Hidup Indonesia", "sector": "Consumer Cyclicals", "aliases": ["ace hardware", "ritel"]},
    {"code": "ERAA", "name": "Erajaya Swasembada", "sector": "Consumer Cyclicals", "aliases": ["erajaya", "gadget"]},
    {"code": "GJTL", "name": "Gajah Tunggal", "sector": "Consumer Cyclicals", "aliases": ["ban", "tire"]},
    {"code": "AUTO", "name": "Astra Otoparts", "sector": "Consumer Cyclicals", "aliases": ["otomotif", "komponen"]},
    {"code": "ANTM", "name": "Aneka Tambang", "sector": "Basic Materials", "aliases": ["antam", "emas", "nikel", "tambang"]},
    {"code": "INCO", "name": "Vale Indonesia", "sector": "Basic Materials", "aliases": ["vale", "nikel", "tambang"]},
    {"code": "TINS", "name": "Timah", "sector": "Basic Materials", "aliases": ["timah", "tambang"]},
    {"code": "MDKA", "name": "Merdeka Copper Gold", "sector": "Basic Materials", "aliases": ["merdeka", "tembaga", "emas"]},
    {"code": "SMGR", "name": "Semen Indonesia", "sector": "Basic Materials", "aliases": ["semen", "cement", "semen gresik"]},
    {"code": "INTP", "name": "Indocement Tunggal Prakarsa", "sector": "Basic Materials", "aliases": ["semen", "cement", "indocement"]},
    {"code": "BRPT", "name": "Barito Pacific", "sector": "Basic Materials", "aliases": ["barito", "petrokimia"]},
    {"code": "TPIA", "name": "Chandra Asri Pacific", "sector": "Basic Materials", "aliases": ["chandra asri", "petrokimia"]},
    {"code": "ADRO", "name": "Alamtri Resources", "sector": "Energy", "aliases": ["adaro", "batu bara", "coal"]},
    {"code": "PTBA", "name": "Bukit Asam", "sector": "Energy", "aliases": ["bukit asam", "batu bara", "coal"]},
    {"code": "ITMG", "name": "Indo Tambangraya Megah", "sector": "Energy", "aliases": ["itm", "batu bara", "coal"]},
    {"code": "HRUM", "name": "Harum Energy", "sector": "Energy", "aliases": ["harum", "batu bara", "coal"]},
    {"code": "MEDC", "name": "Medco Energi", "sector": "Energy", "aliases": ["medco", "minyak", "gas"]},
    {"code": "PGAS", "name": "Perusahaan Gas Negara", "sector": "Energy", "aliases": ["gas", "pgn"]},
    {"code": "AKRA", "name": "AKR Corporindo", "sector": "Energy", "aliases": ["akr", "distribusi"]},
    {"code": "TLKM", "name": "Telkom Indonesia", "sector": "Infrastructure", "aliases": ["telkom", "telekomunikasi", "telco"]},
    {"code": "EXCL", "name": "XL Axiata", "sector": "Infrastructure", "aliases": ["xl", "telekomunikasi", "telco"]},
    {"code": "ISAT", "name": "Indosat Ooredoo Hutchison", "sector": "Infrastructure", "aliases": ["indosat", "telekomunikasi", "telco"]},
    {"code": "TOWR", "name": "Sarana Menara Nusantara", "sector": "Infrastructure", "aliases": ["menara", "tower"]},
    {"code": "TBIG", "name": "Tower Bersama Infrastructure", "sector": "Infrastructure", "aliases": ["menara", "tower"]},
    {"code": "JSMR", "name": "Jasa Marga", "sector": "Infrastructure", "aliases": ["tol", "jalan tol"]},
    {"code": "WIFI", "name": "Solusi Sinergi Digital", "sector": "Infrastructure", "aliases": ["wifi", "internet"]},
    {"code": "KLBF", "name": "Kalbe Farma", "sector": "Healthcare", "aliases": ["kalbe", "farmasi"]},
    {"code": "SIDO", "name": "Sido Muncul", "sector": "Healthcare", "aliases": ["sido muncul", "herbal"]},
    {"code": "MIKA", "name": "Mitra Keluarga Karyasehat", "sector": "Healthcare", "aliases": ["mitra keluarga", "rumah sakit"]},
    {"code": "HEAL", "name": "Medikaloka Hermina", "sector": "Healthcare", "aliases": ["hermina", "rumah sakit"]},
    {"code": "GOTO", "name": "GoTo Gojek Tokopedia", "sector": "Technology", "aliases": ["gojek", "tokopedia", "digital"]},
    {"code": "EMTK", "name": "Elang Mahkota Teknologi", "sector": "Technology", "aliases": ["emtek", "digital"]},
    {"code": "DCII", "name": "DCI Indonesia", "sector": "Technology", "aliases": ["data center", "digital"]},
    {"code": "MTDL", "name": "Metrodata Electronics", "sector": "Technology", "aliases": ["metrodata", "teknologi"]},
    {"code": "BUKA", "name": "Bukalapak", "sector": "Technology", "aliases": ["bukalapak", "ecommerce"]},
    {"code": "BSDE", "name": "Bumi Serpong Damai", "sector": "Properties & Real Estate", "aliases": ["bsd", "properti"]},
    {"code": "PWON", "name": "Pakuwon Jati", "sector": "Properties & Real Estate", "aliases": ["pakuwon", "properti"]},
    {"code": "CTRA", "name": "Ciputra Development", "sector": "Properties & Real Estate", "aliases": ["ciputra", "properti"]},
    {"code": "SMRA", "name": "Summarecon Agung", "sector": "Properties & Real Estate", "aliases": ["summarecon", "properti"]},
    {"code": "ASRI", "name": "Alam Sutera Realty", "sector": "Properties & Real Estate", "aliases": ["alam sutera", "properti"]},
    {"code": "LPKR", "name": "Lippo Karawaci", "sector": "Properties & Real Estate", "aliases": ["lippo", "properti"]},
    {"code": "ASII", "name": "Astra International", "sector": "Industrials", "aliases": ["astra", "otomotif", "alat berat"]},
    {"code": "UNTR", "name": "United Tractors", "sector": "Industrials", "aliases": ["united tractors", "alat berat"]},
    {"code": "HEXA", "name": "Hexindo Adiperkasa", "sector": "Industrials", "aliases": ["hexindo", "alat berat"]},
    {"code": "ARNA", "name": "Arwana Citramulia", "sector": "Industrials", "aliases": ["arwana", "keramik"]},
    {"code": "ASSA", "name": "Adi Sarana Armada", "sector": "Transportation & Logistics", "aliases": ["asssa", "logistik", "rental"]},
    {"code": "BIRD", "name": "Blue Bird", "sector": "Transportation & Logistics", "aliases": ["blue bird", "taksi"]},
    {"code": "TMAS", "name": "Temas", "sector": "Transportation & Logistics", "aliases": ["temas", "pelayaran"]},
    {"code": "SMDR", "name": "Samudera Indonesia", "sector": "Transportation & Logistics", "aliases": ["samudera", "pelayaran"]},
    {"code": "GIAA", "name": "Garuda Indonesia", "sector": "Transportation & Logistics", "aliases": ["garuda", "penerbangan"]},
    {"code": "PGEO", "name": "Pertamina Geothermal Energy", "sector": "Energy", "aliases": ["geothermal", "energi"]},
    {"code": "ESSA", "name": "Essa Industries Indonesia", "sector": "Basic Materials", "aliases": ["essa", "kimia"]},
    {"code": "BRMS", "name": "Bumi Resources Minerals", "sector": "Basic Materials", "aliases": ["bumi resources", "tambang"]},
]

STOPWORDS = {
    "cari",
    "carikan",
    "saham",
    "ticker",
    "tikers",
    "kode",
    "di",
    "industri",
    "sektor",
    "yang",
    "dan",
    "atau",
    "untuk",
    "apa",
    "saja",
    "beri",
    "berikan",
    "list",
    "daftar",
    "ini",
    "itu",
    "the",
    "in",
    "of",
    "and",
    "please",
    "tolong",
    "perusahaan",
    "emiten",
    "per",
}

CATALOG_BY_CODE = {item["code"]: item for item in CATALOG}


class AssistantError(RuntimeError):
    pass


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if token not in STOPWORDS]


def catalog_suggestions(query: str, limit: int = MAX_SUGGESTIONS) -> list[dict[str, Any]]:
    entries = universe.search_universe(query, limit=limit)
    if entries:
        return entries
    if universe.load_universe():
        return []
    return _catalog_fallback(query, limit)


def _catalog_fallback(query: str, limit: int = 12) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    if not tokens:
        return []
    lowered_query = str(query).lower()
    results: list[tuple[int, dict[str, Any], list[str]]] = []
    for item in CATALOG:
        score = 0
        matched: list[str] = []
        code = item["code"].lower()
        name = item["name"].lower()
        sector = item["sector"].lower()
        aliases = [str(alias).lower() for alias in item.get("aliases", [])]
        sector_aliases = [str(alias).lower() for alias in SECTOR_ALIASES.get(item["sector"], [])]
        if item["code"].lower() in tokens and len(item["code"]) == 4:
            score += 120
            matched.append(item["code"])
        if name in lowered_query:
            score += 50
        for token in tokens:
            if token == code:
                score += 120
                matched.append(token)
            elif token in name:
                score += 25
                matched.append(token)
            elif any(token in alias for alias in aliases):
                score += 35
                matched.append(token)
            elif token in sector:
                score += 15
                matched.append(token)
            elif any(token in alias for alias in sector_aliases):
                score += 20
                matched.append(token)
        if score > 0:
            results.append(
                (
                    score,
                    {
                        "code": item["code"],
                        "name": item["name"],
                        "sector": item["sector"],
                        "subsector": "",
                        "reason": "Cocok: " + ", ".join(sorted(set(matched))),
                        "known": True,
                        "source": "katalog bawaan",
                    },
                    matched,
                )
            )
    results.sort(key=lambda row: (-row[0], row[1]["code"]))
    return [row[1] for row in results[:limit]]


def normalize_code(value: Any) -> str:
    return universe.normalize_code(value)


def merge_catalog_details(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if universe.load_universe():
        return universe.merge_details(items)
    return _catalog_merge(items)


def _catalog_merge(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        code = normalize_code(item.get("code") or item.get("ticker") or item.get("kode") or item.get("symbol"))
        if not code or code in seen:
            continue
        seen.add(code)
        known = CATALOG_BY_CODE.get(code)
        name = str(item.get("name") or item.get("nama") or (known["name"] if known else "")).strip()
        sector = str(item.get("sector") or item.get("sektor") or (known["sector"] if known else "")).strip()
        reason = str(item.get("reason") or item.get("alasan") or "").strip()
        if known is None:
            note = "Kode tidak ada di katalog; verifikasi sebelum ambil data."
            reason = f"{reason} {note}".strip()
        merged.append(
            {
                "code": code,
                "name": name,
                "sector": sector,
                "reason": reason,
                "known": known is not None,
            }
        )
    return merged


def system_prompt(candidates: Sequence[Mapping[str, Any]] | None = None) -> str:
    sectors = ", ".join(sorted(SECTOR_ALIASES))
    base = (
        "Anda asisten analisa saham Indonesia (IDX). Tugas Anda hanya memilih ticker IDX yang relevan "
        "dengan pertanyaan pengguna. Balas HANYA satu objek JSON valid tanpa teks lain, dengan skema: "
        '{"message":"ringkasan singkat","tickers":[{"code":"BBCA","name":"Bank Central Asia",'
        '"sector":"Financials","reason":"alasan singkat"}]}. '
        "Aturan: kode 4 huruf tanpa akhiran .JK, hanya saham yang tercatat di IDX, maksimal 20 ticker, "
        "jangan mengarang kode. Jika tidak yakin, kosongkan tickers dan jelaskan di message. "
        f"Sektor yang dipakai: {sectors}."
    )
    if candidates:
        lines = universe.prompt_lines(candidates)
        base += (
            "\n\nKandidat resmi dari universe (kode|nama|sektor|subsektor):\n"
            f"{lines}\n\n"
            "Pilih HANYA dari kandidat di atas. Jangan menambah kode di luar daftar. "
            "Daftar lengkap tetap ditampilkan aplikasi; Anda cukup meranking dan menjelaskan."
        )
    else:
        base += "\n\nTidak ada kandidat dari universe. Kosongkan tickers dan jelaskan bahwa tidak ada kandidat."
    return base


def build_copy_prompt(query: str, candidates: Sequence[Mapping[str, Any]] | None = None) -> str:
    return f"{system_prompt(candidates)}\n\nPertanyaan pengguna: {query}\n\nJawab hanya dengan JSON sesuai skema."


def universe_suggestions(query: str, limit: int = MAX_SUGGESTIONS) -> tuple[list[dict[str, Any]], bool]:
    return universe.search_universe(query, limit=limit), universe.is_broad_query(query)


def select_suggestions(
    query: str,
    qwen_tickers: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    qwen_tickers = [dict(item) for item in qwen_tickers]
    allowed = {item["code"]: item for item in candidates}
    chosen = [item for item in qwen_tickers if item.get("code") in allowed]
    ignored = [str(item.get("code")) for item in qwen_tickers if item.get("code") not in allowed]
    if universe.is_broad_query(query) or universe.is_group_query(query):
        final = []
        reasons = {item["code"]: item.get("reason", "") for item in chosen}
        for item in candidates:
            row = dict(item)
            if reasons.get(item["code"]):
                row["reason"] = reasons[item["code"]]
            final.append(row)
        return final, ignored
    if chosen:
        merged = []
        for item in chosen:
            base = dict(allowed[item["code"]])
            if item.get("reason"):
                base["reason"] = item["reason"]
            merged.append(base)
        return merged, ignored
    return [dict(item) for item in candidates], ignored


def parse_ticker_response(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {"tickers": [], "message": "", "error": "Jawaban kosong."}
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).replace("```", "").strip()
    payload: Any = None
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(cleaned[start : end + 1])
            except (json.JSONDecodeError, TypeError):
                payload = None
        if payload is None:
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(cleaned[start : end + 1])
                except (json.JSONDecodeError, TypeError):
                    payload = None
    if payload is None:
        return {"tickers": [], "message": cleaned[:500], "error": "Jawaban bukan JSON valid."}

    message = ""
    items: Any = []
    if isinstance(payload, dict):
        message = str(payload.get("message") or payload.get("pesan") or "").strip()
        for key in ("tickers", "saham", "results", "data", "rekomendasi"):
            if key in payload:
                items = payload[key]
                break
        else:
            if any(key in payload for key in ("code", "ticker", "kode", "symbol")):
                items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        return {"tickers": [], "message": message, "error": "Struktur JSON tidak dikenal."}

    if isinstance(items, (str, dict)):
        items = [items]
    if not isinstance(items, list):
        return {"tickers": [], "message": message, "error": "Daftar ticker tidak valid."}

    normalized = []
    for item in items:
        if isinstance(item, str):
            normalized.append({"code": item})
        elif isinstance(item, Mapping):
            normalized.append(dict(item))
    tickers = merge_catalog_details(normalized)
    return {"tickers": tickers, "message": message, "error": None}


def openai_chat_url(endpoint: str) -> str:
    base = str(endpoint or "").strip().rstrip("/")
    if not base:
        raise AssistantError("Endpoint kosong.")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    if re.search(r"/v1/", base):
        return base
    return f"{base}/v1/chat/completions"


def chat_openai(
    endpoint: str,
    model: str,
    messages: Sequence[Mapping[str, str]],
    *,
    api_key: str | None = None,
    timeout: float = 90.0,
) -> str:
    try:
        import requests
    except ImportError as exc:
        raise AssistantError("Library requests belum terpasang.") from exc
    url = openai_chat_url(endpoint)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": list(messages),
        "temperature": 0.2,
        "stream": False,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise AssistantError(f"Tidak bisa menghubungi {url}: {exc}") from exc
    if response.status_code >= 400:
        raise AssistantError(f"Endpoint menolak ({response.status_code}): {response.text[:300]}")
    try:
        data = response.json()
        return str(data["choices"][0]["message"]["content"])
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AssistantError(f"Format jawaban tidak dikenal: {response.text[:300]}") from exc


def ask_openai(
    endpoint: str,
    model: str,
    query: str,
    *,
    candidates: Sequence[Mapping[str, Any]] | None = None,
    history: Sequence[Mapping[str, str]] | None = None,
    api_key: str | None = None,
    timeout: float = 90.0,
) -> str:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt(candidates)}]
    for message in history or []:
        role = message.get("role")
        content = message.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    messages.append({"role": "user", "content": query})
    return chat_openai(endpoint, model, messages, api_key=api_key, timeout=timeout)


def test_connection(endpoint: str, model: str, api_key: str | None = None) -> str:
    return chat_openai(
        endpoint,
        model,
        [
            {"role": "system", "content": "Balas hanya dengan kata OK."},
            {"role": "user", "content": "Tes koneksi."},
        ],
        api_key=api_key,
        timeout=30.0,
    )


def catalog_table(tickers: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in tickers:
        rows.append(
            {
                "Ticker": item.get("code", ""),
                "Nama": item.get("name", ""),
                "Sektor": item.get("sector", ""),
                "Subsektor": item.get("subsector", ""),
                "Alasan": item.get("reason", ""),
                "Dikenal": "Ya" if item.get("known") else "Tidak",
                "Sumber": item.get("source", "universe"),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["Ticker", "Nama", "Sektor", "Subsektor", "Alasan", "Dikenal", "Sumber"],
    )
