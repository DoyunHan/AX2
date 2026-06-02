"""
합성데이터 기반 스모크/정합성 테스트.

  pip install pytest 후:  pytest -q
  또는 그냥:               python tests/test_strategy.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from box_breakout import StrategyConfig, BacktestConfig, Backtester, compute_metrics
from box_breakout.data import generate_synthetic
from box_breakout.strategy import compute_features, generate_signals


def test_no_lookahead_in_box():
    """box_high/box_low/avg_vol은 현재 봉을 포함하면 안 된다(shift(1) 검증)."""
    df = generate_synthetic(n_bars=500, seed=1)
    cfg = StrategyConfig(box_lookback=10)
    f = compute_features(df, cfg)
    lb = cfg.box_lookback
    # 임의 지점에서 박스값이 '직전' lb개로만 계산됐는지 직접 대조
    i = 100
    expected_high = df["high"].iloc[i - lb : i].max()
    expected_low = df["low"].iloc[i - lb : i].min()
    assert np.isclose(f["box_high"].iloc[i], expected_high)
    assert np.isclose(f["box_low"].iloc[i], expected_low)


def test_signals_are_boolean_and_sparse():
    df = generate_synthetic(n_bars=2000, seed=2)
    cfg = StrategyConfig()
    sig = generate_signals(df, cfg)
    assert sig["long_signal"].dtype == bool
    assert sig["short_signal"].dtype == bool
    # 돌파는 드물게 나와야 정상 (전체의 절반 미만)
    assert sig["long_signal"].sum() + sig["short_signal"].sum() < len(df) * 0.5


def test_backtest_runs_and_is_consistent():
    df = generate_synthetic(n_bars=4000, seed=3)
    strat = StrategyConfig()
    bt = BacktestConfig(initial_equity=10_000)
    res = Backtester(strat, bt).run(df)
    m = compute_metrics(res, 10_000)

    # 자본곡선 길이 = 봉 수
    assert len(res.equity_curve) == len(df)
    # 거래가 1건 이상 발생해야 데모로서 의미 있음
    assert m["num_trades"] >= 1
    # 순손익 합 ≈ 최종자본 - 초기자본
    total_net = sum(t.net_pnl for t in res.trades)
    assert np.isclose(total_net, res.final_equity - 10_000, atol=1e-6)
    # 모든 거래는 비용(수수료>0)을 부담
    assert all(t.fees > 0 for t in res.trades)


def test_long_only_has_no_shorts():
    df = generate_synthetic(n_bars=3000, seed=4)
    strat = StrategyConfig(allow_short=False)
    res = Backtester(strat, BacktestConfig()).run(df)
    assert all(t.side == "long" for t in res.trades)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS  {name}")
    print("\n모든 테스트 통과")
