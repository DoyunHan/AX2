#!/usr/bin/env python3
"""
데이터 취득 헬퍼 — 노트북(인터넷 가능 환경)에서 실데이터 CSV를 받는다.

기본: Binance USD-M 선물에서 BTC/ETH 1h봉을 data/ 폴더에 저장.

예시
  python fetch_data.py                                  # BTC+ETH 1h, 각 5000봉
  python fetch_data.py --symbols BTC/USDT:USDT SOL/USDT:USDT --timeframe 4h
  python fetch_data.py --since 2021-01-01 --limit 50000 # 특정일부터 대량

네트워크가 막힌 환경(예: 일부 클라우드)이라면 fetch_binance가 실패한다.
그 경우 노트북 등 인터넷 되는 곳에서 이 스크립트를 돌려 CSV를 만든 뒤
저장소로 옮겨 `--csv` 로 백테스트하면 된다. (HANDOFF.md 참고)
"""

from __future__ import annotations

import argparse
import os

from box_breakout.data import fetch_binance


def main() -> None:
    p = argparse.ArgumentParser(description="Binance OHLCV 다운로드 → data/*.csv")
    p.add_argument("--symbols", nargs="+", default=["BTC/USDT:USDT", "ETH/USDT:USDT"],
                   help="ccxt 심볼들 (USD-M 무기한은 'XXX/USDT:USDT')")
    p.add_argument("--timeframe", default="1h", help="15m/30m/1h/4h ...")
    p.add_argument("--limit", type=int, default=5000, help="심볼당 봉 수")
    p.add_argument("--since", default=None, help="시작일 YYYY-MM-DD (없으면 최근부터)")
    p.add_argument("--outdir", default="data", help="저장 폴더")
    a = p.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    for sym in a.symbols:
        base = sym.split("/")[0].lower()          # BTC/USDT:USDT -> btc
        out = os.path.join(a.outdir, f"{base}_{a.timeframe}.csv")
        print(f"[fetch] {sym} {a.timeframe} limit={a.limit} ...")
        df = fetch_binance(sym, a.timeframe, a.limit, a.since)
        df.to_csv(out, index=False)
        t0, t1 = df["timestamp"].iloc[0], df["timestamp"].iloc[-1]
        print(f"  -> {out}  ({len(df)} rows, {t0} ~ {t1})")


if __name__ == "__main__":
    main()
