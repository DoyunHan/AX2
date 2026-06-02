"""
마하세븐 봇 60일 day-by-day 통합 시뮬레이션.

목적: kiwoom/main.py 의 MachasevenBot 을 실제 운용처럼 매일 호출해
      포지션·자금·일일손실한도가 룰대로 작동하는지 end-to-end 검증.

방법:
  - MockKiwoomAdapter 에 모든 일봉 패널 주입
  - 거래일마다 adapter.current_date 갱신 → bot.run_one_day(date)
  - run_one_day 는 scan_entries → check_exits 순으로 호출
  - 매일 종가 후 포지션 / 일일 PnL / 잠금 상태 기록
  - 60일 누적 결과를 markdown + chart 로 정리

이 시뮬레이션과 backtest/ 의 결과 차이:
  - backtest/run_all.py : 전략 신호로 trades 리스트만 생성 (포지션 제약 X)
  - 본 시뮬레이션 : Portfolio + DailyLimitGuard 모두 적용한 실 운용 가까운 결과
                  (동시 5종목 한도, 일일 -5% 잠금, 진입당 20% 사이징 등)
"""

from __future__ import annotations

import logging
import sys
from datetime import date as Date, timedelta
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for cand in ["WenQuanYi Zen Hei", "Noto Sans CJK KR", "NanumGothic"]:
    if any(cand in f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "backtest"))

from data_loader import build_stock_panel  # backtest/data_loader.py
from kiwoom.api.kiwoom_adapter import MockKiwoomAdapter
from kiwoom.main import MachasevenBot
from kiwoom.config.machaseven import CFG

RESULTS = _ROOT / "backtest" / "results"
RESULTS.mkdir(exist_ok=True)


class TrackingAdapter(MockKiwoomAdapter):
    """
    MockKiwoomAdapter 위에 시뮬레이션 보강:
      - 시장가 체결가를 그 날 시초가로 가정 (검토 위 결정)
      - 청산 시 5MA hard stop / trailing / time cut 가격 받아 사용
      - 실제 P&L 계산용 fills 기록
    """

    def __init__(self, panels):
        super().__init__(panels)
        self.fills: list[dict] = []

    def _today_open(self, code):
        df = self.get_daily_chart(code, days=1)
        if df.empty:
            return None
        return float(df["Open"].iloc[-1])

    def send_buy_market(self, code: str, qty: int) -> str:
        oid = super().send_buy_market(code, qty)
        px = self._today_open(code) or 0.0
        self.fills.append({
            "date": self.current_date.date(), "code": code, "side": "BUY",
            "qty": qty, "price": px, "order_id": oid,
        })
        return oid

    def send_sell_market(self, code: str, qty: int) -> str:
        oid = super().send_sell_market(code, qty)
        px = self._today_open(code) or 0.0
        self.fills.append({
            "date": self.current_date.date(), "code": code, "side": "SELL",
            "qty": qty, "price": px, "order_id": oid,
        })
        return oid


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    print("=== Loading panels ===")
    panels = build_stock_panel("krx", verbose=False)
    print(f"  {len(panels)} stocks")

    adapter = TrackingAdapter(panels)
    bot = MachasevenBot(adapter)

    all_dates = sorted({d for df in panels.values() for d in df.index})
    print(f"\n=== Running bot day-by-day ({len(all_dates)} dates) ===")

    daily_log = []
    starting_capital = bot.portfolio.total_capital

    for i, date_ts in enumerate(all_dates):
        adapter.current_date = date_ts
        d = date_ts.date()
        # 매일 가드 reset 은 자동 (DailyLimitGuard._maybe_reset)
        try:
            bot.run_one_day(d)
        except Exception as e:
            print(f"  ⚠️  {d} run_one_day error: {e}")
            continue
        # 일일 누적
        daily_log.append({
            "date": d,
            "open_positions": bot.portfolio.num_open,
            "daily_pnl_pct": bot.guard.daily_pnl_ratio * 100,
            "locked": d in bot.guard.locked_dates,
            "fills_today": sum(1 for f in adapter.fills if f["date"] == d),
        })
        if i % 10 == 0:
            print(f"  day {i:3d}/{len(all_dates)}  {d}  "
                  f"open={bot.portfolio.num_open}  "
                  f"daily_pnl={bot.guard.daily_pnl_ratio*100:+.2f}%  "
                  f"fills_today={daily_log[-1]['fills_today']}  "
                  f"orders_total={len(adapter.fills)}")

    log_df = pd.DataFrame(daily_log)
    log_df["date"] = pd.to_datetime(log_df["date"])
    fills_df = pd.DataFrame(adapter.fills)

    # 포지션 단위 매매 매치업
    print(f"\n=== Match fills into trades ===")
    trades = match_fills_into_trades(fills_df)
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df["pnl"] = (trades_df["exit_price"] - trades_df["entry_price"]) * trades_df["qty"]
        trades_df["ret_pct"] = ((trades_df["exit_price"] - trades_df["entry_price"]) /
                                trades_df["entry_price"] * 100)
        trades_df["holding"] = (
            pd.to_datetime(trades_df["exit_date"]) - pd.to_datetime(trades_df["entry_date"])
        ).dt.days
    open_count = len([f for f in adapter.fills if f["side"] == "BUY"]) - len(trades)

    # 누적 equity (실 fills 기준)
    if not trades_df.empty:
        trades_df = trades_df.sort_values("exit_date")
        trades_df["cum_pnl"] = trades_df["pnl"].cumsum()
        trades_df["equity"] = (starting_capital + trades_df["cum_pnl"]) / starting_capital
    else:
        trades_df["equity"] = []

    # ===== 요약 =====
    print(f"\n=== 시뮬레이션 결과 ({len(all_dates)} 거래일) ===")
    print(f"  Starting capital   : {starting_capital:,.0f} 원")
    print(f"  Total fills        : {len(adapter.fills)} (buy+sell)")
    print(f"  Completed trades   : {len(trades_df)}")
    print(f"  Still open at end  : {open_count}")
    if not trades_df.empty:
        wins = trades_df["pnl"] > 0
        print(f"  Win rate           : {wins.mean()*100:.1f}%")
        print(f"  Avg holding (days) : {trades_df['holding'].mean():.1f}")
        print(f"  Avg return / trade : {trades_df['ret_pct'].mean():+.2f}%")
        total_pnl = trades_df["pnl"].sum()
        print(f"  Total realized PnL : {total_pnl:+,.0f} 원 "
              f"({total_pnl/starting_capital*100:+.2f}%)")
    lock_days = log_df["locked"].sum()
    print(f"  Days locked (-5%)  : {lock_days} / {len(log_df)}")
    print(f"  Max concurrent pos : {log_df['open_positions'].max()}")
    print(f"  Avg open positions : {log_df['open_positions'].mean():.1f}")

    # ===== 시각화 =====
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True)
    ax = axes[0]
    ax.plot(log_df["date"], log_df["open_positions"], lw=1.5, color="#7eb0d5")
    ax.axhline(CFG.MAX_CONCURRENT_POSITIONS, color="red", ls="--", lw=0.7,
               label=f"max ({CFG.MAX_CONCURRENT_POSITIONS})")
    ax.set_ylabel("동시 보유 종목 수")
    ax.set_title("마하세븐 봇 60일 통합 시뮬레이션")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[1]
    ax.bar(log_df["date"], log_df["daily_pnl_pct"],
           color=["#fd7f6f" if v < 0 else "#b2e061" for v in log_df["daily_pnl_pct"]],
           width=1.0)
    ax.axhline(CFG.DAILY_LOSS_LIMIT * 100, color="red", ls="--", lw=0.7,
               label=f"잠금 한도 ({CFG.DAILY_LOSS_LIMIT*100:.0f}%)")
    ax.set_ylabel("일일 P&L (%)")
    ax.legend()
    ax.grid(alpha=0.3)

    ax = axes[2]
    if not trades_df.empty:
        ax.plot(pd.to_datetime(trades_df["exit_date"]), trades_df["equity"],
                lw=1.5, color="black")
        ax.axhline(1.0, color="gray", ls="--", lw=0.5)
    ax.set_ylabel("Equity (start=1.0)")
    ax.set_xlabel("Date")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(RESULTS / "14_bot_sim_60day.png", dpi=110)
    plt.close()

    # ===== Save outputs =====
    log_df.to_csv(RESULTS / "bot_sim_daily_log.csv", index=False)
    if not trades_df.empty:
        trades_df.to_csv(RESULTS / "bot_sim_trades.csv", index=False)
    fills_df.to_csv(RESULTS / "bot_sim_fills.csv", index=False)

    # Markdown 요약
    md = ["# 마하세븐 봇 60일 통합 시뮬레이션 결과\n",
          f"기간: 2026-03-08 ~ 2026-05-27 ({len(all_dates)} 거래일)\n",
          f"시작 자본: {starting_capital:,.0f} 원\n",
          f"포지션 제약: 동시 {CFG.MAX_CONCURRENT_POSITIONS}종목, 진입당 {CFG.POSITION_PCT_PER_TRADE*100:.0f}%,\n"
          f"           일일 {CFG.DAILY_LOSS_LIMIT*100:.0f}% 손실 잠금, {CFG.CASH_RESERVE_PCT*100:.0f}% 현금 락다운\n\n",
          "## 핵심 결과\n",
          f"- 완료 매매: **{len(trades_df)} 건**\n",
          (f"- 승률: **{wins.mean()*100:.1f}%**\n" if not trades_df.empty else ""),
          (f"- 거래당 평균: **{trades_df['ret_pct'].mean():+.2f}%**\n" if not trades_df.empty else ""),
          (f"- 총 실현 PnL: **{trades_df['pnl'].sum():+,.0f} 원** "
           f"({trades_df['pnl'].sum()/starting_capital*100:+.2f}%)\n" if not trades_df.empty else ""),
          f"- 일일 잠금 발동: {lock_days} 일\n",
          f"- 최대 동시 보유: {log_df['open_positions'].max()} 종목\n\n"]
    (RESULTS / "bot_sim_summary.md").write_text("".join(md), encoding="utf-8")
    print(f"\n✅ Saved: {RESULTS / '14_bot_sim_60day.png'}")
    print(f"   {RESULTS / 'bot_sim_summary.md'}")


def match_fills_into_trades(fills_df: pd.DataFrame) -> list[dict]:
    """
    FIFO 로 BUY/SELL 매치업하여 trade 단위로 재구성.
    """
    if fills_df.empty:
        return []
    trades = []
    open_pos: dict[str, list[dict]] = {}
    for _, row in fills_df.sort_values(["date", "code"]).iterrows():
        code = row["code"]
        if row["side"] == "BUY":
            open_pos.setdefault(code, []).append(row.to_dict())
        else:  # SELL
            if not open_pos.get(code):
                continue
            buy = open_pos[code].pop(0)
            trades.append({
                "code": code,
                "qty": min(buy["qty"], row["qty"]),
                "entry_date": buy["date"],
                "entry_price": buy["price"],
                "exit_date": row["date"],
                "exit_price": row["price"],
            })
    return trades


if __name__ == "__main__":
    main()
