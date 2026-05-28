"""
마하세븐 포식자 시스템 — 메인 실행 루프.

Production:
    1) PyQt5 QApplication 안에서 KiwoomAdapter 인스턴스 생성
    2) 로그인 후 trading_loop() 호출
    3) 실시간 데이터는 OnReceiveRealData 콜백으로 들어옴
       → on_realtime_update() 가 청산 신호를 매 봉마다 평가

테스트:
    MockKiwoomAdapter + 일봉 패널로 시뮬레이션 실행 가능
    (테스트 코드는 별도)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from .api.kiwoom_adapter import KiwoomAdapterProto
from .config.machaseven import CFG
from .risk.daily_limit import DailyLimitGuard
from .risk.position import Portfolio
from .strategy.machaseven_breakout import (
    Position, Signal, check_entry, check_exit,
)

logger = logging.getLogger(__name__)


class MachasevenBot:

    def __init__(self, adapter: KiwoomAdapterProto):
        self.adapter = adapter
        balance = self.adapter.get_account_balance()
        self.portfolio = Portfolio(total_capital=balance)
        self.guard = DailyLimitGuard(capital=balance)
        self.positions: dict[str, Position] = {}
        self.entry_dates: dict[str, date] = {}

    # ------------------------------------------------------------------
    # 진입 스캔 — 시초가 매매 시 09:00 직후 1회 실행
    # ------------------------------------------------------------------
    def scan_entries(self, today: date):
        if not self.guard.can_enter(today):
            logger.info("Daily loss limit hit — skipping entry scan. %s",
                        self.guard.status(today))
            return
        if not self.portfolio.can_open_new():
            logger.info("Max concurrent positions reached (%d)",
                        self.portfolio.num_open)
            return

        # 1) Universe: 거래대금 상위 50
        universe = self.adapter.get_universe_amount_top(CFG.AMOUNT_TOP_N)
        logger.info("Universe: %d stocks", len(universe))

        for code in universe:
            if code in self.positions:
                continue
            df = self.adapter.get_daily_chart(code, days=60)
            if df.empty:
                continue
            decision = check_entry(df, code, in_amount_universe=True)
            if decision.signal != Signal.BUY:
                continue

            ref_price = decision.price_ref
            qty = self.portfolio.size_for_entry(ref_price)
            if qty <= 0:
                logger.info("[%s] BUY signal but qty=0 (capital/slot full)", code)
                continue
            order_id = self.adapter.send_buy_market(code, qty)
            logger.info("[%s] BUY %d shares (ref=%.0f) order=%s reason=%s",
                        code, qty, ref_price, order_id, decision.reason)
            # 체결 후 콜백에서 진입가 확정 — 여기서는 ref_price 로 임시 등록
            self.positions[code] = Position(
                code=code, entry_date=today, entry_price=ref_price,
                peak_high=ref_price, holding_days=0,
            )
            self.portfolio.open_positions[code] = qty

            if not self.portfolio.can_open_new():
                break

    # ------------------------------------------------------------------
    # 청산 평가 — 보유 종목마다 매 봉(또는 일봉 종가)마다 호출
    # ------------------------------------------------------------------
    def check_exits(self, today: date):
        for code, pos in list(self.positions.items()):
            df = self.adapter.get_daily_chart(code, days=30)
            if df.empty:
                continue
            decision = check_exit(df, pos)
            pos.holding_days += 1  # 일봉 모드에서는 일자별 호출이므로 매번 1 증가

            if decision.signal == Signal.HOLD:
                continue

            qty = self.portfolio.open_positions.get(code, 0)
            if qty <= 0:
                continue
            order_id = self.adapter.send_sell_market(code, qty)
            exit_px = decision.exit_price_target if decision.exit_price_target is not None else float(df["Close"].iloc[-1])
            realized_pnl = (exit_px - pos.entry_price) * qty
            self.guard.record_pnl(today, realized_pnl)
            logger.info("[%s] SELL %d shares signal=%s reason=%s order=%s pnl=%+.0f",
                        code, qty, decision.signal.value, decision.reason,
                        order_id, realized_pnl)
            del self.positions[code]
            del self.portfolio.open_positions[code]

    # ------------------------------------------------------------------
    # 메인 루프 (일봉 모드)
    # ------------------------------------------------------------------
    def run_one_day(self, today: date):
        """
        하루의 실행 순서:
          09:00  시가 직후    : scan_entries (전일 종가 기준 신호 → 시초가 진입)
          09:00~15:30 매 봉   : check_exits (실시간 트레일링/하드스탑)
          15:30  종가 마감 직후: check_exits (타임컷)
        """
        logger.info("=== %s ===", today)
        self.scan_entries(today)
        # 일봉 모드에서는 종가 후 한 번만 청산 평가
        self.check_exits(today)
        logger.info("End of day: positions=%d, %s",
                    self.portfolio.num_open, self.guard.status(today))


# ============================================================================
# Entrypoint
# ============================================================================

def main():
    """
    Production 진입점.

    Windows + 키움 OpenAPI+ 설치 환경에서만 실행 가능.
    """
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QAxContainer import QAxWidget
    import sys

    app = QApplication(sys.argv)
    ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")

    # CommConnect 로그인 (이벤트 루프 진입은 별도 구현 필요)
    ocx.dynamicCall("CommConnect()")
    # 실제로는 OnEventConnect 콜백을 기다려야 함 — 생략

    from .api.kiwoom_adapter import KiwoomAdapter
    adapter = KiwoomAdapter(ocx)
    bot = MachasevenBot(adapter)
    bot.run_one_day(date.today())

    sys.exit(app.exec_())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    main()
