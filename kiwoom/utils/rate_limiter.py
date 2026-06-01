"""
TR 요청 속도 제한 가드 — 키움 OpenAPI+ 의 초당 5회 / 시간당 1,000회 제한 준수.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock


class TRRateLimiter:
    """
    Kiwoom TR 호출 속도 제한.

    제한:
      - 초당 5회: 200ms 간격 보장 (안전 마진 250ms 권장)
      - 시간당 1,000회: 슬라이딩 윈도우로 추적

    사용:
        limiter = TRRateLimiter()
        ...
        limiter.wait()  # 호출 전 반드시 — 필요 시 sleep
        ocx.dynamicCall("CommRqData(...)", ...)
    """

    def __init__(self,
                 min_interval_sec: float = 0.25,
                 max_per_hour: int = 950):
        self.min_interval = min_interval_sec
        self.max_per_hour = max_per_hour
        self._last_call: float = 0.0
        self._hourly: deque[float] = deque()
        self._lock = Lock()

    def wait(self) -> None:
        """다음 TR 호출 직전에 호출. 필요 시 blocking."""
        with self._lock:
            now = time.monotonic()
            # (1) 최소 간격 보장
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.monotonic()
            # (2) 시간당 윈도우 — 1시간 이전 항목 제거
            cutoff = now - 3600
            while self._hourly and self._hourly[0] < cutoff:
                self._hourly.popleft()
            if len(self._hourly) >= self.max_per_hour:
                # 윈도우가 꽉 차면 가장 오래된 항목이 1시간 지날 때까지 대기
                wait_sec = self._hourly[0] + 3600 - now + 0.5
                time.sleep(max(wait_sec, 0.1))
                now = time.monotonic()
                while self._hourly and self._hourly[0] < now - 3600:
                    self._hourly.popleft()
            self._last_call = now
            self._hourly.append(now)

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            cutoff = now - 3600
            recent = sum(1 for t in self._hourly if t >= cutoff)
            return {
                "calls_last_hour": recent,
                "limit": self.max_per_hour,
                "headroom": self.max_per_hour - recent,
            }
