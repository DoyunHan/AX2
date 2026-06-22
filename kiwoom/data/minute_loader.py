"""
분봉 데이터 로더 및 정밀 진입 시뮬레이터.

운영(Production):
  - 키움 OpenAPI+ OPT10080(주식분봉차트조회)로 1분/5분 봉 수신
  - SetInputValue: 종목코드(string), 틱범위(string, "1"/"3"/"5"/"10"/"15"/"30"/"60"),
                   수정주가구분(string, "1")
  - 응답 컬럼: 현재가/거래량/체결시간/시가/고가/저가
  - 초당 5회 TR 제한, 시간당 1,000회 → 진입 직전 1회만 호출 권장
  - 종일 누적 캐싱은 SQLite 등에 저장 (다음날 백테스트 용)

테스트(Test):
  - SyntheticMinuteGenerator: 일봉 OHLCV 로부터 Brownian-bridge 로 분봉 합성
  - 실데이터 도착 전까지 entry rule 백테스트에 사용
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol

import numpy as np
import pandas as pd


# ============================================================================
# Interface
# ============================================================================

class MinuteDataSource(Protocol):
    def get_minute_bars(
        self,
        code: str,
        target_date: date,
        interval: int = 1,
    ) -> pd.DataFrame:
        """
        Returns: DataFrame index=Timestamp, columns=[Open,High,Low,Close,Volume,Amount]
                 단일 거래일의 분봉 시계열. interval=1 → 약 390행 (09:00~15:30).
        """
        ...


# ============================================================================
# Production: 키움 OPT10080 어댑터
# ============================================================================

class KiwoomMinuteSource:
    """
    실제 키움 OpenAPI+ 어댑터.

    사전 준비:
      - main.py 와 동일한 PyQt5 QApplication / QAxWidget("KHOPENAPI...") 세팅
      - CommConnect 로그인 완료
      - 초당 5회 / 시간당 1000회 TR 제한 준수 — 진입 직전 1회만 호출

    Note: TR 응답은 OnReceiveTrData 콜백으로 비동기 도착. event-loop pump
          필요. 여기서는 동기 API 형태로 노출하기 위해 QEventLoop 활용.
    """

    def __init__(self, ocx):
        self.ocx = ocx
        self._screen_no_counter = 6000
        self._pending_data: dict | None = None

    def _next_screen_no(self) -> str:
        self._screen_no_counter = (self._screen_no_counter + 1) % 10_000
        return str(max(self._screen_no_counter, 1000))

    def get_minute_bars(self, code: str, target_date: date, interval: int = 1) -> pd.DataFrame:
        """
        TR 호출:
          SetInputValue("종목코드", code)
          SetInputValue("틱범위", str(interval))
          SetInputValue("수정주가구분", "1")
          CommRqData("주식분봉차트", "OPT10080", 0, self._next_screen_no())

        OnReceiveTrData 콜백에서 GetRepeatCnt + GetCommData 루프로 행 추출
          → DataFrame 으로 변환 → self._pending_data 에 저장
          → 이벤트 루프 종료

        target_date 로 필터링하여 반환.

        구현은 plan.md Phase 1 에서 채울 것 — 여기서는 시그니처와 로직 기록.
        """
        raise NotImplementedError(
            "OPT10080 wrapper to be implemented in plan.md Phase 1. "
            "See https://wikidocs.net/4264 for reference snippet."
        )


# ============================================================================
# Test: 일봉 → 합성 분봉 (Brownian bridge)
# ============================================================================

@dataclass
class SyntheticMinuteGenerator:
    """
    일봉 OHLCV 로부터 1분봉 합성.

    수식:
      - 첫 봉: 시가 = 일봉 Open
      - 마지막 봉: 종가 = 일봉 Close
      - 중간 경로: O→C 직선 + Brownian bridge 변동
      - High/Low 제약: 경로의 max/min 이 일봉 High/Low 와 일치하도록 스케일
      - Volume: U-shape (시초·종가 부근 거래량 집중) 분포로 일봉 Volume 분배

    한계:
      - 호가창 정보 없음 → 슬리피지 모델 불가
      - 체결 강도 / tick imbalance 없음 → 마하세븐 본연의 호가창 매매 불가
      - 백테스트 sensitivity 분석 용도로만 사용. 운영 의사결정은 실데이터 후.
    """

    seed: int = 42
    bars_per_day: int = 390  # 09:00 ~ 15:30 = 6.5h = 390분

    def __post_init__(self):
        self.rng = np.random.default_rng(self.seed)

    def generate(self, daily_bar: pd.Series, target_date: date) -> pd.DataFrame:
        """
        daily_bar: index에 Open/High/Low/Close/Volume 포함된 Series.
        Returns: 분봉 DataFrame.
        """
        O, H, L, C, V = (float(daily_bar["Open"]), float(daily_bar["High"]),
                          float(daily_bar["Low"]), float(daily_bar["Close"]),
                          float(daily_bar.get("Volume", 0)))
        N = self.bars_per_day

        # 1) Linear interpolation Open → Close
        t = np.linspace(0, 1, N)
        baseline = O + (C - O) * t

        # 2) Brownian bridge: starts 0, ends 0
        # std proportional to sqrt of t*(1-t), scaled so that resulting path
        # has range approximately matching (H-L)
        sigma = (H - L) * 0.4  # heuristic
        dB = self.rng.normal(0, 1, N) * sigma / np.sqrt(N)
        W = np.cumsum(dB)
        bridge = W - t * W[-1]
        path = baseline + bridge

        # 3) Rescale so min(path)=L, max(path)=H (preserving O, C is approximate)
        cur_min, cur_max = path.min(), path.max()
        if cur_max > cur_min:
            path = L + (path - cur_min) * (H - L) / (cur_max - cur_min)
        # Force first/last to exact O/C
        path[0] = O
        path[-1] = C

        # 4) Per-bar OHLC (each bar covers ~2 path points)
        opens = path.copy()
        highs = path.copy()
        lows = path.copy()
        closes = np.roll(path, -1)
        closes[-1] = C
        # For each bar, compute OHLC from a small jitter
        bar_range = (H - L) / N * 2
        for i in range(N):
            jitter_h = abs(self.rng.normal(0, bar_range))
            jitter_l = abs(self.rng.normal(0, bar_range))
            highs[i] = max(opens[i], closes[i]) + jitter_h
            lows[i] = min(opens[i], closes[i]) - jitter_l
        # Clip to daily H, L
        highs = np.clip(highs, None, H)
        lows = np.clip(lows, L, None)

        # 5) Volume: U-shape weight
        u_weight = 1.5 + np.cos(2 * np.pi * t) * 0.5  # higher at open/close
        u_weight /= u_weight.sum()
        volumes = (V * u_weight).astype(int)

        # 6) Timestamps
        timestamps = pd.date_range(
            start=datetime.combine(target_date, time(9, 0)),
            periods=N, freq="1min",
        )
        df = pd.DataFrame({
            "Open": opens, "High": highs, "Low": lows, "Close": closes,
            "Volume": volumes,
        }, index=timestamps)
        df["Amount"] = df["Close"] * df["Volume"]
        return df


# ============================================================================
# 정밀 진입 시뮬레이터
# ============================================================================

@dataclass
class EntryRule:
    """
    분봉 데이터 기반 진입 룰.

    제공 룰 (실데이터 도착 후 그대로 사용):
      1. market_open      : 09:00 정각 시장가
      2. wait_n_minutes   : 09:00 + N분 시점 시장가 (예: 15분)
      3. limit_below_open : Open 대비 -X% 지정가, 미체결 시 fallback
      4. first_pullback   : 시초가 이후 X% 조정 후 첫 회복 봉 진입 (눌림목)
      5. volume_confirm   : 시초 15분 누적 거래량이 평균의 N배 이상이면 진입
    """
    rule_name: str
    wait_minutes: int = 0
    limit_offset_pct: float = 0.0
    pullback_pct: float = 0.0
    volume_mult_threshold: float = 0.0
    fallback: str = "skip"  # "skip" or "market"


def simulate_entry(minute_df: pd.DataFrame, rule: EntryRule) -> tuple[float, datetime] | None:
    """
    분봉 DataFrame 과 진입 룰을 받아 (체결가, 체결시각) 반환.
    체결되지 못하면 None.
    """
    if minute_df.empty:
        return None
    open_px = float(minute_df.iloc[0]["Open"])

    if rule.rule_name == "market_open":
        return open_px, minute_df.index[0]

    if rule.rule_name == "wait_n_minutes":
        idx = min(rule.wait_minutes, len(minute_df) - 1)
        return float(minute_df.iloc[idx]["Open"]), minute_df.index[idx]

    if rule.rule_name == "limit_below_open":
        limit = open_px * (1 - rule.limit_offset_pct / 100)
        hit = minute_df[minute_df["Low"] <= limit]
        if not hit.empty:
            return limit, hit.index[0]
        if rule.fallback == "market":
            return float(minute_df.iloc[-1]["Close"]), minute_df.index[-1]
        return None  # skip

    if rule.rule_name == "first_pullback":
        # Open 대비 -pullback_pct% 도달 후 직전 분봉보다 Close 가 높은 첫 봉 진입
        threshold = open_px * (1 - rule.pullback_pct / 100)
        pullback_idx = minute_df[minute_df["Low"] <= threshold].index
        if len(pullback_idx) == 0:
            return None if rule.fallback == "skip" else (open_px, minute_df.index[0])
        first_pb = pullback_idx[0]
        after = minute_df.loc[first_pb:].iloc[1:]
        prev_close = float(minute_df.loc[first_pb, "Close"])
        for ts, row in after.iterrows():
            if row["Close"] > prev_close:
                return float(row["Open"]), ts
            prev_close = float(row["Close"])
        return None

    if rule.rule_name == "volume_confirm":
        first_15 = minute_df.iloc[:15]
        first_15_vol = first_15["Volume"].sum()
        # Compare to today's avg per-15-min (V/26)
        avg_15 = minute_df["Volume"].mean() * 15
        if first_15_vol >= avg_15 * rule.volume_mult_threshold:
            idx = 15
            return float(minute_df.iloc[idx]["Open"]), minute_df.index[idx]
        return None

    raise ValueError(f"unknown rule_name: {rule.rule_name}")
