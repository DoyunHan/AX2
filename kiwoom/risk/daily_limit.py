"""
일일 손실 한도 관리 — 보복성 매매 방지의 핵심 장치.

마하세븐 명세의 "Daily Drawdown Limit": 하루 누적 손실액이 임계치에 도달하면
당일 프로그램의 API 주문 권한을 자체 차단한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from ..config.machaseven import CFG


@dataclass
class DailyLimitGuard:
    """
    매일 자정에 reset 되는 누적 손익 트래커.

    사용:
        guard = DailyLimitGuard()
        ...
        # 청산 시
        guard.record_pnl(today, realized_pnl_pct=-0.012)
        if not guard.can_enter(today):
            # 신규 진입 차단
    """
    capital: float
    daily_pnl_ratio: float = 0.0   # 자본 대비 비율 (-0.03 = -3%)
    locked_dates: set = field(default_factory=set)
    last_reset: Optional[date] = None

    def _maybe_reset(self, today: date):
        if self.last_reset != today:
            self.daily_pnl_ratio = 0.0
            self.last_reset = today

    def record_pnl(self, today: date, realized_pnl_amount: float):
        """청산 발생 시 호출. 자본 대비 비율로 누적."""
        self._maybe_reset(today)
        self.daily_pnl_ratio += realized_pnl_amount / self.capital
        if self.daily_pnl_ratio <= CFG.DAILY_LOSS_LIMIT:
            self.locked_dates.add(today)

    def can_enter(self, today: date) -> bool:
        """신규 진입 가능 여부."""
        self._maybe_reset(today)
        if today in self.locked_dates:
            return False
        if self.daily_pnl_ratio <= CFG.DAILY_LOSS_LIMIT:
            self.locked_dates.add(today)
            return False
        return True

    def status(self, today: date) -> str:
        self._maybe_reset(today)
        locked = today in self.locked_dates
        return (f"daily_pnl={self.daily_pnl_ratio*100:+.2f}% "
                f"limit={CFG.DAILY_LOSS_LIMIT*100:.1f}% "
                f"locked={locked}")
