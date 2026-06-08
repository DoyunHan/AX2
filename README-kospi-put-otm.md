# 코스피 외가격(OTM) 풋옵션 폭락장 수익 — 데이터 검증 프로젝트

> 브랜치: `claude/kospi-put-otm-analysis-SOzQT`
> "코스피가 폭락할 때 외가격 풋옵션을 미리 사두면 정말 큰 수익이 나는가?"를
> 과거 5대 폭락(2008·2011·2018·2020·2024) 데이터 + Black-Scholes로 검증한 분석.
> **교육·연구용 사후 분석이며 투자 권유가 아니다.**

---

## 💻 노트북 터미널에서 이어받기

```bash
# 1) 저장소가 없으면 클론
git clone <REPO_URL> AX2 && cd AX2
# 이미 있으면 최신화
git fetch origin

# 2) 작업 브랜치로 전환
git checkout claude/kospi-put-otm-analysis-SOzQT
git pull origin claude/kospi-put-otm-analysis-SOzQT

# 3) 실행 (Python 3.8+ , 추가 설치 불필요 — 표준 라이브러리만 사용)
python3 kospi_put_otm_analysis.py     # 과거 5대 폭락 백테스트
python3 kospi_put_now_scenario.py     # ② '지금(2026-06) 사면?' 시나리오
python3 kospi_put_validation.py       # ① 실측 검증 (모델 vs 실제 체결가)

# 4) 시각화 리포트는 브라우저로 열기
#    macOS:  open kospi-put-otm-analysis.html
#    Linux:  xdg-open kospi-put-otm-analysis.html
```

> 의존성: 없음(`math`, `json`, `datetime`만 사용). 가상환경·pip 설치 불필요.
> 커밋 규칙: 변경은 위 브랜치에 커밋 후 `git push -u origin <branch>`.

---

## 📁 파일 구성

| 파일 | 역할 | 재현 명령 |
|------|------|-----------|
| `kospi_put_otm_analysis.py` | **핵심 엔진** — Black-Scholes 풋 + 5대 폭락 백테스트 | `python3 kospi_put_otm_analysis.py` |
| `kospi_put_now_scenario.py` | ② 현재(2026-06, 고VKOSPI) 진입 시나리오 | `python3 kospi_put_now_scenario.py` |
| `kospi_put_validation.py` | ① 모델 vs 실제 기록된 옵션 체결가 검증 | `python3 kospi_put_validation.py` |
| `kospi-put-otm-analysis.html` | 시각화 리포트(자체 완결형) | 브라우저로 열기 |
| `kospi-put-otm-analysis.md` | 전체 결과 요약(①②포함) | 텍스트 열람 |
| `kospi_put_*_results.json` | 각 스크립트 산출 데이터 | 자동 생성 |

> `kospi_put_now_scenario.py`·`kospi_put_validation.py`는 `kospi_put_otm_analysis.py`의
> `bs_put()`를 import해 재사용한다. 셋은 같은 디렉터리에 있어야 한다.

---

## 🔑 결론 3줄

1. **과거 5대 폭락 모두에서 외가격 풋은 수 배~수백 배 가능**했다(2020 -10% OTM 약 983×).
   동력은 *델타(지수 하락) × 베가(공포로 IV 급등)*. 모델은 실제 '400배' 사례도 재현(§①).
2. **알파는 'IV 낮을 때 미리 사두는 것'에서 나온다.** 지금(2026-06)은 VKOSPI가 이미 65~70이라
   같은 폭락이라도 배수가 약 176배 압축된다(§②).
3. **핵심 리스크는 수익률이 아니라 타이밍.** 폭락이 만기 전에 안 오면 프리미엄은 전액 소멸(-100%).
   기록에 남은 대박은 모두 '성공한 베팅'만의 생존편향이다.

---

## 🛠 다음에 할 수 있는 작업 (TODO)

- [ ] **HTML 리포트에 ①②섹션 시각화 추가** (현재 HTML은 과거 백테스트 중심).
- [ ] **KRX 실데이터 정밀 재검증**: `pykrx`로 특정 행사가·일자의 실제 일별 종가 전수 수집.
      ⚠ 현재 원격 환경은 네트워크 allowlist로 `data.krx.co.kr` 차단 → **로컬(노트북)에서는 가능**.
      ```bash
      pip install pykrx
      # 예: 2020-03 코스피200 옵션 일별 시세 조회 후 모델과 대조
      ```
- [ ] 변동성 스큐를 실제 KRX IV 곡면으로 교체(현재는 근사 기울기 가정).
- [ ] 거래비용·호가 스프레드를 반영한 '실현 가능' 수익률로 보정.

---

*면책: 옵션 매수는 원금 전액 손실이 빈번한 고위험 거래다. 본 자료는 정량 분석·교육 목적이며
투자 자문이 아니다. 모든 가격은 Black-Scholes 이론가 추정치다.*
