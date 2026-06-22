# 키움 OpenAPI+ 셋업 가이드 (plan.md Phase 1)

> 마하세븐 포식자 시스템을 실 계좌로 운영하기 위한 환경 구성 가이드.
> 본 문서는 plan.md Phase 1 ("기반 구축") 의 체크리스트를 실제 단계로 풀어 쓴 것.
>
> 결론: 키움 OpenAPI+ 는 **Windows 32-bit Python + PyQt5 + 키움 OCX** 의 까다로운
> 조합을 요구한다. 한 번 셋업이 끝나면 안정적이지만, 첫 설치에서 잡혀야 할
> 함정이 많다.

---

## 1. 사전 준비물

| 항목 | 비고 |
|------|------|
| Windows 10/11 PC | OpenAPI+ OCX 는 Windows 전용 (Linux/Mac 미지원) |
| 키움증권 계좌 | 비대면 개설 가능, 신분증·휴대폰 필요 |
| 본인 명의 휴대폰 | OTP 발급용 |
| 인터넷 + 안정 전원 | 매매 중 끊김 = 손실 위험 |
| 모의투자 계정 (선택) | 실전 투입 전 필수 |

**시간 견적**: 계좌 개설 30분 → API 신청 1~2일 승인 대기 → 환경 셋업 1~2시간.

---

## 2. 계좌 개설 (비대면)

### 2.1 키움증권 모바일 앱(영웅문S#) 설치
- Play Store / App Store 에서 "키움증권" 검색
- "비대면 계좌개설" 선택 → 신분증 촬영 → 본인인증

### 2.2 모의투자 계정 (강력 권장)
- 영웅문S# → "모의투자" → 신청
- **실 계좌와 별도 API 사용 신청 필요** (3.3 참고)
- 가상 자본 1억원 한도, 실시간 데이터로 동일하게 검증 가능
- plan.md Phase 6 ("모의투자" 4주) 의 토대

---

## 3. OpenAPI+ 사용 신청

### 3.1 영웅문 (PC HTS) 설치
- 키움증권 홈페이지 → "다운로드센터" → "영웅문4" 다운로드
- 설치 후 ID/PW 로 로그인 (계좌 개설 시 발급된 ID)

### 3.2 실계좌 API 사용 신청
1. 영웅문 메뉴: **"OPEN API"** → "서비스 사용 등록/해지"
2. 약관 동의 → 사용 신청
3. **승인까지 영업일 기준 1~2일** 소요 (보통 즉시~다음날)

### 3.3 모의투자 API 별도 신청
- 실계좌와 **다른 신청 절차**. 자주 빼먹는 함정.
- 영웅문 → "모의투자" 메뉴 → "Open API 사용 신청"
- 모의투자 기간 (3개월) 갱신 필요

### 3.4 OpenAPI+ 다운로드 및 설치
- 영웅문 → "OPEN API" → "Open API 모듈 다운로드"
- 설치 후 자동으로 `KHOPENAPI.KHOpenAPICtrl.1` ActiveX 가 시스템에 등록됨
- 설치 위치: 보통 `C:\OpenAPI\` 또는 `C:\Program Files (x86)\Kiwoom OpenAPI\`

---

## 4. 개발 환경 (가장 자주 막히는 단계)

### 4.1 ⚠️  Python 32비트 설치 (절대 64비트 X)
**OCX 는 32-bit COM 컴포넌트** 라 64-bit Python 에서는 로딩 자체가 안 됨.

```powershell
# 잘못된 예 (Python 64-bit)
> python -c "import struct; print(struct.calcsize('P') * 8)"
64   # ❌ OCX 로딩 실패

# 올바른 예 (Python 32-bit)
> python -c "import struct; print(struct.calcsize('P') * 8)"
32   # ✅
```

**다운로드**: python.org → Releases → "Windows installer (32-bit)" 명시된 파일.
보통 `python-3.9.x-32.exe` 같은 이름. **3.9 또는 3.10 권장** (PyQt5 호환).

설치 시 "Add Python to PATH" 체크. `pip` 도 자동 32비트로.

### 4.2 가상환경
```powershell
> python -m venv venv32
> venv32\Scripts\activate
(venv32) > python -m pip install --upgrade pip
```

### 4.3 필수 패키지

```powershell
(venv32) > pip install pyqt5==5.15.9
(venv32) > pip install pandas numpy
(venv32) > pip install pykiwoom    # 선택 — OCX 직접 호출이 불편하면
```

**버전 주의**:
- `pyqt5` 6.x 는 OCX 지원 불안정. 5.15.x 권장.
- `numpy` 는 64-bit / 32-bit 휠 자동 선택, 문제 없음.

### 4.4 OCX 등록 확인 (실패 시 수동 등록)
```powershell
# 관리자 권한 PowerShell
> regsvr32 "C:\Program Files (x86)\Kiwoom OpenAPI\khopenapi.ocx"
DllRegisterServer in ... succeeded.
```

---

## 5. KOA Studio (TR 명세 학습 도구)

- 영웅문 → "OPEN API" → "KOA Studio 다운로드"
- TR 코드 검색 (OPT10081, OPT10080 등) → 입력 파라미터 / 응답 컬럼 확인 가능
- **모든 TR 호출 전 KOA Studio 로 명세 1회 확인** 필수 (입력 키 오타 빈번)

---

## 6. 최소 연결 테스트 스크립트

`kiwoom/scripts/test_connection.py` 로 저장. 셋업 검증용.

```python
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from PyQt5.QtCore import QEventLoop

class KiwoomTest:
    def __init__(self):
        self.ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
        self.login_loop = QEventLoop()
        self.ocx.OnEventConnect.connect(self.on_event_connect)

    def on_event_connect(self, err_code):
        if err_code == 0:
            print("✅ 로그인 성공")
            acc_no = self.ocx.dynamicCall("GetLoginInfo(QString)", "ACCNO")
            user_id = self.ocx.dynamicCall("GetLoginInfo(QString)", "USER_ID")
            user_name = self.ocx.dynamicCall("GetLoginInfo(QString)", "USER_NAME")
            server = self.ocx.dynamicCall("GetLoginInfo(QString)", "GetServerGubun")
            print(f"  ID: {user_id}, Name: {user_name}")
            print(f"  Account(s): {acc_no}")
            print(f"  Server: {'모의' if server == '1' else '실'}")
        else:
            print(f"❌ 로그인 실패 (err_code={err_code})")
        self.login_loop.exit()

    def connect(self):
        self.ocx.dynamicCall("CommConnect()")
        self.login_loop.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    test = KiwoomTest()
    test.connect()
    sys.exit(0)
```

**실행 결과 (성공 시)**:
```
✅ 로그인 성공
  ID: kjhigh11
  Name: 한도윤
  Account(s): 1234567890;1234567891;
  Server: 모의
```

브라우저 형태의 로그인 창이 뜸 → ID/PW + 공인인증서/간편인증 후 자동 처리.

---

## 7. 첫 TR 호출 — 삼성전자 일봉 (OPT10081)

```python
# OPT10081: 주식일봉차트조회요청
# 입력: 종목코드, 기준일자(YYYYMMDD), 수정주가구분(0/1)
# 응답 (반복): 일자, 시가, 고가, 저가, 현재가, 거래량, ...

self.ocx.dynamicCall("SetInputValue(QString, QString)", "종목코드", "005930")
self.ocx.dynamicCall("SetInputValue(QString, QString)", "기준일자", "20260527")
self.ocx.dynamicCall("SetInputValue(QString, QString)", "수정주가구분", "1")
self.ocx.dynamicCall("CommRqData(QString, QString, int, QString)",
                     "주식일봉차트조회", "OPT10081", 0, "0101")
# → OnReceiveTrData 콜백에서 GetCommData / GetRepeatCnt 로 응답 추출
```

콜백 처리 예제는 `pykiwoom` 라이브러리의 wrapper 코드 참고 권장.

---

## 8. TR 제한 — 반드시 준수

| 제한 | 수치 | 위반 시 |
|------|------|--------|
| 초당 TR 호출 | 5회 | 일시 차단 |
| 시간당 TR 호출 | 1,000회 | 1시간 차단 |
| 주문 전송 | 초당 5회 | 일시 차단 |
| 조건검색 호출 | 1분당 1회 | 일시 차단 |
| 동시 접속 | HTS와 동시 X | 둘 중 하나 끊김 |

**실전 대응**:
- TR 사이에 `time.sleep(0.25)` (4회/초 안전 마진)
- `collections.deque` 로 1시간 슬라이딩 윈도우 카운터 구현
- 시세 데이터는 가능한 **실시간 등록(SetRealReg)** 으로 받고, TR 폴링 최소화

---

## 9. 자주 막히는 문제 + 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| `QAxWidget` 생성 시 즉시 죽음 | 64비트 Python 사용 | 32비트 Python 재설치 |
| OnEventConnect 가 안 옴 | `QApplication.exec_()` 미실행 | 이벤트 루프 필요 (QEventLoop) |
| 로그인 창이 안 뜸 | OCX 미등록 | `regsvr32` 관리자 권한 실행 |
| `GetLoginInfo` 가 빈 문자열 | OnEventConnect 전 호출 | 로그인 완료 후 호출 |
| TR 호출이 5회 후 멈춤 | rate limit | 0.25초 sleep |
| 조건검색이 안 옴 | HTS 에 조건식 미등록 | HTS 에서 먼저 조건식 저장 |
| 분봉 데이터가 600개 이상 X | TR 응답 최대 행 제한 | prev_next 로 연속조회 |
| 시간외 단일가에 주문 X | 호가구분 잘못 | KOA Studio 로 호가구분 확인 |

---

## 10. plan.md Phase 1 체크리스트 매핑

| plan.md Phase 1 항목 | 본 가이드 섹션 | 예상 시간 |
|--------------------|--------------|--------|
| ☐ 키움증권 계좌 개설 | §2 | 30분 |
| ☐ OpenAPI+ 신청 | §3 | 신청 5분 + 승인 1~2일 |
| ☐ 모의투자 계정 + Open API 신청 | §2.2, §3.3 | 15분 |
| ☐ 개발 환경 설정 (Python 32비트, PyQt5, pykiwoom) | §4 | 30분 |
| ☐ KOA Studio 설치 및 TR 함수 테스트 | §5 | 30분 |
| ☐ 로그인/접속 모듈 개발 | §6 | 30분 |
| ☐ 기본 시세 조회 기능 구현 | §7 | 1시간 |

**Phase 1 완료 기준**: §6 의 테스트 스크립트가 모의투자 계정으로 정상 로그인 + §7 의 OPT10081 호출이 005930 (삼성전자) 일봉 60개를 반환.

---

## 11. 다음 단계 (Phase 2 진입 전 권장)

1. **`kiwoom/api/kiwoom_real.py` 의 KiwoomAdapter 검증** ✅ 코드 작성 완료
   - 모든 TR (`OPT10001/10004/10080/10081`, `OPW00018`, `SendCondition`, `SendOrder`) 구현됨
   - `kiwoom/tests/test_parsers.py` 로 응답 파싱 11종 단위 테스트 통과
   - Windows 에서 첫 실행 시 `kiwoom/scripts/test_connection.py` → `get_daily_chart("005930")` 순으로 sanity check
2. **HTS 에 "거래대금 상위 50" 조건검색 등록**
   - 영웅문 → 조건검색 → 신규
   - 거래대금 > 거래대금 상위 50위
   - 이름은 `KiwoomAdapter(condition_name_amount_top=...)` 와 일치시킬 것
3. **OPT10081 (일봉) 으로 1년 데이터 받아 backtest 데이터 캐시 만들기**
   - 본 sandbox 의 `backtest/data_cache/` 와 동일한 CSV 포맷으로 저장
   - 1년 분량 = 약 250종목 × 1.5초/요청 = 6분
4. **OPT10080 (분봉) 으로 마하세븐 거래 일자만 받아 진입 룰 검증**
   - 백테스트의 `run_minute_synthetic.py` 의 `SyntheticMinuteGenerator` 를
     `KiwoomMinuteSource` 로 교체 → 동일 EntryRule 들 (first_pullback, limit, etc.) 재검증
5. **모의투자 계정에서 봇 가동 — 1주일 paper trading**
   - `kiwoom/main.py` 의 `MachasevenBot` 을 실제 어댑터로 가동
   - 매일 종가 후 로그 검토, 룰대로 매매가 나가는지 확인
6. **실계좌 소액 (100만원) 으로 1주일 운영**
   - plan.md Phase 7 "점진적 실전 투입" 과 일치
   - 종목당 자본의 20% (= 20만원) × 동시 5종목 한도

---

## 12. 위험·운영 주의

- **첫 1개월은 수익을 노리지 말고 시스템 안정성 검증**
- 매일 로그 확인 (주문 실패, TR 에러, 잠금 발동 여부)
- 일일 손실 한도 (-5%) 발동이 잦으면 룰 점검
- 실시간 데이터 끊김 → 재연결 로직 필수 (`OnEventConnect` reconnect)
- 윈도우 자동 업데이트로 PC 재부팅 → 봇 정지 → 작업스케줄러로 자동 시작
- 최소 1주에 한 번은 백업 (코드 + 매매 로그 + 캐시)

---

## 13. 참고 자료

- 키움 OpenAPI+ 공식 가이드: 영웅문 "OPEN API" 메뉴 내 매뉴얼
- KOA Studio 도움말: KOA Studio 실행 후 F1
- 커뮤니티: WikiDocs "파이썬으로 배우는 알고리즘 트레이딩"
- pykiwoom 라이브러리: GitHub sharebook-kr/pykiwoom

---

*마지막 업데이트: 2026-05-30 — 단계는 변동될 수 있으니 키움 공식 안내 우선*
