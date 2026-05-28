"""
포지션 사이징 — 마하세븐 명세의 자금 관리 룰.

  - 50% 룰: 총 예수금의 50%는 항상 현금 (lockdown)
  - 진입당 사용 자본의 20% (5종목 동시 보유 한도)
  - 모든 매수 금액은 호가단위·수량 단위로 내림 적용
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config.machaseven import CFG


@dataclass
class Portfolio:
    """
    현재 보유 종목과 가용 자본 추적.
    Kiwoom OPW00018 (계좌평가현황요청) 결과로 동기화 가능.
    """
    total_capital: float                # 총 예수금
    open_positions: dict = field(default_factory=dict)  # code -> qty

    @property
    def cash_reserve(self) -> float:
        """현금 락다운(절대 손대지 않음)."""
        return self.total_capital * CFG.CASH_RESERVE_PCT

    @property
    def tradable_capital(self) -> float:
        """매매에 쓸 수 있는 자본."""
        return self.total_capital * (1 - CFG.CASH_RESERVE_PCT)

    @property
    def num_open(self) -> int:
        return len(self.open_positions)

    def can_open_new(self) -> bool:
        return self.num_open < CFG.MAX_CONCURRENT_POSITIONS

    def size_for_entry(self, price: float) -> int:
        """
        진입 시 매수 수량.
        가용 자본 × position_pct / 진입가 → 정수 내림.
        """
        if not self.can_open_new():
            return 0
        if price <= 0:
            return 0
        budget = self.tradable_capital * CFG.POSITION_PCT_PER_TRADE
        qty = int(budget // price)
        return max(qty, 0)
