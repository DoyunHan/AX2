"""
결합 전략 백테스트 — 진짜 분산 (마하세븐 돌파 + B.N.F ETF 역추세).

설계 결정:
  - 같은 60일 기간으로 B.N.F·마하세븐 백테스트
  - 두 전략 모두 자본의 10%/거래 포지션 사이징 가정
    → 일별 P&L = Σ(거래수익률 × 0.10)
    → 실제 포트폴리오에 가까운 변동성 시뮬레이션
  - B.N.F 임계는 60일 윈도우에서 시그널이 나오도록 -2% 이격도, MA15로 완화
    (장기 -7%/MA25는 별도 sanity check 로만 보고)
  - KOSPI 지수를 KODEX 200 NAV 프록시로 사용
"""

from __future__ import annotations

import sys
from pathlib import Path

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
from data_loader import load_index, build_stock_panel
from strategies import (
    bnf_mean_reversion, machaseven_predator, apply_daily_loss_limit,
)
from universe import amount_rank_universe
from metrics import compute_stats, ROUND_TRIP_COST

RESULTS = Path(__file__).parent / "results"
POSITION_SIZE = 0.10  # 거래당 자본의 10% 투입 (max 10개 동시 가능 가정)


def trades_to_daily_pnl(trades: list[dict],
                        date_range: pd.DatetimeIndex,
                        size: float = POSITION_SIZE) -> pd.Series:
    """
    거래 리스트를 날짜별 P&L 시리즈(자본 대비 %)로 변환.
    각 거래는 자본의 `size` 비율 만큼 투입했다고 가정.
    """
    if not trades:
        return pd.Series(0.0, index=date_range)
    df = pd.DataFrame(trades)
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    df["pnl"] = ((df["exit_price"] - df["entry_price"]) / df["entry_price"]
                 - ROUND_TRIP_COST) * size
    daily = df.groupby("exit_date")["pnl"].sum()
    return daily.reindex(date_range).fillna(0.0)


def main():
    print("=== Loading data ===")
    panels = build_stock_panel("krx", verbose=False)
    amount_uni = amount_rank_universe(panels, top_n=50)
    kospi = load_index("ks11", "2026-03-08", "2026-05-27")
    kospi_long = load_index("ks11", "2020-01-01", "2026-05-27")
    print(f"KOSPI 60일: {len(kospi)}, KOSPI 장기: {len(kospi_long)}, "
          f"개별주: {len(panels)}")

    # ─── 마하세븐 돌파 (개별주, walk-forward 통과 파라미터) ───
    print("\n=== 마하세븐 돌파 ===")
    m7_raw = []
    for code, df in panels.items():
        eligible = amount_uni.get(code, set())
        if not eligible:
            continue
        trades = machaseven_predator(
            df, eligible_dates=eligible,
            mode="breakout",
            amount_surge_ratio=1.5, require_alignment=True,
            long_ma_period=20, breakout_period=20,
            hard_stop_5ma=True, trailing_stop_pct=0.02, max_holding=3,
        )
        for t in trades:
            t["code"] = code
        m7_raw.extend(trades)
    m7_trades = apply_daily_loss_limit(m7_raw, daily_limit=-0.05)
    m7_stats = compute_stats(m7_trades).as_dict(include_compound=False)
    print(f"  trades={m7_stats['trades']}, win={m7_stats['win_rate(%)']}%, "
          f"expect={m7_stats['expect/trade(%)']}%, PF={m7_stats['PF']}")

    # ─── B.N.F (KOSPI 지수, 같은 60일에 시그널 나오게 임계 완화) ───
    print("\n=== B.N.F (KOSPI 지수, 60일 완화 임계) ===")
    bnf_short = bnf_mean_reversion(
        kospi.rename(columns={}),
        ma_period=15, disparity_threshold=-2.0, exit_disparity=0.5,
        max_holding=7, cooldown=2,
    )
    bnf_short_stats = compute_stats(bnf_short).as_dict()
    print(f"  trades={bnf_short_stats['trades']}, "
          f"expect={bnf_short_stats['expect/trade(%)']}%, "
          f"PF={bnf_short_stats['PF']}")

    print("\n=== B.N.F (KOSPI 장기 2020~2026, 원 파라미터) ===")
    bnf_long = bnf_mean_reversion(
        kospi_long, ma_period=25, disparity_threshold=-7.0,
        exit_disparity=0.0, max_holding=10, cooldown=2,
    )
    bnf_long_stats = compute_stats(bnf_long).as_dict()
    print(f"  trades={bnf_long_stats['trades']}, "
          f"expect={bnf_long_stats['expect/trade(%)']}%, "
          f"PF={bnf_long_stats['PF']}")

    # ─── 일별 P&L 시리즈로 변환 (포지션 사이징 10%/거래 적용) ───
    print(f"\n=== 일별 P&L 시뮬레이션 (자본의 {POSITION_SIZE*100:.0f}%/거래) ===")
    date_range = pd.bdate_range("2026-03-08", "2026-05-27")
    pnl_m7 = trades_to_daily_pnl(m7_trades, date_range)
    pnl_bnf = trades_to_daily_pnl(bnf_short, date_range)
    pnl_combined = 0.5 * pnl_m7 + 0.5 * pnl_bnf  # 자본 50:50 배분

    # 결합은 두 전략에 각 50% 자본 → 일별 P&L 합산이 아니라 가중평균
    # 즉 결합 자본 곡선 = (1 + 0.5*pnl_m7 + 0.5*pnl_bnf).cumprod()
    eq_m7 = (1 + pnl_m7).cumprod()
    eq_bnf = (1 + pnl_bnf).cumprod()
    eq_combined = (1 + pnl_combined).cumprod()

    # 상관성
    corr = pnl_m7.corr(pnl_bnf)
    if pd.isna(corr):
        corr = 0.0

    def mdd(eq):
        return float(((eq / eq.cummax()) - 1).min())

    def sharpe(s):
        return float(s.mean() / s.std() * np.sqrt(252)) if s.std() > 0 else 0.0

    rows = [
        ("마하세븐 단독", pnl_m7, eq_m7),
        ("B.N.F 단독", pnl_bnf, eq_bnf),
        ("50:50 결합", pnl_combined, eq_combined),
    ]
    summary = pd.DataFrame([
        {
            "전략": name,
            "총수익(%)": round((eq.iloc[-1] - 1) * 100, 2),
            "Max DD(%)": round(mdd(eq) * 100, 2),
            "일변동성(%)": round(pnl.std() * 100, 3),
            "Sharpe(연환산)": round(sharpe(pnl), 2),
        }
        for name, pnl, eq in rows
    ])
    print(summary.to_string(index=False))
    print(f"\n일별 P&L 상관: {corr:+.3f}")

    # ─── Plot ───
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    ax = axes[0]
    ax.plot(eq_m7.index, eq_m7.values, label=f"마하세븐 단독 (n={len(m7_trades)})", lw=1.5, color="#fd7f6f")
    ax.plot(eq_bnf.index, eq_bnf.values, label=f"B.N.F KOSPI 단독 (n={len(bnf_short)})", lw=1.5, color="#7eb0d5")
    ax.plot(eq_combined.index, eq_combined.values, label="50:50 결합", lw=2.2, color="black")
    ax.axhline(1.0, color="gray", lw=0.5, linestyle="--")
    ax.set_title(f"결합 전략 자본 곡선 (포지션 사이즈 {POSITION_SIZE*100:.0f}%/거래, 자본 50:50)")
    ax.set_ylabel("Equity (start=1.0)")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    # P&L 분포 비교
    ax.hist(pnl_m7[pnl_m7 != 0].values * 100, bins=30, alpha=0.5,
            label=f"마하세븐 (σ={pnl_m7.std()*100:.2f}%)", color="#fd7f6f")
    ax.hist(pnl_bnf[pnl_bnf != 0].values * 100, bins=30, alpha=0.5,
            label=f"B.N.F (σ={pnl_bnf.std()*100:.2f}%)", color="#7eb0d5")
    ax.hist(pnl_combined[pnl_combined != 0].values * 100, bins=30, alpha=0.6,
            label=f"결합 (σ={pnl_combined.std()*100:.2f}%)", color="black", histtype="step", lw=1.5)
    ax.axvline(0, color="gray", lw=0.5)
    ax.set_title(f"일별 P&L 분포 (상관 {corr:+.3f})")
    ax.set_xlabel("일별 P&L (%)")
    ax.set_ylabel("일수")
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS / "12_combined_equity.png", dpi=110)
    plt.close()

    # ─── Summary file ───
    summary.to_csv(RESULTS / "combined_summary.csv", index=False)
    md = ["# 마하세븐 + B.N.F 결합 전략 백테스트\n",
          f"기간 2026-03-08 ~ 2026-05-27 · 포지션 {POSITION_SIZE*100:.0f}%/거래 · 자본 50:50\n",
          f"수수료 왕복 {ROUND_TRIP_COST*100:.2f}% 차감\n\n",
          "## 시나리오별 성과\n",
          summary.to_markdown(index=False),
          f"\n\n## 일별 P&L 상관: **{corr:+.3f}**\n",
          f"\n참고: B.N.F 장기 검증 (2020~2026, 25일 이격도 -7%): "
          f"trades={bnf_long_stats['trades']}, "
          f"expect={bnf_long_stats['expect/trade(%)']}%, "
          f"PF={bnf_long_stats['PF']}\n"]
    (RESULTS / "combined_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nSaved {RESULTS / '12_combined_equity.png'} & combined_summary.md")


if __name__ == "__main__":
    main()
