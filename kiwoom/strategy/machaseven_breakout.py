"""
마하세븐 포식자 시스템 — 돌파 모드 (Walk-forward 검증 통과 전략).

핵심 룰 (backtest/walk_forward.py 에서 OOS PF 3.28, 승률 63.7% 확인):

  진입 조건 (모두 충족):
    1. 당일 거래대금 상위 50 종목군에 속함
    2. 당일 거래대금 ≥ 20일 평균 거래대금 × 1.5
    3. 5MA > 20MA (정배열 — 역배열 종목 절대 진입 X)
    4. 20일 신고가 돌파 (당일 종가 > 직전 20일 최고가)

  진입 시점: 시그널 발생 다음날 시초가 시장가 매수.

  청산 조건 (선후 발생 순):
    1. Hard stop: 저가가 5일선 이하로 하향 돌파 → 즉시 시장가 청산
    2. Trailing stop: 보유 중 최고가 대비 -2% 도달 → 즉시 시장가 청산
    3. Time cut: 매수 후 3거래일 경과 → 당일 종가 청산

  자금 관리:
    - 일일 누적 P&L 이 -5% 도달 시 당일 신규 진입 차단 (보복 매매 방지)
    - 총 자본의 50%는 항상 현금
    - 진입당 사용 가능 자본의 20% (5종목 동시 보유 한도)

Kiwoom OpenAPI+ 연동 메모:
  - 실시간 시세: SetRealReg(현재가/체결강도/거래량 등록) → OnReceiveRealData
  - 분봉 데이터: OPT10080 (주식분봉차트조회)
  - 일봉 데이터: OPT10081 (주식일봉차트조회)
  - 주문: SendOrder(시장가 = "03", 지정가 = "00")
  - 호가창: OPT10004 (주식호가요청) — 진입 직전 매도 1호가 슬리피지 확인용
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

import pandas as pd

from ..config.machaseven import CFG
from . import indicators as ind


class Signal(str, Enum):
    BUY = "buy"
    HOLD = "hold"
    HARD_STOP = "hard_stop"
    TRAILING_STOP = "trailing_stop"
    TIME_CUT = "time_cut"


@dataclass
class EntryDecision:
    code: str
    signal: Signal
    reason: str
    price_ref: float  # 참고용 가격 (전일 종가 또는 진입 추천가)


@dataclass
class ExitDecision:
    code: str
    signal: Signal
    reason: str
    exit_price_target: Optional[float] = None  # 트레일링 stop 가격 등 참고용


# ============================================================================
# 진입 신호 판단
# ============================================================================

def check_entry(df: pd.DataFrame, code: str, in_amount_universe: bool) -> EntryDecision:
    """
    한 종목의 일봉 시계열 df 를 받아 진입 신호를 평가한다.

    df 요구 컬럼: Open, High, Low, Close, Volume, Amount (index=Date)
    df 마지막 행 = 오늘. 시그널 발생 시 다음 영업일 시초가 진입.
    """
    if not in_amount_universe:
        return EntryDecision(code, Signal.HOLD, "not in amount top-50", float("nan"))
    if len(df) < max(CFG.AMOUNT_AVG_WINDOW, CFG.LONG_MA_PERIOD, CFG.BREAKOUT_PERIOD) + 1:
        return EntryDecision(code, Signal.HOLD, "warmup insufficient", float("nan"))

    today = df.iloc[-1]

    # 1) Amount surge
    surge = ind.amount_surge(df, CFG.AMOUNT_AVG_WINDOW).iloc[-1]
    if pd.isna(surge) or surge < CFG.AMOUNT_SURGE_RATIO:
        return EntryDecision(code, Signal.HOLD,
                             f"amount surge {surge:.2f} < {CFG.AMOUNT_SURGE_RATIO}",
                             float(today["Close"]))

    # 2) 정배열
    if CFG.REQUIRE_ALIGNMENT:
        aligned = ind.is_aligned(df, 5, CFG.LONG_MA_PERIOD).iloc[-1]
        if not bool(aligned):
            return EntryDecision(code, Signal.HOLD, "역배열 (5MA < 20MA)",
                                 float(today["Close"]))

    # 3) 20일 신고가 돌파
    breakout = ind.is_breakout(df, CFG.BREAKOUT_PERIOD).iloc[-1]
    if not bool(breakout):
        return EntryDecision(code, Signal.HOLD,
                             f"no {CFG.BREAKOUT_PERIOD}-day breakout",
                             float(today["Close"]))

    return EntryDecision(code, Signal.BUY,
                         f"surge x{surge:.2f} + 정배열 + {CFG.BREAKOUT_PERIOD}일 돌파",
                         float(today["Close"]))


# ============================================================================
# 청산 신호 판단 — 보유 포지션마다 매 봉마다 호출
# ============================================================================

@dataclass
class Position:
    code: str
    entry_date: date
    entry_price: float
    peak_high: float        # 보유 중 최고가 (트레일링용)
    holding_days: int


def check_exit(df: pd.DataFrame, pos: Position) -> ExitDecision:
    """
    포지션 pos 에 대해 오늘 df.iloc[-1] 봉을 기준으로 청산 판단.

    호출 시점:
      - 실시간 모드: 매 체결마다 (OnReceiveRealData 콜백 내)
      - 일봉 모드: 매일 종가 직후
    """
    today = df.iloc[-1]
    high_today = float(today["High"])
    low_today = float(today["Low"])
    close_today = float(today["Close"])

    # 보유 최고가 갱신
    pos.peak_high = max(pos.peak_high, high_today)

    # 1) Hard stop: 5MA 하향 돌파 (전일 5MA를 기준으로 — 데이터 누수 회피)
    ma5_yesterday = ind.sma(df["Close"], 5).iloc[-2]
    if CFG.HARD_STOP_5MA and pd.notna(ma5_yesterday) and ma5_yesterday > 0:
        if low_today < ma5_yesterday:
            return ExitDecision(pos.code, Signal.HARD_STOP,
                                f"5MA={ma5_yesterday:.0f} 하향 돌파 (Low={low_today:.0f})",
                                exit_price_target=ma5_yesterday)

    # 2) Trailing stop
    trail_level = pos.peak_high * (1 - CFG.TRAILING_STOP_PCT)
    if low_today <= trail_level and pos.holding_days >= 1:
        return ExitDecision(pos.code, Signal.TRAILING_STOP,
                            f"peak={pos.peak_high:.0f} - {CFG.TRAILING_STOP_PCT*100:.0f}% = {trail_level:.0f} 이탈",
                            exit_price_target=trail_level)

    # 3) Time cut
    if pos.holding_days >= CFG.MAX_HOLDING_DAYS:
        return ExitDecision(pos.code, Signal.TIME_CUT,
                            f"{CFG.MAX_HOLDING_DAYS}일 보유 한도 도달",
                            exit_price_target=close_today)

    return ExitDecision(pos.code, Signal.HOLD, "holding", exit_price_target=None)
