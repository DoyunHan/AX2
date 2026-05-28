"""
키움 OpenAPI+ 어댑터 — 전략 코드를 키움 TR/실시간 데이터에 연결.

이 모듈은 실제 KiwoomOCX 인스턴스에 의존한다. plan.md Phase 1 (키움 계정/
OpenAPI+ 설치) 후 Windows 환경에서만 동작.

테스트 환경에서는 MockKiwoomAdapter 를 대신 사용.
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
        """OPT10081 일봉 차트. 컬럼: Date/Open/High/Low/Close/Volume/Amount."""
        ...

    def get_minute_chart(self, code: str, interval: int = 1, count: int = 240) -> pd.DataFrame:
        """OPT10080 분봉 차트. interval=1/3/5/10/15/30."""
        ...

    def get_orderbook(self, code: str) -> dict:
        """OPT10004 호가창. 진입 슬리피지 확인용."""
        ...

    def send_buy_market(self, code: str, qty: int) -> str:
        """시장가 매수 (시장가 = 호가구분 03). 반환: 주문번호."""
        ...

    def send_sell_market(self, code: str, qty: int) -> str:
        ...


# ============================================================================
# 실제 키움 어댑터 (PyQt5 OCX 의존) — production
# ============================================================================

class KiwoomAdapter:
    """
    실제 KiwoomOCX 인스턴스를 감싸는 어댑터.

    pip install pyqt5
    + OpenAPI+ 설치 (Windows 전용, 키움증권 계좌 필수)
    + KOA Studio 로 TR 코드 학습 권장.

    스레딩 주의: PyQt5 이벤트 루프가 메인 스레드여야 한다.
    초당 5회 TR 제한, 시간당 1,000회 제한 준수 필요.
    """

    def __init__(self, ocx):
        # ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1") 인스턴스
        self.ocx = ocx
        self._screen_no_counter = 5000

    def _next_screen_no(self) -> str:
        self._screen_no_counter = (self._screen_no_counter + 1) % 10_000
        return str(max(self._screen_no_counter, 1000))

    def get_login_account(self) -> str:
        return self.ocx.dynamicCall("GetLoginInfo(QString)", "ACCNO").split(";")[0]

    def get_account_balance(self) -> float:
        # OPW00018 또는 OPW00001 호출 필요. 상세 구현은 키움 TR 명세 참조.
        raise NotImplementedError("Implement with OPW00018 TR call")

    def get_universe_amount_top(self, n: int = 50) -> list[str]:
        # 권장: HTS 조건검색에 "거래대금 상위 50" 등록 후 SendCondition 호출
        # 또는: 거래소별 전 종목 OPT10009 결과 정렬
        raise NotImplementedError("Implement via SendCondition or OPT10009 loop")

    def get_daily_chart(self, code: str, days: int = 60) -> pd.DataFrame:
        # OPT10081 호출 → GetCommData 로 행 추출
        raise NotImplementedError("Implement OPT10081 wrapper")

    def get_minute_chart(self, code: str, interval: int = 1, count: int = 240) -> pd.DataFrame:
        # OPT10080 호출. interval 은 분단위.
        raise NotImplementedError("Implement OPT10080 wrapper")

    def get_orderbook(self, code: str) -> dict:
        raise NotImplementedError("Implement OPT10004 wrapper")

    def send_buy_market(self, code: str, qty: int) -> str:
        # SendOrder("매수주문", screen_no, account, 1, code, qty, 0, "03", "")
        account = self.get_login_account()
        ret = self.ocx.dynamicCall(
            "SendOrder(QString,QString,QString,int,QString,int,int,QString,QString)",
            ["BUY_M", self._next_screen_no(), account, 1, code, qty, 0, "03", ""],
        )
        return str(ret)

    def send_sell_market(self, code: str, qty: int) -> str:
        account = self.get_login_account()
        ret = self.ocx.dynamicCall(
            "SendOrder(QString,QString,QString,int,QString,int,int,QString,QString)",
            ["SELL_M", self._next_screen_no(), account, 2, code, qty, 0, "03", ""],
        )
        return str(ret)


# ============================================================================
# Mock 어댑터 — 테스트/시뮬레이션용
# ============================================================================

class MockKiwoomAdapter:
    """
    파일에 저장된 일봉 데이터로 키움을 흉내내는 mock.
    pytest 및 plan.md Phase 5 백테스팅 통합 테스트에서 사용.
    """

    def __init__(self, daily_panels: dict[str, pd.DataFrame], snapshot_dir: str | None = None):
        self.panels = daily_panels
        self.snapshot_dir = snapshot_dir
        self.orders_log: list[dict] = []
        self.current_date: datetime | None = None

    def get_login_account(self) -> str:
        return "MOCK1234"

    def get_account_balance(self) -> float:
        return 10_000_000.0

    def get_universe_amount_top(self, n: int = 50) -> list[str]:
        # 현재 날짜의 거래대금 상위 추출
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
