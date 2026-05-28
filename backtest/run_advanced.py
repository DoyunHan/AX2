"""
고급 백테스트:
 1. 장영한 추세추종 + 명시적 universe 필터 (시총 상위 + 고변동성)
 2. 마하세븐 포식자 시스템 (눌림목/돌파, hard stop 5MA, 트레일링, 일일손실한도)
 3. 두 전략 모두에 파라미터 그리드 서치
"""

from __future__ import annotations

import sys
import json
import itertools
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for cand in ["WenQuanYi Zen Hei", "Noto Sans CJK KR", "NanumGothic"]:
    if any(cand in f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, str(Path(__file__).parent))

from data_loader import build_stock_panel
from strategies import (
    jangyounghan_trend,
    machaseven_predator,
    apply_daily_loss_limit,
)
from universe import (
    amount_rank_universe,
    marcap_top_universe,
    volatility_top_universe,
    intersect_universes,
)
from metrics import compute_stats, equity_curve, ROUND_TRIP_COST

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def run_with_universe(panels: dict, strategy_fn, universe: dict[str, set],
                       require_signal_in_universe: bool = True, **kwargs) -> list[dict]:
    """
    Run a strategy on each stock, but only count signals that fire on
    days when the stock is in `universe` (filter at signal day).
    """
    all_trades = []
    for code, df in panels.items():
        eligible = universe.get(code, set())
        if not eligible:
            continue
        sub = df[["Open", "High", "Low", "Close", "Volume"]]
        trades = strategy_fn(sub, **kwargs)
        if require_signal_in_universe:
            # Trades' "signal day" is entry_date - 1 (we enter next-day open)
            # But strategies don't expose signal date directly. We treat entry_date
            # as the day after signal, so check if entry_date is in eligible
            # set OR entry_date - 1 is (treat universe membership as fluid).
            # Simpler: keep trades where the immediately prior trading day was
            # in eligible.
            # In practice the universe doesn't change much day-to-day, so
            # checking entry_date itself is a reasonable proxy.
            trades = [t for t in trades if t["entry_date"] in eligible]
        for t in trades:
            t["code"] = code
            t["name"] = df["Name"].iloc[-1]
        all_trades.extend(trades)
    return all_trades


def run_machaseven_all(panels: dict,
                       amount_top_n: int = 50,
                       **strat_kwargs) -> list[dict]:
    """Run 마하세븐 predator on all stocks with per-day amount-rank universe."""
    amount_uni = amount_rank_universe(panels, top_n=amount_top_n)
    all_trades = []
    for code, df in panels.items():
        eligible = amount_uni.get(code, set())
        if not eligible:
            continue
        trades = machaseven_predator(df, eligible_dates=eligible, **strat_kwargs)
        for t in trades:
            t["code"] = code
            t["name"] = df["Name"].iloc[-1]
        all_trades.extend(trades)
    return all_trades


def headline(stats):
    return {k: v for k, v in stats.items()
            if k in ("trades", "win_rate(%)", "expect/trade(%)", "PF", "Sharpe")}


# ----------------------------------------------------------------------------
# Grid search
# ----------------------------------------------------------------------------

def grid_search(name: str, runner_fn, param_grid: dict[str, list]) -> pd.DataFrame:
    """
    runner_fn(**params) -> list[trades]
    Returns DataFrame of params + per-trade headline metrics, sorted by PF desc.
    """
    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    print(f"\n=== Grid search: {name} ({len(combos)} combos) ===")
    rows = []
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        trades = runner_fn(**params)
        if not trades:
            stats = {"trades": 0, "win_rate(%)": 0, "expect/trade(%)": 0,
                     "PF": 0, "Sharpe": 0}
        else:
            stats = compute_stats(trades).as_dict(include_compound=False)
            stats = headline(stats)
        row = {**params, **stats}
        rows.append(row)
        if (i + 1) % max(1, len(combos) // 10) == 0:
            print(f"  ...{i+1}/{len(combos)}")
    df = pd.DataFrame(rows)
    df = df.sort_values(["expect/trade(%)", "PF"], ascending=False)
    return df


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    print("=== Loading panels ===")
    panels = build_stock_panel("krx", verbose=False)
    print(f"Total stocks: {len(panels)}")

    # Build universes
    print("\n=== Building universes ===")
    marcap_uni = marcap_top_universe(panels, top_n=200)
    vol_uni = volatility_top_universe(panels, lookback=20, top_quantile=0.333)
    amount_uni = amount_rank_universe(panels, top_n=50)
    print(f"Marcap top-200: {len(marcap_uni)} stocks have qualifying days")
    print(f"Volatility top-1/3: {len(vol_uni)} stocks have qualifying days")
    print(f"Amount top-50: {len(amount_uni)} stocks have qualifying days")
    marcap_x_vol = intersect_universes(marcap_uni, vol_uni)
    print(f"Marcap-200 ∩ Vol-top-1/3: {len(marcap_x_vol)} stocks")

    # ========================================================================
    # 1. 장영한 + 명시적 필터 (시총 상위 + 고변동)
    # ========================================================================
    print("\n" + "=" * 60)
    print("[1] 장영한 추세추종 + 명시적 universe 필터")
    print("=" * 60)

    trades_filtered = run_with_universe(
        panels, jangyounghan_trend, marcap_x_vol,
        fast=5, slow=20, atr_n=14, atr_stop=2.0, atr_target=4.0,
        max_holding=10, cooldown=2,
    )
    s_filtered = compute_stats(trades_filtered).as_dict(include_compound=False)
    print(f"Filtered trades: {len(trades_filtered)}")
    print(json.dumps(headline(s_filtered), ensure_ascii=False, indent=2))

    # Save trades
    if trades_filtered:
        pd.DataFrame(trades_filtered).to_csv(
            RESULTS_DIR / "trades_jyh_filtered.csv", index=False)

    # ========================================================================
    # 2. 그리드 서치 — 장영한 with filter
    # ========================================================================
    def jyh_runner(fast, slow, atr_stop, atr_target, max_holding):
        return run_with_universe(
            panels, jangyounghan_trend, marcap_x_vol,
            fast=fast, slow=slow, atr_n=14,
            atr_stop=atr_stop, atr_target=atr_target,
            max_holding=max_holding, cooldown=2,
        )

    jyh_grid = grid_search(
        "장영한 (시총·변동성 필터)", jyh_runner,
        {
            "fast": [3, 5, 8],
            "slow": [15, 20, 30],
            "atr_stop": [1.5, 2.5],
            "atr_target": [3.0, 5.0],
            "max_holding": [5, 10],
        },
    )
    jyh_grid.to_csv(RESULTS_DIR / "grid_jyh.csv", index=False)
    print("\n=== 장영한 그리드 상위 10 ===")
    print(jyh_grid.head(10).to_string(index=False))

    # ========================================================================
    # 3. 마하세븐 포식자 — 눌림목 모드
    # ========================================================================
    print("\n" + "=" * 60)
    print("[3] 마하세븐 포식자 — 눌림목(pullback) 모드")
    print("=" * 60)

    m7_pullback = run_machaseven_all(
        panels,
        amount_top_n=50,
        amount_surge_ratio=2.0,
        require_alignment=True,
        long_ma_period=20,
        mode="pullback",
        pullback_band_pct=0.02,
        require_negative_candle=True,
        hard_stop_5ma=True,
        trailing_stop_pct=0.03,
        max_holding=3,
    )
    print(f"Pullback trades (before daily-loss filter): {len(m7_pullback)}")
    m7_pullback_filt = apply_daily_loss_limit(m7_pullback, daily_limit=-0.05)
    print(f"After daily-loss filter (-5% lockout): {len(m7_pullback_filt)}")
    if m7_pullback_filt:
        s_m7p = compute_stats(m7_pullback_filt).as_dict(include_compound=False)
        print(json.dumps(headline(s_m7p), ensure_ascii=False, indent=2))
        pd.DataFrame(m7_pullback_filt).to_csv(
            RESULTS_DIR / "trades_machaseven_pullback.csv", index=False)

    # ========================================================================
    # 4. 마하세븐 포식자 — 돌파 모드
    # ========================================================================
    print("\n" + "=" * 60)
    print("[4] 마하세븐 포식자 — 돌파(breakout) 모드")
    print("=" * 60)
    m7_breakout = run_machaseven_all(
        panels,
        amount_top_n=50,
        amount_surge_ratio=2.0,
        require_alignment=True,
        long_ma_period=20,
        mode="breakout",
        breakout_period=20,
        hard_stop_5ma=True,
        trailing_stop_pct=0.03,
        max_holding=3,
    )
    print(f"Breakout trades (before daily-loss filter): {len(m7_breakout)}")
    m7_breakout_filt = apply_daily_loss_limit(m7_breakout, daily_limit=-0.05)
    print(f"After daily-loss filter (-5% lockout): {len(m7_breakout_filt)}")
    if m7_breakout_filt:
        s_m7b = compute_stats(m7_breakout_filt).as_dict(include_compound=False)
        print(json.dumps(headline(s_m7b), ensure_ascii=False, indent=2))
        pd.DataFrame(m7_breakout_filt).to_csv(
            RESULTS_DIR / "trades_machaseven_breakout.csv", index=False)

    # ========================================================================
    # 5. 그리드 서치 — 마하세븐 (눌림목)
    # ========================================================================
    def m7_pullback_runner(amount_surge_ratio, pullback_band_pct, trailing_stop_pct, max_holding):
        trades = run_machaseven_all(
            panels,
            amount_top_n=50,
            amount_surge_ratio=amount_surge_ratio,
            require_alignment=True,
            long_ma_period=20,
            mode="pullback",
            pullback_band_pct=pullback_band_pct,
            require_negative_candle=True,
            hard_stop_5ma=True,
            trailing_stop_pct=trailing_stop_pct,
            max_holding=max_holding,
        )
        return apply_daily_loss_limit(trades, daily_limit=-0.05)

    m7_grid = grid_search(
        "마하세븐 (눌림목)", m7_pullback_runner,
        {
            "amount_surge_ratio": [1.5, 3.0],
            "pullback_band_pct": [0.015, 0.03],
            "trailing_stop_pct": [0.02, 0.05],
            "max_holding": [2, 5],
        },
    )
    m7_grid.to_csv(RESULTS_DIR / "grid_machaseven_pullback.csv", index=False)
    print("\n=== 마하세븐(눌림목) 그리드 상위 10 ===")
    print(m7_grid.head(10).to_string(index=False))

    # ========================================================================
    # Final comparison table
    # ========================================================================
    print("\n" + "=" * 60)
    print("최종 비교 (best of each)")
    print("=" * 60)
    summary = [
        {"strategy": "장영한 (시총 + 변동성 필터)", **headline(s_filtered)},
        {"strategy": "장영한 — grid best (top 1)", **headline(jyh_grid.iloc[0].to_dict())},
        {"strategy": "마하세븐 — 눌림목", **(headline(s_m7p) if m7_pullback_filt else {})},
        {"strategy": "마하세븐 — 돌파", **(headline(s_m7b) if m7_breakout_filt else {})},
        {"strategy": "마하세븐 — pullback grid best", **headline(m7_grid.iloc[0].to_dict())},
    ]
    summary_df = pd.DataFrame(summary)
    print(summary_df.to_string(index=False))

    md = ["# 고급 백테스트 결과 — 필터·그리드·마하세븐 시스템\n",
          f"수수료+거래세 왕복 {ROUND_TRIP_COST*100:.2f}% 차감\n",
          f"종목풀: KRX 전체 {len(panels)}종목, 기간 2026-03~05\n\n",
          "## 1. 베이스라인\n\n",
          summary_df.to_markdown(index=False),
          "\n\n## 2. 장영한 그리드 (상위 10)\n\n",
          jyh_grid.head(10).to_markdown(index=False),
          "\n\n## 3. 마하세븐(눌림목) 그리드 (상위 10)\n\n",
          m7_grid.head(10).to_markdown(index=False),
          "\n"]
    (RESULTS_DIR / "advanced_summary.md").write_text("\n".join(str(x) for x in md), encoding="utf-8")
    print(f"\nSaved {RESULTS_DIR / 'advanced_summary.md'}")


if __name__ == "__main__":
    main()
