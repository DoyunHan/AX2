# 코인 선물 박스권 돌파 추세추종 전략 (Box Breakout Trend)

횡보(consolidation) 구간을 **박스**로 규정하고, 박스를 이탈하는 **방향으로 진입**한 뒤
**ATR 트레일링 스탑**으로 추세를 끝까지 홀딩해 수익을 극대화하는 전략의 백테스트 모듈.

- **대상**: Binance USD-M Futures (무기한 선물)
- **기준 타임프레임**: 15m ~ 1h
- **방향**: 롱·숏 양방향 (코인 선물은 강제청산 없이 추세를 며칠이고 홀딩 가능)

> ⚠️ 교육/연구용 백테스트입니다. 합성데이터 결과는 실거래 성과를 보장하지 않습니다.
> 실거래 전 반드시 실데이터 백테스트 → 파라미터 검증 → 소액 검증 순서를 거치세요.

---

## 전략 로직

```
[1] 박스 탐지 → [2] 돌파 감지 → [3] 진입 → [4] 추세 홀딩 → [5] 청산
```

1. **박스(횡보) 규정** — 직전 `box_lookback`개 봉의 고/저 범위가
   `box_max_width_pct`(예: 4%) 이내로 압축된 구간을 박스로 인정.
2. **돌파 감지** — 종가가 박스 상단(+버퍼) 위로 마감 → 롱 / 하단(-버퍼) 아래로 마감 → 숏.
   **거짓 돌파 필터**: 돌파봉 거래량이 평균 대비 `vol_mult`(예: 1.5배) 이상일 때만 유효.
3. **진입** — 돌파봉 종가에서 체결. 포지션 크기는 손절거리 기반(자본의 `risk_per_trade`만 노출).
4. **추세 홀딩** — 고정 익절 대신 **ATR 트레일링 스탑**(`최고가 - atr_trail_mult × ATR`).
   스탑은 절대 후퇴하지 않으며, 추세가 살아있는 한 계속 보유.
5. **청산** — 트레일링 스탑 터치 / (선택)최대보유봉 초과 / 데이터 끝.
   초기 손절은 **박스 반대편 경계**(= 돌파 실패 = 박스 복귀)로, 손절폭이 박스로 자연 정의됨.

비용 모델: taker 수수료(진입·청산), 무기한 **펀딩비**(8h 주기), 레버리지·**강제청산가 안전장치** 포함.
모든 지표는 `.shift(1)`로 **미래참조(look-ahead)를 차단**합니다.

---

## 설치

```bash
# 원클릭(권장): 가상환경 + 의존성 + 테스트 + 데모
bash setup.sh
source .venv/bin/activate

# 또는 수동
pip install -r requirements.txt
```

> 노트북 등 새 환경에서 이어서 작업한다면 [`HANDOFF.md`](HANDOFF.md)부터 읽으세요
> (현재 상태·다음 할 일·시작 명령 정리).

## 빠른 시작

```bash
# 1) 오프라인 데모 — 네트워크/API 키 불필요 (합성데이터)
python run_backtest.py --demo

# 2) 실데이터 다운로드(인터넷 필요) → 백테스트
python fetch_data.py                          # BTC/ETH 1h를 data/ 에 저장
python run_backtest.py --csv data/btc_1h.csv
python analyze.py data/btc_1h.csv             # 연도별·인/아웃샘플 견고성

# 3) Binance에서 직접(단발) 백테스트
python run_backtest.py --symbol "BTC/USDT:USDT" --timeframe 1h --limit 2000

# 4) 파라미터 튜닝 / 그리드 탐색
python run_backtest.py --demo --box-width 0.015 --atr-trail 6.0 --leverage 5
python sweep.py data/btc_1h.csv
```

### 출력 예시 (데모)

```json
{
  "num_trades": 9,
  "win_rate": 0.5556,
  "total_return_pct": 24.92,
  "profit_factor": 12.88,
  "payoff_ratio": 10.3,        // 이긴 거래가 진 거래보다 평균 10배 → 추세 홀딩 효과
  "max_drawdown_pct": -1.3,
  "avg_bars_held": 48.7,
  "total_fees": 36.67,
  "total_funding": 20.54
}
```

---

## 주요 파라미터

> 기본값은 **BTC 1h 실데이터(2021~2026)로 튜닝·검증**된 값이다. 근거·검증 결과는 [`TUNING.md`](TUNING.md) 참조.

| CLI 옵션 | 의미 | 기본값 |
|---|---|---|
| `--box-lookback` | 박스를 만드는 직전 봉 수 | 48 |
| `--box-width` | 박스폭 상한 `(상단-하단)/하단` | 0.025 |
| `--vol-mult` | 돌파봉 거래량 / 평균거래량 하한(거짓돌파 필터) | 2.0 |
| `--buffer` | 박스 경계 너머 진입 버퍼 | 0.001 |
| `--atr-period` | ATR 기간 | 14 |
| `--atr-trail` | 트레일링 스탑 ATR 배수 (클수록 추세 길게 홀딩) | 8.0 |
| `--no-long` / `--no-short` | 단방향 운용 | (양방향) |
| `--max-hold` | 최대 보유 봉(0=무제한) | 0 |
| `--leverage` | 레버리지 | 3.0 |
| `--risk` | 1회 거래 리스크(자본 비율) | 0.01 |
| `--fee` | taker 수수료율 | 0.0005 |
| `--funding` | 8h당 펀딩비율(평균 가정) | 0.0001 |

### 튜닝 가이드
- **거짓 돌파가 많다** → `--vol-mult` ↑, `--buffer` ↑, `--box-width` ↓(더 타이트한 박스만)
- **추세를 너무 일찍 놓친다** → `--atr-trail` ↑ (스탑을 느슨하게)
- **드로다운이 크다** → `--risk` ↓, `--leverage` ↓
- 여러 타임프레임/심볼로 돌려 파라미터 견고성(robustness)을 확인하세요.

---

## 구조

```
crypto_box_breakout/
├── README.md
├── requirements.txt
├── run_backtest.py            # CLI 진입점
├── box_breakout/
│   ├── data.py                # Binance 다운로드 / CSV / 합성데이터
│   ├── strategy.py            # 박스 탐지 + 돌파 시그널 + ATR
│   ├── backtest.py            # 백테스트 엔진(수수료·펀딩·레버리지·청산)
│   └── metrics.py             # 성과지표(승률·손익비·MDD·샤프)
└── tests/test_strategy.py     # 미래참조 차단·정합성 검증
```

## 테스트

```bash
python tests/test_strategy.py     # 또는: pytest -q
```

---

## 다음 단계 (실거래까지)

1. **실데이터 백테스트** — BTC 1h(2021~2026) 결과·튜닝은 [`TUNING.md`](TUNING.md)에 정리됨.
   ETH 등 다른 자산 교차검증으로 견고성 추가 확인 (과최적화 주의).
2. **워크포워드 분석** — 구간을 나눠 인샘플 최적화 → 아웃샘플 검증 (`analyze.py` 참고).
3. **실시간 자동매매 봇** — WebSocket 시세 수신 + ccxt `create_order`로 진입/청산,
   현재 백테스트의 시그널·리스크 로직을 그대로 재사용 가능.
4. **운영 리스크** — API 키 권한 최소화(출금 비활성), 청산가 모니터링, 펀딩비 추적,
   거래소 점검/네트워크 단절 대비 페일세이프.
