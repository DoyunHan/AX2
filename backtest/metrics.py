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
    avg_return: float          # per trade (net of cost)
    total_return: float         # compounded equity if 100% each trade
    median_return: float
    win_avg: float
    loss_avg: float
    profit_factor: float
    max_drawdown: float
    sharpe: float               # simple per-trade sharpe (not annualized)
    avg_holding_days: float

    def as_dict(self) -> dict:
        return {
            "trades": self.n_trades,
            "win_rate(%)": round(self.win_rate * 100, 2),
            "avg_ret(%)": round(self.avg_return * 100, 3),
            "median_ret(%)": round(self.median_return * 100, 3),
            "total_ret(%)": round(self.total_return * 100, 2),
            "win_avg(%)": round(self.win_avg * 100, 3),
            "loss_avg(%)": round(self.loss_avg * 100, 3),
            "PF": round(self.profit_factor, 2),
            "MDD(%)": round(self.max_drawdown * 100, 2),
            "Sharpe": round(self.sharpe, 2),
            "hold_days": round(self.avg_holding_days, 1),
        }


def compute_stats(trades: list[dict], cost: float = ROUND_TRIP_COST) -> TradeStats:
    if not trades:
        return TradeStats(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    df = pd.DataFrame(trades)
    gross = (df["exit_price"] - df["entry_price"]) / df["entry_price"]
    net = gross - cost
    df["net_ret"] = net
    df["holding"] = (pd.to_datetime(df["exit_date"]) - pd.to_datetime(df["entry_date"])).dt.days

    wins = net[net > 0]
    losses = net[net <= 0]

    # Equity curve (compounding, assuming 100% per trade — same notional each entry)
    equity = (1 + net).cumprod()
    peak = equity.cummax()
    dd = (equity / peak - 1).min()

    profit_factor = (wins.sum() / abs(losses.sum())) if len(losses) > 0 and losses.sum() < 0 else float("inf")
    sharpe = net.mean() / net.std(ddof=0) if net.std(ddof=0) > 0 else 0.0

    return TradeStats(
        n_trades=len(net),
        win_rate=(net > 0).mean(),
        avg_return=net.mean(),
        total_return=equity.iloc[-1] - 1,
        median_return=net.median(),
        win_avg=wins.mean() if len(wins) > 0 else 0.0,
        loss_avg=losses.mean() if len(losses) > 0 else 0.0,
        profit_factor=profit_factor,
        max_drawdown=dd,
        sharpe=sharpe,
        avg_holding_days=df["holding"].mean(),
    )


def equity_curve(trades: list[dict], cost: float = ROUND_TRIP_COST) -> pd.Series:
    if not trades:
        return pd.Series(dtype=float)
    df = pd.DataFrame(trades).sort_values("exit_date").reset_index(drop=True)
    net = (df["exit_price"] - df["entry_price"]) / df["entry_price"] - cost
    eq = (1 + net).cumprod()
    eq.index = pd.to_datetime(df["exit_date"])
    return eq
