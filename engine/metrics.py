from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .formats import annualization_factor, annualize_return, annualize_volatility, normalize_period


class InsufficientDataError(ValueError):
    pass


@dataclass
class AssetMetrics:
    instrument: str
    period: str
    n: int
    mean_return: float
    sd: float
    cv: float | None
    cv_valid: bool
    beta: float | None
    beta_category: str
    rf_annual: float
    rf_period: float
    er_market: float
    erp: float
    capm: float | None
    alpha: float | None
    mean_annual: float
    sd_annual: float
    capm_annual: float | None
    alpha_annual: float | None
    legacy: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _prepare_pair(
    stock_returns: Sequence[float] | pd.Series,
    market_returns: Sequence[float] | pd.Series,
) -> pd.DataFrame:
    stock = pd.Series(stock_returns, dtype=float)
    market = pd.Series(market_returns, dtype=float)
    if not stock.index.equals(market.index):
        stock = stock.reset_index(drop=True)
        market = market.reset_index(drop=True)
    joined = pd.concat({"stock": stock, "market": market}, axis=1, join="inner").dropna()
    return joined


def rf_period_from_annual(rf_annual: float, period: str = "D") -> float:
    factor = annualization_factor(period)
    base = 1.0 + rf_annual
    if base <= 0:
        raise ValueError("Risk-free annual harus lebih besar dari -100%.")
    return base ** (1.0 / factor) - 1.0


def beta(stock_returns: Sequence[float] | pd.Series, market_returns: Sequence[float] | pd.Series) -> float | None:
    joined = _prepare_pair(stock_returns, market_returns)
    if len(joined) < 2:
        return None
    variance = float(joined["market"].var(ddof=1))
    if variance == 0.0 or np.isnan(variance):
        return None
    covariance = float(joined["stock"].cov(joined["market"]))
    return covariance / variance


def capm(rf_period: float, beta_value: float | None, er_market: float) -> float | None:
    if beta_value is None:
        return None
    return rf_period + beta_value * (er_market - rf_period)


def jensen_alpha(actual_mean: float, capm_return: float | None) -> float | None:
    if capm_return is None:
        return None
    return actual_mean - capm_return


def coefficient_variation(mean: float, sd: float, allow_negative: bool = False) -> float | None:
    if mean > 0:
        return sd / mean
    if allow_negative and mean != 0:
        return sd / mean
    return None


def beta_category(beta_value: float | None) -> str:
    if beta_value is None:
        return "Tidak tersedia"
    if beta_value < 0:
        return "Invers"
    if beta_value < 0.5:
        return "Defensif"
    if beta_value < 1.0:
        return "Sedikit Terpengaruh"
    if beta_value < 1.2:
        return "Terpengaruh"
    return "Sangat Berpengaruh"


def _annualize_guarded(value: float | None, period: str) -> float | None:
    if value is None:
        return None
    try:
        return annualize_return(value, period)
    except ValueError:
        return None


def analyze_asset(
    stock_returns: Sequence[float] | pd.Series,
    market_returns: Sequence[float] | pd.Series,
    *,
    instrument: str = "",
    rf_annual: float = 0.06,
    period: str = "D",
    legacy: bool = False,
    er_market_override: float | None = None,
    notes: list[str] | None = None,
) -> AssetMetrics:
    normalized = normalize_period(period)
    joined = _prepare_pair(stock_returns, market_returns)
    n = int(len(joined))
    if n < 2:
        raise InsufficientDataError("Butuh minimal dua observasi return yang sejajar.")
    mean_return = float(joined["stock"].mean())
    sd = float(joined["stock"].std(ddof=1))
    er_market = float(er_market_override) if er_market_override is not None else float(joined["market"].mean())
    beta_value = beta(joined["stock"], joined["market"])
    rf_period = float(rf_annual) if legacy else rf_period_from_annual(rf_annual, normalized)
    capm_return = capm(rf_period, beta_value, er_market)
    alpha_value = jensen_alpha(mean_return, capm_return)
    cv = coefficient_variation(mean_return, sd, allow_negative=legacy)
    messages = list(notes or [])
    if legacy:
        messages.append("Mode legacy: Rf tahunan dipakai langsung tanpa konversi periode (seperti Excel).")
    else:
        messages.append("Rf tahunan dikonversi ke periode analisis.")
    if mean_return <= 0:
        if legacy:
            messages.append("CV negatif dihitung karena mode legacy; tidak bisa dibandingkan sebagai efisiensi.")
        else:
            messages.append("CV tidak valid karena rata-rata return <= 0.")
    if beta_value is None:
        messages.append("Beta tidak tersedia karena variansi pasar nol.")
    mean_annual = _annualize_guarded(mean_return, normalized)
    if mean_annual is None:
        mean_annual = mean_return * annualization_factor(normalized)
    return AssetMetrics(
        instrument=instrument,
        period=normalized,
        n=n,
        mean_return=mean_return,
        sd=sd,
        cv=cv,
        cv_valid=mean_return > 0,
        beta=beta_value,
        beta_category=beta_category(beta_value),
        rf_annual=float(rf_annual),
        rf_period=rf_period,
        er_market=er_market,
        erp=er_market - rf_period,
        capm=capm_return,
        alpha=alpha_value,
        mean_annual=mean_annual,
        sd_annual=annualize_volatility(sd, normalized),
        capm_annual=_annualize_guarded(capm_return, normalized),
        alpha_annual=_annualize_guarded(alpha_value, normalized),
        legacy=legacy,
        notes=messages,
    )


def analyze_universe(
    returns: pd.DataFrame,
    market_column: str,
    *,
    rf_annual: float = 0.06,
    period: str = "D",
    legacy: bool = False,
    er_market_override: float | None = None,
) -> dict[str, AssetMetrics]:
    if market_column not in returns.columns:
        raise KeyError(f"Kolom pasar {market_column!r} tidak ada.")
    market = returns[market_column]
    result: dict[str, AssetMetrics] = {}
    for column in returns.columns:
        if column == market_column:
            continue
        stock = returns[column]
        pair = pd.concat({"stock": stock, "market": market}, axis=1, join="inner").dropna()
        if len(pair) < 2:
            continue
        result[column] = analyze_asset(
            pair["stock"],
            pair["market"],
            instrument=column,
            rf_annual=rf_annual,
            period=period,
            legacy=legacy,
            er_market_override=er_market_override,
        )
    return result


def correlation_matrix(returns: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    return returns.corr(method=method)


def portfolio_stats(
    weights: Mapping[str, float] | Sequence[float],
    covariance: pd.DataFrame | np.ndarray,
) -> dict[str, float]:
    if isinstance(covariance, pd.DataFrame):
        if isinstance(weights, Mapping):
            labels = list(weights)
            vector = np.array([weights[label] for label in labels], dtype=float)
            matrix = covariance.loc[labels, labels].to_numpy(dtype=float)
        else:
            vector = np.array(weights, dtype=float)
            matrix = covariance.to_numpy(dtype=float)
    else:
        vector = np.array(list(weights.values()) if isinstance(weights, Mapping) else weights, dtype=float)
        matrix = np.asarray(covariance, dtype=float)
    if vector.shape[0] != matrix.shape[0]:
        raise ValueError("Jumlah bobot tidak sama dengan ukuran matriks kovariansi.")
    variance = float(vector.T @ matrix @ vector)
    return {"variance": variance, "sd": float(np.sqrt(max(variance, 0.0))), "weights": vector}


def classify_quadrant(fundamental_above: bool, alpha_value: float | None) -> dict[str, str]:
    if alpha_value is None:
        return {
            "quadrant": "Tidak tersedia",
            "business": "Data alpha tidak cukup",
            "market": "Tidak dapat dinilai",
            "action": "Kumpulkan data",
        }
    if fundamental_above and alpha_value > 0:
        return {
            "quadrant": "Kuadran 1: Sweet Spot",
            "business": "Outperforming",
            "market": "Menghasilkan alpha",
            "action": "BUY / CORE ASSET",
        }
    if fundamental_above and alpha_value <= 0:
        return {
            "quadrant": "Kuadran 2: Value Trap",
            "business": "Sehat",
            "market": "Underperforming",
            "action": "WATCHLIST / HOLD",
        }
    if not fundamental_above and alpha_value > 0:
        return {
            "quadrant": "Kuadran 3: Spekulatif",
            "business": "Lemah",
            "market": "Momentum/sentimen",
            "action": "TRADING SINGKAT / AVOID",
        }
    return {
        "quadrant": "Kuadran 4: Avoid",
        "business": "Lemah",
        "market": "Merusak nilai",
        "action": "AVOID / CUT LOSS",
    }
