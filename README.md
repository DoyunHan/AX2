# Overnight Gainers Toolkit

미국 소형주 "하룻밤 급등" 현상을 **이해하고, 후보를 거르고, 결과를 보는** 교육용 도구 모음.

> ⚠️ **면책:** 교육·정보 목적이며 투자 권유가 아닙니다. 여기 다루는 저플로팅 소형주는
> 변동성과 손실 위험이 극단적입니다. 점수는 **예측이 아니라 조건 충족도(0~100)**입니다.

---

## 구성

| 파일 | 설명 | 여는 법 |
|------|------|---------|
| `overnight-gainers-guide.html` | 교육용 페이지 — 폭등 5유형, 4대 필터, 도구, 리스크(거래정지·롤백·희석) | 브라우저 |
| `screener.py` | 후보 스크리너 — 저플로팅·공매도·갭·거래량·소셜 거론량·가격대 → 0~100 점수 | 터미널 |
| `results.html` | 스크리너 결과 뷰어 — `candidates.json`을 표/점수바/플래그로 표시 | 브라우저 |
| `catalyst-calendar.html` | 카탈리스트 캘린더 — PDUFA·임상·실적·락업·지수리밸런싱 | 브라우저 |

---

## 시작하기 (노트북 터미널)

```bash
# 1) 저장소 클론 + 작업 브랜치로 전환
git clone <repo-url> AX2
cd AX2
git checkout claude/overnight-stock-gainers-ovd5X
git pull origin claude/overnight-stock-gainers-ovd5X   # 최신 동기화

# 2) 요구사항 (Python 3.9+)
python3 --version
pip install requests        # 라이브 데이터용 (데모만 쓰면 없어도 됨)
```

> 이미 클론돼 있으면 위 2줄(`git checkout` + `git pull`)만 하면 됩니다.

---

## 스크리너 사용법

```bash
# 오프라인 데모 (네트워크 불필요 — 동작 확인용)
python3 screener.py --demo

# 라이브 (Yahoo Finance + StockTwits, API 키 불필요)
python3 screener.py

# 결과를 파일로 저장 → results.html 로 보기
python3 screener.py --out candidates
#   → candidates.json / candidates.csv 생성

# 주요 옵션
python3 screener.py --max-float 20 --min-change 10 --top 25
python3 screener.py --trending          # StockTwits 인기 심볼도 후보에 추가
python3 screener.py --social none        # 소셜 신호 끄기
python3 screener.py -h                    # 전체 옵션
```

### 옵션 요약

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--demo` | off | 오프라인 합성 데이터로 시연 |
| `--provider {yahoo,demo}` | yahoo | 시세/펀더멘털 소스 |
| `--social {auto,stocktwits,demo,none}` | auto | 소셜 거론량 소스 |
| `--trending` | off | StockTwits 인기 심볼을 후보 풀에 추가 |
| `--min-change` | 5.0 | 최소 변동률(%) 필터 |
| `--max-float` | 없음 | 최대 유통주식(백만 주) 필터 |
| `--top` | 20 | 상위 N개만 출력 |
| `--out <stem>` | 없음 | `<stem>.json` / `<stem>.csv` 저장 |

### 점수 구성 (가중치 합 = 1.0)

| 축 | 가중치 | 의미 |
|----|--------|------|
| 저플로팅 | 0.25 | 유통주식 적을수록 ↑ (공급 부족) |
| 공매도 비중 | 0.20 | 높을수록 ↑ (스퀴즈 연료) |
| 갭/변동률 | 0.18 | 클수록 ↑ (모멘텀) |
| 상대거래량 | 0.17 | 급증할수록 ↑ (수급) |
| 소셜 거론량 | 0.15 | 평소 대비 급증 ↑ (리테일 FOMO) |
| 가격대 | 0.05 | $1~$20 가산 |

**플래그:** `LOW_FLOAT` `HIGH_SHORT` `BIG_GAP` `VOL_SPIKE` `SOCIAL_SURGE` `CATALYST`(긍정)
· `NO_CATALYST?` `SUB_DOLLAR`(⚠️ 위험 — 이유 불명/동전주).
점수가 높아도 `NO_CATALYST?`면 작전(펌프) 의심 신호.

---

## 결과 보는 3가지 방법

1. **터미널** — 실행 즉시 표가 출력됨 (저장 옵션 없이도)
2. **파일** — `--out candidates` → `candidates.csv`(엑셀) / `candidates.json`
3. **브라우저 대시보드** — `results.html` 열고 `candidates.json` 불러오기

### results.html 사용
```bash
python3 screener.py --out candidates     # candidates.json 생성
```
- `results.html`을 브라우저로 열고 **파일을 끌어다 놓거나 "파일 선택"**으로 `candidates.json` 불러오기
- 처음 열면 내장 데모 데이터가 보임
- 정렬(헤더 클릭)·검색·최소점수·"카탈리스트만" 필터 지원

> **CORS 주의:** `file://`로 직접 열면 자동 로드가 막힙니다. "파일 선택"으로 불러오거나,
> 폴더에서 로컬 서버를 띄우면 "자동로드" 버튼이 작동합니다:
> ```bash
> python3 -m http.server 8000
> # → http://localhost:8000/results.html
> ```

---

## 데이터 소스 메모

- **시세/펀더멘털:** Yahoo Finance 공개 엔드포인트 (predefined screener + quoteSummary)
- **소셜:** StockTwits 공개 API (종목별 메시지 수/강세비율 + trending). Reddit은 OAuth 필요해
  미포함 — `screener.py`의 `StockTwitsSocial` 옆에 확장 지점 주석 표시.
- 실제 일정으로 캘린더를 채우려면: BioPharmaCatalyst(PDUFA), Nasdaq/Yahoo earnings,
  MarketBeat(락업), FTSE/Russell·S&P(지수). `catalyst-calendar.html`의 `EVENTS` 배열 편집.

---

## 작업 마무리 (커밋/푸시)

```bash
git add -A
git commit -m "작업 내용"
git push -u origin claude/overnight-stock-gainers-ovd5X
```
`candidates.json/csv`와 `__pycache__/`는 `.gitignore`로 제외됨(개인 결과물).
