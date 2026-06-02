# CLAUDE.md

향후 Claude 세션이 본 저장소를 빠르게 파악하기 위한 핸드오프 문서.

## 프로젝트 한 줄 요약

한국 데이트레이딩 대가들의 매매법을 백테스트로 검증해 **마하세븐 포식자 시스템 (돌파 모드)** 을 자동매매 룰로 채택, 키움 OpenAPI+ 로 운영할 코드까지 완성된 상태.

## 현재 진행 상황

| 단계 | 상태 |
|------|------|
| 매매법 정리 (`masters.md`) | ✅ 완료 |
| 백테스트 시스템 (`backtest/`) | ✅ 7개 분석 모듈 완료 |
| Walk-forward 검증 | ✅ 마하세븐 돌파 OOS PF 3.28 통과 |
| 키움 OpenAPI+ 코드 트리 (`kiwoom/`) | ✅ 모든 메서드 구현 + 단위 테스트 |
| 60일 통합 mock 시뮬레이션 | ✅ +58% PnL, 룰대로 동작 확인 |
| Windows 실 환경 검증 | ⬜ 사용자 단계 (사용자가 직접) |
| 모의투자 1주일 | ⬜ 사용자 단계 |
| 실계좌 소액 운영 | ⬜ 사용자 단계 |

## 핵심 채택 룰

**마하세븐 포식자 — 돌파 모드** (walk-forward OOS PF 3.28, 승률 63.7%, 거래당 +3.46%)

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
  · 총 자본의 50%는 항상 현금 락다운
  · 진입당 자본의 20%, 동시 최대 5종목
```

이 룰의 단일 정의 출처는 `kiwoom/config/machaseven.py` 의 `CFG`. 변경 시 walk-forward 재검증 필수.

## 디렉터리 구조

```
AX2/
├── masters.md                          # 대가 5명 매매법 정리
├── plan.md                             # 자동매매 시스템 종합 계획
├── 실습내용.md                          # 별개 작업 (US-Iran 보고서) — 무시
│
├── backtest/                           # 백테스트 시스템 (Linux sandbox)
│   ├── data_loader.py                  # FDR 캐시 → 패널 빌드
│   ├── strategies.py                   # 5개 전략 함수 + apply_daily_loss_limit
│   ├── universe.py                     # 시총/변동성/거래대금 universe
│   ├── metrics.py                      # 거래 통계 + equity 곡선
│   ├── run_all.py                      # 4 전략 비교 (KOSPI 지수 + 개별주)
│   ├── run_individual.py               # KRX 2,806종목 시총·변동성 분해
│   ├── run_advanced.py                 # 명시 필터 + 그리드 서치 + 마하세븐
│   ├── walk_forward.py                 # 3-fold rolling walk-forward
│   ├── run_combined.py                 # 마하세븐 + B.N.F 결합
│   ├── run_entry_timing.py             # 일봉 진입가 sensitivity
│   ├── run_minute_synthetic.py         # 합성 분봉 EntryRule 시뮬
│   ├── plot_advanced.py                # 비교 차트
│   ├── README.md                       # 백테스트 전체 결과 + 해석
│   ├── data_cache/                     # (gitignore) FDR CSV 캐시 ~30MB
│   └── results/                        # PNG, CSV, MD 결과물 모두 포함
│
├── kiwoom/                             # 키움 OpenAPI+ 시스템 (Windows 전용)
│   ├── SETUP.md                        # Phase 1 셋업 13개 섹션 가이드
│   ├── main.py                         # MachasevenBot 메인 루프
│   ├── config/machaseven.py            # CFG dataclass (검증 통과 룰)
│   ├── strategy/
│   │   ├── indicators.py               # SMA, ATR, amount_surge, breakout
│   │   ├── screener.py                 # universe 헬퍼
│   │   └── machaseven_breakout.py      # check_entry / check_exit
│   ├── risk/
│   │   ├── daily_limit.py              # DailyLimitGuard (-5% 잠금)
│   │   └── position.py                 # Portfolio (50%/20%/5종목)
│   ├── api/
│   │   ├── kiwoom_adapter.py           # Protocol + MockKiwoomAdapter
│   │   └── kiwoom_real.py              # 실 KiwoomAdapter (Windows OCX)
│   ├── data/minute_loader.py           # Kiwoom + Synthetic minute sources
│   ├── utils/rate_limiter.py           # TRRateLimiter (5/s, 1000/h)
│   ├── tests/test_parsers.py           # 11개 단위 테스트 (sandbox)
│   └── scripts/
│       ├── test_connection.py          # Windows 첫 로그인 검증 스크립트
│       └── simulate_60day.py           # 통합 mock 시뮬레이션
└── design.md, *.html, 토큰 대시보드 등   # 별개 작업물 — 무시
```

## 본 환경의 결정적 제약 (반드시 인지)

| 제약 | 영향 |
|------|------|
| **Linux sandbox** | 키움 OCX 실행 불가 → `kiwoom_real.py` 는 단위 테스트로만 검증 |
| **네트워크 allowlist** | `raw.githubusercontent.com` 외 모든 host 403. KRX·네이버·Yahoo 분봉 모두 차단 |
| **데이터 범위** | 일봉 약 60일 (2026-03-08 ~ 2026-05-27), 지수는 1995~2026 장기 |
| **분봉 부재** | 본 sandbox 에서 실분봉 백테스트 불가. 합성 분봉으로 룰만 비교 |

→ 본격 검증은 **사용자의 Windows + 키움 OpenAPI+ 환경** 에서만 가능.

## 자주 쓰는 명령

```bash
# Sandbox 검증
python3 kiwoom/tests/test_parsers.py                    # 11개 단위 테스트
python3 kiwoom/scripts/simulate_60day.py                # 60일 통합 mock 시뮬

# 백테스트
cd backtest
python3 run_all.py                                       # 4 전략 비교
python3 run_individual.py                                # 개별주 + 시총/변동성
python3 run_advanced.py                                  # 그리드 서치 (~2분)
python3 walk_forward.py                                  # OOS 검증 (~1.5분)
python3 run_combined.py                                  # 결합 전략
python3 run_entry_timing.py                              # 진입 타이밍
python3 run_minute_synthetic.py                          # 합성 분봉
```

## 핵심 백테스트 결과 (cheat sheet)

| 분석 | 결과 |
|------|------|
| 4 전략 비교 (run_all) | 마하세븐 변동성 추격 -99% (수수료 부담 증명), 나머지 양의 엣지 |
| 개별주 분해 (run_individual) | B.N.F 개별주 음의 엣지 / 장영한은 대형·중형주에서 +2% |
| 그리드 best (run_advanced) | 마하세븐 돌파 PF 2.04, 장영한 PF 2.02 (in-sample) |
| Walk-forward (walk_forward) | 마하세븐 OOS PF 3.28 ✅ / 장영한 F2 -4.79% ❌ |
| 결합 (run_combined) | 일별 상관 +0.038, MDD/변동성 절반 감소 |
| 진입 타이밍 (entry_timing) | open(베이스라인)이 거의 최적, 지연 진입은 모멘텀 잠식 |
| 합성 분봉 (minute_synthetic) | first_pullback -0.5% PF 3.94 (실데이터 검증 1순위 후보) |
| 60일 통합 시뮬 (simulate_60day) | 128 거래, 승률 52%, +58% PnL, 잠금 0회 |

## 정직 코너 (PR 본문에도 명시)

- 60거래일은 2026-03~05 강세장 → 시장 편향 가능
- 마하세븐 본연의 분·초 호가창 매매는 일봉으로 미검증
- `kiwoom_real.py` 의 TR 필드명(한글) 은 KOA Studio 명세 기준이나 Windows 첫 실행 시 재확인 필요
- 실데이터로 walk-forward 5~10 fold 재검증 후에야 실전 투입 권장

## 사용자 컨텍스트

- email: kjhigh11@gmail.com
- 활성 작업 브랜치: `claude/korean-stock-trading-ideas-5pJAO`
- PR: https://github.com/DoyunHan/AX2/pull/1
- 기본 브랜치: `master`

## 다음 세션이 받을 만한 작업

| 우선순위 | 작업 | 비고 |
|---------|------|------|
| 1 | Windows 환경 셋업 후 `kiwoom_real.py` 동작 검증 도와주기 | TR 필드명 매칭 / OnReceive 콜백 |
| 2 | 키움 OPT10081 로 1년치 일봉 받아 backtest/data_cache 확장 후 walk-forward 재실행 | sandbox 에선 불가, 사용자 PC 필요 |
| 3 | 키움 OPT10080 분봉으로 `first_pullback` 룰 실데이터 검증 | run_minute_synthetic.py 의 generator 교체 |
| 4 | 모의투자 1주일 paper trading 로그 분석 | 거래 일지 / 룰 위반 패턴 검토 |
| 5 | 실시간 데이터 (SetRealReg) 통합 — intraday hard stop | 현재 일봉 모드만 |

## 작업 시 주의

- **PR/커밋 메시지에 모델명·세션 ID 노출 금지**: claude-opus-x.x 같은 식별자는 chat 답변에만 사용
- **금융 관련 추정치 발언 금지**: "이 룰로 N% 수익 보장" 같은 표현은 모두 거짓. 백테스트 수치만 인용.
- **`raw.githubusercontent.com` 외 모든 host 403** — 다른 데이터 소스 시도 X
- **분봉 데이터 확보 시도 X** — 본 sandbox 에서 불가, 사용자 환경에서만 가능
- **plan.md 의 plan workflow (purrfect-rolling-peach.md)** 는 일회성 작업 자취, 무시 가능

## 변경 이력 (최근)

- PR #1 생성, master 머지 대기
- `kiwoom/api/kiwoom_real.py` 모든 TR 메서드 구현 + 단위 테스트 11개 통과
- 마하세븐 봇 60일 통합 mock 시뮬레이션: 128 거래, +58%, 잠금 0회
- 합성 분봉으로 first_pullback 룰 발견 (PF 3.94)
- Walk-forward 3 fold: 마하세븐 OOS PF 3.28, 장영한 F2 음의 엣지
- 마하세븐 + B.N.F 결합 일별 상관 +0.038 확인
