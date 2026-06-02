#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
②"지금 사면?" — 2026-06 시점 코스피 OTM 풋옵션 시나리오 분석
=============================================================

과거 검증(kospi_put_otm_analysis.py)은 '폭락이 오면 외가격 풋이 수백 배가 됐다'를
보였다. 그러나 그 대박의 전제는 **진입 시점의 낮은 변동성(IV 14~20%)** 이었다.
'싸게 사서 공포에 판다'가 핵심이기 때문이다.

문제: 2026년 6월 현재는 정반대 국면이다.
  · 코스피 사상 최고권(≈8,500, AI·반도체 랠리, 버핏지수 256% 과열)
  · 그런데 VKOSPI가 이미 ~65~70 (5/18 장중 82.23) — '공포가 이미 비싸게 선반영'
즉 외가격 풋을 **지금** 사면 진입 IV가 ~68%로, 역사적 대박 케이스(IV 14%)보다
3~5배 비싸다. 베가(변동성 급등) 여력도 줄었다(이미 높아서 더 오를 폭이 작다).

이 스크립트는 동일한 Black-Scholes 엔진으로:
  (A) '지금' 진입(IV 68%) 시 폭락 시나리오별 수익배수
  (B) '평시 IV(15%)에 샀다면'의 반사실(counterfactual) 비교 → 비싼 진입의 대가
를 계산한다. (교육용 시나리오, 투자 권유 아님)
"""

import math
import json
from kospi_put_otm_analysis import bs_put   # 동일 BS 엔진 재사용


# ---- 2026-06-02 시점 시장 가정 (공개 보도 기반 근사치) -------------------
TODAY_KOSPI   = 8500.0     # 코스피 사상 최고권 (≈8,500)
ENTRY_IV_NOW  = 0.68       # 현재 VKOSPI ≈ 65~70 (이미 '공포존')
ENTRY_IV_CALM = 0.15       # 반사실: 만약 평시처럼 쌌다면
R             = 0.025      # 무위험금리 근사

ENTRY_DTE   = 40           # 진입 시 잔존만기(일) — 근월물 가정
DAYS_HELD   = 28           # 폭락까지 보유일수 → 청산 시 잔존 12일
T_ENTRY = ENTRY_DTE / 365.0
T_EXIT  = (ENTRY_DTE - DAYS_HELD) / 365.0

# 코스피200 옵션 실거래 최소 호가(프리미엄 하한). 이보다 싼 풋은 사실상
# 호가가 없어 거래 불가 → 배수 계산이 의미 없으므로 'n/a'로 표기.
MIN_TRADEABLE = 0.01

OTM_LEVELS = [0.0, 0.05, 0.10, 0.15, 0.20]   # ATM ~ -20% OTM

# 폭락 시나리오: (낙폭, 청산 시점 IV)
#  현재 IV가 이미 높으므로 추가 상승 여력은 제한적(80~110)으로 가정
CRASH = [
    ("조정  -10%", 0.10, 0.80),
    ("급락  -20%", 0.20, 0.95),
    ("패닉  -30%", 0.30, 1.10),
]


def scenario(entry_iv):
    out = []
    for otm in OTM_LEVELS:
        K = TODAY_KOSPI * (1.0 - otm)
        entry = bs_put(TODAY_KOSPI, K, T_ENTRY, entry_iv, R)
        tradeable = entry >= MIN_TRADEABLE
        legs = []
        for label, drop, exit_iv in CRASH:
            S1 = TODAY_KOSPI * (1.0 - drop)
            exitp = bs_put(S1, K, T_EXIT, exit_iv, R)
            mult = round(exitp / entry, 1) if tradeable else None
            legs.append({"label": label, "drop": drop, "exit_iv": exit_iv,
                         "exit_prem": round(exitp, 2), "mult": mult})
        out.append({"otm": otm, "strike": round(K, 1),
                    "entry_prem": round(entry, 2), "tradeable": tradeable, "legs": legs})
    return out


def main():
    now  = scenario(ENTRY_IV_NOW)
    calm = scenario(ENTRY_IV_CALM)

    def crash_label(i): return CRASH[i][0]

    print("=" * 80)
    print(" ②'지금 사면?' — 2026-06 코스피 OTM 풋 시나리오 (Black-Scholes)")
    print("=" * 80)
    print(f"  현재가정: 코스피 {TODAY_KOSPI:.0f} · 진입 IV(현 VKOSPI) {ENTRY_IV_NOW*100:.0f}%")
    print(f"  옵션: 잔존 {ENTRY_DTE}일 진입 → 폭락까지 {DAYS_HELD}일 보유(잔존 {ENTRY_DTE-DAYS_HELD}일 익절)")
    print(f"  수익배수(×) = 폭락 후 청산가 / 진입 프리미엄\n")

    print("[A] 지금 IV(68%)에 매수 — 폭락 시나리오별 수익배수")
    print(f"   {'외가격':>7} | {'행사가':>8} | {'진입료':>8} | "
          f"{crash_label(0):>10} | {crash_label(1):>10} | {crash_label(2):>10}")
    print("   " + "-"*7 + " | " + "-"*8 + " | " + "-"*8 + " | "
          + "-"*10 + " | " + "-"*10 + " | " + "-"*10)
    def fmt(leg):
        return "n/a" if leg["mult"] is None else f"{leg['mult']:.1f}×"

    for row in now:
        lab = "ATM" if row["otm"] == 0 else f"-{int(row['otm']*100)}%"
        m = [fmt(leg) for leg in row["legs"]]
        print(f"   {lab:>7} | {row['strike']:>8.0f} | {row['entry_prem']:>8.1f} | "
              f"{m[0]:>10} | {m[1]:>10} | {m[2]:>10}")

    print("\n[B] 반사실: 평시 IV(15%)에 샀다면 같은 폭락의 배수 (역사적 대박 조건)")
    print(f"   {'외가격':>7} | {'진입료':>8} | "
          f"{crash_label(0):>10} | {crash_label(1):>10} | {crash_label(2):>10}")
    print("   " + "-"*7 + " | " + "-"*8 + " | " + "-"*10 + " | " + "-"*10 + " | " + "-"*10)
    for row in calm:
        lab = "ATM" if row["otm"] == 0 else f"-{int(row['otm']*100)}%"
        m = [fmt(leg) for leg in row["legs"]]
        note = "" if row["tradeable"] else "  ← 진입료≈0, 사실상 호가 없음"
        print(f"   {lab:>7} | {row['entry_prem']:>8.2f} | "
              f"{m[0]:>10} | {m[1]:>10} | {m[2]:>10}{note}")

    # 비교: -10% OTM, -30% 패닉 케이스의 배수 압축
    now10  = next(r for r in now  if r["otm"] == 0.10)["legs"][2]["mult"]
    calm10 = next(r for r in calm if r["otm"] == 0.10)["legs"][2]["mult"]
    now_prem  = next(r for r in now  if r["otm"] == 0.10)["entry_prem"]
    calm_prem = next(r for r in calm if r["otm"] == 0.10)["entry_prem"]

    print("\n" + "=" * 80)
    print(" 핵심 비교 — -10% 외가격 풋 / -30% 패닉 시나리오")
    print("=" * 80)
    print(f"  · 지금 진입료 {now_prem:.1f}pt (IV 68%)  vs  평시 진입료 {calm_prem:.1f}pt (IV 15%)"
          f"  → 약 {now_prem/calm_prem:.0f}배 비쌈")
    print(f"  · 같은 -30% 폭락 수익배수:  지금 {now10:.0f}×   vs   평시 {calm10:.0f}×"
          f"   → 배수 약 {calm10/now10:.0f}배 압축")
    print(f"  ⇒ '폭락 방향'이 맞아도, 공포(IV)가 이미 비싸게 반영된 지금 진입하면")
    print(f"     역사적 '수백 배' 대박은 구조적으로 어렵다. 비싸게 사서 덜 비싸게 파는 셈.")
    print(f"  ⇒ 단, 진짜 패닉(-20~30%)이면 여전히 수~수십 배 수익은 가능(원금 대비 큰 베팅).")

    with open("kospi_put_now_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "as_of": "2026-06-02",
            "kospi": TODAY_KOSPI, "entry_iv_now": ENTRY_IV_NOW,
            "entry_iv_calm": ENTRY_IV_CALM,
            "entry_dte": ENTRY_DTE, "days_held": DAYS_HELD,
            "otm_levels": OTM_LEVELS,
            "crash_scenarios": [{"label": c[0], "drop": c[1], "exit_iv": c[2]} for c in CRASH],
            "now": now, "calm_counterfactual": calm,
        }, f, ensure_ascii=False, indent=2)
    print("\n→ 결과 저장: kospi_put_now_results.json")


if __name__ == "__main__":
    main()
