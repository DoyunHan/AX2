"""
마하세븐 포식자 시스템 설정.

Walk-forward 검증으로 안정성 확인된 파라미터를 채택.
변경 시 백테스트 재검증 필수.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MachasevenConfig:
    # ───── Universe / Liquidity ─────
    # 당일 거래대금 상위 N위 이내 종목만 대상
    AMOUNT_TOP_N: int = 50
    # 당일 거래대금이 N일 평균 거래대금 대비 이 배수 이상
    AMOUNT_SURGE_RATIO: float = 1.5
    AMOUNT_AVG_WINDOW: int = 20

    # ───── Structure / Alignment ─────
    # 5MA > LONG_MA 정배열 강제 (역배열 종목은 절대 진입 X)
    REQUIRE_ALIGNMENT: bool = True
    LONG_MA_PERIOD: int = 20

    # ───── Entry: 돌파 모드 ─────
    # N일 신고가 돌파 시 진입 (눌림목 모드는 일봉으로 검증 불가하여 제외)
    BREAKOUT_PERIOD: int = 20

    # ───── Exit ─────
    # 5MA 하향 돌파 시 즉시 시장가 청산 (호가창 무시)
    HARD_STOP_5MA: bool = True
    # 고점 대비 이 비율 하락 시 트레일링 청산
    TRAILING_STOP_PCT: float = 0.02
    # N거래일 보유 후 강제 청산 (15분 타임컷의 일봉 근사)
    MAX_HOLDING_DAYS: int = 3

    # ───── Money Management ─────
    # 일일 누적 손실이 이 비율 도달 시 당일 신규 진입 차단
    DAILY_LOSS_LIMIT: float = -0.05
    # 총 자본의 이 비율은 항상 현금 (락다운)
    CASH_RESERVE_PCT: float = 0.50
    # 진입당 사용 가능 자본의 비율
    POSITION_PCT_PER_TRADE: float = 0.20
    # 동시 보유 최대 종목 수
    MAX_CONCURRENT_POSITIONS: int = 5

    # ───── Cost (한국 시장) ─────
    # 매도 시 거래세 + 농특세
    SELL_TAX_RATE: float = 0.0018
    # 위탁 수수료 (키움 HTS 기준, 매수+매도 각각)
    COMMISSION_RATE: float = 0.00015


# Default 인스턴스 — production에서 import해 그대로 사용
CFG = MachasevenConfig()
