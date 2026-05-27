"""
B.N.F & 장영한 전략을 KRX 전체 종목(2,894개)에 적용.
시총 / 변동성 구간별로 성과를 분해해 어떤 종목군에서 잘 먹히는지 확인.

기본 종목 데이터는 2026-03-08 ~ 2026-05-27 (약 60거래일)로 짧음.
시계열은 짧지만 횡단면(종목 수)이 커서 통계적 표본 확보 가능.
"""

from __future__ import annotations

import sys
import json
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

from data_loader import build_stock_panel
from strategies import bnf_mean_reversion, jangyounghan_trend
from metrics import compute_stats, equity_curve, ROUND_TRIP_COST

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ----------------------------------------------------------------------------
# Tiering helpers
# ----------------------------------------------------------------------------

def make_marcap_tiers(panels: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Classify each stock as 대형/중형/소형 by latest market cap (tertiles)."""
    marcaps = {code: float(df["Marcap"].iloc[-1]) for code, df in panels.items()}
    s = pd.Series(marcaps)
    q33, q67 = s.quantile(0.667), s.quantile(0.333)
    tier = {}
    for code, mc in marcaps.items():
        if mc >= q33:
            tier[code] = "대형"
        elif mc >= q67:
            # We'll never enter this branch because q67 < q33 in tertile labeling
            # Actually we need q33 > q67. Let me recompute:
            tier[code] = "중형"
        else:
            tier[code] = "소형"
    # Recompute cleanly using quantile-based bucketing
    s_sorted = s.rank(pct=True)
    tier = {}
    for code, pct in s_sorted.items():
        if pct >= 2 / 3:
            tier[code] = "대형"
        elif pct >= 1 / 3:
            tier[code] = "중형"
        else:
            tier[code] = "소형"
    return tier


def entry_volatility(panel: pd.DataFrame, entry_date, lookback: int = 20) -> float:
    """20-day return std at entry."""
    try:
        idx = panel.index.get_loc(entry_date)
    except KeyError:
        return np.nan
    start = max(0, idx - lookback)
    rets = panel["Close"].iloc[start:idx].pct_change().dropna()
    if len(rets) < 5:
        return np.nan
    return float(rets.std())


def classify_vol(v: float, thresholds: tuple[float, float]) -> str:
    if pd.isna(v):
        return "?"
    low, high = thresholds
    if v >= high:
        return "고변동"
    if v >= low:
        return "중변동"
    return "저변동"


# ----------------------------------------------------------------------------
# Run strategy on all panels
# ----------------------------------------------------------------------------

def run_strategy_all(panels: dict[str, pd.DataFrame], strategy_fn, **kwargs) -> list[dict]:
    all_trades = []
    for code, df in panels.items():
        sub = df[["Open", "High", "Low", "Close", "Volume"]]
        trades = strategy_fn(sub, **kwargs)
        name = df["Name"].iloc[-1]
        marcap = float(df["Marcap"].iloc[-1])
        for t in trades:
            t["code"] = code
            t["name"] = name
            t["marcap"] = marcap
            t["entry_vol"] = entry_volatility(df, t["entry_date"], 20)
        all_trades.extend(trades)
    return all_trades


# ----------------------------------------------------------------------------
# Per-tier analysis
# ----------------------------------------------------------------------------

def tier_stats(trades: list[dict], tier_key: str) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    rows = []
    for tier_val, sub in df.groupby(tier_key):
        sub_trades = sub.to_dict("records")
        s = compute_stats(sub_trades).as_dict(include_compound=False)
        rows.append({tier_key: tier_val, **s})
    return pd.DataFrame(rows)


def tag_marcap_tier(trades: list[dict], marcap_tiers: dict[str, str]):
    for t in trades:
        t["marcap_tier"] = marcap_tiers.get(t["code"], "?")


def tag_vol_tier(trades: list[dict]):
    vols = pd.Series([t["entry_vol"] for t in trades]).dropna()
    if len(vols) < 10:
        for t in trades:
            t["vol_tier"] = "?"
        return None
    low_thr = float(vols.quantile(1 / 3))
    high_thr = float(vols.quantile(2 / 3))
    for t in trades:
        t["vol_tier"] = classify_vol(t["entry_vol"], (low_thr, high_thr))
    return (low_thr, high_thr)


def plot_per_tier_equity(trades: list[dict], tier_key: str, title: str, path: Path):
    """
    Per-tier cumulative edge (additive). Y-axis represents 1.0 + sum of
    per-trade net returns; this avoids the explosive compounding artifact
    when many parallel trades are aggregated.
    """
    if not trades:
        return
    df = pd.DataFrame(trades)
    plt.figure(figsize=(10, 5))
    for tier, sub in df.groupby(tier_key):
        eq = equity_curve(sub.to_dict("records"), mode="cumsum")
        if eq.empty:
            continue
        plt.plot(eq.index, eq.values, lw=1.5, label=f"{tier} (n={len(sub)})")
    plt.axhline(1.0, color="gray", lw=0.7, linestyle="--")
    plt.title(title + " — 누적 엣지(net 합산)")
    plt.ylabel("1.0 + Σ(per-trade net return)")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=110)
    plt.close()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    print("=== Loading stock panels (KOSPI + KOSDAQ) ===")
    panels_krx = build_stock_panel("krx", verbose=False)
    panels_kq = build_stock_panel("kosdaq", verbose=False)
    panels = {**panels_krx, **panels_kq}
    print(f"Total stocks: {len(panels)} (KOSPI {len(panels_krx)}, KOSDAQ {len(panels_kq)})")

    marcap_tiers = make_marcap_tiers(panels)
    counts = pd.Series(marcap_tiers).value_counts()
    print(f"Marcap tiers: {dict(counts)}")

    # ----- 1) B.N.F on all stocks -----
    print("\n=== B.N.F 이격도 역추세 — 전체 종목 ===")
    trades_bnf = run_strategy_all(
        panels, bnf_mean_reversion,
        ma_period=20,             # 60일 데이터에서 가능한 최대치 근처
        disparity_threshold=-7.0,
        exit_disparity=0.0,
        max_holding=5,            # 짧은 데이터 → 짧게 청산
        cooldown=2,
    )
    print(f"Total trades: {len(trades_bnf)}")
    overall = compute_stats(trades_bnf).as_dict(include_compound=False)
    print("Overall:", json.dumps(overall, ensure_ascii=False, indent=2))

    tag_marcap_tier(trades_bnf, marcap_tiers)
    vol_thr_bnf = tag_vol_tier(trades_bnf)
    print(f"Vol thresholds (1/3, 2/3): {vol_thr_bnf}")

    bnf_by_marcap = tier_stats(trades_bnf, "marcap_tier")
    bnf_by_vol = tier_stats(trades_bnf, "vol_tier")
    print("\nBy market cap tier:")
    print(bnf_by_marcap.to_string(index=False))
    print("\nBy 20-day volatility tier:")
    print(bnf_by_vol.to_string(index=False))

    plot_per_tier_equity(trades_bnf, "marcap_tier",
                         "B.N.F 이격도 역추세 — 시총별",
                         RESULTS_DIR / "5_bnf_by_marcap.png")
    plot_per_tier_equity(trades_bnf, "vol_tier",
                         "B.N.F 이격도 역추세 — 변동성별",
                         RESULTS_DIR / "6_bnf_by_vol.png")
    pd.DataFrame(trades_bnf).to_csv(RESULTS_DIR / "trades_bnf_all_stocks.csv", index=False)

    # ----- 2) 장영한 on all stocks -----
    print("\n=== 장영한 시스템 추세추종 — 전체 종목 ===")
    trades_jyh = run_strategy_all(
        panels, jangyounghan_trend,
        fast=5,
        slow=20,
        atr_n=14,
        atr_stop=2.0,
        atr_target=4.0,
        max_holding=10,           # 짧은 데이터 대응
        cooldown=2,
    )
    print(f"Total trades: {len(trades_jyh)}")
    overall = compute_stats(trades_jyh).as_dict(include_compound=False)
    print("Overall:", json.dumps(overall, ensure_ascii=False, indent=2))

    tag_marcap_tier(trades_jyh, marcap_tiers)
    vol_thr_jyh = tag_vol_tier(trades_jyh)
    print(f"Vol thresholds (1/3, 2/3): {vol_thr_jyh}")

    jyh_by_marcap = tier_stats(trades_jyh, "marcap_tier")
    jyh_by_vol = tier_stats(trades_jyh, "vol_tier")
    print("\nBy market cap tier:")
    print(jyh_by_marcap.to_string(index=False))
    print("\nBy 20-day volatility tier:")
    print(jyh_by_vol.to_string(index=False))

    plot_per_tier_equity(trades_jyh, "marcap_tier",
                         "장영한 시스템 추세추종 — 시총별",
                         RESULTS_DIR / "7_jyh_by_marcap.png")
    plot_per_tier_equity(trades_jyh, "vol_tier",
                         "장영한 시스템 추세추종 — 변동성별",
                         RESULTS_DIR / "8_jyh_by_vol.png")
    pd.DataFrame(trades_jyh).to_csv(RESULTS_DIR / "trades_jyh_all_stocks.csv", index=False)

    # ----- Summary report -----
    print("\n=== Writing summary ===")
    md = ["# 개별주 전체 백테스트 결과 (B.N.F & 장영한)\n"]
    md.append(f"대상: KRX 전체 {len(panels)}종목 (KOSPI {len(panels_krx)}, KOSDAQ {len(panels_kq)})\n")
    md.append(f"기간: 2026-03-08 ~ 2026-05-27 (약 60거래일)\n")
    md.append(f"수수료+거래세: 왕복 {ROUND_TRIP_COST*100:.2f}% 차감\n\n")

    md.append("## 시총 구간 분류 (3분위)\n")
    md.append(f"- 대형 ≥ 상위 33%, 중형 = 33~67%, 소형 ≤ 67%\n")
    md.append(f"- 분포: {dict(counts)}\n\n")

    md.append("## B.N.F 이격도 역추세\n\n")
    md.append("### 전체\n")
    md.append(pd.DataFrame([compute_stats(trades_bnf).as_dict(include_compound=False)]).to_markdown(index=False))
    md.append("\n\n### 시총별\n")
    md.append(bnf_by_marcap.to_markdown(index=False))
    md.append("\n\n### 변동성별 (20일 수익률 표준편차)\n")
    if vol_thr_bnf:
        md.append(f"_thresholds: 저변동 < {vol_thr_bnf[0]:.4f} < 중변동 < {vol_thr_bnf[1]:.4f} < 고변동_\n\n")
    md.append(bnf_by_vol.to_markdown(index=False))

    md.append("\n\n## 장영한 시스템 추세추종\n\n")
    md.append("### 전체\n")
    md.append(pd.DataFrame([compute_stats(trades_jyh).as_dict(include_compound=False)]).to_markdown(index=False))
    md.append("\n\n### 시총별\n")
    md.append(jyh_by_marcap.to_markdown(index=False))
    md.append("\n\n### 변동성별\n")
    if vol_thr_jyh:
        md.append(f"_thresholds: 저변동 < {vol_thr_jyh[0]:.4f} < 중변동 < {vol_thr_jyh[1]:.4f} < 고변동_\n\n")
    md.append(jyh_by_vol.to_markdown(index=False))

    (RESULTS_DIR / "individual_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Saved {RESULTS_DIR / 'individual_summary.md'}")


if __name__ == "__main__":
    main()
