"""
기술적 지표 계산 모듈.

키움 OpenAPI+에서 받은 시세 데이터(pandas DataFrame)에 적용 가능.
Live 시세 업데이트마다 호출되므로 마지막 N개 봉만 다루도록 설계.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    """단순 이동평균."""
    return s.rolling(n, min_periods=n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Average True Range (변동성 지표)."""
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def amount_surge(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    당일 거래대금 / N일 평균 거래대금 (전일까지).
    1.5 이상이면 거래대금 급증.
    """
    avg_prev = df["Amount"].rolling(window, min_periods=window).mean().shift(1)
    return df["Amount"] / avg_prev


def is_aligned(df: pd.DataFrame, short_period: int = 5, long_period: int = 20) -> pd.Series:
    """정배열 여부: 단기MA > 장기MA."""
    return sma(df["Close"], short_period) > sma(df["Close"], long_period)


def is_breakout(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """N일 신고가 돌파 여부 (당일 종가 > 직전 N일 최고가)."""
    prior_high = df["Close"].rolling(period, min_periods=period).max().shift(1)
    return df["Close"] > prior_high
