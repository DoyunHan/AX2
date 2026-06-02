"""
코인 선물 박스권 돌파 추세추종 전략 (Box Breakout Trend Strategy).

횡보(consolidation) 구간을 박스로 규정하고, 박스 이탈 방향으로 진입한 뒤
ATR 트레일링 스탑으로 추세를 끝까지 홀딩해 수익을 극대화한다.

대상: Binance USD-M Futures (무기한 선물), 기준 타임프레임 15m ~ 1h.
"""

from .strategy import StrategyConfig, compute_features, generate_signals
from .backtest import Backtester, BacktestConfig, Trade
from .metrics import compute_metrics

__all__ = [
    "StrategyConfig",
    "compute_features",
    "generate_signals",
    "Backtester",
    "BacktestConfig",
    "Trade",
    "compute_metrics",
]
