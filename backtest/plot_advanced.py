"""Plot equity curves for the best advanced strategies."""

import sys
from pathlib import Path
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
from metrics import equity_curve

RESULTS = Path(__file__).parent / "results"

# Compare three winners on one chart: cumulative edge (additive)
files = {
    "장영한 (필터)": "trades_jyh_filtered.csv",
    "마하세븐 — 돌파": "trades_machaseven_breakout.csv",
    "마하세븐 — 눌림목": "trades_machaseven_pullback.csv",
}

plt.figure(figsize=(11, 5.5))
for name, fname in files.items():
    p = RESULTS / fname
    if not p.exists():
        continue
    df = pd.read_csv(p, parse_dates=["entry_date", "exit_date"])
    if df.empty:
        continue
    eq = equity_curve(df.to_dict("records"), mode="cumsum")
    plt.plot(eq.index, eq.values, lw=1.7, label=f"{name} (n={len(df)})")

plt.axhline(1.0, color="gray", lw=0.7, linestyle="--")
plt.title("고급 전략 비교 — 누적 엣지 (per-trade net 합산)")
plt.ylabel("1.0 + Σ(per-trade net return)")
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS / "9_advanced_comparison.png", dpi=110)
plt.close()
print("Saved:", RESULTS / "9_advanced_comparison.png")

# 마하세븐 돌파 — exit reason breakdown
df = pd.read_csv(RESULTS / "trades_machaseven_breakout.csv", parse_dates=["entry_date", "exit_date"])
df["net_ret"] = (df["exit_price"] - df["entry_price"]) / df["entry_price"] - 0.0023
reason_stats = df.groupby("reason").agg(
    n=("net_ret", "count"),
    avg=("net_ret", "mean"),
    win_rate=("net_ret", lambda s: (s > 0).mean()),
).reset_index()
print("\n마하세븐 돌파 — exit reason 분해:")
print(reason_stats.to_string(index=False))
reason_stats.to_csv(RESULTS / "machaseven_breakout_reasons.csv", index=False)
