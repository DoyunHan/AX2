#!/usr/bin/env python3
"""
박스권 돌파 추세추종 전략 — 백테스트 실행 CLI.

예시
  # 오프라인 데모(합성데이터). 네트워크/API 키 불필요
  python run_backtest.py --demo

  # Binance에서 1h봉 2000개 받아 백테스트
  python run_backtest.py --symbol "BTC/USDT:USDT" --timeframe 1h --limit 2000

  # CSV 파일로 백테스트 + 거래내역 저장
  python run_backtest.py --csv data/btc_1h.csv --save-trades trades.csv

  # 파라미터 오버라이드
  python run_backtest.py --demo --box-lookback 36 --box-width 0.03 --atr-trail 2.5 --leverage 5
"""

from __future__ import annotations

import argparse
import json

from box_breakout import (
    StrategyConfig,
    BacktestConfig,
    Backtester,
    compute_metrics,
)
from box_breakout.data import fetch_binance, load_csv, generate_synthetic
from box_breakout.metrics import trades_to_dataframe


def build_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Box Breakout Trend Strategy backtest")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--demo", action="store_true", help="합성데이터로 오프라인 실행")
    src.add_argument("--csv", type=str, help="OHLCV CSV 경로")
    src.add_argument("--symbol", type=str, default="BTC/USDT:USDT", help="ccxt 심볼")

    p.add_argument("--timeframe", type=str, default="1h", help="15m/30m/1h ...")
    p.add_argument("--limit", type=int, default=2000, help="가져올 봉 수")
    p.add_argument("--since", type=str, default=None, help="시작일 YYYY-MM-DD")

    # 전략 파라미터
    p.add_argument("--box-lookback", type=int, default=24)
    p.add_argument("--box-width", type=float, default=0.04, help="박스폭 상한(비율)")
    p.add_argument("--vol-mult", type=float, default=1.5)
    p.add_argument("--buffer", type=float, default=0.001)
    p.add_argument("--atr-period", type=int, default=14)
    p.add_argument("--atr-trail", type=float, default=3.0)
    p.add_argument("--no-long", action="store_true")
    p.add_argument("--no-short", action="store_true")
    p.add_argument("--max-hold", type=int, default=0)

    # 백테스트 파라미터
    p.add_argument("--equity", type=float, default=10_000.0)
    p.add_argument("--leverage", type=float, default=3.0)
    p.add_argument("--risk", type=float, default=0.01, help="1회 리스크(자본 비율)")
    p.add_argument("--fee", type=float, default=0.0005)
    p.add_argument("--funding", type=float, default=0.0001)

    p.add_argument("--save-trades", type=str, default=None, help="거래내역 CSV 저장 경로")
    return p.parse_args()


def main() -> None:
    a = build_args()

    if a.demo:
        tf_min = {"15m": 15, "30m": 30, "1h": 60}.get(a.timeframe, 60)
        df = generate_synthetic(n_bars=max(a.limit, 4000), timeframe_minutes=tf_min)
        source = f"synthetic({len(df)} bars)"
    elif a.csv:
        df = load_csv(a.csv)
        source = f"csv:{a.csv} ({len(df)} bars)"
    else:
        df = fetch_binance(a.symbol, a.timeframe, a.limit, a.since)
        source = f"binance:{a.symbol} {a.timeframe} ({len(df)} bars)"

    strat_cfg = StrategyConfig(
        box_lookback=a.box_lookback,
        box_max_width_pct=a.box_width,
        breakout_buffer_pct=a.buffer,
        vol_mult=a.vol_mult,
        atr_period=a.atr_period,
        atr_trail_mult=a.atr_trail,
        allow_long=not a.no_long,
        allow_short=not a.no_short,
        max_hold_bars=a.max_hold,
    )
    bt_cfg = BacktestConfig(
        initial_equity=a.equity,
        leverage=a.leverage,
        risk_per_trade=a.risk,
        taker_fee=a.fee,
        funding_rate=a.funding,
    )

    result = Backtester(strat_cfg, bt_cfg).run(df)
    metrics = compute_metrics(result, a.equity)

    print(f"\n=== Box Breakout Backtest ===")
    print(f"data    : {source}")
    print(f"period  : {df['timestamp'].iloc[0]}  →  {df['timestamp'].iloc[-1]}")
    print("-" * 48)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))

    if a.save_trades:
        trades_to_dataframe(result).to_csv(a.save_trades, index=False)
        print(f"\n거래내역 저장: {a.save_trades}")


if __name__ == "__main__":
    main()
