"""
키움 TR 응답 파서 단위 테스트.
키움 OCX 가 없어도(즉 Windows 가 아니어도) 실행 가능.

실행:
    python -m pytest kiwoom/tests/test_parsers.py -v
    또는
    python kiwoom/tests/test_parsers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from kiwoom.api.kiwoom_real import (
    parse_daily_chart_rows,
    parse_minute_chart_rows,
    parse_orderbook_row,
    parse_account_eval,
    _safe_int, _safe_float,
)


def test_safe_int_handles_signs_and_commas():
    assert _safe_int("+1,234,567") == 1234567
    assert _safe_int("-50") == -50
    assert _safe_int("") == 0
    assert _safe_int("abc", default=42) == 42


def test_safe_float():
    assert _safe_float("+1.23") == 1.23
    assert _safe_float("-0.005") == -0.005
    assert _safe_float("invalid") == 0.0


def test_parse_daily_chart_basic():
    rows = [
        {"일자": "20260527", "시가": "+188,200", "고가": "189700",
         "저가": "181000", "현재가": "-185000", "거래량": "29522650",
         "거래대금": "5496089060945"},
        {"일자": "20260526", "시가": "190000", "고가": "192000",
         "저가": "188000", "현재가": "189000", "거래량": "20000000",
         "거래대금": "3800000000000"},
    ]
    df = parse_daily_chart_rows(rows)
    assert len(df) == 2
    assert df.index[0].strftime("%Y-%m-%d") == "2026-05-26"  # sorted asc
    assert df.iloc[-1]["Open"] == 188200.0
    assert df.iloc[-1]["Close"] == 185000.0  # abs value
    assert df.iloc[-1]["Volume"] == 29522650
    assert "Amount" in df.columns


def test_parse_daily_chart_skips_invalid_date():
    rows = [
        {"일자": "invalid", "시가": "100", "고가": "100", "저가": "100",
         "현재가": "100", "거래량": "1000", "거래대금": "100000"},
        {"일자": "20260527", "시가": "100", "고가": "100", "저가": "100",
         "현재가": "100", "거래량": "1000", "거래대금": "100000"},
    ]
    df = parse_daily_chart_rows(rows)
    assert len(df) == 1


def test_parse_minute_chart_uses_timestamp():
    rows = [
        {"체결시간": "20260527093000", "시가": "100", "고가": "102",
         "저가": "99", "현재가": "101", "거래량": "500"},
        {"체결시간": "20260527093100", "시가": "101", "고가": "103",
         "저가": "100", "현재가": "102", "거래량": "600"},
    ]
    df = parse_minute_chart_rows(rows)
    assert len(df) == 2
    assert df.index[0].minute == 30
    assert df.index[1].minute == 31
    assert df["Amount"].iloc[0] == 101 * 500  # Close × Volume


def test_parse_orderbook_basic():
    row = {}
    # 10-deep order book
    for i in range(1, 11):
        row[f"매도호가{i}"] = str(1000 + i)
        row[f"매도호가수량{i}"] = str(100 * i)
        row[f"매수호가{i}"] = str(999 - i)
        row[f"매수호가수량{i}"] = str(50 * i)
    row["총매도잔량"] = "5000"
    row["총매수잔량"] = "5000"

    ob = parse_orderbook_row(row)
    assert len(ob["asks"]) == 10
    assert len(ob["bids"]) == 10
    assert ob["best_ask"] == 1001
    assert ob["best_bid"] == 998
    assert ob["buy_strength_pct"] == 50.0


def test_parse_orderbook_buy_strength():
    row = {f"매도호가{i}": "0" for i in range(1, 11)}
    row.update({f"매도호가수량{i}": "0" for i in range(1, 11)})
    row.update({f"매수호가{i}": "0" for i in range(1, 11)})
    row.update({f"매수호가수량{i}": "0" for i in range(1, 11)})
    row["매도호가1"] = "1000"
    row["매도호가수량1"] = "100"
    row["매수호가1"] = "999"
    row["매수호가수량1"] = "100"
    row["총매도잔량"] = "1000"
    row["총매수잔량"] = "3000"  # 매수 우위

    ob = parse_orderbook_row(row)
    assert ob["buy_strength_pct"] == 75.0


def test_parse_account_eval():
    row = {
        "총매입금액": "1,000,000",
        "총평가금액": "1,050,000",
        "총평가손익금액": "+50,000",
        "총수익률(%)": "+5.00",
        "추정예탁자산": "2,000,000",
    }
    info = parse_account_eval(row)
    assert info["total_buy"] == 1000000
    assert info["total_eval"] == 1050000
    assert info["total_pnl"] == 50000
    assert info["total_return_pct"] == 5.0
    assert info["estimated_assets"] == 2000000


def test_parse_minute_chart_empty():
    df = parse_minute_chart_rows([])
    assert df.empty
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_rate_limiter_min_interval():
    import time
    from kiwoom.utils.rate_limiter import TRRateLimiter
    rl = TRRateLimiter(min_interval_sec=0.1, max_per_hour=1000)
    t0 = time.monotonic()
    for _ in range(3):
        rl.wait()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.2, f"Expected ≥0.2s for 3 calls @ 100ms, got {elapsed:.3f}s"


def test_rate_limiter_stats():
    from kiwoom.utils.rate_limiter import TRRateLimiter
    rl = TRRateLimiter(min_interval_sec=0.001, max_per_hour=10)
    for _ in range(5):
        rl.wait()
    s = rl.stats()
    assert s["calls_last_hour"] == 5
    assert s["headroom"] == 5


def _run_all():
    """간단 러너 (pytest 없이도 실행)."""
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    sys.exit(_run_all())
