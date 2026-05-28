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


# ============================================================================
# 마하세븐 포식자 시스템 — 사용자 명세 기반 구체화
# ============================================================================
#
# 일봉 데이터의 한계로 다음 항목은 근사:
#   - "1분봉 거래대금 N억 연속" → 일별 거래대금 급증으로 대체
#   - "15분 타임컷" → N거래일 보유 후 청산
#   - "60일/120일 매물대 돌파" → 데이터 길이 부족하면 20일로 축소 가능
#
# 그대로 구현 가능:
#   - 거래대금 상위 universe 필터, 정배열 필터, 5일선 눌림목 + 음봉,
#     5일선 이탈 hard stop, 트레일링 스탑, 초식동물 모드(no signal → no trade),
#     일일 손실 한도(엔진에서 처리).
# ============================================================================

def machaseven_predator(
    df: pd.DataFrame,
    eligible_dates: set | None = None,   # 거래대금 상위 universe (cross-sectional)
    # liquidity
    amount_surge_ratio: float = 2.0,      # 당일 거래대금 ≥ N일 평균 × ratio
    amount_avg_window: int = 20,
    # alignment / structure
    require_alignment: bool = True,        # 5MA > 20MA (역배열 제외)
    long_ma_period: int = 20,
    # entry mode: "pullback" or "breakout"
    mode: str = "pullback",
    # breakout params
    breakout_period: int = 20,            # 데이터 짧으면 20, 보통은 60/120
    # pullback params
    pullback_band_pct: float = 0.02,      # 5MA ± 2%
    require_negative_candle: bool = True,
    # exits
    hard_stop_5ma: bool = True,            # 5MA 이탈 시 즉시 청산
    trailing_stop_pct: float = 0.03,      # 고점 대비 -3% 트레일링
    max_holding: int = 3,                  # N거래일 타임컷 (15분 대신)
    cooldown: int = 1,
) -> list[dict]:
    """
    한 종목에 대한 마하세븐 포식자 신호 생성.

    `eligible_dates`가 주어지면 그 날짜에 시그널 발생 시에만 진입(거래대금
    universe 필터). None이면 universe 필터 없이 종목 자체 조건만 본다.
    """
    n = len(df)
    if n < max(amount_avg_window, long_ma_period, breakout_period) + 5:
        return []

    ma5 = sma(df["Close"], 5)
    ma_long = sma(df["Close"], long_ma_period)
    # Use *yesterday's* MA as the reference to avoid look-ahead within day i
    ma5_prev = ma5.shift(1)
    amount_avg_prev = df["Amount"].rolling(amount_avg_window, min_periods=amount_avg_window).mean().shift(1)
    rolling_high_prev = df["Close"].rolling(breakout_period, min_periods=breakout_period).max().shift(1)

    trades = []
    i = max(amount_avg_window, long_ma_period, breakout_period)
    while i < n - 1:
        date = df.index[i]

        # Universe filter
        if eligible_dates is not None and date not in eligible_dates:
            i += 1
            continue

        # Liquidity surge
        if pd.isna(amount_avg_prev.iloc[i]) or amount_avg_prev.iloc[i] <= 0:
            i += 1
            continue
        if df["Amount"].iloc[i] < amount_avg_prev.iloc[i] * amount_surge_ratio:
            i += 1
            continue

        # Alignment: 5MA > long MA (정배열 요구)
        if require_alignment:
            if not (pd.notna(ma5.iloc[i]) and pd.notna(ma_long.iloc[i])
                    and ma5.iloc[i] > ma_long.iloc[i]):
                i += 1
                continue

        # Entry trigger
        triggered = False
        if mode == "breakout":
            if pd.notna(rolling_high_prev.iloc[i]) and df["Close"].iloc[i] > rolling_high_prev.iloc[i]:
                triggered = True
        elif mode == "pullback":
            five = ma5.iloc[i]
            close = df["Close"].iloc[i]
            if pd.notna(five) and five > 0:
                in_band = abs(close - five) / five <= pullback_band_pct
                is_red = df["Close"].iloc[i] < df["Open"].iloc[i]
                triggered = in_band and (is_red if require_negative_candle else True)

        if not triggered:
            i += 1
            continue

        # Entry next day open
        entry_idx = i + 1
        if entry_idx >= n:
            break
        entry_price = float(df["Open"].iloc[entry_idx])
        if entry_price <= 0:
            i += 1
            continue
        entry_date = df.index[entry_idx]

        # Track exits
        exit_idx, exit_price, exit_reason = None, None, "time_cut"
        peak = entry_price
        for j in range(entry_idx, min(entry_idx + max_holding, n)):
            high_j = float(df["High"].iloc[j])
            low_j = float(df["Low"].iloc[j])
            peak = max(peak, high_j)

            # 1) Hard stop on 5MA breakdown — use yesterday's 5MA as reference
            if hard_stop_5ma and pd.notna(ma5_prev.iloc[j]) and ma5_prev.iloc[j] > 0:
                if low_j < ma5_prev.iloc[j]:
                    exit_idx = j
                    exit_price = float(ma5_prev.iloc[j])
                    exit_reason = "hard_stop_5MA"
                    break

            # 2) Trailing stop
            ts_level = peak * (1 - trailing_stop_pct)
            if low_j <= ts_level and j > entry_idx:
                exit_idx = j
                exit_price = ts_level
                exit_reason = "trailing_stop"
                break

        if exit_idx is None:
            exit_idx = min(entry_idx + max_holding - 1, n - 1)
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
    return trades


# ============================================================================
# 일일 손실 한도 (Daily Drawdown Limit) — 포트폴리오 차원의 거래 차단
# ============================================================================

def apply_daily_loss_limit(trades: list[dict],
                           daily_limit: float = -0.05,
                           cost: float = 0.0023) -> list[dict]:
    """
    날짜별로 누적 손실이 한도(daily_limit, 예: -5%)에 도달한 다음부터
    그 날의 신규 진입을 차단한다 (보복성 매매 방지).

    실제 운영에서는 실시간 P&L로 동작하지만, 백테스트에서는 시간 순으로
    정렬 후 entry_date 단위로 그 날의 누적(net) 손익을 추적해 차단한다.
    """
    if not trades:
        return []
    df = pd.DataFrame(trades).sort_values("entry_date").reset_index(drop=True)
    df["net_ret"] = (df["exit_price"] - df["entry_price"]) / df["entry_price"] - cost
    kept_rows = []
    daily_acc: dict = {}
    for _, row in df.iterrows():
        d = pd.to_datetime(row["entry_date"]).date()
        if daily_acc.get(d, 0.0) <= daily_limit:
            # Locked out for the day
            continue
        kept_rows.append(row.to_dict())
        daily_acc[d] = daily_acc.get(d, 0.0) + row["net_ret"]
    return kept_rows
