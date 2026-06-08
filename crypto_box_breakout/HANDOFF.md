# 작업 인계 노트 (노트북에서 이어가기)

코인 선물 **박스권 돌파 추세추종 전략** 백테스트 프로젝트. 새 세션에서 이 파일부터 읽으면 맥락이 잡힌다.

## 한 줄 요약
횡보 구간을 박스로 규정 → 박스 이탈 방향으로 진입 → ATR 트레일링으로 추세 홀딩.
대상 Binance USD-M 선물, 15m~1h. BTC 1h 실데이터로 튜닝까지 완료(아웃샘플 흑자).

## 지금 바로 시작하기
```bash
git checkout claude/box-breakout-trend-strategy-7EGdB
cd crypto_box_breakout
bash setup.sh                       # .venv + 의존성 + 테스트 + 데모
source .venv/bin/activate
python fetch_data.py                # BTC/ETH 1h 실데이터 다운로드 (인터넷 필요)
python run_backtest.py --csv data/btc_1h.csv
python analyze.py data/btc_1h.csv   # 연도별·인/아웃샘플 견고성
```
> `data/`와 `*.csv`는 `.gitignore`로 커밋 제외 → 노트북에서 `fetch_data.py`로 새로 받는다.

## 현재 상태 (DONE)
- ✅ 백테스트 엔진 완성 (수수료·펀딩·레버리지·청산 안전장치·손절거리 사이징)
- ✅ 박스 탐지 + 돌파 시그널(거래량 거짓돌파 필터) + ATR 트레일링, 미래참조 차단
- ✅ BTC 1h(2021~2026, 47k봉) 실데이터 백테스트 + 99조합 스윕 튜닝
- ✅ **검증된 파라미터를 기본값으로 반영**: lookback48 / 박스폭2.5% / vol2.0 / atr_trail8
- ✅ 과최적화 점검: 아웃샘플(2024-26) +19.7%·PF1.60 — 엣지 유지. 상세 `TUNING.md`

## 핵심 수치 (BTC 1h, 레버리지3x, 리스크1%)
| | 거래 | 승률 | 수익 | PF | MDD |
|---|---|---|---|---|---|
| 튜닝 전(잘못된 기본값) | 983 | 32% | -49% | 0.73 | -51% |
| 튜닝 후(현재 기본값) | 130 | 40% | +27% | 1.5 | -10% |

## 다음 할 일 (TODO, 우선순위순)
1. **ETH/SOL 교차검증** — `python fetch_data.py` 후 `python analyze.py data/eth_1h.csv`.
   BTC 최적값이 다른 자산에서도 통하는지 확인(통하면 견고, 깨지면 과최적화).
2. **워크포워드 분석** — `analyze.py`의 단순 IN/OUT 분할을 롤링 재최적화로 확장.
   (구간마다 sweep으로 최적값 찾고 다음 구간에서 검증)
3. **슬리피지/지정가 모델** — 현재 트레일링 스탑은 스탑가 정확체결 가정. 보수적 슬리피지 추가.
4. **실시간 봇** — 검증 통과 시 `box_breakout`의 시그널/리스크 로직을 재사용해
   WebSocket 시세 수신 + ccxt `create_order`로 진입/청산. API 키는 출금 비활성·읽기/거래만.

## 파일 안내
| 파일 | 역할 |
|---|---|
| `box_breakout/strategy.py` | 박스/돌파/ATR — **기본 파라미터 위치** |
| `box_breakout/backtest.py` | 백테스트 엔진 |
| `box_breakout/data.py` | fetch_binance / load_csv / generate_synthetic |
| `box_breakout/metrics.py` | 성과지표 |
| `run_backtest.py` | 단일 백테스트 CLI (`--demo`, `--csv`, `--symbol`) |
| `sweep.py` | 파라미터 그리드 탐색 |
| `analyze.py` | 연도별·인/아웃샘플 검증 |
| `fetch_data.py` | 실데이터 다운로드 |
| `TUNING.md` | 튜닝 방법론·결과·한계 |

## 막혔던 점 / 주의
- 이 클라우드 환경은 거래소 API가 403 차단이라 BTC 데이터를 GitHub LFS 데이터셋에서 받았다.
  **노트북은 인터넷이 되므로 `fetch_data.py`(ccxt)로 바로 받으면 된다** — LFS 우회 불필요.
- 견고형(박스폭1.5%)은 거래 29건으로 표본이 적다 → 여러 자산 동시적용으로 표본 확보 권장.
- 펀딩비는 평균 가정값(0.01%/8h). 정밀하게 하려면 실제 펀딩 시계열 반영.
