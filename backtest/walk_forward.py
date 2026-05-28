"""
Walk-forward validation for 마하세븐 돌파 and 장영한 strategies.

방법:
  1. 각 파라미터 조합을 전체 데이터에서 한 번 실행 → 거래 캐시
  2. 시간을 train/test 윈도우로 분할
  3. 각 fold에서: train 윈도우의 거래로 최적 파라미터 선택
                  → 그 파라미터로 test 윈도우 성과 평가
  4. test 성과의 합산이 진짜 out-of-sample 평가

데이터: 2026-03-08 ~ 2026-05-27 (약 60거래일)
  - 시그널 시작: 약 2026-03-30 (20일 워밍업 후)
  - 사용 가능 윈도우: 약 40거래일
  - Fold 설계: train 25일 + test 10일, step 5일 → 약 4 fold
"""

from __future__ import annotations

import sys
import json
import itertools
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import pandas as pd
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
from metrics import compute_stats, ROUND_TRIP_COST

RESULTS = Path(__file__).parent / "results"
RESULTS.mkdir(exist_ok=True)


# ----------------------------------------------------------------------------
# Run-with-cache: execute each combo once on the full panel
# ----------------------------------------------------------------------------

def cache_machaseven_grid(panels, amount_uni, param_grid):
    """Returns {combo_key: (params, trades)}."""
    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    cache = {}
    print(f"  Running {len(combos)} 마하세븐 돌파 combos...")
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        all_trades = []
        for code, df in panels.items():
            eligible = amount_uni.get(code, set())
            if not eligible:
                continue
            trades = machaseven_predator(
                df, eligible_dates=eligible,
                mode="breakout",
                require_alignment=True,
                long_ma_period=20,
                breakout_period=20,
                hard_stop_5ma=True,
                **params,
            )
            for t in trades:
                t["code"] = code
                t["name"] = df["Name"].iloc[-1]
            all_trades.extend(trades)
        all_trades = apply_daily_loss_limit(all_trades, daily_limit=-0.05)
        cache[combo] = (params, all_trades)
        if (i + 1) % max(1, len(combos) // 5) == 0:
            print(f"    ...{i+1}/{len(combos)}")
    return cache


def cache_jyh_grid(panels, universe, param_grid):
    """장영한 with marcap·vol universe filter."""
    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))
    cache = {}
    print(f"  Running {len(combos)} 장영한 combos...")
    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        all_trades = []
        for code, df in panels.items():
            eligible = universe.get(code, set())
            if not eligible:
                continue
            sub = df[["Open", "High", "Low", "Close", "Volume"]]
            trades = jangyounghan_trend(sub, atr_n=14, cooldown=2, **params)
            trades = [t for t in trades if t["entry_date"] in eligible]
            for t in trades:
                t["code"] = code
            all_trades.extend(trades)
        cache[combo] = (params, all_trades)
        if (i + 1) % max(1, len(combos) // 5) == 0:
            print(f"    ...{i+1}/{len(combos)}")
    return cache


# ----------------------------------------------------------------------------
# Walk-forward folds
# ----------------------------------------------------------------------------

def make_folds(start_date: pd.Timestamp, end_date: pd.Timestamp,
               train_days: int = 25, test_days: int = 10,
               step_days: int = 5) -> list:
    """Make rolling-window folds. Returns list of (train_start, train_end, test_start, test_end)."""
    folds = []
    cur = start_date
    while True:
        train_end = cur + pd.Timedelta(days=train_days)
        test_end = train_end + pd.Timedelta(days=test_days)
        if test_end > end_date:
            break
        folds.append((cur, train_end, train_end, test_end))
        cur = cur + pd.Timedelta(days=step_days)
    return folds


def evaluate_fold(cache: dict, train_start, train_end, test_start, test_end,
                  selection_metric: str = "expect") -> dict | None:
    """For one fold, find best combo on train slice, evaluate on test slice."""
    best = None
    for combo, (params, all_trades) in cache.items():
        train_trades = [t for t in all_trades
                        if train_start <= t["entry_date"] < train_end]
        if len(train_trades) < 5:
            continue
        s = compute_stats(train_trades)
        # Selection metric
        if selection_metric == "expect":
            score = s.avg_return
        elif selection_metric == "pf":
            score = s.profit_factor if np.isfinite(s.profit_factor) else 0
        else:
            score = s.avg_return * s.n_trades  # total edge
        if best is None or score > best["score"]:
            best = {
                "score": score, "combo": combo, "params": params,
                "train_stats": s, "train_trades": train_trades,
            }
    if best is None:
        return None
    # Evaluate on test slice
    params, all_trades = cache[best["combo"]]
    test_trades = [t for t in all_trades
                   if test_start <= t["entry_date"] < test_end]
    test_stats = compute_stats(test_trades)
    return {
        "train_period": f"{train_start.date()} ~ {train_end.date()}",
        "test_period": f"{test_start.date()} ~ {test_end.date()}",
        "best_params": best["params"],
        "train_n": best["train_stats"].n_trades,
        "train_win(%)": round(best["train_stats"].win_rate * 100, 1),
        "train_expect(%)": round(best["train_stats"].avg_return * 100, 3),
        "train_PF": round(best["train_stats"].profit_factor, 2),
        "test_n": test_stats.n_trades,
        "test_win(%)": round(test_stats.win_rate * 100, 1),
        "test_expect(%)": round(test_stats.avg_return * 100, 3),
        "test_PF": round(test_stats.profit_factor, 2),
        "test_trades": [t for t in cache[best["combo"]][1]
                        if test_start <= t["entry_date"] < test_end],
    }


def aggregate_test(folds_results: list) -> dict:
    """Aggregate all test trades across folds — true out-of-sample performance."""
    all_test_trades = []
    for fr in folds_results:
        all_test_trades.extend(fr.get("test_trades", []))
    s = compute_stats(all_test_trades).as_dict(include_compound=False)
    return s


# ----------------------------------------------------------------------------
# Plotting
# ----------------------------------------------------------------------------

def plot_walkforward(folds_results: list, title: str, path: Path):
    if not folds_results:
        return
    folds = [f"F{i+1}" for i in range(len(folds_results))]
    train_expect = [fr["train_expect(%)"] for fr in folds_results]
    test_expect = [fr["test_expect(%)"] for fr in folds_results]
    x = np.arange(len(folds))
    w = 0.35
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(x - w/2, train_expect, w, label="Train (in-sample)", color="#7eb0d5")
    ax.bar(x + w/2, test_expect, w, label="Test (out-of-sample)", color="#fd7f6f")
    ax.set_xticks(x, [f"{f}\n{fr['test_period']}" for f, fr in zip(folds, folds_results)],
                  fontsize=8)
    ax.axhline(0, color="black", lw=0.5)
    ax.set_ylabel("거래당 평균 수익률 (%)")
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    print("=== Loading panels ===")
    panels = build_stock_panel("krx", verbose=False)
    print(f"Total stocks: {len(panels)}")

    print("=== Building universes ===")
    amount_uni = amount_rank_universe(panels, top_n=50)
    marcap_uni = marcap_top_universe(panels, top_n=200)
    vol_uni = volatility_top_universe(panels, lookback=20, top_quantile=0.333)
    marcap_x_vol = intersect_universes(marcap_uni, vol_uni)
    print(f"  Amount top-50 universe: {len(amount_uni)} stocks")
    print(f"  Marcap-200 ∩ Vol-1/3:   {len(marcap_x_vol)} stocks")

    # Define grids (smaller for walk-forward — speed matters)
    m7_grid = {
        "amount_surge_ratio": [1.5, 2.0, 3.0],
        "trailing_stop_pct": [0.02, 0.03, 0.05],
        "max_holding": [3, 5],
    }
    jyh_grid = {
        "fast": [3, 5, 8],
        "slow": [15, 20],
        "atr_stop": [1.5, 2.5],
        "atr_target": [3.0, 5.0],
        "max_holding": [5, 10],
    }

    print("\n=== Caching all trades per combo (one-time) ===")
    m7_cache = cache_machaseven_grid(panels, amount_uni, m7_grid)
    jyh_cache = cache_jyh_grid(panels, marcap_x_vol, jyh_grid)

    # Define folds
    start = pd.Timestamp("2026-03-30")
    end = pd.Timestamp("2026-05-27")
    folds = make_folds(start, end, train_days=25, test_days=12, step_days=10)
    print(f"\n=== Folds defined ({len(folds)}) ===")
    for i, (ts, te, vs, ve) in enumerate(folds):
        print(f"  F{i+1}: train {ts.date()} ~ {te.date()}  /  test {vs.date()} ~ {ve.date()}")

    # ---------- 마하세븐 돌파 walk-forward ----------
    print("\n" + "=" * 60)
    print("[1] 마하세븐 돌파 — Walk-forward")
    print("=" * 60)
    m7_results = []
    for i, (ts, te, vs, ve) in enumerate(folds):
        res = evaluate_fold(m7_cache, ts, te, vs, ve, selection_metric="expect")
        if res is None:
            print(f"  F{i+1}: insufficient data, skipped")
            continue
        print(f"  F{i+1}: train {res['train_n']:3d} ({res['train_expect(%)']:+.2f}% / PF {res['train_PF']:.2f})  "
              f"→  test {res['test_n']:3d} ({res['test_expect(%)']:+.2f}% / PF {res['test_PF']:.2f})  "
              f"params {res['best_params']}")
        m7_results.append(res)

    m7_test_agg = aggregate_test(m7_results)
    print(f"\n  통합 test (모든 fold 합산):")
    print(f"    {json.dumps({k: v for k, v in m7_test_agg.items() if k in ('trades','win_rate(%)','expect/trade(%)','PF','Sharpe')}, ensure_ascii=False, indent=2)}")

    pd.DataFrame([{k: v for k, v in r.items() if k != "test_trades"} for r in m7_results]).to_csv(
        RESULTS / "wf_machaseven_breakout.csv", index=False)
    plot_walkforward(m7_results, "마하세븐 돌파 — Walk-forward",
                     RESULTS / "10_wf_machaseven.png")

    # ---------- 장영한 walk-forward ----------
    print("\n" + "=" * 60)
    print("[2] 장영한 (시총·변동성 필터) — Walk-forward")
    print("=" * 60)
    jyh_results = []
    for i, (ts, te, vs, ve) in enumerate(folds):
        res = evaluate_fold(jyh_cache, ts, te, vs, ve, selection_metric="expect")
        if res is None:
            print(f"  F{i+1}: insufficient data, skipped")
            continue
        print(f"  F{i+1}: train {res['train_n']:3d} ({res['train_expect(%)']:+.2f}% / PF {res['train_PF']:.2f})  "
              f"→  test {res['test_n']:3d} ({res['test_expect(%)']:+.2f}% / PF {res['test_PF']:.2f})  "
              f"params {res['best_params']}")
        jyh_results.append(res)

    jyh_test_agg = aggregate_test(jyh_results)
    print(f"\n  통합 test (모든 fold 합산):")
    print(f"    {json.dumps({k: v for k, v in jyh_test_agg.items() if k in ('trades','win_rate(%)','expect/trade(%)','PF','Sharpe')}, ensure_ascii=False, indent=2)}")

    pd.DataFrame([{k: v for k, v in r.items() if k != "test_trades"} for r in jyh_results]).to_csv(
        RESULTS / "wf_jyh.csv", index=False)
    plot_walkforward(jyh_results, "장영한 — Walk-forward",
                     RESULTS / "11_wf_jyh.png")

    # ---------- Summary markdown ----------
    md = []
    md.append("# Walk-forward 검증 결과\n")
    md.append(f"기간: 2026-03-30 ~ 2026-05-27 · Train 25일 / Test 12일 / Step 10일 · {len(folds)} folds\n")
    md.append(f"수수료+거래세 왕복 {ROUND_TRIP_COST*100:.2f}% 차감\n\n")
    md.append("## 마하세븐 돌파\n\n")
    md.append("### 폴드별 결과\n")
    md.append(pd.DataFrame([{k: v for k, v in r.items() if k != "test_trades"} for r in m7_results]).to_markdown(index=False))
    md.append("\n\n### Test 통합 (true out-of-sample)\n")
    md.append("```\n" + json.dumps(m7_test_agg, ensure_ascii=False, indent=2) + "\n```\n\n")
    md.append("## 장영한 (시총·변동성 필터)\n\n")
    md.append("### 폴드별 결과\n")
    md.append(pd.DataFrame([{k: v for k, v in r.items() if k != "test_trades"} for r in jyh_results]).to_markdown(index=False))
    md.append("\n\n### Test 통합 (true out-of-sample)\n")
    md.append("```\n" + json.dumps(jyh_test_agg, ensure_ascii=False, indent=2) + "\n```\n")
    (RESULTS / "walkforward_summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\nSaved walkforward_summary.md")


if __name__ == "__main__":
    main()
