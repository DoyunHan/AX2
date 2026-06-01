"""
키움 OpenAPI+ 실 어댑터 (Production).

⚠️  본 파일의 모든 메서드는 Windows 32-bit Python + 키움 OpenAPI+ OCX 환경에서만
   동작한다. sandbox 또는 Linux/Mac 에서는 import 시도조차 실패할 수 있음
   (PyQt5.QAxContainer 모듈은 Windows 전용).

설계 원칙:
  - TR 호출은 모두 QEventLoop 로 동기화 → 호출자 입장에서 blocking
  - TRRateLimiter 로 5/s, 1000/h 준수
  - 파싱 로직은 _parse_* 메서드로 분리 → unit test 가능
  - 필드명은 KOA Studio 명세 기준. 변경 시 SETUP.md §5 참고.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from itertools import count
from typing import Optional

import pandas as pd

from ..utils.rate_limiter import TRRateLimiter
from .kiwoom_adapter import KiwoomAdapterProto

logger = logging.getLogger(__name__)


# ============================================================================
# Error codes (키움 공식 매뉴얼)
# ============================================================================

KIWOOM_ERROR_CODES: dict[int, str] = {
    0: "정상",
    -10: "실패",
    -100: "사용자 정보교환 실패",
    -101: "서버 접속 실패",
    -102: "버전처리 실패",
    -103: "개인방화벽 실패",
    -104: "메모리 보호실패",
    -106: "통신 단절",
    -200: "시세조회 과부하",
    -201: "전문작성 초기화 실패",
    -202: "전문작성 입력값 오류",
    -300: "주문 입력값 오류",
    -301: "계좌비밀번호 없음",
    -302: "타인 계좌 사용오류",
    -303: "주문가격이 20억원 초과",
    -304: "주문가격이 50억원 초과",
    -305: "주문 수량이 총발행주식수의 1% 초과",
    -306: "주문 수량은 총발행주식수의 3% 초과",
    -307: "주문 전송 실패",
    -308: "주문 전송 과부하",
    -309: "주문 수량 300계약 초과",
    -310: "주문 수량 500계약 초과",
    -340: "계좌정보 없음",
    -500: "종목코드 없음",
}


def kiwoom_err_msg(code: int) -> str:
    return KIWOOM_ERROR_CODES.get(code, f"unknown error ({code})")


# ============================================================================
# Helpers
# ============================================================================

def _safe_int(s: str, default: int = 0) -> int:
    """키움 응답은 종종 부호 포함 (+/-) → strip 후 int."""
    s = s.strip().replace("+", "").replace(",", "")
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return default


def _safe_float(s: str, default: float = 0.0) -> float:
    s = s.strip().replace("+", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return default


def _parse_yyyymmdd(s: str) -> Optional[datetime]:
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y%m%d")
    except ValueError:
        return None


def _parse_yyyymmddhhmmss(s: str) -> Optional[datetime]:
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S")
    except ValueError:
        return None


# ============================================================================
# TR 응답 파서 — 키움 OCX 없이도 단위 테스트 가능하도록 별도 함수로 분리
# ============================================================================

def parse_daily_chart_rows(rows: list[dict]) -> pd.DataFrame:
    """
    OPT10081 (주식일봉차트) 응답 행을 DataFrame 으로 변환.

    rows: [{"일자": "20260527", "시가": "188200", "고가": "189700", ...}, ...]
    Returns: DataFrame index=Date, cols=Open,High,Low,Close,Volume,Amount
    """
    parsed = []
    for r in rows:
        dt = _parse_yyyymmdd(r.get("일자", ""))
        if dt is None:
            continue
        parsed.append({
            "Date": dt,
            "Open": abs(_safe_float(r.get("시가", "0"))),
            "High": abs(_safe_float(r.get("고가", "0"))),
            "Low": abs(_safe_float(r.get("저가", "0"))),
            "Close": abs(_safe_float(r.get("현재가", "0"))),
            "Volume": _safe_float(r.get("거래량", "0")),
            "Amount": _safe_float(r.get("거래대금", "0")),
        })
    if not parsed:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Amount"])
    df = pd.DataFrame(parsed).set_index("Date").sort_index()
    return df


def parse_minute_chart_rows(rows: list[dict]) -> pd.DataFrame:
    """
    OPT10080 (주식분봉차트) 응답 행을 DataFrame 으로 변환.
    """
    parsed = []
    for r in rows:
        dt = _parse_yyyymmddhhmmss(r.get("체결시간", ""))
        if dt is None:
            continue
        parsed.append({
            "Timestamp": dt,
            "Open": abs(_safe_float(r.get("시가", "0"))),
            "High": abs(_safe_float(r.get("고가", "0"))),
            "Low": abs(_safe_float(r.get("저가", "0"))),
            "Close": abs(_safe_float(r.get("현재가", "0"))),
            "Volume": _safe_float(r.get("거래량", "0")),
        })
    if not parsed:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(parsed).set_index("Timestamp").sort_index()
    # Amount 는 OPT10080 에 없음 → Close × Volume 로 근사
    df["Amount"] = df["Close"] * df["Volume"]
    return df


def parse_orderbook_row(row: dict) -> dict:
    """
    OPT10004 (주식호가) 응답 (단일 행) → 표준화된 dict.

    매도1~10 (위에서 아래 = 매도 1호가가 best ask),
    매수1~10 (위에서 아래 = 매수 1호가가 best bid).
    """
    bids = []
    asks = []
    for i in range(1, 11):
        ap = abs(_safe_int(row.get(f"매도호가{i}", "0")))
        av = _safe_int(row.get(f"매도호가수량{i}", "0"))
        bp = abs(_safe_int(row.get(f"매수호가{i}", "0")))
        bv = _safe_int(row.get(f"매수호가수량{i}", "0"))
        if ap > 0:
            asks.append((ap, av))
        if bp > 0:
            bids.append((bp, bv))
    total_ask_vol = _safe_int(row.get("총매도잔량", "0"))
    total_bid_vol = _safe_int(row.get("총매수잔량", "0"))
    buy_strength = (
        total_bid_vol / (total_bid_vol + total_ask_vol) * 100
        if (total_bid_vol + total_ask_vol) > 0 else 50.0
    )
    return {
        "bids": bids, "asks": asks,
        "best_bid": bids[0][0] if bids else None,
        "best_ask": asks[0][0] if asks else None,
        "total_bid_vol": total_bid_vol,
        "total_ask_vol": total_ask_vol,
        "buy_strength_pct": buy_strength,
    }


def parse_account_eval(row: dict) -> dict:
    """
    OPW00018 (계좌평가현황) single row 응답 파싱.
    """
    return {
        "total_buy": _safe_int(row.get("총매입금액", "0")),
        "total_eval": _safe_int(row.get("총평가금액", "0")),
        "total_pnl": _safe_int(row.get("총평가손익금액", "0")),
        "total_return_pct": _safe_float(row.get("총수익률(%)", "0")),
        "estimated_assets": _safe_int(row.get("추정예탁자산", "0")),
    }


# ============================================================================
# 실 KiwoomAdapter
# ============================================================================

class KiwoomAdapter(KiwoomAdapterProto):
    """
    Windows 32-bit Python + PyQt5 + Kiwoom OCX 환경 전용.

    사용 패턴:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QAxContainer import QAxWidget
        app = QApplication(sys.argv)
        ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        adapter = KiwoomAdapter(ocx)
        adapter.connect()              # 로그인 (blocking)
        df = adapter.get_daily_chart("005930", days=60)
    """

    def __init__(self, ocx, condition_name_amount_top: str = "거래대금상위50"):
        """
        ocx: QAxWidget("KHOPENAPI.KHOpenAPICtrl.1") 인스턴스
        condition_name_amount_top: HTS 에 등록된 조건검색 이름.
            (사전에 영웅문에서 "거래대금 상위 50" 조건을 저장해야 함)
        """
        self.ocx = ocx
        self.rate = TRRateLimiter()
        self._screen_no_iter = count(5000)
        self._tr_data: dict = {}      # rq_name → parsed rows
        self._tr_loop = None          # QEventLoop (lazily created)
        self._cond_name = condition_name_amount_top
        self._cond_codes: list[str] = []
        self._cond_loop = None
        self._account_no_cache: Optional[str] = None
        self._connected = False

        # Bind callbacks
        self.ocx.OnEventConnect.connect(self._on_event_connect)
        self.ocx.OnReceiveTrData.connect(self._on_receive_tr_data)
        self.ocx.OnReceiveTrCondition.connect(self._on_receive_tr_condition)

    # ------------------------------------------------------------------
    # Connection / login
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        로그인. PyQt5 QEventLoop 로 동기화. 성공 시 True.
        """
        from PyQt5.QtCore import QEventLoop
        loop = QEventLoop()
        self._connect_loop = loop
        ret = self.ocx.dynamicCall("CommConnect()")
        if ret != 0:
            logger.error("CommConnect returned %d: %s", ret, kiwoom_err_msg(ret))
            return False
        loop.exec_()
        return self._connected

    def _on_event_connect(self, err_code: int):
        if err_code == 0:
            self._connected = True
            logger.info("Logged in to Kiwoom OpenAPI+")
        else:
            self._connected = False
            logger.error("Login failed: %s", kiwoom_err_msg(err_code))
        if hasattr(self, "_connect_loop") and self._connect_loop is not None:
            self._connect_loop.exit()

    def get_login_account(self) -> str:
        if self._account_no_cache:
            return self._account_no_cache
        raw = self.ocx.dynamicCall("GetLoginInfo(QString)", "ACCNO")
        first = raw.split(";")[0] if raw else ""
        self._account_no_cache = first
        return first

    def _next_screen_no(self) -> str:
        return str((next(self._screen_no_iter) % 9000) + 1000)

    # ------------------------------------------------------------------
    # TR helpers
    # ------------------------------------------------------------------

    def _call_tr(self, tr_code: str, rq_name: str,
                 inputs: dict[str, str],
                 fields_single: list[str] | None = None,
                 fields_multi: list[str] | None = None,
                 prev_next: int = 0,
                 timeout_ms: int = 5000) -> tuple[list[dict], dict, str]:
        """
        TR 호출 + 동기 응답 대기. 반환:
          - rows: 반복 데이터 (multi)
          - single: 단일 응답 필드 dict
          - next_flag: "2" 면 연속조회 필요, "" 면 끝
        """
        from PyQt5.QtCore import QEventLoop, QTimer
        self.rate.wait()

        # 입력값 설정
        for k, v in inputs.items():
            self.ocx.dynamicCall("SetInputValue(QString, QString)", k, v)

        # 콜백 결과를 받을 슬롯 준비
        self._tr_data[rq_name] = {
            "tr_code": tr_code,
            "fields_single": fields_single or [],
            "fields_multi": fields_multi or [],
            "rows": [],
            "single": {},
            "next_flag": "",
            "received": False,
        }

        loop = QEventLoop()
        self._tr_loop = (rq_name, loop)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(timeout_ms)

        scr = self._next_screen_no()
        ret = self.ocx.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            rq_name, tr_code, prev_next, scr,
        )
        if ret != 0:
            logger.error("CommRqData(%s) failed: %s", tr_code, kiwoom_err_msg(ret))
            self._tr_loop = None
            return [], {}, ""

        loop.exec_()
        self._tr_loop = None
        info = self._tr_data.pop(rq_name, None)
        if info is None or not info["received"]:
            logger.warning("TR %s timeout or no data", tr_code)
            return [], {}, ""
        return info["rows"], info["single"], info["next_flag"]

    def _on_receive_tr_data(self, scr_no, rq_name, tr_code,
                            record_name, prev_next):
        info = self._tr_data.get(rq_name)
        if info is None:
            return
        # Single fields
        for fname in info["fields_single"]:
            v = self.ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                tr_code, rq_name, 0, fname,
            )
            info["single"][fname] = v
        # Multi fields
        if info["fields_multi"]:
            count = self.ocx.dynamicCall(
                "GetRepeatCnt(QString, QString)", tr_code, rq_name,
            )
            for i in range(count):
                row = {}
                for fname in info["fields_multi"]:
                    v = self.ocx.dynamicCall(
                        "GetCommData(QString, QString, int, QString)",
                        tr_code, rq_name, i, fname,
                    )
                    row[fname] = v
                info["rows"].append(row)
        info["next_flag"] = str(prev_next or "")
        info["received"] = True
        if self._tr_loop and self._tr_loop[0] == rq_name:
            self._tr_loop[1].exit()

    # ------------------------------------------------------------------
    # OPT10081 — 일봉
    # ------------------------------------------------------------------

    def get_daily_chart(self, code: str, days: int = 60) -> pd.DataFrame:
        """
        OPT10081 주식일봉차트조회. 최신부터 역순.
        days < 600 이면 단일 호출, 그 이상은 prev_next 로 연속.
        """
        today = datetime.now().strftime("%Y%m%d")
        fields_multi = ["일자", "시가", "고가", "저가", "현재가", "거래량", "거래대금"]
        all_rows: list[dict] = []
        prev_next = 0
        while len(all_rows) < days:
            rows, _, nflag = self._call_tr(
                tr_code="OPT10081",
                rq_name="주식일봉차트조회",
                inputs={
                    "종목코드": code,
                    "기준일자": today,
                    "수정주가구분": "1",
                },
                fields_multi=fields_multi,
                prev_next=prev_next,
            )
            if not rows:
                break
            all_rows.extend(rows)
            if nflag != "2":
                break
            prev_next = 2
        df = parse_daily_chart_rows(all_rows[:days])
        return df

    # ------------------------------------------------------------------
    # OPT10080 — 분봉
    # ------------------------------------------------------------------

    def get_minute_chart(self, code: str, interval: int = 1,
                         count: int = 240) -> pd.DataFrame:
        """
        OPT10080 주식분봉차트조회. interval=1/3/5/10/15/30/60(분).
        """
        fields_multi = ["체결시간", "시가", "고가", "저가", "현재가", "거래량"]
        all_rows: list[dict] = []
        prev_next = 0
        while len(all_rows) < count:
            rows, _, nflag = self._call_tr(
                tr_code="OPT10080",
                rq_name="주식분봉차트조회",
                inputs={
                    "종목코드": code,
                    "틱범위": str(interval),
                    "수정주가구분": "1",
                },
                fields_multi=fields_multi,
                prev_next=prev_next,
            )
            if not rows:
                break
            all_rows.extend(rows)
            if nflag != "2":
                break
            prev_next = 2
        df = parse_minute_chart_rows(all_rows[:count])
        return df

    # ------------------------------------------------------------------
    # OPT10004 — 호가창
    # ------------------------------------------------------------------

    def get_orderbook(self, code: str) -> dict:
        fields_single = []
        for i in range(1, 11):
            fields_single += [
                f"매도호가{i}", f"매도호가수량{i}",
                f"매수호가{i}", f"매수호가수량{i}",
            ]
        fields_single += ["총매도잔량", "총매수잔량"]
        _, single, _ = self._call_tr(
            tr_code="OPT10004",
            rq_name="주식호가요청",
            inputs={"종목코드": code},
            fields_single=fields_single,
        )
        return parse_orderbook_row(single)

    # ------------------------------------------------------------------
    # OPW00018 — 계좌평가현황
    # ------------------------------------------------------------------

    def get_account_balance(self) -> float:
        """
        총 예탁자산을 float 로 반환. 종목별 명세는 .get_account_detail() 참고.
        """
        info = self.get_account_detail()
        return float(info.get("estimated_assets", 0))

    def get_account_detail(self) -> dict:
        account = self.get_login_account()
        fields_single = ["총매입금액", "총평가금액", "총평가손익금액",
                         "총수익률(%)", "추정예탁자산"]
        _, single, _ = self._call_tr(
            tr_code="OPW00018",
            rq_name="계좌평가현황요청",
            inputs={
                "계좌번호": account,
                "비밀번호": "",
                "비밀번호입력매체구분": "00",
                "조회구분": "1",
            },
            fields_single=fields_single,
        )
        return parse_account_eval(single)

    # ------------------------------------------------------------------
    # 조건검색 — 거래대금 상위 universe
    # ------------------------------------------------------------------

    def get_universe_amount_top(self, n: int = 50) -> list[str]:
        """
        HTS 에 등록된 조건검색 (self._cond_name) 으로 universe 조회.

        사전 준비:
          영웅문 → "조건검색" → 신규 조건 → "거래대금 상위 50" 식으로 등록.
          본 어댑터의 condition_name_amount_top 인자와 일치해야 함.

        제한: 조건검색은 1분에 1회만 호출 가능. 자주 부르면 차단.
        """
        from PyQt5.QtCore import QEventLoop, QTimer
        # 1) 조건식 목록 로드 (최초 1회)
        if not hasattr(self, "_cond_loaded"):
            ret = self.ocx.dynamicCall("GetConditionLoad()")
            if ret != 1:
                logger.error("GetConditionLoad failed")
                return []
            # OnReceiveConditionVer 콜백을 기다려야 함 — 간단히 짧은 대기로 처리
            # 정밀하게는 OnReceiveConditionVer 도 시그널 바인딩 필요
            import time as _t
            _t.sleep(0.8)
            self._cond_loaded = True

        # 2) 조건식 이름 → 인덱스 매핑
        cond_list_raw = self.ocx.dynamicCall("GetConditionNameList()")
        # 형식: "0^조건1;1^조건2;..."
        cond_map = {}
        for item in cond_list_raw.split(";"):
            if "^" in item:
                idx, name = item.split("^", 1)
                cond_map[name] = int(idx)
        cond_idx = cond_map.get(self._cond_name)
        if cond_idx is None:
            logger.error("Condition '%s' not registered in HTS",
                         self._cond_name)
            return []

        # 3) 조건검색 호출
        self._cond_codes = []
        loop = QEventLoop()
        self._cond_loop = loop
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timeout.start(5000)
        scr = self._next_screen_no()
        ret = self.ocx.dynamicCall(
            "SendCondition(QString, QString, int, int)",
            scr, self._cond_name, cond_idx, 0,
        )
        if ret != 1:
            logger.error("SendCondition failed")
            return []
        loop.exec_()
        self._cond_loop = None
        return self._cond_codes[:n]

    def _on_receive_tr_condition(self, scr_no, code_list, cond_name,
                                  cond_idx, prev_next):
        # code_list: "005930;000660;035720;..." (세미콜론 구분, 마지막 ; 가능)
        codes = [c for c in code_list.split(";") if c]
        self._cond_codes = codes
        if self._cond_loop:
            self._cond_loop.exit()

    # ------------------------------------------------------------------
    # 주문 — SendOrder
    # ------------------------------------------------------------------

    def send_buy_market(self, code: str, qty: int) -> str:
        return self._send_order(code, qty, side="buy", order_type="market")

    def send_sell_market(self, code: str, qty: int) -> str:
        return self._send_order(code, qty, side="sell", order_type="market")

    def send_buy_limit(self, code: str, qty: int, price: int) -> str:
        return self._send_order(code, qty, side="buy",
                                order_type="limit", price=price)

    def send_sell_limit(self, code: str, qty: int, price: int) -> str:
        return self._send_order(code, qty, side="sell",
                                order_type="limit", price=price)

    def _send_order(self, code: str, qty: int, side: str,
                    order_type: str, price: int = 0) -> str:
        """
        SendOrder(rqName, scrNo, accNo, orderType, code, qty, price, hogaGubun, origOrderNo)

        orderType: 1=신규매수, 2=신규매도, 3=매수취소, 4=매도취소, 5=매수정정, 6=매도정정
        hogaGubun: "00"=지정가, "03"=시장가, "05"=조건부지정가 등
        """
        self.rate.wait()
        account = self.get_login_account()
        ot = {"buy": 1, "sell": 2}[side]
        hoga = {"market": "03", "limit": "00"}[order_type]
        rq_name = f"{side.upper()}_{order_type.upper()}_{code}"
        scr = self._next_screen_no()
        ret = self.ocx.dynamicCall(
            "SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
            [rq_name, scr, account, ot, code, int(qty), int(price), hoga, ""],
        )
        if ret != 0:
            logger.error("SendOrder(%s %s qty=%d) failed: %s",
                         side, code, qty, kiwoom_err_msg(ret))
            return f"ERROR_{ret}"
        logger.info("SendOrder OK: %s %s qty=%d price=%d", side, code, qty, price)
        return f"OK_{rq_name}"
