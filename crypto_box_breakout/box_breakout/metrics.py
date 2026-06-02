"""백테스트 성과지표 계산."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(result, initial_equity: float) -> dict:
    """거래 리스트 + 자본곡선으로 핵심 성과지표를 dict로 반환."""
    trades = result.trades
    eq = result.equity_curve

    if not trades:
        return {
            "num_trades": 0,
            "note": "거래 없음 — 파라미터(box_max_width_pct, vol_mult 등)를 완화해 보세요.",
        }

    pnls = np.array([t.net_pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    gross_win = wins.sum()
    gross_loss = -losses.sum()
    final = result.final_equity

    # 최대낙폭(MDD) — 자본곡선 기준
    curve = eq["equity"].to_numpy()
    running_max = np.maximum.accumulate(curve)
    drawdown = (curve - running_max) / running_max
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0

    # 거래단위 샤프 근사
    sharpe = float(pnls.mean() / pnls.std()) if pnls.std() > 0 else 0.0

    avg_bars = float(np.mean([t.bars_held for t in trades]))
    long_n = sum(1 for t in trades if t.side == "long")
    short_n = sum(1 for t in trades if t.side == "short")

    total_fees = sum(t.fees for t in trades)
    total_funding = sum(t.funding for t in trades)

    return {
        "num_trades": len(trades),
        "long_trades": long_n,
        "short_trades": short_n,
        "win_rate": round(len(wins) / len(trades), 4),
        "total_return_pct": round((final / initial_equity - 1) * 100, 2),
        "final_equity": round(final, 2),
        "avg_win": round(float(wins.mean()) if len(wins) else 0.0, 2),
        "avg_loss": round(float(losses.mean()) if len(losses) else 0.0, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else float("inf"),
        "payoff_ratio": (
            round((wins.mean() / -losses.mean()), 2) if len(wins) and len(losses) else None
        ),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trade_sharpe": round(sharpe, 2),
        "avg_bars_held": round(avg_bars, 1),
        "total_fees": round(total_fees, 2),
        "total_funding": round(total_funding, 2),
    }


def trades_to_dataframe(result) -> pd.DataFrame:
    """거래 내역을 DataFrame으로 변환 (CSV 저장/분석용)."""
    rows = []
    for t in result.trades:
        rows.append(
            {
                "side": t.side,
                "entry_time": t.entry_time,
                "entry_price": round(t.entry_price, 2),
                "exit_time": t.exit_time,
                "exit_price": round(t.exit_price, 2),
                "bars_held": t.bars_held,
                "notional": round(t.notional, 2),
                "gross_pnl": round(t.gross_pnl, 2),
                "fees": round(t.fees, 2),
                "funding": round(t.funding, 2),
                "net_pnl": round(t.net_pnl, 2),
                "exit_reason": t.exit_reason,
                "equity_after": round(t.equity_after, 2),
            }
        )
    return pd.DataFrame(rows)
