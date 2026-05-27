"""
Run all four strategies and print a comparison report.

- B.N.F & 장영한: run on KOSPI/KOSDAQ INDEX data (long history 1995~2026)
- 남석관 & 마하세븐: run on TOP-N individual stocks (2026-03-08 ~ 2026-05-27)

Index-based runs are more statistically meaningful; individual stock runs
are limited by the 60 trading-day window we currently have cached.
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Use a font that has CJK glyphs (WenQuanYi Zen Hei is installed in this env)
for cand in ["WenQuanYi Zen Hei", "Noto Sans CJK KR", "NanumGothic", "Unifont"]:
    try:
        from matplotlib import font_manager
        if any(cand in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = cand
            break
    except Exception:
        pass
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, str(Path(__file__).parent))

from data_loader import load_index, build_stock_panel, top_by_marketcap
from strategies import (
    bnf_mean_reversion,
    namseokgwan_vol_breakout,
    jangyounghan_trend,
    machaseven_volatility,
)
from metrics import compute_stats, equity_curve, ROUND_TRIP_COST


RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ----------------------------------------------------------------------------
# Runners
# ----------------------------------------------------------------------------

def run_on_index(name: str, strategy_fn, index_symbol: str, start: str, end: str, **kwargs):
    df = load_index(index_symbol, start, end)
    # Normalize columns to OHLCV
    df = df.rename(columns={"Open": "Open", "High": "High", "Low": "Low",
                            "Close": "Close", "Volume": "Volume"})
    trades = strategy_fn(df, **kwargs)
    for t in trades:
        t["code"] = index_symbol
        t["name"] = index_symbol.upper()
    return trades, df


def run_on_stocks(name: str, strategy_fn, panels: dict, codes: list[str], **kwargs):
    all_trades = []
    for code in codes:
        df = panels[code]
        # Ensure required columns (already present from data_loader)
        trades = strategy_fn(df[["Open", "High", "Low", "Close", "Volume"]], **kwargs)
        name_kr = df["Name"].iloc[-1]
        for t in trades:
            t["code"] = code
            t["name"] = name_kr
        all_trades.extend(trades)
    return all_trades


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------

def plot_equity(name: str, trades: list[dict], path: Path):
    eq = equity_curve(trades)
    if eq.empty:
        return
    plt.figure(figsize=(10, 4))
    plt.plot(eq.index, eq.values, lw=1.5)
    plt.axhline(1.0, color="gray", lw=0.7, linestyle="--")
    plt.title(f"{name} — Equity Curve (per-trade compounded, cost {ROUND_TRIP_COST*100:.2f}%)")
    plt.ylabel("Equity (start=1.0)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close()


def write_summary(rows: list[dict], path: Path):
    df = pd.DataFrame(rows)
    md = "# 백테스트 결과 요약\n\n"
    md += f"수수료+거래세: 왕복 {ROUND_TRIP_COST*100:.2f}% 차감 (한국 시장 기본)\n\n"
    md += df.to_markdown(index=False)
    md += "\n\n## 컬럼 설명\n\n"
    md += "- **trades**: 발생한 매매 수\n"
    md += "- **win_rate(%)**: 수익 거래 비율\n"
    md += "- **avg_ret(%)**: 거래당 평균 순수익률 (수수료 차감 후)\n"
    md += "- **total_ret(%)**: 누적 수익률 (매 거래에 동일 비중 100% 투입 가정)\n"
    md += "- **PF (Profit Factor)**: 총 이익 / 총 손실. 1.0 이상이면 흑자, 1.5+ 양호, 2.0+ 우수\n"
    md += "- **MDD(%)**: 최대 낙폭\n"
    md += "- **Sharpe**: 거래별 수익률의 평균/표준편차 (연환산 아님, 거래 간 비교용)\n"
    md += "- **hold_days**: 평균 보유일\n"
    path.write_text(md, encoding="utf-8")
    print("\n" + md)


def print_trades_sample(name: str, trades: list[dict], n: int = 5):
    if not trades:
        print(f"  [no trades]")
        return
    df = pd.DataFrame(trades).sort_values("entry_date")
    print(f"  trades sample (first {n} of {len(df)}):")
    for _, r in df.head(n).iterrows():
        ret = (r["exit_price"] - r["entry_price"]) / r["entry_price"] * 100
        print(f"    {r['entry_date'].date()} → {r['exit_date'].date()}  "
              f"{r['name']:>20s}  {r['entry_price']:>10.2f} → {r['exit_price']:>10.2f}  "
              f"{ret:+6.2f}%  ({r['reason']})")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    # Index runs (long history)
    INDEX_START = "2020-01-01"
    INDEX_END = "2026-05-27"

    summary_rows = []

    # ---- 1. B.N.F on KOSPI index ----
    print("\n=== 1. B.N.F 이격도 역추세 (KOSPI 지수, 2020~2026) ===")
    trades_bnf_idx, _ = run_on_index(
        "B.N.F (KOSPI)", bnf_mean_reversion, "ks11",
        INDEX_START, INDEX_END,
        ma_period=25, disparity_threshold=-7.0, exit_disparity=0.0, max_holding=10,
    )
    stats = compute_stats(trades_bnf_idx).as_dict()
    stats = {"strategy": "B.N.F 이격도 역추세 (KOSPI)", **stats}
    summary_rows.append(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print_trades_sample("B.N.F KOSPI", trades_bnf_idx)
    plot_equity("B.N.F — KOSPI 이격도 역추세", trades_bnf_idx, RESULTS_DIR / "1_bnf_kospi_equity.png")

    # ---- 2. 장영한 trend following on KOSPI index ----
    print("\n=== 2. 장영한 시스템 추세추종 (KOSPI 지수, 2020~2026) ===")
    trades_jyh_idx, _ = run_on_index(
        "장영한 (KOSPI)", jangyounghan_trend, "ks11",
        INDEX_START, INDEX_END,
        fast=5, slow=20, atr_n=14, atr_stop=2.0, atr_target=4.0, max_holding=20,
    )
    stats = compute_stats(trades_jyh_idx).as_dict()
    stats = {"strategy": "장영한 추세추종 (KOSPI)", **stats}
    summary_rows.append(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print_trades_sample("장영한 KOSPI", trades_jyh_idx)
    plot_equity("장영한 — KOSPI 시스템 추세추종", trades_jyh_idx, RESULTS_DIR / "2_jyh_kospi_equity.png")

    # ---- Build individual stock panels (2026-03~05) ----
    print("\n=== Loading individual stock panels (KOSPI snapshots) ===")
    panels = build_stock_panel("krx")
    top100 = top_by_marketcap(panels, n=100)
    print(f"Using top {len(top100)} stocks by market cap")

    # ---- 3. 남석관 volume breakout on individual stocks ----
    print("\n=== 3. 남석관 거래량 폭증 + 돌파 (KOSPI 상위 100종목, 2026-03~05) ===")
    trades_nsk = run_on_stocks(
        "남석관", namseokgwan_vol_breakout, panels, top100,
        vol_ma=10, vol_mult=2.5, hi_period=10,
        stop_loss=-0.05, take_profit=0.08, max_holding=5,
    )
    stats = compute_stats(trades_nsk).as_dict()
    stats = {"strategy": "남석관 거래량 돌파 (개별주)", **stats}
    summary_rows.append(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print_trades_sample("남석관", trades_nsk)
    plot_equity("남석관 — 거래량 폭증 돌파", trades_nsk, RESULTS_DIR / "3_nsk_stocks_equity.png")

    # ---- 4. 마하세븐 volatility chase on individual stocks ----
    print("\n=== 4. 마하세븐 변동성 추격(근사) (KOSPI 상위 100종목, 2026-03~05) ===")
    trades_m7 = run_on_stocks(
        "마하세븐", machaseven_volatility, panels, top100,
        intraday_range_threshold=0.04,  # ≥4% intraday range
        min_volume=500_000,
        holding_days=1,
    )
    stats = compute_stats(trades_m7).as_dict()
    stats = {"strategy": "마하세븐 변동성 추격 (근사)", **stats}
    summary_rows.append(stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print_trades_sample("마하세븐", trades_m7)
    plot_equity("마하세븐 — 변동성 종목 추격(일봉 근사)", trades_m7, RESULTS_DIR / "4_m7_stocks_equity.png")

    # ---- Summary ----
    write_summary(summary_rows, RESULTS_DIR / "summary.md")

    # Save raw trades for inspection
    all_trades = {
        "bnf_kospi": trades_bnf_idx,
        "jyh_kospi": trades_jyh_idx,
        "nsk_stocks": trades_nsk,
        "m7_stocks": trades_m7,
    }
    for name, ts in all_trades.items():
        if ts:
            df = pd.DataFrame(ts)
            df.to_csv(RESULTS_DIR / f"trades_{name}.csv", index=False)


if __name__ == "__main__":
    main()
