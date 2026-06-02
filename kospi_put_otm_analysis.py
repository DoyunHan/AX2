#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
코스피200 외가격(OTM) 풋옵션 매수 전략 — 과거 폭락 사례 데이터 검증
================================================================

질문: "코스피가 폭락할 때, 외가격 풋옵션을 미리 사두면 정말 큰 수익이 나는가?"

이 스크립트는 과거 5대 폭락 국면(2008·2011·2018·2020·2024)에 대해
폭락 약 1개월 전에 OTM 풋을 매수했다고 가정하고, 저점에서의
이론가(Black-Scholes)를 계산하여 수익배수를 검증한다.

핵심 메커니즘
-------------
OTM 풋의 폭락장 수익은 두 가지 힘의 곱(乘)으로 발생한다.
  (1) 델타(Delta): 지수가 행사가를 향해/뚫고 내려가며 내재가치가 폭증
  (2) 베가(Vega): 공포로 내재변동성(VKOSPI)이 15 → 45~70으로 급등하며
                  시간가치가 동시에 폭증
두 효과가 동시에 터지기 때문에, 등가격(ATM)보다 깊은 외가격일수록
'배수' 기준 수익률이 폭발적으로 커진다(레버리지 효과).

주의: 본 분석은 교육/연구 목적의 사후(事後) 시나리오이며 투자 권유가 아니다.
      실제 거래에는 매도 호가 스프레드, 유동성, 그리고 무엇보다 '타이밍'
      리스크가 존재한다. 폭락이 만기 전에 오지 않으면 프리미엄은 0으로 소멸한다.
      (스크립트 하단의 base-rate 시뮬레이션 참조)

표준 라이브러리만 사용(numpy/scipy 불필요).
"""

import math
import json
from datetime import date


# --------------------------------------------------------------------------
# 1. Black-Scholes (유럽형 — 코스피200 옵션은 유럽형)
# --------------------------------------------------------------------------
def _norm_cdf(x):
    """표준정규 누적분포함수 (math.erf 이용, 외부 의존성 없음)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, K, T, sigma, r=0.02, q=0.0):
    """
    유럽형 풋 이론가.
      S     : 기초자산(지수) 현재가
      K     : 행사가
      T     : 잔존만기(연 단위)
      sigma : 내재변동성(소수, 예: 0.45 = 45%)
      r     : 무위험금리, q: 배당수익률
    """
    if T <= 0:
        return max(K - S, 0.0)
    if sigma <= 0:
        return max(K * math.exp(-r * T) - S * math.exp(-q * T), 0.0)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


# --------------------------------------------------------------------------
# 2. 과거 폭락 사례 데이터셋
#    (지수 종가·일자는 공개 자료 기준, IV는 VKOSPI/실현변동성 기반 추정)
#    * VKOSPI는 2009-04 도입 → 2008년은 실현변동성 기반 추정치 사용
# --------------------------------------------------------------------------
EVENTS = [
    {
        "key": "2008_GFC",
        "name": "2008 글로벌 금융위기",
        "desc": "리먼 사태 → 신용경색. 코스피 사상최고(2,064.85, 07-10-31) 대비 -54.5%.",
        "entry_date": "2008-09-24", "entry_level": 1430.0,
        "trough_date": "2008-10-24", "trough_level": 938.75,
        "iv_entry": 0.30, "iv_exit": 0.70, "r": 0.05,
        "note": "VKOSPI 도입 전. IV는 당시 실현변동성 기반 추정.",
    },
    {
        "key": "2011_EU",
        "name": "2011 유럽 재정위기·美 신용강등",
        "desc": "S&P의 미국 신용등급 강등 + 유로존 위기. 8/2~8/9 6거래일 연속 -2%대.",
        "entry_date": "2011-08-01", "entry_level": 2172.0,
        "trough_date": "2011-08-19", "trough_level": 1744.0,
        "iv_entry": 0.20, "iv_exit": 0.42, "r": 0.0325,
        "note": "옵션 수명 내 저점(8/19). 이후 9월 말 1,652까지 추가 하락.",
    },
    {
        "key": "2018_TRADE",
        "name": "2018 미·중 무역분쟁 (검은 10월)",
        "desc": "연초 사상최고(2,598.19, 01-29) 후 무역전쟁·금리인상 우려로 조정.",
        "entry_date": "2018-10-01", "entry_level": 2338.88,
        "trough_date": "2018-10-29", "trough_level": 1996.05,
        "iv_entry": 0.14, "iv_exit": 0.28, "r": 0.015,
        "note": "상대적으로 완만한 -15% 조정. VKOSPI 28 부근.",
    },
    {
        "key": "2020_COVID",
        "name": "2020 코로나 팬데믹 쇼크",
        "desc": "한 달 만에 -34%. VKOSPI 사상최고 69.24(장중 ~71). 교과서적 사례.",
        "entry_date": "2020-02-19", "entry_level": 2210.0,
        "trough_date": "2020-03-19", "trough_level": 1457.64,
        "iv_entry": 0.14, "iv_exit": 0.69, "r": 0.0125,
        "note": "지수 급락 + IV 폭등이 동시 발생한 최적 사례.",
    },
    {
        "key": "2024_YEN",
        "name": "2024.8 엔캐리 청산 (블랙 먼데이)",
        "desc": "8/5 하루 -8.77%(역대 최대 낙폭, 종가 2,441.55). VKOSPI 하루 +110% → 45.86.",
        "entry_date": "2024-07-11", "entry_level": 2891.35,
        "trough_date": "2024-08-05", "trough_level": 2441.55,
        "iv_entry": 0.16, "iv_exit": 0.46, "r": 0.035,
        "note": "초단기 급락. 며칠 만에 반등 → '저점 매도(익절)' 타이밍이 관건.",
    },
]

# 외가격 수준 (행사가 = 진입지수 × (1 - OTM))
OTM_LEVELS = [0.0, 0.025, 0.05, 0.075, 0.10]   # ATM, -2.5%, -5%, -7.5%, -10%

# 만기 가정: 진입 시 잔존 45일, 저점까지 보유 → 잔존만기 = (45일 - 보유일수)
ENTRY_DTE = 45  # 진입 시점 잔존만기(일)


def _days(d1, d2):
    a = date.fromisoformat(d1)
    b = date.fromisoformat(d2)
    return (b - a).days


def analyze_event(ev):
    S0 = ev["entry_level"]
    S1 = ev["trough_level"]
    held = _days(ev["entry_date"], ev["trough_date"])
    T_entry = ENTRY_DTE / 365.0
    T_exit = max(ENTRY_DTE - held, 1) / 365.0   # 저점 도달 시 잔존만기(최소 1일)
    drop_pct = (S1 / S0 - 1.0) * 100.0

    rows = []
    for otm in OTM_LEVELS:
        K = S0 * (1.0 - otm)
        # 진입 프리미엄 (평시 IV)
        entry = bs_put(S0, K, T_entry, ev["iv_entry"], ev["r"])
        # 저점 청산가 (델타+베가, 공포 IV)
        exit_full = bs_put(S1, K, T_exit, ev["iv_exit"], ev["r"])
        # 비교: IV 변화 없었다면 (델타 효과만 분리)
        exit_delta_only = bs_put(S1, K, T_exit, ev["iv_entry"], ev["r"])
        # 만기까지 보유 시 내재가치만 (시간가치·베가 소멸 시나리오)
        intrinsic = max(K - S1, 0.0)

        mult_full = exit_full / entry if entry > 1e-9 else float("inf")
        mult_delta = exit_delta_only / entry if entry > 1e-9 else float("inf")
        mult_intr = intrinsic / entry if entry > 1e-9 else float("inf")

        rows.append({
            "otm": otm,
            "strike": round(K, 2),
            "entry_prem": round(entry, 3),
            "exit_prem": round(exit_full, 3),
            "exit_delta_only": round(exit_delta_only, 3),
            "intrinsic": round(intrinsic, 3),
            "mult_full": round(mult_full, 2),
            "mult_delta_only": round(mult_delta, 2),
            "mult_intrinsic": round(mult_intr, 2),
            "ret_full_pct": round((mult_full - 1.0) * 100.0, 1),
        })

    return {
        "key": ev["key"], "name": ev["name"], "desc": ev["desc"], "note": ev["note"],
        "entry_date": ev["entry_date"], "trough_date": ev["trough_date"],
        "entry_level": S0, "trough_level": S1,
        "held_days": held, "drop_pct": round(drop_pct, 1),
        "iv_entry": ev["iv_entry"], "iv_exit": ev["iv_exit"],
        "rows": rows,
    }


# --------------------------------------------------------------------------
# 3. Base-rate 현실 점검: '매달 -5% OTM 풋을 사두면?'
#    평상시(폭락 없는 달)에는 만기에 0으로 소멸 → -100%.
#    폭락 1회의 대박이 '몇 달치 보험료'를 회수하는지 계산.
# --------------------------------------------------------------------------
def base_rate_check():
    # 평상시 한 달물 -5% OTM 풋: IV 15%, 30일물 → 만기 0 소멸 가정
    S = 100.0
    K = 95.0
    monthly_prem = bs_put(S, K, 30 / 365.0, 0.15, 0.03)   # 지수 100 기준 프리미엄
    # 2020 코로나급 대박 1회 수익배수(전체 표에서 -5% OTM full multiple) 사용
    return monthly_prem


def main():
    results = [analyze_event(ev) for ev in EVENTS]

    print("=" * 78)
    print(" 코스피200 OTM 풋옵션 매수 — 과거 폭락 사례 백테스트 (Black-Scholes 모델)")
    print("=" * 78)
    print(f"  공통 가정: 진입 시 잔존만기 {ENTRY_DTE}일, 저점에서 익절 청산")
    print(f"  수익배수(×) = 저점 청산가 / 진입 프리미엄")
    print()

    for R in results:
        print("-" * 78)
        print(f"■ {R['name']}")
        print(f"  {R['desc']}")
        print(f"  진입 {R['entry_date']} @ {R['entry_level']:.2f}  →  "
              f"저점 {R['trough_date']} @ {R['trough_level']:.2f}  "
              f"({R['drop_pct']:+.1f}%, {R['held_days']}일)")
        print(f"  내재변동성(IV): {R['iv_entry']*100:.0f}%  →  {R['iv_exit']*100:.0f}%   "
              f"({R['note']})")
        print()
        print(f"   {'외가격':>7} | {'행사가':>9} | {'진입료':>8} | {'청산가':>9} | "
              f"{'수익배수':>8} | {'델타만':>7} | {'만기보유':>8}")
        print(f"   {'-'*7} | {'-'*9} | {'-'*8} | {'-'*9} | {'-'*8} | {'-'*7} | {'-'*8}")
        for row in R["rows"]:
            otm_label = "ATM" if row["otm"] == 0 else f"-{row['otm']*100:.1f}%"
            print(f"   {otm_label:>7} | {row['strike']:>9.1f} | "
                  f"{row['entry_prem']:>8.2f} | {row['exit_prem']:>9.1f} | "
                  f"{row['mult_full']:>7.1f}× | {row['mult_delta_only']:>6.1f}× | "
                  f"{row['mult_intrinsic']:>7.1f}×")
        print()

    # Base rate
    mp = base_rate_check()
    # 2020 -5% OTM full multiple
    covid = next(R for R in results if R["key"] == "2020_COVID")
    covid_5otm = next(r for r in covid["rows"] if r["otm"] == 0.05)
    breakeven_months = covid_5otm["mult_full"]
    print("=" * 78)
    print(" Base-rate 현실 점검 — '매달 -5% OTM 풋을 보험처럼 산다면?'")
    print("=" * 78)
    print(f"  · 평상시 30일물 -5% OTM 풋 프리미엄 ≈ 지수의 {mp:.3f}% "
          f"(폭락 없는 달엔 만기 0 소멸 = -100%)")
    print(f"  · 2020 코로나급 1회 수익배수(-5% OTM) ≈ {covid_5otm['mult_full']:.0f}×")
    print(f"  · 즉, 대박 1회(+{covid_5otm['ret_full_pct']:.0f}%)로 약 "
          f"{breakeven_months:.0f}개월치 '꽝' 프리미엄을 회수 가능")
    print(f"  ⇒ 핵심은 '폭락이 만기 전에 오느냐'(타이밍). 안 오면 매달 프리미엄이 녹는다.")
    print()

    # JSON 덤프 (HTML 리포트가 소비)
    out = {
        "assumptions": {
            "entry_dte_days": ENTRY_DTE,
            "model": "Black-Scholes (European put)",
            "otm_levels": OTM_LEVELS,
            "monthly_5otm_premium_pct": round(mp, 3),
        },
        "events": results,
    }
    with open("kospi_put_otm_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("→ 결과 저장: kospi_put_otm_results.json")


if __name__ == "__main__":
    main()
