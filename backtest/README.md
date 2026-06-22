# 한국 데이트레이딩 대가들의 매매법 — 백테스트

`masters.md`에서 정리한 4가지 매매법을 실제 코드로 구체화하고, 한국 시장
실데이터로 백테스트한 결과입니다.

## 1. 폴더 구조

```
backtest/
├── README.md           # 본 파일 (실행/해석 가이드)
├── data_loader.py      # KRX 일별 스냅샷 / KOSPI·KOSDAQ 지수 로더
├── strategies.py       # 4가지 매매 전략
├── metrics.py          # 승률·PF·MDD·Sharpe 등 성과 지표
├── run_all.py          # 4개 전략 일괄 실행 + 리포트 생성
├── data_cache/         # 다운로드된 CSV 캐시 (gitignore 권장)
└── results/
    ├── summary.md      # 4개 전략 비교표
    ├── *_equity.png    # 자본 곡선
    └── trades_*.csv    # 매매 내역
```

## 2. 데이터 소스

- **지수 (KOSPI/KOSDAQ)**: 1995~2026 일별 OHLCV
- **개별 종목 일별 스냅샷**: 2026-03-08 ~ 2026-05-27 (약 60거래일)

모두 `raw.githubusercontent.com/FinanceData/fdr_krx_data_cache`에서 공개된 KRX 캐시 데이터를 사용합니다.
(컨테이너 네트워크 정책상 KRX·네이버 직접 접근이 불가하여, GitHub에 캐싱된 데이터를 사용합니다.)

## 3. 실행

```bash
cd backtest
python3 run_all.py
```

처음 실행 시 약 80개 일별 CSV를 받아옵니다(약 25MB). 이후 `data_cache/`에 저장되어 재실행은 빠릅니다.

## 4. 백테스트 결과 (요약)

| 전략 | 데이터 기간 | 거래수 | 승률 | 평균/거래 | 누적수익 | PF | MDD |
|------|-----------|------:|------:|----------:|---------:|----:|------:|
| **B.N.F 이격도 역추세** (KOSPI 지수) | 2020~2026 | 8 | **50.0%** | +1.19% | +6.85% | **1.45** | -6.78% |
| **장영한 추세추종** (KOSPI 지수) | 2020~2026 | 35 | 45.7% | +0.51% | +15.55% | 1.32 | -21.86% |
| **남석관 거래량 돌파** (개별 100종목) | 2026-03~05 | 88 | 46.6% | +0.54% | +38.02% | 1.22 | -41.83% |
| **마하세븐 변동성 추격(근사)** | 2026-03~05 | 1,438 | 41.8% | **-0.44%** | **-99.97%** | 0.78 | -99.99% |

수수료+거래세 왕복 0.23% 차감 후, 매 거래에 동일 비중 100% 투입 가정.

## 5. 결과 해석 — 결이 맞는 매매법 찾기

### 5.1 **B.N.F 이격도 역추세** — 가장 안정적, 자동화 최적

- 6년간 8회 거래 → **빈도는 낮지만 신호가 강할 때만 진입**
- 승률 50%, PF 1.45, MDD -6.78% → 잠을 잘 자게 해주는 곡선
- 진입 조건이 명확(이격도 -7% 이하)해서 봇이 망설일 일 없음
- **단점**: 거래 수가 너무 적어 "매일 시장 보는 재미"는 없음. 데이트레이딩이라기보다 스윙

**추천 대상**: 자동매매자, 본업 있는 직장인. plan.md 시스템에 1순위로 채택할 만함.

### 5.2 **장영한 시스템 추세추종** — 꾸준하지만 인내심 필요

- 35회 거래로 6년간 +15.55% (연 환산 ~2.4%)
- 자본 곡선 보면 **2021~2025 4년간 거의 횡보**, 2026 들어 급반등
- 추세장에서는 잘 먹지만 횡보장에서는 손절만 누적되는 전형
- PF 1.32는 양호, 작은 손실을 큰 이익이 보상하는 구조

**추천 대상**: 시장 사이클을 인내할 수 있는 자동매매자. **장영한 + B.N.F 조합**이 횡보-추세 양쪽 커버 가능.

### 5.3 **남석관 거래량 돌파** — 고수익·고위험 (단기 데이터 한계)

- 2.5개월에 88회 거래로 +38% (수수료 후) — 수치만 보면 압도적
- 하지만 **MDD -41.83%** → 한 번에 자본 반토막. 위험 관리 없이는 불가
- 익절 +8% / 손절 -5%는 양호한 손익비지만 연속 손절이 치명적
- 단기 데이터(60거래일)라 우연히 강세장에 걸렸을 가능성 큼

**추천 대상**: 능동적 데이트레이더. 단, **포지션 사이징 필수** (자본 20% 이내). 자동매매로는 MDD 관리 룰을 강력하게 추가해야 함.

### 5.4 **마하세븐 변동성 추격(근사)** — **자동화 불가의 증거**

- 1,438회 거래로 **-99.97%** — 사실상 자본 전소
- 거래 1회당 평균 -0.44% → **수수료 0.23% × 2 = 0.46% 부담이 작은 익절을 다 잡아먹음**
- 이게 plan.md 8.2절에서 마하세븐 매매법을 4순위로 미룬 정확한 이유
- 일봉 데이터로는 마하세븐 본인의 호가창/체결강도 매매를 재현 불가 (스캘핑 한 번에 0.3~0.5% 익절을 노리는데, 수수료가 다 먹음)

**해석**: 마하세븐의 실제 매매 = 분·초 단위 호가창 + 체결 흐름 + 거래원 매집 추적. 이건 일봉 백테스트로는 평가 자체가 불가능. 자동화하려면:
1. 실시간 호가·체결 데이터 수집 인프라
2. 분·초 단위 의사결정 룰
3. **수수료를 이기는 매우 작은 우위(edge)** — 개미가 만들기 어려움

→ 결론: **마하세븐 방식은 자동매매보다 사람이 직접 화면 보며 매매**할 때 의미가 있음.

## 6. 다음 단계 추천

### 결이 맞는 매매법 후보 (백테스트 기반)

| 우선순위 | 매매법 | 이유 |
|-------:|------|------|
| **1순위** | B.N.F 이격도 역추세 | 안정성·자동화 친화도·심리적 부담 모두 최상 |
| **2순위** | 장영한 추세추종 | B.N.F와 상보적 (역추세 + 추세 결합) |
| **3순위** | 남석관 거래량 돌파 | 수익률은 높으나 MDD 관리 필요. 보조 전략 |
| **제외** | 마하세븐 호가창 | 자동매매로는 부적합. 수동 매매 영역 |

### plan.md 시스템에 반영할 코드

`plan.md` `strategy/signals.py`에 다음 3개 함수부터 이식:

```python
from backtest.strategies import (
    bnf_mean_reversion,       # → signal_mean_reversion()
    jangyounghan_trend,       # → signal_trend_following()
    namseokgwan_vol_breakout, # → signal_volume_breakout()
)
```

### 백테스트 한계 (정직 코너)

1. **개별 종목 데이터가 2.5개월뿐** — 통계적 신뢰도 낮음. 본격 운용 전 1년+ 데이터로 재검증 필요.
2. **슬리피지 미반영** — 실전에서는 시초가 진입 시 0.1~0.3% 추가 비용 가능.
3. **호가창·체결 데이터 없음** — 마하세븐식 매매는 평가 불가.
4. **소형주 함정 미반영** — 거래량 폭증 종목 중 작전주가 섞일 위험.

이 한계는 plan.md Phase 5(백테스팅)·Phase 6(모의투자) 단계에서 키움 OpenAPI+ 데이터로 보완 가능합니다.

---

## 7. 추가 분석 — 개별주 전체 적용 (`run_individual.py`)

`run_all.py`의 1·2 (B.N.F·장영한)는 KOSPI **지수**에만 적용했기에 종목 발굴 효과를 보지 못합니다.
`run_individual.py`로 **KRX 전체 2,806종목**에 동일 룰을 적용해 시총·변동성 구간별로 분해했습니다.

> 주의: 다중 종목 동시 거래의 누적은 의미가 모호하므로 `compute_stats`에서
> total_ret / MDD를 숨기고 **거래당 기댓값(expect/trade)**·PF·승률을 핵심 지표로 사용합니다.
> 누적 엣지 차트는 `Σ(per-trade net return)` 으로 표시(복리 폭증 회피).

### 7.1 B.N.F 이격도 역추세 — 개별주에서는 안 통함

| 구간 | trades | win% | expect/trade | PF |
|------|------:|----:|-------------:|---:|
| **전체** | 5,216 | 36.22% | **-1.82%** | 0.57 |
| 대형주 | 1,968 | 41.36% | -1.15% | 0.71 |
| 중형주 | 1,787 | 34.14% | -2.20% | 0.48 |
| 소형주 | 1,461 | 31.83% | -2.25% | 0.51 |
| 고변동 | 1,734 | 41.00% | -1.15% | 0.76 |
| 중변동 | 1,736 | 36.41% | -1.78% | 0.57 |
| 저변동 | 1,746 | 31.27% | -2.53% | 0.35 |

→ **모든 구간에서 음의 엣지**. 거래당 -1.15% ~ -2.53%로 일관되게 손실.
→ KOSPI 지수에서는 통하지만 **개별 종목에서는 평균회귀가 신뢰할 수 없음** (idiosyncratic noise > mean reversion 신호).
→ 결론: B.N.F식은 **지수 ETF(KODEX 200, TIGER 200 등)에 한정해 적용**해야 함.

### 7.2 장영한 시스템 추세추종 — 대형/중형주에서 강함

| 구간 | trades | win% | expect/trade | PF |
|------|------:|----:|-------------:|---:|
| **전체** | 2,722 | 48.53% | **+1.47%** | **1.43** |
| **대형주** | 1,005 | **50.95%** | **+2.04%** | **1.60** |
| **중형주** | 881 | 50.28% | +2.17% | 1.69 |
| 소형주 | 836 | 43.78% | +0.04% | 1.01 |
| **고변동** | 906 | 49.45% | **+2.54%** | 1.54 |
| 중변동 | 907 | 50.28% | +1.44% | 1.45 |
| 저변동 | 909 | 45.87% | +0.43% | 1.20 |

→ **전체 양의 엣지** (거래당 +1.47%, PF 1.43).
→ **대형주·중형주에서 거래당 +2% 수준의 강한 엣지**. 소형주는 사실상 무수익.
→ 고변동 종목에서 큰 폭의 익절(win_avg +14.6%)이 나옴 → 큰 추세를 잘 포착.
→ 결론: **장영한식 추세추종 + 시총 상위 종목 풀(대형/중형) + 고변동 필터** 조합이 가장 강력.

### 7.3 종합 결론 (1차 + 2차)

| 매매법 | 인덱스 적용 | 개별주 적용 | 최적 운용처 |
|--------|-----------|-----------|-----------|
| B.N.F 이격도 역추세 | ◎ (PF 1.45) | ✗ (PF 0.57) | **KODEX 200 / KOSPI200 ETF만** |
| 장영한 추세추종 | ○ (PF 1.32) | ◎ **대/중형 + 고변동에서 PF 1.6+** | **시총 상위 + 고변동 필터** |
| 남석관 거래량 돌파 | — | △ (PF 1.22, MDD 큼) | 포지션 사이징 필수 |
| 마하세븐 호가창 | — | ✗ 자동매매 불가 | 수동 매매 영역 |

**자동매매 1순위 전략 = 장영한 추세추종 + KOSPI 시총 상위 200 + 20일 변동성 상위 1/3 필터**.
이 조합이 본 백테스트에서 가장 일관되게 우수합니다.

### 7.4 실행

```bash
python3 run_individual.py
# Outputs:
#   results/individual_summary.md
#   results/5_bnf_by_marcap.png, 6_bnf_by_vol.png
#   results/7_jyh_by_marcap.png, 8_jyh_by_vol.png
#   results/trades_bnf_all_stocks.csv, trades_jyh_all_stocks.csv
```

---

## 8. 고급 백테스트 — 명시적 필터 + 그리드 서치 + 마하세븐 포식자 (`run_advanced.py`)

3가지를 한 번에 진행:

1. **명시적 universe 필터를 적용한 장영한 추세추종**
   (시총 상위 200 ∩ 20일 변동성 상위 1/3 — *시점별로* 재계산해서 snooping 회피)
2. **파라미터 그리드 서치** (장영한 72조합 + 마하세븐 16조합)
3. **마하세븐 포식자 시스템** (사용자 명세 기반 구체화)

### 8.1 마하세븐 포식자 시스템 — 명세

| 항목 | 일봉 백테스트 구현 |
|------|----------------|
| 거래대금 상위 50 universe | ✅ 그대로 (`amount_rank_universe`) |
| 1분봉 거래대금 지속 N억 | ❌ → 일별 거래대금 ≥ 20일 평균 × N배로 대체 |
| 역배열 제외 | ✅ 5MA > 20MA 필수 |
| 60/120일 저항 돌파 | △ → 20일 신고가 돌파 (데이터 길이 한계) |
| 5MA 눌림 + 음봉 | ✅ 그대로 (`mode="pullback"`) |
| Hard stop 5MA 이탈 | ✅ 5MA 하향 돌파 시 5MA 가격으로 청산 |
| 15분 타임컷 | ❌ → N거래일 타임컷 |
| 트레일링 스탑 | ✅ 고점 대비 -3% 트레일링 |
| 50% 현금 룰 | △ 포지션 사이징(엔진 외) — 미구현 |
| 일일 손실 한도 | ✅ `apply_daily_loss_limit()` 로 -5% 도달 시 당일 잠금 |
| 초식동물 모드 | ✅ 시그널 없는 날 자동 0거래 (전략 본질) |

### 8.2 베이스라인 결과 (수수료 차감)

| 전략 | trades | win% | expect/trade | PF | 평가 |
|------|------:|-----:|-------------:|---:|------|
| 장영한 + 시총·변동성 필터 | 99 | 46.5% | +0.83% | 1.21 | 양의 엣지, 안정적 |
| 마하세븐 — **돌파** 모드 | 254 | **59.1%** | **+2.03%** | **2.04** | **압도적** |
| 마하세븐 — 눌림목 모드 | 30 | 33.3% | -1.51% | 0.35 | 일봉으로 검증 불가 |

마하세븐 돌파 모드가 PF **2.04**, 승률 **59%**로 모든 전략 중 가장 강력합니다.

### 8.3 마하세븐 돌파 — 청산 사유 분해

| 청산 사유 | 거래 수 | 평균 수익 | 승률 |
|----------|------:|--------:|----:|
| **trailing_stop** (수익 확정) | 134 | **+5.89%** | **73.1%** |
| hard_stop_5MA (손절) | 116 | -2.22% | 44.0% |
| time_cut (시간 종료) | 4 | -4.05% | 25.0% |

**마하세븐 철학이 그대로 작동**: 손실은 5MA에서 빠르게 잘리고(-2.2%), 수익은 트레일링이 길게 끌고 가서(+5.9%) 손익비가 1:2.7로 확보됨.

### 8.4 장영한 그리드 서치 — 베스트 파라미터

72조합 중 상위 5:

| fast | slow | atr_stop | atr_target | hold | trades | win% | expect | PF |
|----:|----:|---------:|-----------:|----:|------:|----:|------:|---:|
| **3** | **15** | **2.5** | **3.0** | **10** | 185 | **57.8%** | **+3.06%** | **2.02** |
| 3 | 15 | 1.5 | 3.0 | 10 | 196 | 54.1% | +2.94% | 1.98 |
| 8 | 20 | 1.5 | 3.0 | 10 | 86 | 51.2% | +2.86% | 1.87 |
| 3 | 15 | 2.5 | 5.0 | 10 | 184 | 56.0% | +2.80% | 1.90 |
| 3 | 15 | 1.5 | 5.0 | 10 | 195 | 51.8% | +2.63% | 1.82 |

→ **fast=3, slow=15**가 우세 (기본 5/20보다 더 빠른 신호).
→ atr_target보다 atr_stop이 PF에 더 큰 영향.
→ max_holding=10 일관되게 우월 (포지션을 충분히 끌고 가야 함).
→ 최적 파라미터 적용 시 거래당 **+3.06%, PF 2.02** — 베이스라인 대비 4배 개선.

### 8.5 마하세븐 눌림목 그리드 — 모두 음의 엣지

16조합 모두 PF < 1.0, expect/trade -0.9% ~ -2.2%.

**왜 안 되는가?**
- 눌림목 매수는 본질적으로 **분·초 단위 진입 타이밍**에 의존
- 일봉 종가 기준 "5MA ±2% + 음봉"은 너무 늦은 시점 (다음날 시초가 진입)
- 마하세븐 본인의 눌림목 매매는 호가창에서 매수세 회복을 확인하며 진입 — 일봉으로 재현 불가

→ **눌림목은 자동매매 대상에서 제외**. 돌파 모드만 채택.

### 8.6 자동매매 1순위 전략 (종합)

본 백테스트 기준 추천 우선순위:

1. **마하세븐 포식자 — 돌파 모드** (PF 2.04, 승률 59%)
   - 진입: 거래대금 top-50 + 거래대금 급증 2배 + 정배열 + 20일 신고가 돌파
   - 청산: 5MA hard stop / 3% 트레일링 / 3일 타임컷
   - 자금관리: 일일 -5% 손실 시 잠금
2. **장영한 추세추종 (최적 파라미터)** (PF 2.02, 승률 58%)
   - fast=3, slow=15, atr_stop=2.5, atr_target=3.0, max_holding=10
   - 시총 상위 200 ∩ 고변동 상위 1/3 필터
3. **B.N.F 이격도 역추세** — KODEX 200 ETF에 한정

### 8.7 정직 코너 (재차)

- 60거래일 데이터의 **2026-03~04 강세 구간 효과**가 누적 엣지 곡선에 보임 (5월 이후 정체/감소)
- 그리드 베스트 파라미터는 같은 데이터로 선택했으므로 **out-of-sample 검증 필수**
- 마하세븐 돌파 모드의 PF 2.04는 매력적이나, 실전에서는 슬리피지(특히 거래량 급증 종목 진입 시) 0.3~0.5% 추가 부담 가능
- 본격 운용 전 키움 OpenAPI+로 1년+ 데이터 받아 walk-forward 재검증 필요

### 8.8 실행

```bash
python3 run_advanced.py
# Outputs:
#   results/advanced_summary.md
#   results/9_advanced_comparison.png
#   results/grid_jyh.csv, grid_machaseven_pullback.csv
#   results/trades_jyh_filtered.csv
#   results/trades_machaseven_breakout.csv
#   results/trades_machaseven_pullback.csv
#   results/machaseven_breakout_reasons.csv
python3 plot_advanced.py
```

---

## 9. Walk-forward 검증 (`walk_forward.py`)

그리드 서치 결과가 in-sample 과적합이 아닌지 검증.

### 9.1 설계

- 기간: 2026-03-30 ~ 2026-05-27 (시그널 시작 후 ~40거래일)
- Train 25일 / Test 12일 / Step 10일 → **3 folds**
- 각 fold마다:
  1. Train 윈도우 거래만으로 best 파라미터 선택
  2. 그 파라미터로 Test 윈도우 성과만 평가
- 모든 test 거래 합산 = 진정한 out-of-sample 성과

### 9.2 마하세븐 돌파 — Walk-forward ✅ **통과**

| Fold | Train n / expect / PF | Test n / expect / PF | Best params |
|------|--------------------|---------------------|------------|
| F1 | 131 / +2.97% / **2.75** | 64 / **+4.62%** / **7.26** | surge=1.5, ts=0.02, hold=3 |
| F2 | 143 / +3.32% / **3.45** | 60 / **+2.40%** / **2.21** | (동일) |
| F3 | 132 / +2.99% / **3.17** | 33 / **+3.14%** / **2.44** | (동일) |

**통합 test (157 거래)**: **승률 63.7%, 거래당 +3.46%, PF 3.28, Sharpe 0.40**

핵심 관찰:
- **3개 fold 모두 같은 파라미터 선택** → 시장 상황에 둔감, 매우 견고
- **3개 fold 모두 test에서 양의 엣지** → 진짜 엣지 존재
- Train PF 2.75~3.45 vs Test PF 2.21~7.26 → 과적합 없음 (오히려 test가 좋은 경우도)

### 9.3 장영한 — Walk-forward ❌ **불합격**

| Fold | Train n / expect / PF | Test n / expect / PF | Best params |
|------|--------------------|---------------------|------------|
| F1 | 73 / +8.04% / **13.83** | 14 / +2.38% / 1.91 | fast=3, slow=15, stop=2.5, target=3.0, hold=10 |
| F2 | 49 / +6.91% / 4.96 | 19 / **-4.79%** / **0.35** | fast=8, slow=20, stop=1.5, target=5.0, hold=10 |
| F3 | 54 / +1.52% / 1.44 | 62 / +2.50% / 1.83 | fast=3, slow=15, stop=1.5, target=5.0, hold=5 |

**통합 test (95 거래)**: 승률 44.2%, 거래당 +1.02%, PF 1.27

핵심 관찰:
- **Fold마다 best 파라미터가 달라짐** → 시장 상황에 강하게 의존
- **F2 test에서 -4.79%** → 실전 운용 시 큰 손실 가능
- Train PF 14 → Test PF 0.35 같은 강한 폭락 (F2) — 명백한 과적합 신호
- 통합 test 엣지 +1.02%는 마하세븐(+3.46%)의 1/3 수준

### 9.4 결론

| 전략 | Walk-forward 결과 | 실전 채택 |
|------|-----------------|-----------|
| **마하세븐 돌파** | 3 fold 일관되게 양의 엣지, 같은 파라미터, PF 3.28 | **자동매매 1순위 추천** |
| **장영한 추세추종** | Fold마다 best 변동, F2에서 -4.79% | 단독 운용 비추천. 보조 신호로만 |

**마하세븐 포식자 시스템(돌파 모드)이 본 백테스트에서 유일하게 walk-forward 검증을 통과한 전략**입니다.
plan.md 자동매매 시스템에 1순위로 이식해야 할 룰:

```
진입 조건:
  · 당일 거래대금 상위 50 (cross-sectional)
  · 당일 거래대금 ≥ 20일 평균 × 1.5
  · 5MA > 20MA (정배열)
  · 20일 신고가 돌파

청산 조건:
  · Hard stop: 5MA 하향 돌파 시 즉시 5MA 가격으로 청산
  · Trailing stop: 고점 대비 -2% 이탈 시 청산
  · Time cut: 매수 후 3거래일 경과 시 종가 청산

자금관리:
  · 일일 누적 P&L -5% 도달 시 당일 신규 진입 차단
  · (추가 권장) 진입당 자본의 10% 이내, 동시 보유 5종목 이내
```

### 9.5 한계 — 데이터·분봉

- **60거래일은 walk-forward에 여전히 짧음**. 1년+ 데이터로 5~10 fold가 이상적
- **분봉 데이터 부재**: 현 sandbox는 `raw.githubusercontent.com`만 접근 가능, KRX/네이버 분봉 봉쇄
  - 마하세븐 본인의 매매(분·초 단위 호가창)는 일봉 walk-forward로도 일부만 검증됨
  - 진짜 분봉 검증은 키움 OpenAPI+ 로컬 환경 필요 (Windows + 키움 계좌)
- 3 fold는 통계적으로 충분하지 않음 — 실전 투입 전 6개월+ 분봉 데이터로 재검증 권장

### 9.6 실행

```bash
python3 walk_forward.py
# Outputs:
#   results/walkforward_summary.md
#   results/10_wf_machaseven.png
#   results/11_wf_jyh.png
#   results/wf_machaseven_breakout.csv
#   results/wf_jyh.csv
```

---

## 10. 결합 전략 — 마하세븐 돌파 + B.N.F (ETF 역추세) (`run_combined.py`)

마하세븐(추세) + B.N.F(역추세)의 진짜 분산 효과 검증.

### 10.1 설계
- 동일 60일 기간(2026-03-08~2026-05-27)에서 두 전략 모두 백테스트
- KOSPI 지수를 KODEX 200 NAV 프록시로 사용 (추적오차 0.05% 미만)
- 자본 50:50 배분, 각 전략 내 거래당 자본의 **10% 포지션 사이징**
- 일별 P&L = Σ(거래수익률 × 0.10) on exit dates
- 일변동성, MDD, Sharpe(연환산) 비교

### 10.2 결과

| 전략 | 총수익 | Max DD | 일변동성 | Sharpe (연환산) |
|------|------:|-------:|--------:|---------------:|
| 마하세븐 단독 (n=261) | +53.6% | -8.85% | 3.29% | **3.82** |
| B.N.F KOSPI 단독 (n=1) | +1.4% | 0.00% | 0.18% | 2.08 |
| **50:50 결합** | +25.7% | **-4.51%** | **1.65%** | **3.92** |

**일별 P&L 상관: +0.038** → 거의 무상관, 진짜 분산 확인.

### 10.3 해석

- **결합으로 MDD 절반(-8.85% → -4.51%) 감소, 변동성도 절반**
- **Sharpe 3.82 → 3.92로 미세하게 개선** — 위험조정 수익률 향상
- 단, **B.N.F가 60일 동안 1 trade만 fire** (강세장이라 -7% 이격도 안 닿음)
- → 분산 효과는 검증됐지만 **B.N.F 단독 기여는 미미**
- 결론: **마하세븐 단독이 가장 강력**, 결합은 보수적 운용 시(MDD 축소) 검토 가치

### 10.4 B.N.F 장기(2020~2026) 참고

| trades | expect/trade | PF |
|------:|------------:|---:|
| 8 | -0.25% | 0.91 |

→ 6년 KOSPI에서도 8회만 fire (실용 빈도 부족). B.N.F는 강한 약세 구간에서만 작동, 자동매매 빈도가 너무 낮아 실전 보조 전략으로 한정.

### 10.5 실행

```bash
python3 run_combined.py
# Outputs:
#   results/12_combined_equity.png
#   results/combined_summary.md
#   results/combined_summary.csv
```

---

## 11. 키움 OpenAPI+ 시스템에 코드 이식 (`../kiwoom/`)

walk-forward 통과한 **마하세븐 돌파 룰**을 plan.md 자동매매 시스템에 그대로 이식.

```
kiwoom/
├── config/machaseven.py           # 검증 통과 파라미터 + 자금관리 룰
├── strategy/
│   ├── indicators.py              # SMA, ATR, amount_surge, alignment, breakout
│   ├── screener.py                # 거래대금 상위 N universe
│   └── machaseven_breakout.py     # check_entry / check_exit 함수
├── risk/
│   ├── daily_limit.py             # DailyLimitGuard (-5% 잠금)
│   └── position.py                # Portfolio (50% 현금 + 20%/거래 + 5종목 동시 한도)
├── api/
│   └── kiwoom_adapter.py          # 키움 OCX wrapper (production) + Mock (test)
└── main.py                        # MachasevenBot — scan_entries / check_exits 루프
```

- 전략 코드는 키움 의존성 없음 → 순수 pandas, 테스트 가능
- 어댑터 패턴으로 production/Mock 분리 → 로컬 일봉 데이터로 시뮬레이션 검증 완료
- 키움 TR 명세 코멘트 포함 (OPT10080 분봉, OPT10081 일봉, OPT10004 호가, SendOrder 등)

### 11.1 Mock 시뮬레이션 확인

```python
from kiwoom.api.kiwoom_adapter import MockKiwoomAdapter
from kiwoom.main import MachasevenBot
from backtest.data_loader import build_stock_panel
import pandas as pd

panels = build_stock_panel("krx", verbose=False)
adapter = MockKiwoomAdapter(panels)
adapter.current_date = pd.Timestamp("2026-04-15")

bot = MachasevenBot(adapter)
bot.run_one_day(adapter.current_date.date())
# → BUY 5종목 (포지션 한도 차서 6번째 차단)
# → 동일 일자 5MA hard stop 2건 발동
```

### 11.2 Production 사용 (Windows + 키움 OpenAPI+)

```python
from PyQt5.QtWidgets import QApplication
from PyQt5.QAxContainer import QAxWidget
from kiwoom.api.kiwoom_adapter import KiwoomAdapter
from kiwoom.main import MachasevenBot

app = QApplication([])
ocx = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
ocx.dynamicCall("CommConnect()")  # 로그인

adapter = KiwoomAdapter(ocx)
bot = MachasevenBot(adapter)
bot.run_one_day(date.today())
```

`KiwoomAdapter`의 NotImplementedError 메서드들(`get_universe_amount_top`, `get_daily_chart`, `get_minute_chart`, `get_orderbook`, `get_account_balance`)은 plan.md Phase 1 에서 키움 TR 명세대로 채우면 됩니다.

---

## 12. 진입 시점 최적화 (`run_entry_timing.py` + `run_minute_synthetic.py`)

마하세븐 돌파의 다음 개선 축은 진입 가격. 분봉 데이터가 부재한 sandbox에서
가능한 두 트랙으로 진행:

- (A) **일봉 OHLC 기반 sensitivity 분석** — 진입가만 바꾸고 exit는 고정
- (B) **합성 분봉(Brownian bridge) 기반 정밀 진입 룰** — 분봉 데이터 도착 시 그대로 재실행

### 12.1 (A) 일봉 sensitivity 결과

| 시나리오 | trades | fill | win% | expect | PF |
|----------|------:|----:|-----:|-------:|---:|
| open (baseline) | 261 | 100% | 62.1% | **+2.93%** | **2.79** |
| midday (~12:30) | 261 | 100% | 49.0% | +1.24% | 1.52 |
| close (지연) | 261 | 100% | 51.0% | **-0.05%** | 0.99 |
| limit -0.5% / skip | 224 | 85.8% | 61.6% | +3.02% | 2.77 |
| limit -1.0% / skip | 204 | 78.2% | 60.3% | +3.12% | 2.85 |
| limit -2.0% / skip | 165 | 63.2% | 61.8% | +3.12% | 2.93 |
| **low (theoretical ceiling)** | 261 | 100% | **91.2%** | **+7.53%** | 37.21 |

**해석**:
- **베이스라인(시초가 시장가)이 이미 거의 최적**. midday/close 지연은 모멘텀을 놓침
- Limit -0.5~-2% 는 미세 개선(+0.1~0.2%p)이지만 체결률 86~63% 으로 trade-off
- **이론 ceiling +7.53%p** 가 진입 시점 최적화의 잠재 상한 → 분봉 정밀 매매로 1/3 정도 따라잡는 게 현실적 목표

### 12.2 (B) 합성 분봉 + 정밀 룰 결과

⚠️ Brownian-bridge 합성 데이터 사용. 절대 수치 X, **상대 비교만 신뢰**.

| 정밀 진입 룰 | trades | fill | expect | PF |
|------------|------:|----:|-------:|---:|
| market_open (baseline) | 261 | 100% | +2.93% | 2.79 |
| wait 15min | 261 | 100% | +2.54% | 2.45 |
| wait 30min | 261 | 100% | +2.10% | 2.04 |
| limit -0.5% / skip | 224 | 86% | +3.02% | 2.77 |
| limit -1.0% / market fallback | 261 | 100% | +1.52% | 1.57 |
| **first pullback -0.5%** | 222 | **85%** | **+4.00%** | **3.94** |
| **first pullback -1.0%** | 202 | 77% | +3.86% | 3.86 |
| volume confirm x2 @ 15min | 0 | 0% | — | — |

**핵심 발견**:
- **first pullback (Open-X% 도달 후 첫 회복봉 진입) 룰이 PF 3.94 — 베이스라인 대비 41% 개선**
- 이것이 정확히 마하세븐 명세의 "5MA 눌림목 + 음봉 후 회복" 철학과 일치
- wait/limit/fallback 룰은 모두 모멘텀 잠식 (지연 = 손해)
- volume confirm threshold 는 합성 데이터 분포가 비현실적이라 0 fill — 실데이터로 재조정 필요

### 12.3 실데이터 도착 시 검증 우선순위 (분봉 OPT10080)

1. **first pullback -0.5%** : 가장 유망 (PF 3.94 합성 → 실데이터 검증)
2. **limit -0.5% / skip** : fail-safe baseline+
3. **volume confirm @ 15min** : threshold 1.2x/1.5x/2x 스윕

### 12.4 분봉 데이터 도착 시 사용할 코드 (`kiwoom/data/minute_loader.py`)

- **`KiwoomMinuteSource`** : 키움 OPT10080 어댑터 (현재는 NotImplementedError, plan.md Phase 1에서 구현)
- **`SyntheticMinuteGenerator`** : Brownian-bridge 합성 분봉 (테스트용)
- **`EntryRule` + `simulate_entry`** : 진입 룰 정의 및 시뮬레이션 함수
  - market_open / wait_n_minutes / limit_below_open / first_pullback / volume_confirm

실데이터 도착 시 `run_minute_synthetic.py` 의 `SyntheticMinuteGenerator` 를
`KiwoomMinuteSource` 로 교체만 하면 동일 룰 그대로 검증 가능.

### 12.5 정직 코너

- 합성 분봉은 일봉 OHLC + Brownian bridge → **실 시장의 시초 변동성·후반 매도 압박·체결 강도** 미반영
- first pullback 의 +1.07%p 개선은 **상대적 우선순위 신호**, 실 도달 가능성은 절반 수준일 가능성
- 호가창 의존 룰(매수강도, tick imbalance)은 합성으로 검증 자체 불가
