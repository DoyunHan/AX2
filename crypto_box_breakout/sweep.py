"""실데이터 파라미터 스윕: 박스/돌파/트레일링 조합 그리드 탐색."""
import itertools, sys
import pandas as pd
from box_breakout import StrategyConfig, BacktestConfig, Backtester, compute_metrics
from box_breakout.data import load_csv

path = sys.argv[1] if len(sys.argv) > 1 else "data/btc_1h.csv"
df = load_csv(path)

grid = {
    "box_lookback": [48, 72, 96, 144],
    "box_max_width_pct": [0.015, 0.025, 0.04],
    "vol_mult": [1.5, 2.0, 3.0],
    "atr_trail_mult": [4.0, 6.0, 8.0],
}
keys = list(grid)
rows = []
for combo in itertools.product(*grid.values()):
    p = dict(zip(keys, combo))
    strat = StrategyConfig(**p)
    res = Backtester(strat, BacktestConfig()).run(df)
    m = compute_metrics(res, 10_000)
    if m["num_trades"] == 0:
        continue
    rows.append({**p, **{k: m[k] for k in
        ["num_trades","win_rate","total_return_pct","profit_factor",
         "payoff_ratio","max_drawdown_pct","avg_bars_held","total_fees"]}})

r = pd.DataFrame(rows).sort_values("total_return_pct", ascending=False)
pd.set_option("display.width", 200, "display.max_columns", 30)
print(f"combos tested: {len(rows)}\n")
print("TOP 8 by total return:")
print(r.head(8).to_string(index=False))
print("\nTOP 5 by profit factor (min 30 trades):")
print(r[r.num_trades>=30].sort_values("profit_factor",ascending=False).head(5).to_string(index=False))
