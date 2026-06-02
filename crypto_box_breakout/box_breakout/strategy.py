"""
박스권 탐지 + 돌파 시그널 + ATR 트레일링 파라미터.

핵심 아이디어
  - 박스(횡보): 최근 lookback개 봉의 고/저 범위가 box_max_width_pct 이내로 압축된 구간.
  - 돌파: 현재 봉 종가가 박스 상단(+버퍼) 위로 마감 + 거래량 급증 → 롱.
          박스 하단(-버퍼) 아래로 마감 + 거래량 급증 → 숏.
  - 거짓 돌파(fakeout) 필터: 거래량이 평균 대비 vol_mult 이상일 때만 유효.

룩어헤드(미래참조) 방지
  박스 상/하단·평균거래량은 모두 .shift(1) 으로 "직전까지의 정보"만 사용한다.
  돌파 판정에는 현재 봉의 '종가'를 쓰는데, 이는 봉 마감 시점에 확정되는 값이므로
  종가 진입 가정과 일관된다(현실적).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StrategyConfig:
    # --- 박스(횡보) 정의 ---
    box_lookback: int = 24          # 박스를 만드는 직전 봉 수
    box_max_width_pct: float = 0.04  # 박스 폭 상한 (상단-하단)/하단, 4%
    # --- 돌파 판정 ---
    breakout_buffer_pct: float = 0.001  # 박스 경계 너머 버퍼 0.1%
    vol_mult: float = 1.5               # 돌파봉 거래량 / 평균거래량 하한
    # --- 추세 홀딩(ATR 트레일링) ---
    atr_period: int = 14
    atr_trail_mult: float = 3.0     # 트레일링 스탑 = 최고가 - mult*ATR
    allow_long: bool = True
    allow_short: bool = True
    max_hold_bars: int = 0          # 0이면 무제한(추세 끝까지 홀딩)


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder True Range 기반 ATR (단순이동평균 근사)."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def compute_features(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """박스 상/하단, 박스폭, 평균거래량, ATR, 횡보 여부를 컬럼으로 추가."""
    out = df.copy()
    lb = cfg.box_lookback

    # 직전 lookback개 봉의 박스 (현재 봉 제외 → shift(1))
    out["box_high"] = out["high"].rolling(lb, min_periods=lb).max().shift(1)
    out["box_low"] = out["low"].rolling(lb, min_periods=lb).min().shift(1)
    out["box_width"] = (out["box_high"] - out["box_low"]) / out["box_low"]
    out["avg_vol"] = out["volume"].rolling(lb, min_periods=lb).mean().shift(1)
    out["atr"] = compute_atr(out, cfg.atr_period)

    out["is_box"] = out["box_width"] <= cfg.box_max_width_pct
    return out


def generate_signals(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """
    long_signal / short_signal (bool) 컬럼 추가.

    조건:
      - 직전 구간이 박스(is_box)일 것
      - 종가가 박스 경계를 버퍼 이상 돌파 마감
      - 돌파봉 거래량 > 평균거래량 * vol_mult
    """
    out = df if "is_box" in df.columns else compute_features(df, cfg)
    if "is_box" not in out.columns:
        out = compute_features(df, cfg)

    buf = cfg.breakout_buffer_pct
    vol_ok = out["volume"] > (out["avg_vol"] * cfg.vol_mult)
    valid = out["is_box"] & out["box_high"].notna() & out["avg_vol"].notna()

    long_sig = valid & vol_ok & (out["close"] > out["box_high"] * (1 + buf))
    short_sig = valid & vol_ok & (out["close"] < out["box_low"] * (1 - buf))

    out["long_signal"] = long_sig if cfg.allow_long else False
    out["short_signal"] = short_sig if cfg.allow_short else False
    return out
