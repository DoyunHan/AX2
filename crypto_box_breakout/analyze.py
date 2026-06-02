"""추천 설정의 연도별 견고성 + 인샘플/아웃샘플 검증."""
import sys
import pandas as pd
from box_breakout import StrategyConfig, BacktestConfig, Backtester, compute_metrics
from box_breakout.data import load_csv

path = sys.argv[1] if len(sys.argv) > 1 else "data/btc_1h.csv"
df = load_csv(path)

# 추천(견고형): 타이트 박스 + 강한 거래량필터 + 느슨한 트레일링
strat = StrategyConfig(box_lookback=48, box_max_width_pct=0.015,
                       vol_mult=2.0, atr_trail_mult=8.0)
bt = BacktestConfig(initial_equity=10_000, leverage=3.0, risk_per_trade=0.01)

res = Backtester(strat, bt).run(df)
print("=== 전체 구간 ===")
print(compute_metrics(res, 10_000))

# 연도별: 각 연도 데이터로 독립 백테스트(자본 매년 1만으로 리셋)
print("\n=== 연도별 (자본 매년 리셋) ===")
df = df.copy()
df["year"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.year
for y, g in df.groupby("year"):
    if len(g) < 500:
        continue
    r = Backtester(strat, bt).run(g.drop(columns="year").reset_index(drop=True))
    m = compute_metrics(r, 10_000)
    if m["num_trades"] == 0:
        print(f"{y}: 거래 없음"); continue
    print(f"{y}: ret={m['total_return_pct']:+6.1f}%  trades={m['num_trades']:3d}  "
          f"win={m['win_rate']:.2f}  PF={m['profit_factor']:.2f}  MDD={m['max_drawdown_pct']:.1f}%")

# 인샘플(2021-2023) vs 아웃샘플(2024-2026)
print("\n=== 인샘플 vs 아웃샘플 (워크포워드 단순판) ===")
ts = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
for label, mask in [("IN  2021-2023", ts < "2024-01-01"),
                    ("OUT 2024-2026", ts >= "2024-01-01")]:
    g = df[mask].drop(columns="year").reset_index(drop=True)
    r = Backtester(strat, bt).run(g)
    m = compute_metrics(r, 10_000)
    print(f"{label}: ret={m['total_return_pct']:+6.1f}%  trades={m['num_trades']:3d}  "
          f"PF={m['profit_factor']:.2f}  MDD={m['max_drawdown_pct']:.1f}%")
