"""
키움 OpenAPI+ 어댑터 — 전략 코드를 키움 TR/실시간 데이터에 연결.

본 모듈은 인터페이스(Protocol) 와 테스트용 MockKiwoomAdapter 를 제공한다.
실제 키움 OCX 어댑터는 별도 모듈 (kiwoom.api.kiwoom_real.KiwoomAdapter) 에
구현되어 있으며 Windows 32-bit Python + 키움 OpenAPI+ 환경에서만 동작.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import pandas as pd


# ============================================================================
# Interface — 전략은 이 protocol 만 의존
# ============================================================================

class KiwoomAdapterProto(Protocol):
    def get_login_account(self) -> str: ...

    def get_account_balance(self) -> float: ...

    def get_universe_amount_top(self, n: int = 50) -> list[str]:
        """당일 거래대금 상위 N개 종목 코드."""
        ...

    def get_daily_chart(self, code: str, days: int = 60) -> pd.DataFrame:
        """OPT10081 일봉 차트. 컬럼: Open/High/Low/Close/Volume/Amount."""
        ...

    def get_minute_chart(self, code: str, interval: int = 1,
                         count: int = 240) -> pd.DataFrame:
        """OPT10080 분봉 차트. interval=1/3/5/10/15/30."""
        ...

    def get_orderbook(self, code: str) -> dict:
        """OPT10004 호가창. 진입 슬리피지 확인용."""
        ...

    def send_buy_market(self, code: str, qty: int) -> str:
        """시장가 매수 (호가구분 03). 반환: 주문번호 또는 ERROR_x."""
        ...

    def send_sell_market(self, code: str, qty: int) -> str:
        ...


# ============================================================================
# 실 키움 어댑터는 kiwoom_real 모듈에서 import — Windows 외 환경에서는
# import 시도 자체가 실패할 수 있으므로 lazy import 권장.
# ============================================================================

def get_real_adapter(ocx, **kwargs):
    """
    Production 어댑터 인스턴스화.
    Windows + PyQt5 + 키움 OpenAPI+ OCX 가 셋업된 후 호출.
    """
    from .kiwoom_real import KiwoomAdapter as _Real
    return _Real(ocx, **kwargs)


# ============================================================================
# Mock 어댑터 — 테스트/시뮬레이션용 (sandbox 에서 동작)
# ============================================================================

class MockKiwoomAdapter:
    """
    파일에 저장된 일봉 데이터로 키움을 흉내내는 mock.
    sandbox 시뮬레이션, pytest, plan.md Phase 5 통합 테스트에서 사용.
    """

    def __init__(self, daily_panels: dict[str, pd.DataFrame],
                 snapshot_dir: str | None = None):
        self.panels = daily_panels
        self.snapshot_dir = snapshot_dir
        self.orders_log: list[dict] = []
        self.current_date: datetime | None = None

    def get_login_account(self) -> str:
        return "MOCK1234"

    def get_account_balance(self) -> float:
        return 10_000_000.0

    def get_universe_amount_top(self, n: int = 50) -> list[str]:
        if self.current_date is None:
            return []
        today_amounts = []
        for code, df in self.panels.items():
            if self.current_date in df.index:
                today_amounts.append((code, df.loc[self.current_date, "Amount"]))
        today_amounts.sort(key=lambda x: x[1], reverse=True)
        return [code for code, _ in today_amounts[:n]]

    def get_daily_chart(self, code: str, days: int = 60) -> pd.DataFrame:
        df = self.panels.get(code)
        if df is None:
            return pd.DataFrame()
        if self.current_date is not None:
            df = df.loc[:self.current_date]
        return df.tail(days)

    def get_minute_chart(self, *args, **kwargs):
        raise NotImplementedError("Mock does not provide minute data")

    def get_orderbook(self, code: str) -> dict:
        df = self.get_daily_chart(code, days=1)
        if df.empty:
            return {}
        last_close = float(df["Close"].iloc[-1])
        return {"매도1": last_close, "매수1": last_close - 1}

    def send_buy_market(self, code: str, qty: int) -> str:
        order_id = f"MOCK_BUY_{len(self.orders_log)}"
        self.orders_log.append({
            "order_id": order_id, "code": code, "side": "BUY", "qty": qty,
            "date": self.current_date,
        })
        return order_id

    def send_sell_market(self, code: str, qty: int) -> str:
        order_id = f"MOCK_SELL_{len(self.orders_log)}"
        self.orders_log.append({
            "order_id": order_id, "code": code, "side": "SELL", "qty": qty,
            "date": self.current_date,
        })
        return order_id
