"""
Performance metrics for a list of trades.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

# Korean round-trip cost: 0.18% (sell tax) + 0.015% × 2 (commission) ≈ 0.21~0.23%
ROUND_TRIP_COST = 0.0023


@dataclass
class TradeStats:
    n_trades: int
    win_rate: float
    avg_return: float          # per trade (net of cost) — the headline edge metric
    median_return: float
    win_avg: float
    loss_avg: float
    profit_factor: float
    max_drawdown: float         # only meaningful for sequential single-line runs
    total_return: float          # compounded; only meaningful for sequential runs
    sharpe: float               # simple per-trade sharpe (not annualized)
    avg_holding_days: float

    def as_dict(self, include_compound: bool = True) -> dict:
        d = {
            "trades": self.n_trades,
            "win_rate(%)": round(self.win_rate * 100, 2),
            "expect/trade(%)": round(self.avg_return * 100, 3),
            "win_avg(%)": round(self.win_avg * 100, 3),
            "loss_avg(%)": round(self.loss_avg * 100, 3),
            "PF": round(self.profit_factor, 2),
            "Sharpe": round(self.sharpe, 2),
            "hold_days": round(self.avg_holding_days, 1),
        }
        if include_compound:
            d["total_ret(%)"] = round(self.total_return * 100, 2)
            d["MDD(%)"] = round(self.max_drawdown * 100, 2)
            d["median_ret(%)"] = round(self.median_return * 100, 3)
        return d


def compute_stats(trades: list[dict], cost: float = ROUND_TRIP_COST,
                  extreme_threshold: float = 0.5) -> TradeStats:
    empty = TradeStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    if not trades:
        return empty
    df = pd.DataFrame(trades)
    # Defensive: drop trades with bad entry_price or extreme returns
    # (likely corporate actions: split / reverse split / halts).
    df = df[df["entry_price"] > 0].copy()
    gross = (df["exit_price"] - df["entry_price"]) / df["entry_price"]
    df = df[gross.abs() <= extreme_threshold].copy()
    if df.empty:
        return empty
    gross = (df["exit_price"] - df["entry_price"]) / df["entry_price"]
    net = gross - cost
    df["net_ret"] = net
    df["holding"] = (pd.to_datetime(df["exit_date"]) - pd.to_datetime(df["entry_date"])).dt.days

    wins = net[net > 0]
    losses = net[net <= 0]

    # Equity (compounded) — only meaningful when trades are sequential
    equity = (1 + net).cumprod()
    peak = equity.cummax()
    mdd = float((equity / peak - 1).min())
    total_ret = float(equity.iloc[-1] - 1)

    profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) > 0 and losses.sum() < 0 else float("inf")
    sharpe = net.mean() / net.std(ddof=0) if net.std(ddof=0) > 0 else 0.0

    return TradeStats(
        n_trades=len(net),
        win_rate=(net > 0).mean(),
        avg_return=net.mean(),
        median_return=net.median(),
        win_avg=wins.mean() if len(wins) > 0 else 0.0,
        loss_avg=losses.mean() if len(losses) > 0 else 0.0,
        profit_factor=profit_factor,
        max_drawdown=mdd,
        total_return=total_ret,
        sharpe=sharpe,
        avg_holding_days=df["holding"].mean(),
    )


def equity_curve(trades: list[dict], cost: float = ROUND_TRIP_COST,
                 extreme_threshold: float = 0.5, mode: str = "cumsum") -> pd.Series:
    """
    mode:
      - "cumprod": compounded equity, appropriate for single sequential position
      - "cumsum":  additive cumulation of per-trade returns. Appropriate for
                   cross-sectional (many parallel trades) — interprets as
                   "edge accumulated" rather than compound capital.
    """
    if not trades:
        return pd.Series(dtype=float)
    df = pd.DataFrame(trades).sort_values("exit_date").reset_index(drop=True)
    df = df[df["entry_price"] > 0]
    gross = (df["exit_price"] - df["entry_price"]) / df["entry_price"]
    df = df[gross.abs() <= extreme_threshold]
    if df.empty:
        return pd.Series(dtype=float)
    net = (df["exit_price"] - df["entry_price"]) / df["entry_price"] - cost
    if mode == "cumprod":
        eq = (1 + net).cumprod()
    else:
        eq = net.cumsum() + 1.0  # start at 1.0 for consistent plotting
    eq.index = pd.to_datetime(df["exit_date"])
    return eq
