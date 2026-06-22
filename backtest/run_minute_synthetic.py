"""
합성 분봉을 사용한 정밀 진입 룰 시뮬레이션.

⚠️  주의: 합성 분봉은 일봉 OHLC + Brownian bridge 로 생성된 모델 데이터.
   실제 시장 미세구조(호가창, tick imbalance, 슬리피지)는 반영 안 됨.
   결과는 'rule 별 상대 비교' 용도만 신뢰 가능. 절대 수치는 실데이터 후 재검증.

목적: 분봉 데이터 도착 시 어떤 진입 룰이 가장 promising 한지 사전 후보 선정.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from data_loader import build_stock_panel
from strategies import machaseven_predator, apply_daily_loss_limit
from universe import amount_rank_universe
from metrics import compute_stats, ROUND_TRIP_COST
from kiwoom.data.minute_loader import (
    SyntheticMinuteGenerator, EntryRule, simulate_entry,
)

RESULTS = Path(__file__).parent / "results"


def main():
    print("=== Loading data ===")
    panels = build_stock_panel("krx", verbose=False)
    amount_uni = amount_rank_universe(panels, top_n=50)

    print("=== Baseline 마하세븐 돌파 ===")
    raw = []
    for code, df in panels.items():
        eligible = amount_uni.get(code, set())
        if not eligible:
            continue
        trades = machaseven_predator(
            df, eligible_dates=eligible, mode="breakout",
            amount_surge_ratio=1.5, require_alignment=True,
            long_ma_period=20, breakout_period=20,
            hard_stop_5ma=True, trailing_stop_pct=0.02, max_holding=3,
        )
        for t in trades:
            t["code"] = code
        raw.extend(trades)
    baseline = apply_daily_loss_limit(raw, daily_limit=-0.05)
    print(f"  baseline trades: {len(baseline)}")

    gen = SyntheticMinuteGenerator(seed=42)

    rules = [
        ("market_open (baseline)", EntryRule(rule_name="market_open")),
        ("wait 15min", EntryRule(rule_name="wait_n_minutes", wait_minutes=15)),
        ("wait 30min", EntryRule(rule_name="wait_n_minutes", wait_minutes=30)),
        ("limit -0.5% / skip", EntryRule(rule_name="limit_below_open",
                                          limit_offset_pct=0.5, fallback="skip")),
        ("limit -1.0% / skip", EntryRule(rule_name="limit_below_open",
                                          limit_offset_pct=1.0, fallback="skip")),
        ("limit -1.0% / market", EntryRule(rule_name="limit_below_open",
                                            limit_offset_pct=1.0, fallback="market")),
        ("first pullback -0.5%", EntryRule(rule_name="first_pullback",
                                            pullback_pct=0.5)),
        ("first pullback -1.0%", EntryRule(rule_name="first_pullback",
                                            pullback_pct=1.0)),
        ("volume confirm x2 @ 15min", EntryRule(rule_name="volume_confirm",
                                                  volume_mult_threshold=2.0)),
    ]

    print("\n=== Simulating entry rules on synthetic minute bars ===")
    print(f"(seed=42, 거래 수 × 분봉 시뮬레이션)")

    rows = []
    for rule_name, rule in rules:
        sim_trades = []
        for t in baseline:
            code = t["code"]
            entry_date = pd.to_datetime(t["entry_date"]).date()
            df_panel = panels.get(code)
            if df_panel is None:
                continue
            entry_day = df_panel.loc[pd.Timestamp(entry_date)]
            mins = gen.generate(entry_day, entry_date)
            result = simulate_entry(mins, rule)
            if result is None:
                continue  # 미체결 skip
            entry_px, entry_ts = result
            sim_trades.append({**t, "entry_price": entry_px})
        s = compute_stats(sim_trades).as_dict(include_compound=False)
        fill_rate = len(sim_trades) / len(baseline) * 100
        rows.append({
            "rule": rule_name,
            "trades": s["trades"],
            "fill_rate(%)": round(fill_rate, 1),
            "win_rate(%)": s["win_rate(%)"],
            "expect/trade(%)": s["expect/trade(%)"],
            "PF": s["PF"],
            "Sharpe": s["Sharpe"],
        })
        print(f"  {rule_name:35s}  n={s['trades']:3d} ({fill_rate:5.1f}%)  "
              f"expect={s['expect/trade(%)']:+6.3f}%  PF={s['PF']:5.2f}")

    summary = pd.DataFrame(rows)
    summary.to_csv(RESULTS / "synthetic_minute_summary.csv", index=False)

    md = ["# 합성 분봉 — 정밀 진입 룰 시뮬레이션\n",
          "⚠️ Brownian-bridge 합성 데이터 사용. 절대 수치 X, 상대 비교만 신뢰.\n",
          "실데이터(키움 OPT10080) 도착 후 동일 룰로 재검증 필요.\n\n",
          summary.to_markdown(index=False),
          "\n\n## 해석\n",
          "- expect 가 baseline 보다 높고 fill_rate 가 합리적인 룰이 후보\n",
          "- 합성 데이터 한계상 호가창 의존 룰은 검증 불가\n",
          "- baseline(open 시장가) 이 모멘텀 매매에 가장 효과적이라는 가설 검증/반증\n"]
    (RESULTS / "synthetic_minute_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nSaved {RESULTS / 'synthetic_minute_summary.md'}")


if __name__ == "__main__":
    main()
