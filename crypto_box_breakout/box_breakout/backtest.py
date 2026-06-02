"""
백테스트 엔진.

모델링 항목
  - 양방향(롱/숏), 단일 포지션(동시 1개) 단순화
  - 진입: 돌파봉 '종가'에서 체결 (봉 마감 확정값)
  - 초기 손절: 박스 반대편 경계 (돌파 실패 = 박스 복귀)
  - 추세 홀딩: ATR 트레일링(샹들리에 방식). 스탑은 절대 후퇴하지 않음
  - 청산: 봉의 고/저가 트레일링 스탑 터치 시 스탑가에 체결
  - 비용: taker 수수료(진입+청산), 무기한 펀딩비(8시간 주기)
  - 레버리지: 명목 = min(리스크기반 수량, 증거금*레버리지), 청산가 안전장치 포함
  - 포지션 사이징: 손절거리 기반 (자본의 risk_per_trade 만큼만 손실 노출)

룩어헤드 방지: 진입은 종가, 청산은 진입 '다음 봉'부터 고/저로 판정한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .strategy import StrategyConfig, generate_signals


@dataclass
class BacktestConfig:
    initial_equity: float = 10_000.0
    leverage: float = 3.0
    risk_per_trade: float = 0.01      # 1회 거래 리스크 = 자본의 1%
    taker_fee: float = 0.0005         # 0.05% (Binance USD-M taker 기본)
    funding_rate: float = 0.0001      # 8시간당 0.01% (평균 가정, 추세 방향이 비용 부담)
    funding_interval_hours: int = 8
    # 손절가가 강제청산가에 너무 가까우면 진입 스킵 (청산 버퍼)
    liquidation_buffer: float = 0.5   # 손절거리 < (청산거리 * buffer) 면 OK


@dataclass
class Trade:
    side: str            # 'long' or 'short'
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    qty: float
    notional: float
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float
    bars_held: int
    exit_reason: str
    equity_after: float


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    final_equity: float = 0.0


class Backtester:
    def __init__(self, strat_cfg: StrategyConfig, bt_cfg: BacktestConfig):
        self.s = strat_cfg
        self.b = bt_cfg

    # ---- 헬퍼 ----
    def _funding_events(self, t0: pd.Timestamp, t1: pd.Timestamp) -> int:
        """[t0, t1] 사이에 지나간 펀딩 정산 시각(UTC 00/08/16시) 횟수."""
        h = self.b.funding_interval_hours
        # t0 이후 첫 정산시각부터 t1까지 카운트
        start = t0.ceil(f"{h}h")
        if start <= t0:
            start = start + pd.Timedelta(hours=h)
        if start > t1:
            return 0
        return int((t1 - start) / pd.Timedelta(hours=h)) + 1

    def run(self, df: pd.DataFrame) -> BacktestResult:
        s, b = self.s, self.b
        data = generate_signals(df, s).reset_index(drop=True)

        equity = b.initial_equity
        trades: list[Trade] = []
        eq_times: list[pd.Timestamp] = []
        eq_values: list[float] = []

        in_pos = False
        side = ""
        entry_price = entry_time = qty = notional = 0.0
        stop = 0.0
        extreme = 0.0          # 보유 중 최고가(롱)/최저가(숏)
        entry_idx = 0

        n = len(data)
        for i in range(n):
            row = data.iloc[i]
            ts = row["timestamp"]

            if in_pos:
                atr = row["atr"]
                # 1) 트레일링 스탑 갱신 (스탑은 후퇴 금지)
                if side == "long":
                    extreme = max(extreme, row["high"])
                    if not np.isnan(atr):
                        stop = max(stop, extreme - s.atr_trail_mult * atr)
                else:
                    extreme = min(extreme, row["low"])
                    if not np.isnan(atr):
                        stop = min(stop, extreme + s.atr_trail_mult * atr)

                # 2) 청산 판정 (봉 고/저가 스탑 터치)
                exit_price = None
                reason = ""
                if side == "long" and row["low"] <= stop:
                    exit_price, reason = stop, "trail_stop"
                elif side == "short" and row["high"] >= stop:
                    exit_price, reason = stop, "trail_stop"
                elif s.max_hold_bars and (i - entry_idx) >= s.max_hold_bars:
                    exit_price, reason = row["close"], "max_hold"
                elif i == n - 1:
                    exit_price, reason = row["close"], "end_of_data"

                if exit_price is not None:
                    direction = 1 if side == "long" else -1
                    gross = direction * (exit_price - entry_price) * qty
                    fees = (entry_price + exit_price) * qty * b.taker_fee
                    n_fund = self._funding_events(entry_time, ts)
                    # 펀딩: 추세 방향 포지션이 평균적으로 비용을 부담한다고 가정(보수적)
                    funding = n_fund * b.funding_rate * notional
                    net = gross - fees - funding
                    equity += net
                    trades.append(
                        Trade(
                            side=side,
                            entry_time=entry_time,
                            entry_price=entry_price,
                            exit_time=ts,
                            exit_price=exit_price,
                            qty=qty,
                            notional=notional,
                            gross_pnl=gross,
                            fees=fees,
                            funding=funding,
                            net_pnl=net,
                            bars_held=i - entry_idx,
                            exit_reason=reason,
                            equity_after=equity,
                        )
                    )
                    in_pos = False

            # 3) 신규 진입 (청산 직후 같은 봉 재진입은 금지 → 플랫일 때만)
            if not in_pos:
                go_long = bool(row["long_signal"])
                go_short = bool(row["short_signal"])
                if go_long or go_short:
                    side = "long" if go_long else "short"
                    entry_price = float(row["close"])
                    entry_time = ts
                    entry_idx = i
                    # 초기 손절 = 박스 반대편 경계
                    if side == "long":
                        init_stop = float(row["box_low"])
                    else:
                        init_stop = float(row["box_high"])
                    stop_dist = abs(entry_price - init_stop)

                    if stop_dist > 0:
                        # 청산가 안전장치: 손절거리가 강제청산 거리보다 충분히 작아야
                        liq_dist = entry_price / b.leverage  # 근사 (유지증거금 무시)
                        if stop_dist < liq_dist * b.liquidation_buffer:
                            # 리스크 기반 수량
                            risk_amount = equity * b.risk_per_trade
                            qty = risk_amount / stop_dist
                            # 증거금 한도(레버리지) 캡
                            max_notional = equity * b.leverage
                            qty = min(qty, max_notional / entry_price)
                            notional = qty * entry_price
                            stop = init_stop
                            extreme = entry_price
                            in_pos = True

            eq_times.append(ts)
            eq_values.append(equity)

        result = BacktestResult(
            trades=trades,
            equity_curve=pd.DataFrame({"timestamp": eq_times, "equity": eq_values}),
            final_equity=equity,
        )
        return result
