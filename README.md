# AX2 — 한국 데이트레이딩 자동매매 (마하세븐 포식자 시스템)

한국 데이트레이딩 대가들의 매매법을 백테스트로 검증해 **마하세븐 포식자 (돌파 모드)** 룰을 채택, 키움 OpenAPI+ 로 자동매매할 수 있는 코드까지 완성된 저장소.

> **본 저장소는 교육·연구용**입니다. 실 운용 시 발생하는 손익은 사용자 책임이며, 백테스트 결과가 미래 성과를 보장하지 않습니다.

## 핵심 결과 (walk-forward OOS)

| 지표 | 값 |
|------|---|
| 진정한 out-of-sample PF | **3.28** |
| OOS 승률 | **63.7%** |
| 거래당 평균 (수수료 차감) | **+3.46%** |
| 60일 통합 mock 시뮬 | **+58% PnL, 잠금 0회** |

## 빠른 시작

### 1. 클론

```bash
git clone https://github.com/DoyunHan/AX2.git
cd AX2
git checkout claude/korean-stock-trading-ideas-5pJAO
```

### 2. 환경 (Linux/macOS — 백테스트 검증용)

```bash
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 동작 확인 (3분)

```bash
# (a) 단위 테스트 — 키움 OCX 없이 파싱·rate limiter 검증
python3 kiwoom/tests/test_parsers.py
# → 11 passed, 0 failed

# (b) 60일 통합 mock 시뮬 — Bot end-to-end 동작 확인
python3 kiwoom/scripts/simulate_60day.py
# → 128 매매 / 승률 52% / +58% / 잠금 0회 / 차트 results/14_bot_sim_60day.png
```

처음 실행 시 `backtest/data_cache/` 에 약 30MB 한국 일봉 CSV 캐시 다운로드 (이후 즉시).

### 4. 백테스트 재실행 (선택)

```bash
cd backtest
python3 walk_forward.py     # OOS 검증 (~1.5분)
python3 run_advanced.py     # 그리드 서치 (~2분)
```

## 문서 안내

| 문서 | 용도 |
|------|------|
| **[CLAUDE.md](CLAUDE.md)** | AI 세션이 즉시 컨텍스트 잡는 핸드오프 |
| **[plan.md](plan.md)** | 자동매매 시스템 종합 계획 (Phase 1~7) |
| **[masters.md](masters.md)** | 5명 대가 매매법 정리 (개념) |
| **[backtest/README.md](backtest/README.md)** | 백테스트 전체 결과·해석·실행법 |
| **[kiwoom/SETUP.md](kiwoom/SETUP.md)** | Windows + 키움 OpenAPI+ 셋업 가이드 |

## 디렉터리 구조

```
AX2/
├── CLAUDE.md                # AI 핸드오프 (꼭 먼저 읽으세요)
├── README.md                # 본 파일
├── requirements.txt
├── plan.md / masters.md     # 계획 + 대가 매매법
│
├── backtest/                # 백테스트 시스템 (Linux/macOS 작동)
│   ├── *.py                 # 8개 분석 모듈
│   ├── README.md
│   └── results/             # PNG/CSV/MD 결과물 (committed)
│
└── kiwoom/                  # 키움 OpenAPI+ 시스템 (Windows 전용)
    ├── SETUP.md             # Phase 1 셋업 가이드 (13개 섹션)
    ├── main.py              # MachasevenBot 메인 루프
    ├── config/machaseven.py # 검증 통과 룰 (CFG dataclass)
    ├── strategy/            # 신호·지표·universe 필터
    ├── risk/                # 일일 손실 한도·포지션 사이징
    ├── api/                 # KiwoomAdapter (Real + Mock)
    ├── data/                # 분봉 로더 + 합성 generator
    ├── utils/rate_limiter.py
    ├── tests/test_parsers.py  # 11개 단위 테스트
    └── scripts/             # 연결 테스트 + 60일 시뮬
```

## 채택된 룰 (`kiwoom/config/machaseven.py` 단일 출처)

```
진입 (4조건 모두 충족):
  · 거래대금 상위 50 종목군
  · 당일 거래대금 ≥ 20일 평균 × 1.5
  · 5MA > 20MA (정배열)
  · 20일 신고가 돌파

청산 (선후 발생 순):
  · 5MA hard stop (저가가 5MA 이탈)
  · 트레일링 -2% (고점 대비)
  · 3거래일 타임컷

자금 관리:
  · 일일 -5% 손실 시 당일 신규 진입 차단
  · 총 자본의 50% 는 항상 현금
  · 진입당 자본의 20%, 동시 최대 5종목
```

룰 변경 시 `backtest/walk_forward.py` 재검증 필수.

## 다음 단계 (사용자 측 작업)

1. **Windows 환경 셋업** — `kiwoom/SETUP.md` 따라
   - 키움증권 계좌 + OpenAPI+ 신청 (승인 1~2일)
   - **Python 32-bit** + PyQt5 + 키움 OCX 등록
   - `python kiwoom/scripts/test_connection.py` → 로그인 확인
2. **모의투자 1주일 paper trading**
   - HTS 에 "거래대금 상위 50" 조건검색 등록
   - `kiwoom/main.py` 의 `MachasevenBot` 가동
   - 매일 종가 후 로그 검토
3. **실계좌 소액 (100만원) 1주일**
   - plan.md Phase 7 점진적 투입
4. **(병행) 키움 OPT10081 로 1년치 일봉 받아 walk-forward 5~10 fold 재검증**

## 환경 제약 (Linux/macOS sandbox)

- 키움 OCX 실 호출 불가 (Windows 전용) — `kiwoom_real.py` 는 단위 테스트로만 검증
- 분봉 데이터 부재 (네트워크 제한) — 합성 분봉으로 룰만 비교
- 일봉 데이터 60거래일 (FDR 캐시) — `walk_forward` 도 3 fold 한계

실데이터로 본격 검증은 **Windows + 키움 OpenAPI+ 환경** 에서만 가능.

## 라이선스 / 면책

본 코드는 교육·연구용입니다. **실제 매매에 적용해 발생하는 손익은 전적으로 사용자 책임**입니다. 백테스트 PF 3.28 은 60거래일 + 3 fold 검증 결과로, 실 운용에서는 슬리피지·체결 지연·시장 변동 등으로 결과가 다를 수 있습니다.
