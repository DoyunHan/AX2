"""
OHLCV 데이터 로딩.

세 가지 경로를 제공한다.
  1) fetch_binance() : ccxt로 Binance USD-M 선물 과거봉 다운로드 (네트워크 필요)
  2) load_csv()      : 저장된 CSV 로드
  3) generate_synthetic() : 박스→돌파→추세 패턴을 가진 합성데이터 (오프라인 데모/테스트)

표준 DataFrame 스키마(컬럼):
  timestamp(UTC, tz-aware) | open | high | low | close | volume
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV 데이터에 필요한 컬럼 누락: {missing}")
    df = df[REQUIRED_COLUMNS].copy()
    df = df.dropna().sort_values("timestamp").reset_index(drop=True)
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def load_csv(path: str) -> pd.DataFrame:
    """CSV 파일에서 OHLCV 로드. timestamp는 ISO 문자열 또는 ms epoch 모두 허용."""
    df = pd.read_csv(path)
    if pd.api.types.is_numeric_dtype(df["timestamp"]):
        # epoch milliseconds 로 간주
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return _validate(df)


def fetch_binance(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "1h",
    limit: int = 1500,
    since: str | None = None,
) -> pd.DataFrame:
    """
    ccxt로 Binance USD-M 선물 OHLCV 다운로드.

    symbol  : ccxt 통합 심볼. USD-M 무기한은 'BTC/USDT:USDT' 형식.
    timeframe: '15m', '30m', '1h' 등.
    limit   : 가져올 총 봉 수 (1000 초과 시 자동 페이지네이션).
    since   : 시작 시각 ISO 문자열(예: '2024-01-01'). None이면 최근부터 역순.
    """
    try:
        import ccxt  # 지연 import: 백테스트/CSV 경로만 쓸 땐 ccxt 불필요
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Binance 다운로드에는 ccxt가 필요합니다: pip install ccxt"
        ) from e

    exchange = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True})
    since_ms = exchange.parse8601(f"{since}T00:00:00Z") if since else None

    rows: list[list] = []
    page = 1000  # Binance 단일 요청 상한
    while len(rows) < limit:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=page)
        if not batch:
            break
        rows.extend(batch)
        since_ms = batch[-1][0] + 1
        if len(batch) < page:
            break
    rows = rows[:limit]

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return _validate(df)


def generate_synthetic(
    n_bars: int = 4000,
    timeframe_minutes: int = 60,
    seed: int = 7,
    start: str = "2024-01-01",
) -> pd.DataFrame:
    """
    박스(횡보) → 돌파 → 추세 → 되돌림 레짐을 반복하는 합성 OHLCV 생성.

    네트워크 없이 전략 로직을 검증하기 위한 용도. 실거래 판단에 쓰지 말 것.
    """
    rng = np.random.default_rng(seed)
    price = 30000.0
    closes = np.empty(n_bars)
    vols = np.empty(n_bars)

    i = 0
    while i < n_bars:
        regime = rng.choice(["box", "trend"], p=[0.55, 0.45])
        if regime == "box":
            # 박스 구간은 기본 box_lookback(=48)보다 길게 유지해야 윈도우가 박스 안에 들어옴
            length = int(rng.integers(60, 110))
            center = price
            half = price * rng.uniform(0.005, 0.011)  # 박스 반폭 0.5~1.1% (폭 ~1~2.2%)
            for _ in range(length):
                if i >= n_bars:
                    break
                # 박스 안에서 평균회귀 + 작은 노이즈, 거래량 평시
                price += (center - price) * 0.15 + rng.normal(0, half * 0.25)
                price = float(np.clip(price, center - half, center + half))
                closes[i] = price
                vols[i] = rng.uniform(800, 1200)
                i += 1
        else:
            length = int(rng.integers(40, 90))
            drift = price * rng.uniform(0.0008, 0.0025) * rng.choice([1, -1])
            for k in range(length):
                if i >= n_bars:
                    break
                # 추세 + 변동성, 돌파 초입 거래량 급증
                price += drift + rng.normal(0, price * 0.004)
                price = float(max(price, 1000))
                closes[i] = price
                vols[i] = rng.uniform(1600, 2600) if k < 6 else rng.uniform(1000, 1800)
                i += 1

    # 종가 시계열에서 OHLC 합성
    closes = closes[:n_bars]
    vols = vols[:n_bars]
    opens = np.empty(n_bars)
    opens[0] = closes[0]
    opens[1:] = closes[:-1]
    wick = np.abs(rng.normal(0, closes * 0.0015))
    highs = np.maximum(opens, closes) + wick
    lows = np.minimum(opens, closes) - wick

    ts = pd.date_range(start=start, periods=n_bars, freq=f"{timeframe_minutes}min", tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
        }
    )
    return _validate(df)
