from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "ticker_universe.csv"

SECTOR_ALIASES = {
    "Financials": ["bank", "perbankan", "keuangan", "financial", "finansial", "asuransi"],
    "Consumer Non-Cyclicals": ["konsumsi primer", "consumer non", "makanan", "minuman", "fmcg", "staples", "agro"],
    "Consumer Cyclicals": ["konsumsi sekunder", "consumer cyclicals", "ritel", "retail", "otomotif"],
    "Basic Materials": ["tambang", "mining", "material", "logam", "nikel", "kimia"],
    "Energy": ["energi", "energy", "batu bara", "coal", "minyak", "oil", "gas"],
    "Infrastructure": ["infrastruktur", "telekomunikasi", "telco", "tol", "menara"],
    "Healthcare": ["kesehatan", "healthcare", "farmasi", "rumah sakit", "medis"],
    "Technology": ["teknologi", "technology", "digital", "internet", "software"],
    "Properties & Real Estate": ["properti", "property", "real estate", "perumahan"],
    "Industrials": ["industri", "industrial", "manufaktur", "alat berat"],
    "Transportation & Logistics": ["transportasi", "logistik", "pelayaran", "penerbangan", "kargo"],
}

SUBSECTOR_ALIASES = {
    "Banks": ["bank", "perbankan", "bank umum"],
    "Plantation": ["sawit", "kelapa sawit", "cpo", "perkebunan", "plantation", "agro", "tbs"],
    "Cement": ["semen", "cement"],
}

BROAD_WORDS = {"semua", "seluruh", "daftar", "list", "all", "lengkap"}

STOPWORDS = {
    "cari", "carikan", "saham", "ticker", "tikers", "kode", "di", "industri",
    "sektor", "yang", "dan", "atau", "untuk", "apa", "saja", "beri", "berikan",
    "list", "daftar", "ini", "itu", "the", "in", "of", "and", "please", "tolong",
    "perusahaan", "emiten", "per", "semua", "seluruh", "lengkap", "all", "saja",
    "indonesia", "indo", "idx", "bei", "bursa", "efek", "tercatat", "terdaftar",
}

MAX_CANDIDATES = 100
UNIVERSE_SOURCE = "data/ticker_universe.csv"


def universe_path() -> Path:
    return DEFAULT_PATH


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u00a0", " ").split())


def _split_aliases(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(part.strip().lower() for part in str(value or "").split("|") if part.strip()))


def _entry(row: Mapping[str, Any]) -> dict[str, Any]:
    code = str(row.get("code") or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{4}", code):
        return {}
    return {
        "code": code,
        "name": _clean(row.get("name")),
        "sector": _clean(row.get("sector")),
        "subsector": _clean(row.get("subsector")),
        "aliases": _split_aliases(row.get("aliases", "")),
        "board": _clean(row.get("board")),
        "listed": _clean(row.get("listed")),
        "sector_source": _clean(row.get("sector_source")),
        "source": _clean(row.get("source")),
        "updated": _clean(row.get("updated")),
        "known": True,
    }


@lru_cache(maxsize=4)
def _load_cached(path: str, mtime: float) -> tuple[dict[str, Any], ...]:
    file_path = Path(path)
    rows: list[dict[str, Any]] = []
    with open(file_path, newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            entry = _entry(raw)
            if entry:
                rows.append(entry)
    return tuple(rows)


def load_universe(path: str | Path | None = None) -> list[dict[str, Any]]:
    file_path = Path(path) if path else DEFAULT_PATH
    try:
        stat = file_path.stat()
    except OSError:
        return []
    try:
        return list(_load_cached(str(file_path), stat.st_mtime))
    except (OSError, csv.Error):
        return []


def normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("IDX:", "").replace("IDX.", "")
    text = re.sub(r"[^A-Z0-9.]", "", text)
    if text.endswith(".JK"):
        text = text[:-3]
    text = text.strip(".")
    return text if re.fullmatch(r"[A-Z]{4}", text) else ""


def tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if token not in STOPWORDS]


def is_broad_query(query: str) -> bool:
    return bool(BROAD_WORDS & set(re.findall(r"[a-z0-9]+", str(query).lower())))


def is_group_query(query: str) -> bool:
    return any(token in _SUBSECTOR_TOKENS or token in _SECTOR_TOKENS for token in tokens(query))


def _texts(entry: Mapping[str, Any]) -> list[str]:
    return [
        str(entry.get("code", "")).lower(),
        str(entry.get("name", "")).lower(),
        str(entry.get("sector", "")).lower(),
        str(entry.get("subsector", "")).lower(),
        *[str(alias).lower() for alias in entry.get("aliases", ())],
    ]


def _matches(entry: Mapping[str, Any], token: str) -> bool:
    return any(token in text for text in _texts(entry))


def _alias_tokens(aliases: Mapping[str, Sequence[str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, values in aliases.items():
        for value in values:
            result[str(value).lower()] = name
    return result


_SUBSECTOR_TOKENS = _alias_tokens(SUBSECTOR_ALIASES)
_SECTOR_TOKENS = _alias_tokens(SECTOR_ALIASES)


def _group_matches(entries: Sequence[Mapping[str, Any]], token: str) -> list[Mapping[str, Any]]:
    subsector = _SUBSECTOR_TOKENS.get(token)
    if subsector:
        return [entry for entry in entries if str(entry.get("subsector", "")).lower() == subsector.lower()]
    sector = _SECTOR_TOKENS.get(token)
    if sector:
        return [entry for entry in entries if str(entry.get("sector", "")).lower() == sector.lower()]
    return []


def search_universe(query: str, limit: int = MAX_CANDIDATES, path: str | Path | None = None) -> list[dict[str, Any]]:
    entries = load_universe(path)
    if not entries:
        return []
    query_tokens = tokens(query)
    if not query_tokens:
        return []
    lowered_query = str(query).lower()
    group_tokens = [token for token in query_tokens if token in _SUBSECTOR_TOKENS or token in _SECTOR_TOKENS]
    qualifier_tokens = [token for token in query_tokens if token not in group_tokens]
    all_codes = {entry["code"] for entry in entries}
    exact_codes = {
        token.upper()
        for token in query_tokens
        if len(token) == 4 and token.upper() in all_codes and token not in group_tokens
    }

    group_entries: set[str] = set()
    for token in group_tokens:
        for entry in _group_matches(entries, token):
            if qualifier_tokens and not any(_matches(entry, qualifier) for qualifier in qualifier_tokens):
                continue
            group_entries.add(entry["code"])

    scored: dict[str, tuple[float, list[str]]] = {}
    for entry in entries:
        code = entry["code"]
        score = 0.0
        matched: list[str] = []
        if code in group_entries:
            score += 120.0
            matched.append("grup sektor")
        if code.lower() in query_tokens:
            score += 200.0
            matched.append(code)
        if lowered_query and entry["name"].lower() in lowered_query:
            score += 80.0
            matched.append(entry["name"])
        for token in query_tokens:
            if token == code.lower():
                score += 200.0
                matched.append(token)
            elif token in entry["name"].lower():
                score += 30.0
                matched.append(token)
            elif any(token in alias for alias in entry["aliases"]):
                score += 60.0
                matched.append(token)
            elif token in entry["subsector"].lower():
                score += 50.0
                matched.append(token)
            elif token in entry["sector"].lower():
                score += 20.0
                matched.append(token)
        if score > 0:
            reason = "Cocok: " + ", ".join(dict.fromkeys(matched)) if matched else ""
            scored[code] = (score, [reason])
    rows = []
    for entry in entries:
        if entry["code"] not in scored:
            continue
        score, reasons = scored[entry["code"]]
        rows.append({**entry, "reason": reasons[0] if reasons else "", "match_score": score})
    if exact_codes:
        rows = [row for row in rows if row["code"] in exact_codes]
    if group_entries and qualifier_tokens:
        rows = [row for row in rows if row["code"] in group_entries]
    board_rank = {"utama": 0, "pengembangan": 1, "pemantauan khusus": 2}
    rows.sort(
        key=lambda row: (
            -row["match_score"],
            board_rank.get(str(row.get("board", "")).lower(), 9),
            row["code"],
        )
    )
    return rows[:limit]


def merge_details(items: Sequence[Mapping[str, Any]], path: str | Path | None = None) -> list[dict[str, Any]]:
    entries = load_universe(path)
    by_code = {entry["code"]: entry for entry in entries}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        code = normalize_code(item.get("code") or item.get("ticker") or item.get("kode") or item.get("symbol"))
        if not code or code in seen:
            continue
        seen.add(code)
        known = by_code.get(code)
        name = _clean(item.get("name") or item.get("nama") or (known["name"] if known else ""))
        sector = _clean(item.get("sector") or item.get("sektor") or (known["sector"] if known else ""))
        subsector = _clean(item.get("subsector") or item.get("subsektor") or (known["subsector"] if known else ""))
        reason = _clean(item.get("reason") or item.get("alasan") or "")
        if known is None:
            reason = f"{reason} Kode tidak ada di universe; verifikasi sebelum ambil data.".strip()
        merged.append(
            {
                "code": code,
                "name": name,
                "sector": sector,
                "subsector": subsector,
                "reason": reason,
                "known": known is not None,
                "source": UNIVERSE_SOURCE if known else "luar universe",
            }
        )
    return merged


def filter_known(items: Sequence[Mapping[str, Any]], path: str | Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    entries = load_universe(path)
    codes = {entry["code"] for entry in entries}
    kept: list[dict[str, Any]] = []
    ignored: list[str] = []
    for item in items:
        code = normalize_code(item.get("code"))
        if not code:
            continue
        if code in codes:
            kept.append(dict(item))
        else:
            ignored.append(code)
    return kept, ignored


def sector_lookup(path: str | Path | None = None) -> dict[str, str]:
    return {entry["code"]: entry.get("sector", "") for entry in load_universe(path)}


def prompt_lines(entries: Sequence[Mapping[str, Any]], limit: int = MAX_CANDIDATES) -> str:
    lines = []
    for entry in entries[:limit]:
        lines.append(
            f"{entry['code']}|{entry.get('name','')}|{entry.get('sector','')}|{entry.get('subsector','')}"
        )
    return "\n".join(lines)


def stats(path: str | Path | None = None) -> dict[str, Any]:
    entries = load_universe(path)
    return {
        "count": len(entries),
        "banks": sum(1 for entry in entries if entry.get("subsector") == "Banks"),
        "plantation": sum(1 for entry in entries if entry.get("subsector") == "Plantation"),
        "path": str(Path(path) if path else DEFAULT_PATH),
    }
