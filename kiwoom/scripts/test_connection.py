"""
키움 OpenAPI+ 최소 연결 테스트 스크립트.

목적: SETUP.md §6 — Phase 1 완료의 1차 검증.

실행 요구:
  - Windows 32-bit Python (3.9 또는 3.10 권장)
  - pip install pyqt5==5.15.9
  - 키움 OpenAPI+ OCX 등록 완료
  - 모의투자 계정 + OpenAPI 사용 신청 승인

사용법:
  > venv32\Scripts\activate
  > python kiwoom/scripts/test_connection.py

성공 시 출력:
  ✅ 로그인 성공
    ID: ..., Name: ..., Account(s): ..., Server: 모의 / 실

실패 시 SETUP.md §9 (자주 막히는 문제) 참고.
"""

from __future__ import annotations

import sys
import platform


def _verify_environment():
    """Python 32비트 여부, OS 검사."""
    bits = platform.architecture()[0]
    if bits != "32bit":
        print(f"❌ Python is {bits}. Must be 32-bit for Kiwoom OCX.")
        print("   See SETUP.md §4.1 for fix.")
        sys.exit(1)
    if platform.system() != "Windows":
        print(f"❌ OS is {platform.system()}. Kiwoom OpenAPI+ requires Windows.")
        sys.exit(1)
    print(f"✅ Python {sys.version.split()[0]} {bits} on {platform.system()}")


def main():
    _verify_environment()

    # PyQt5 import는 환경 검증 후에 (import 자체가 OCX 로드 시 죽을 수 있음)
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QAxContainer import QAxWidget
        from PyQt5.QtCore import QEventLoop
    except ImportError as e:
        print(f"❌ PyQt5 import failed: {e}")
        print("   Install: pip install pyqt5==5.15.9")
        sys.exit(1)

    app = QApplication(sys.argv)
    ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    login_loop = QEventLoop()

    def on_event_connect(err_code: int):
        if err_code == 0:
            print("✅ 로그인 성공")
            acc_no = ocx.dynamicCall("GetLoginInfo(QString)", "ACCNO")
            user_id = ocx.dynamicCall("GetLoginInfo(QString)", "USER_ID")
            user_name = ocx.dynamicCall("GetLoginInfo(QString)", "USER_NAME")
            server_gubun = ocx.dynamicCall("GetLoginInfo(QString)", "GetServerGubun")
            server_label = "모의" if server_gubun == "1" else "실"
            print(f"  ID:       {user_id}")
            print(f"  Name:     {user_name}")
            print(f"  Accounts: {acc_no}")
            print(f"  Server:   {server_label}")
        else:
            err_msgs = {
                -100: "사용자 정보교환 실패",
                -101: "서버 접속 실패",
                -102: "버전처리 실패",
                -106: "통신 단절",
            }
            msg = err_msgs.get(err_code, "알 수 없는 오류")
            print(f"❌ 로그인 실패 (err_code={err_code}: {msg})")
        login_loop.exit()

    ocx.OnEventConnect.connect(on_event_connect)

    print("로그인 창을 띄웁니다... (브라우저 형태)")
    ocx.dynamicCall("CommConnect()")
    login_loop.exec_()

    # 2차 검증: 간단한 종목 정보 조회 (OPT10001)
    print("\n--- OPT10001 (삼성전자 기본정보) 호출 테스트 ---")
    tr_loop = QEventLoop()
    result: dict = {}

    def on_receive_tr_data(scr_no, rq_name, tr_code, record_name, prev_next):
        if rq_name == "주식기본정보":
            name = ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                tr_code, rq_name, 0, "종목명"
            ).strip()
            price = ocx.dynamicCall(
                "GetCommData(QString, QString, int, QString)",
                tr_code, rq_name, 0, "현재가"
            ).strip()
            result["name"] = name
            result["price"] = price
        tr_loop.exit()

    ocx.OnReceiveTrData.connect(on_receive_tr_data)
    ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", "005930")
    ret = ocx.dynamicCall(
        "CommRqData(QString, QString, int, QString)",
        "주식기본정보", "OPT10001", 0, "0101"
    )
    if ret != 0:
        print(f"❌ CommRqData 실패 (ret={ret})")
        sys.exit(1)
    tr_loop.exec_()

    if result:
        print(f"✅ 응답 수신: {result.get('name')} 현재가 {result.get('price')}")
    else:
        print("❌ 응답 없음 — TR rate limit 또는 통신 오류")

    print("\n🎉 Phase 1 1차 검증 완료. plan.md Phase 2 (데이터 수집) 진행 가능.")


if __name__ == "__main__":
    main()
