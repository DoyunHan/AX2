"""
Four day-trading strategies derived from Korean trading masters.

Each strategy is a function that takes an OHLCV DataFrame and returns a
list of trade dicts: {entry_date, entry_price, exit_date, exit_price, reason}.

The DataFrame must have columns: Open, High, Low, Close, Volume
indexed by Date (datetime).

Strategies:
  1. bnf_mean_reversion       — B.N.F 이격도 역추세 (수치 명확, 자동화 친화 최상)
  2. namseokgwan_vol_breakout — 남석관 거래량 폭증 + 돌파
  3. jangyounghan_trend       — 장영한 시스템 추세추종 (이평선 + ATR 손익비)
  4. machaseven_volatility    — 마하세븐 호가창 스캘핑의 근사
                                (일봉 데이터 한계로 '변동성 종목 추격'으로 대체)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# Common indicators
# ----------------------------------------------------------------------------

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Average True Range."""
    h, l, c = df["High"], df["Low"], df["Close"]
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


# ----------------------------------------------------------------------------
# 1) B.N.F — 이격도 역추세
# ----------------------------------------------------------------------------

def bnf_mean_reversion(
    df: pd.DataFrame,
    ma_period: int = 25,
    disparity_threshold: float = -10.0,  # % below MA
    exit_disparity: float = 0.0,         # exit when disparity recovers to >= 0%
    max_holding: int = 10,
    cooldown: int = 5,
) -> list[dict]:
    """
    B.N.F-style mean reversion:
    - Buy when (Close - MA25) / MA25 * 100 <= disparity_threshold (e.g., -10%)
    - Exit when disparity recovers to >= exit_disparity, or max_holding days reached
    """
    if len(df) < ma_period + 5:
        return []
    ma = sma(df["Close"], ma_period)
    disp = (df["Close"] - ma) / ma * 100.0

    trades = []
    i = ma_period
    while i < len(df) - 1:
        if pd.isna(disp.iloc[i]):
            i += 1
            continue
        if disp.iloc[i] <= disparity_threshold:
            entry_idx = i + 1  # next-day open entry
            if entry_idx >= len(df):
                break
            entry_date = df.index[entry_idx]
            entry_price = float(df["Open"].iloc[entry_idx])
            # Find exit
            exit_idx = None
            exit_reason = "holding_limit"
            for j in range(entry_idx, min(entry_idx + max_holding, len(df))):
                if disp.iloc[j] >= exit_disparity:
                    exit_idx = j
                    exit_reason = "disparity_recovered"
                    break
            if exit_idx is None:
                exit_idx = min(entry_idx + max_holding, len(df) - 1)
            exit_date = df.index[exit_idx]
            exit_price = float(df["Close"].iloc[exit_idx])
            trades.append({
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "reason": exit_reason,
            })
            i = exit_idx + cooldown
        else:
            i += 1
    return trades


# ----------------------------------------------------------------------------
# 2) 남석관 — 거래량 폭증 + 신고가 돌파
# ----------------------------------------------------------------------------

def namseokgwan_vol_breakout(
    df: pd.DataFrame,
    vol_ma: int = 20,
    vol_mult: float = 3.0,
    hi_period: int = 20,
    stop_loss: float = -0.05,
    take_profit: float = 0.08,
    max_holding: int = 5,
    cooldown: int = 2,
) -> list[dict]:
    """
    Volume breakout:
    - Trigger: Volume > vol_ma 평균 × vol_mult  AND  Close == hi_period 신고가
    - Entry: next day open
    - Exit: -stop_loss, +take_profit, or max_holding days
    """
    if len(df) < max(vol_ma, hi_period) + 5:
        return []
    vol_avg = df["Volume"].rolling(vol_ma, min_periods=vol_ma).mean().shift(1)
    rolling_high = df["Close"].rolling(hi_period, min_periods=hi_period).max()

    trades = []
    i = max(vol_ma, hi_period)
    while i < len(df) - 1:
        vol_ok = df["Volume"].iloc[i] > (vol_avg.iloc[i] or 0) * vol_mult
        new_high = df["Close"].iloc[i] >= rolling_high.iloc[i]
        if vol_ok and new_high:
            entry_idx = i + 1
            if entry_idx >= len(df):
                break
            entry_date = df.index[entry_idx]
            entry_price = float(df["Open"].iloc[entry_idx])
            exit_idx, exit_price, exit_reason = None, None, "holding_limit"
            for j in range(entry_idx, min(entry_idx + max_holding, len(df))):
                # Intraday check using High/Low
                hi_ret = (df["High"].iloc[j] - entry_price) / entry_price
                lo_ret = (df["Low"].iloc[j] - entry_price) / entry_price
                if lo_ret <= stop_loss:
                    exit_idx = j
                    exit_price = entry_price * (1 + stop_loss)
                    exit_reason = "stop_loss"
                    break
                if hi_ret >= take_profit:
                    exit_idx = j
                    exit_price = entry_price * (1 + take_profit)
                    exit_reason = "take_profit"
                    break
            if exit_idx is None:
                exit_idx = min(entry_idx + max_holding, len(df) - 1)
                exit_price = float(df["Close"].iloc[exit_idx])
            exit_date = df.index[exit_idx]
            trades.append({
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "reason": exit_reason,
            })
            i = exit_idx + cooldown
        else:
            i += 1
    return trades


# ----------------------------------------------------------------------------
# 3) 장영한 — 시스템 추세추종 (이평선 정배열 + ATR 손익비)
# ----------------------------------------------------------------------------

def jangyounghan_trend(
    df: pd.DataFrame,
    fast: int = 5,
    slow: int = 20,
    atr_n: int = 14,
    atr_stop: float = 2.0,    # stop = entry - atr_stop * ATR
    atr_target: float = 4.0,  # target = entry + atr_target * ATR  → 손익비 1:2
    max_holding: int = 20,
    cooldown: int = 3,
) -> list[dict]:
    """
    Trend following:
    - Trigger: fast MA crosses above slow MA AND Close > slow MA
    - Entry: next day open
    - Stop: entry - atr_stop * ATR(at entry)
    - Target: entry + atr_target * ATR(at entry)
    - Time stop: max_holding days
    """
    if len(df) < slow + atr_n + 5:
        return []
    fast_ma = sma(df["Close"], fast)
    slow_ma = sma(df["Close"], slow)
    atr_val = atr(df, atr_n)

    cross_up = (fast_ma > slow_ma) & (fast_ma.shift(1) <= slow_ma.shift(1))
    above_slow = df["Close"] > slow_ma

    trades = []
    i = slow + atr_n
    while i < len(df) - 1:
        if cross_up.iloc[i] and above_slow.iloc[i] and pd.notna(atr_val.iloc[i]):
            entry_idx = i + 1
            if entry_idx >= len(df):
                break
            entry_date = df.index[entry_idx]
            entry_price = float(df["Open"].iloc[entry_idx])
            entry_atr = float(atr_val.iloc[i])
            stop_px = entry_price - atr_stop * entry_atr
            tgt_px = entry_price + atr_target * entry_atr
            exit_idx, exit_price, exit_reason = None, None, "holding_limit"
            for j in range(entry_idx, min(entry_idx + max_holding, len(df))):
                if df["Low"].iloc[j] <= stop_px:
                    exit_idx = j
                    exit_price = stop_px
                    exit_reason = "stop_loss"
                    break
                if df["High"].iloc[j] >= tgt_px:
                    exit_idx = j
                    exit_price = tgt_px
                    exit_reason = "take_profit"
                    break
            if exit_idx is None:
                exit_idx = min(entry_idx + max_holding, len(df) - 1)
                exit_price = float(df["Close"].iloc[exit_idx])
            exit_date = df.index[exit_idx]
            trades.append({
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "reason": exit_reason,
            })
            i = exit_idx + cooldown
        else:
            i += 1
    return trades


# ----------------------------------------------------------------------------
# 4) 마하세븐 — 호가창 스캘핑의 근사 (일봉 한계 명시)
# ----------------------------------------------------------------------------

def machaseven_volatility(
    df: pd.DataFrame,
    intraday_range_threshold: float = 0.05,  # (High-Low)/Open >= 5%
    min_volume: float = 1_000_000,           # 거래량 100만주 이상
    holding_days: int = 1,                   # 다음날 종가 청산
    cooldown: int = 1,
) -> list[dict]:
    """
    APPROXIMATION ONLY. 마하세븐 본인의 호가창/체결강도 매매는 일봉으로
    재현 불가. 여기서는 "고변동성 + 고거래량 종목을 다음날 추격"이라는
    스캘핑 후보 종목 발굴 로직의 근사를 백테스트한다.

    Logic:
      - Today: (High - Low) / Open >= intraday_range_threshold (e.g., 5%)
        AND Volume >= min_volume
      - Entry: next day open
      - Exit: holding_days 후 종가
    """
    if len(df) < 5:
        return []
    intra_range = (df["High"] - df["Low"]) / df["Open"]

    trades = []
    i = 1
    while i < len(df) - 1:
        if intra_range.iloc[i] >= intraday_range_threshold and df["Volume"].iloc[i] >= min_volume:
            entry_idx = i + 1
            if entry_idx >= len(df):
                break
            entry_date = df.index[entry_idx]
            entry_price = float(df["Open"].iloc[entry_idx])
            exit_idx = min(entry_idx + holding_days - 1, len(df) - 1)
            exit_date = df.index[exit_idx]
            exit_price = float(df["Close"].iloc[exit_idx])
            trades.append({
                "entry_date": entry_date,
                "entry_price": entry_price,
                "exit_date": exit_date,
                "exit_price": exit_price,
                "reason": "time_exit",
            })
            i = exit_idx + cooldown
        else:
            i += 1
    return trades


STRATEGIES = {
    "B.N.F 이격도 역추세": bnf_mean_reversion,
    "남석관 거래량 돌파": namseokgwan_vol_breakout,
    "장영한 시스템 추세추종": jangyounghan_trend,
    "마하세븐 변동성 추격(근사)": machaseven_volatility,
}
