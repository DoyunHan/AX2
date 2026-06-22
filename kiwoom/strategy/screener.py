"""
거래대금 상위 universe 스크리너.

키움 OpenAPI+ 연동:
- OPT10032 (당일 거래량 상위) — 거래량 기준이라 직접 사용 불가
- 대안: 조건검색 (GetConditionLoad / SendCondition) 으로 "거래대금 상위 50"
       조건식을 HTS에서 미리 등록 후 봇이 호출.
- 또는: OPT10009 (관심종목 정보) 로 코스피/코스닥 전체 종목 받아
       Amount 정렬 후 상위 N개 추출 (5초당 1회 제한 주의).
"""

from __future__ import annotations

import pandas as pd


def amount_top_n(snapshot: pd.DataFrame, top_n: int = 50) -> list[str]:
    """
    당일 거래대금 상위 N개 종목 코드 반환.

    snapshot: 전체 종목의 OHLCV + Amount + Code 컬럼을 가진 DataFrame
              (키움 OPT10009 결과 또는 자체 수집 시세를 합친 것)
    """
    if "Amount" not in snapshot.columns or "Code" not in snapshot.columns:
        raise ValueError("snapshot must have Code and Amount columns")
    return (
        snapshot.dropna(subset=["Amount"])
        .nlargest(top_n, "Amount")["Code"]
        .astype(str)
        .tolist()
    )


def universe_intersect(*universes: list[str]) -> list[str]:
    """여러 universe의 교집합 (순서 보존, 첫 universe 기준)."""
    if not universes:
        return []
    result = list(universes[0])
    common = set(universes[0])
    for u in universes[1:]:
        common &= set(u)
    return [code for code in result if code in common]
