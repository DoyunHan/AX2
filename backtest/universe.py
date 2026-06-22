"""
Universe filtering utilities for cross-sectional strategies.

- amount_rank_universe: per-day top-N by 거래대금 (Amount)
- marcap_tier_universe: per-day stocks above a marcap threshold
- volatility_filter_universe: per-day stocks above a trailing-volatility threshold
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def _pivot_panels(panels: dict[str, pd.DataFrame], column: str) -> pd.DataFrame:
    """Pivot per-stock OHLCV panels into wide format: rows=dates, cols=codes."""
    all_dates = sorted({d for p in panels.values() for d in p.index})
    df = pd.DataFrame(index=all_dates, columns=list(panels.keys()), dtype=float)
    for code, p in panels.items():
        df.loc[p.index, code] = p[column].values
    return df


def amount_rank_universe(panels: dict[str, pd.DataFrame],
                         top_n: int = 50) -> dict[str, set]:
    """
    Per day, rank stocks by 거래대금 (Amount) and return top-N.
    Returns: {code: set of dates the stock was in top-N}
    """
    amounts = _pivot_panels(panels, "Amount")
    eligible: dict[str, set] = {}
    for date, row in amounts.iterrows():
        top_codes = row.dropna().nlargest(top_n).index.tolist()
        for code in top_codes:
            eligible.setdefault(code, set()).add(date)
    return eligible


def marcap_top_universe(panels: dict[str, pd.DataFrame],
                        top_n: int = 200) -> dict[str, set]:
    """
    Per day, rank stocks by marcap and return top-N.
    Avoids the snooping bias of using *latest* marcap for tiering.
    """
    marcaps = _pivot_panels(panels, "Marcap")
    eligible: dict[str, set] = {}
    for date, row in marcaps.iterrows():
        top_codes = row.dropna().nlargest(top_n).index.tolist()
        for code in top_codes:
            eligible.setdefault(code, set()).add(date)
    return eligible


def volatility_top_universe(panels: dict[str, pd.DataFrame],
                            lookback: int = 20,
                            top_quantile: float = 0.333) -> dict[str, set]:
    """
    Per day, compute trailing N-day return std for each stock, return top tertile.
    """
    closes = _pivot_panels(panels, "Close")
    rets = closes.pct_change()
    vols = rets.rolling(lookback, min_periods=lookback // 2).std()
    eligible: dict[str, set] = {}
    for date, row in vols.iterrows():
        if row.dropna().empty:
            continue
        thr = row.dropna().quantile(1 - top_quantile)
        top_codes = row[row >= thr].dropna().index.tolist()
        for code in top_codes:
            eligible.setdefault(code, set()).add(date)
    return eligible


def intersect_universes(*universes: dict[str, set]) -> dict[str, set]:
    """Intersect multiple {code: set-of-dates} mappings."""
    all_codes = set()
    for u in universes:
        all_codes.update(u.keys())
    result: dict[str, set] = {}
    for code in all_codes:
        dates = None
        for u in universes:
            d = u.get(code, set())
            dates = d if dates is None else dates & d
            if not dates:
                break
        if dates:
            result[code] = dates
    return result
