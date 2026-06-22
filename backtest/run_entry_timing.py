"""
마하세븐 돌파 — 진입 시점 민감도 분석 (일봉 OHLC 기반).

문제: 현재 룰은 시그널 다음날 '시초가' 시장가 매수. 더 좋은 진입 시점은?

분봉 데이터가 없으므로 일봉 OHLC 만으로 가능한 'what-if' 분석:
  · 각 거래의 진입일에 다른 진입 가격이 가능했는지 시뮬레이션
  · Exit 가격은 원본 청산 가격을 그대로 사용 (sensitivity 분석)
  · Limit 주문은 그 날 Low <= 한계가 충족 시만 체결, 아니면 거래 skip

테스트 시나리오:
  1. open  (베이스라인 시초가 시장가)
  2. midday (= (Open+Close)/2, 분봉 없이 정오 근사)
  3. close  (당일 종가 시장가, 지연 진입)
  4. limit -0.5% / -1% / -2% (지정가, 미체결 시 거래 skip)
  5. low   (이론적 ceiling — 그 날 최저가 매수)

캐비어트:
  · Exit 가격 고정 → 실제로 진입가 바뀌면 trailing/stop 시점도 바뀜.
  · 그러므로 결과는 '진입 시점 개선 잠재력의 상한 추정'.
  · 진짜 정밀 분석은 분봉(OPT10080) 데이터 필요.
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
from data_loader import build_stock_panel
from strategies import machaseven_predator, apply_daily_loss_limit
from universe import amount_rank_universe
from metrics import compute_stats, ROUND_TRIP_COST

RESULTS = Path(__file__).parent / "results"


def alternative_entries(open_p: float, high_p: float, low_p: float, close_p: float) -> dict:
    """
    같은 진입일에 가능했을 대안 진입 가격들.
    None 이면 그 시나리오에서 해당 거래는 미체결 (skip).
    """
    out = {
        "open (baseline)": open_p,
        "midday (~12:30, est)": (open_p + close_p) / 2.0,
        "close": close_p,
    }
    # Limit 주문: Low ≤ 한계가 충족 시 한계가에 체결
    for pct in (0.5, 1.0, 2.0):
        limit_px = open_p * (1 - pct / 100)
        out[f"limit -{pct:.1f}% (skip if no fill)"] = limit_px if low_p <= limit_px else None
    # Theoretical ceiling: 그 날 최저가
    out["low (theoretical max)"] = low_p
    return out


def simulate_timing(trades: list[dict], panels: dict) -> dict[str, list[dict]]:
    """
    각 시나리오별 (조정된 entry_price 적용) 거래 리스트 생성.
    Exit_price 는 원본 그대로 (sensitivity 가정).
    """
    scenarios: dict[str, list[dict]] = {}
    for t in trades:
        code = t["code"]
        entry_date = pd.to_datetime(t["entry_date"])
        df = panels.get(code)
        if df is None or entry_date not in df.index:
            continue
        day = df.loc[entry_date]
        o, h, l, c = (float(day["Open"]), float(day["High"]),
                      float(day["Low"]), float(day["Close"]))
        alts = alternative_entries(o, h, l, c)
        for scenario, new_entry in alts.items():
            if new_entry is None:
                continue
            scenarios.setdefault(scenario, []).append({
                **t,
                "entry_price": new_entry,
                "scenario": scenario,
            })
    return scenarios


def main():
    print("=== Loading data ===")
    panels = build_stock_panel("krx", verbose=False)
    amount_uni = amount_rank_universe(panels, top_n=50)

    print("=== Running baseline 마하세븐 돌파 ===")
    raw = []
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
        raw.extend(trades)
    baseline = apply_daily_loss_limit(raw, daily_limit=-0.05)
    print(f"  baseline trades: {len(baseline)}")

    print("\n=== Simulating alternative entry timings ===")
    scenarios = simulate_timing(baseline, panels)

    rows = []
    for scen_name, sc_trades in scenarios.items():
        s = compute_stats(sc_trades).as_dict(include_compound=False)
        # Cancellation rate (limit orders): fraction of baseline trades skipped
        fill_rate = len(sc_trades) / len(baseline) * 100
        rows.append({
            "scenario": scen_name,
            "trades": s["trades"],
            "fill_rate(%)": round(fill_rate, 1),
            "win_rate(%)": s["win_rate(%)"],
            "expect/trade(%)": s["expect/trade(%)"],
            "win_avg(%)": s["win_avg(%)"],
            "loss_avg(%)": s["loss_avg(%)"],
            "PF": s["PF"],
            "Sharpe": s["Sharpe"],
        })
    summary = pd.DataFrame(rows)
    # 'open' 베이스라인 우선, 나머지는 expect 내림차순
    summary["_baseline"] = summary["scenario"].str.contains("baseline").astype(int)
    summary = summary.sort_values(["_baseline", "expect/trade(%)"],
                                  ascending=[False, False]).drop(columns="_baseline")
    print(summary.to_string(index=False))

    summary.to_csv(RESULTS / "entry_timing_summary.csv", index=False)

    # ── Plot: expect/trade per scenario ──
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    ax = axes[0]
    plotted = summary.copy()
    ax.barh(plotted["scenario"], plotted["expect/trade(%)"],
            color=["#7eb0d5" if "baseline" in s else
                   ("#fd7f6f" if "low (theoretical)" in s else
                    ("#bd7ebe" if "limit" in s else "#b2e061"))
                   for s in plotted["scenario"]])
    ax.axvline(0, color="black", lw=0.5)
    ax.set_xlabel("거래당 평균 순수익률 (%)")
    ax.set_title("진입 시점별 expect/trade")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    ax = axes[1]
    ax.barh(plotted["scenario"], plotted["fill_rate(%)"], color="#999")
    ax.set_xlim(0, 110)
    ax.set_xlabel("체결률 (%) — limit 외엔 모두 100%")
    ax.set_title("진입 시점별 체결률")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    plt.tight_layout()
    plt.savefig(RESULTS / "13_entry_timing.png", dpi=110)
    plt.close()
    print(f"\nSaved {RESULTS / '13_entry_timing.png'}")

    # Markdown summary
    md = ["# 마하세븐 돌파 — 진입 시점 민감도 분석 결과\n",
          f"베이스라인: 시그널 다음날 시초가 시장가 매수 (n={len(baseline)})\n",
          "Exit 가격은 원본 그대로 → '진입 시점만 바꿨을 때의 효과' 추정.\n",
          "Limit 시나리오: Low ≤ 한계가 충족 시만 체결, 아니면 거래 skip.\n\n",
          "## 시나리오별 성과\n",
          summary.to_markdown(index=False),
          "\n\n## 해석 가이드\n",
          "- **expect/trade 가 높을수록 진입 가격이 낮았다 = 수익률 개선**\n",
          "- **체결률(fill rate) 낮을수록 기회 손실 위험**\n",
          "- **low (theoretical max)** 는 실제 도달 불가능한 ceiling — 분봉 데이터 + 정밀 매매로도 이 수준은 어려움\n",
          "- limit 시나리오 fill rate 가 50% 미만이면 trade-off 부정적\n",
          "- baseline 대비 +X% 개선 vs fill rate 감소를 종합해 채택 여부 결정\n"]
    (RESULTS / "entry_timing_summary.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()
