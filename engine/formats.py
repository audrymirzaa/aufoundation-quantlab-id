from __future__ import annotations

from typing import Literal

Period = Literal["D", "W", "M"]

ANNUALIZATION = {"D": 252, "W": 52, "M": 12}
PERIOD_LABEL = {"D": "Harian", "W": "Mingguan", "M": "Bulanan"}
RESAMPLE_RULE = {"W": "W-FRI", "M": "ME"}

PERIOD_ALIASES = {
    "d": "D",
    "h": "D",
    "harian": "D",
    "day": "D",
    "daily": "D",
    "w": "W",
    "minggu": "W",
    "mingguan": "W",
    "week": "W",
    "weekly": "W",
    "m": "M",
    "bulan": "M",
    "bulanan": "M",
    "month": "M",
    "monthly": "M",
}


def normalize_period(value: str) -> str:
    key = str(value).strip().lower()
    if key not in PERIOD_ALIASES:
        raise ValueError(f"Periode tidak dikenal: {value!r}. Gunakan D, W, atau M.")
    return PERIOD_ALIASES[key]


def annualization_factor(period: str) -> int:
    return ANNUALIZATION[normalize_period(period)]


def annualize_return(periodic_return: float, period: str) -> float:
    factor = annualization_factor(period)
    base = 1.0 + periodic_return
    if base <= 0:
        return periodic_return * factor
    return base**factor - 1.0


def annualize_volatility(periodic_sd: float, period: str) -> float:
    return periodic_sd * (annualization_factor(period) ** 0.5)


def format_percent(value: float | None, decimals: int = 2, locale: str = "id") -> str:
    if value is None:
        return "N/A"
    try:
        if value != value:
            return "N/A"
    except TypeError:
        return "N/A"
    text = f"{value * 100:,.{decimals}f}"
    if locale == "id":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{text}%"


def format_decimal(value: float | None, decimals: int = 4, locale: str = "id") -> str:
    if value is None:
        return "N/A"
    text = f"{value:,.{decimals}f}"
    if locale == "id":
        text = text.replace(",", "_").replace(".", ",").replace("_", ".")
    return text
