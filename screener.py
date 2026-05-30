#!/usr/bin/env python3
"""
overnight-gainers screener
===========================

하룻밤에 급등할 "후보군"을 좁히는 미니 스크리너.

핵심 철학(overnight-gainers-guide.html 참고): 이건 예측기가 아니라 *필터*다.
폭등 가능성이 높은 조건(저플로팅 + 높은 공매도 + 갭 + 거래량 급증 + 가격대)을
점수화해서 매일 후보 풀을 좁히는 용도다. "잡는" 게 아니라 "확률 게임"임을 잊지 말 것.

데이터 소스
-----------
* yahoo : Yahoo Finance 공개 엔드포인트(API 키 불필요). 일반 네트워크에서 동작.
          - predefined screener: small_cap_gainers, day_gainers
          - quoteSummary defaultKeyStatistics: floatShares, shortPercentOfFloat ...
* demo  : 네트워크 없이 동작하는 내장 샘플 데이터(이 스크립트 검증/시연용).

사용법
------
    python3 screener.py --demo                 # 오프라인 시연
    python3 screener.py                          # 라이브(Yahoo), 기본 필터
    python3 screener.py --max-float 20 --min-change 10 --limit 25
    python3 screener.py --out candidates        # candidates.csv / candidates.json 저장

면책: 교육/정보 목적. 투자 권유 아님. 저플로팅 소형주는 손실 위험이 극단적이다.
"""

from __future__ import annotations
import argparse
import csv
import json
import sys
from dataclasses import dataclass, asdict, field
from typing import Optional

try:
    import requests  # stdlib에는 없지만 대부분 환경에 있음
except ImportError:  # pragma: no cover
    requests = None

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")


# ──────────────────────────────────────────────────────────────────────────
# 데이터 모델
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    symbol: str
    name: str = ""
    price: Optional[float] = None
    change_pct: Optional[float] = None        # 당일/프리마켓 변동률 (%)
    volume: Optional[float] = None
    avg_volume: Optional[float] = None
    market_cap: Optional[float] = None
    float_shares: Optional[float] = None       # 유통주식수
    short_pct_float: Optional[float] = None     # 공매도 비중 (% of float)
    catalyst: str = ""                          # 알려진 카탈리스트(있으면)
    score: float = 0.0
    flags: list = field(default_factory=list)

    @property
    def rel_volume(self) -> Optional[float]:
        if self.volume and self.avg_volume:
            return self.volume / self.avg_volume
        return None

    @property
    def float_millions(self) -> Optional[float]:
        return self.float_shares / 1e6 if self.float_shares else None


# ──────────────────────────────────────────────────────────────────────────
# 스코어링 — "예측"이 아니라 조건 충족도. 각 축 0~1로 정규화 후 가중합.
# ──────────────────────────────────────────────────────────────────────────
WEIGHTS = {
    "low_float": 0.30,    # 유통주식 적을수록 ↑ (공급 부족 = 변동성)
    "short":     0.25,    # 공매도 비중 높을수록 ↑ (스퀴즈 연료)
    "gap":       0.20,    # 변동률 클수록 ↑ (모멘텀)
    "rel_vol":   0.20,    # 거래량 급증할수록 ↑ (관심/수급)
    "price":     0.05,    # 적정 가격대($1~$20) 가산
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_candidate(c: Candidate) -> Candidate:
    s = 0.0
    flags: list[str] = []

    # 저플로팅: 50M 주에서 0, 5M 주 이하에서 1 (로그 스케일 근사)
    if c.float_shares:
        fm = c.float_shares / 1e6
        lf = _clamp((50 - fm) / 45)
        s += WEIGHTS["low_float"] * lf
        if fm < 10:
            flags.append("LOW_FLOAT")

    # 공매도 비중: 0%→0, 30%+→1
    if c.short_pct_float is not None:
        sh = _clamp(c.short_pct_float / 30)
        s += WEIGHTS["short"] * sh
        if c.short_pct_float >= 20:
            flags.append("HIGH_SHORT")

    # 갭/변동률: +5%→0, +50%+→1
    if c.change_pct is not None:
        g = _clamp((c.change_pct - 5) / 45)
        s += WEIGHTS["gap"] * g
        if c.change_pct >= 20:
            flags.append("BIG_GAP")

    # 상대 거래량: 1x→0, 5x+→1
    rv = c.rel_volume
    if rv is not None:
        r = _clamp((rv - 1) / 4)
        s += WEIGHTS["rel_vol"] * r
        if rv >= 3:
            flags.append("VOL_SPIKE")

    # 가격대: $1~$20 선호(작은 절대가가 % 폭발 쉬움), 그 밖은 감점 없이 0
    if c.price is not None:
        if 1 <= c.price <= 20:
            s += WEIGHTS["price"]
        elif c.price < 1:
            flags.append("SUB_DOLLAR")  # 변동성↑이지만 상폐/희석 위험도↑

    if c.catalyst:
        flags.append("CATALYST")
    else:
        flags.append("NO_CATALYST?")   # 60초 룰: 이유 없으면 위험 신호

    c.score = round(s * 100, 1)   # 0~100 스케일
    c.flags = flags
    return c


# ──────────────────────────────────────────────────────────────────────────
# 데이터 소스: Yahoo Finance (live)
# ──────────────────────────────────────────────────────────────────────────
class YahooProvider:
    SCREENERS = ["small_cap_gainers", "day_gainers"]

    def __init__(self):
        if requests is None:
            raise RuntimeError("requests 모듈이 필요합니다: pip install requests")
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})
        self._crumb = ""
        self._bootstrap()

    def _bootstrap(self):
        try:
            self.s.get("https://fc.yahoo.com", timeout=10)
            r = self.s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
            if r.ok and "<" not in r.text:
                self._crumb = r.text.strip()
        except Exception:
            pass

    def candidates(self, limit: int = 50) -> list[Candidate]:
        out: dict[str, Candidate] = {}
        for scr in self.SCREENERS:
            params = {"scrIds": scr, "count": limit}
            if self._crumb:
                params["crumb"] = self._crumb
            try:
                r = self.s.get(
                    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved",
                    params=params, timeout=15)
                r.raise_for_status()
                quotes = r.json()["finance"]["result"][0]["quotes"]
            except Exception as e:
                print(f"  [warn] {scr} 가져오기 실패: {e}", file=sys.stderr)
                continue
            for q in quotes:
                sym = q.get("symbol")
                if not sym or sym in out:
                    continue
                out[sym] = Candidate(
                    symbol=sym,
                    name=q.get("shortName", ""),
                    price=q.get("regularMarketPrice"),
                    change_pct=q.get("regularMarketChangePercent"),
                    volume=q.get("regularMarketVolume"),
                    avg_volume=q.get("averageDailyVolume3Month"),
                    market_cap=q.get("marketCap"),
                )
        cands = list(out.values())
        for c in cands:
            self._enrich(c)
        return cands

    def _enrich(self, c: Candidate):
        """floatShares, shortPercentOfFloat 보강."""
        try:
            params = {"modules": "defaultKeyStatistics"}
            if self._crumb:
                params["crumb"] = self._crumb
            r = self.s.get(
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{c.symbol}",
                params=params, timeout=12)
            if not r.ok:
                return
            ks = r.json()["quoteSummary"]["result"][0]["defaultKeyStatistics"]
            c.float_shares = (ks.get("floatShares") or {}).get("raw")
            spf = (ks.get("shortPercentOfFloat") or {}).get("raw")
            if spf is not None:
                c.short_pct_float = round(spf * 100, 2)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────
# 데이터 소스: 내장 데모(오프라인) — 실제 값이 아니라 시연용 합성 데이터
# ──────────────────────────────────────────────────────────────────────────
def demo_candidates() -> list[Candidate]:
    raw = [
        # symbol, name, price, chg%, vol, avgvol, mcap, float, short%, catalyst
        ("SQZX", "Squeezeco Bio",   3.40,  28.0, 18_000_000, 1_200_000,  90e6,  6.5e6, 31.0, "FDA PDUFA 결과 임박"),
        ("LOWF", "LowFloat Mining", 1.85,  62.0, 22_000_000,   800_000,  45e6,  4.2e6, 24.0, ""),
        ("PUMP", "Hype Holdings",   0.74, 140.0, 95_000_000,   500_000,  30e6,  9.8e6,  8.0, ""),
        ("BIOX", "BioCat Therap",   7.20,  18.0,  6_500_000, 1_500_000, 210e6, 22.0e6, 12.0, "임상 3상 톱라인"),
        ("MEME", "MemeStonk Inc",  12.10,  9.5,   8_000_000, 2_000_000, 480e6, 35.0e6, 19.0, "Reddit 거론량 급증"),
        ("BIGC", "BigCap Stable",  88.00,  6.0,   3_000_000, 2_800_000,  12e9, 400e6,   2.0, "실적 호조"),
        ("REVS", "RevSplit Corp",   2.05,  41.0, 14_000_000,   600_000,  20e6,  3.1e6, 27.0, "리버스 스플릿 직후"),
    ]
    cands = []
    for sym, name, px, chg, vol, av, mc, fl, sh, cat in raw:
        cands.append(Candidate(symbol=sym, name=name, price=px, change_pct=chg,
                               volume=vol, avg_volume=av, market_cap=mc,
                               float_shares=fl, short_pct_float=sh, catalyst=cat))
    return cands


# ──────────────────────────────────────────────────────────────────────────
# 출력
# ──────────────────────────────────────────────────────────────────────────
def fmt(v, suffix="", n=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.{n}f}{suffix}"
    return f"{v}{suffix}"


def print_table(cands: list[Candidate]):
    hdr = ["#", "SYM", "PRICE", "CHG%", "RVOL", "FLOAT(M)", "SHORT%", "SCORE", "FLAGS"]
    rows = []
    for i, c in enumerate(cands, 1):
        rows.append([
            str(i), c.symbol, fmt(c.price, "", 2), fmt(c.change_pct, "%"),
            fmt(c.rel_volume, "x", 1), fmt(c.float_millions, "", 1),
            fmt(c.short_pct_float, "%"), f"{c.score:.1f}",
            " ".join(c.flags),
        ])
    widths = [max(len(h), *(len(r[j]) for r in rows)) if rows else len(h)
              for j, h in enumerate(hdr)]
    line = "  ".join(h.ljust(widths[j]) for j, h in enumerate(hdr))
    print("\n" + line)
    print("─" * len(line))
    for r in rows:
        print("  ".join(r[j].ljust(widths[j]) for j in range(len(hdr))))
    print()


def write_outputs(cands: list[Candidate], stem: str):
    data = [asdict(c) | {"rel_volume": c.rel_volume} for c in cands]
    with open(f"{stem}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    cols = ["symbol", "name", "price", "change_pct", "rel_volume",
            "float_shares", "short_pct_float", "market_cap", "catalyst", "score"]
    with open(f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for c in cands:
            d = asdict(c) | {"rel_volume": c.rel_volume}
            w.writerow([d.get(k) for k in cols])
    print(f"[saved] {stem}.json / {stem}.csv")


# ──────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="overnight-gainers 후보 스크리너")
    ap.add_argument("--provider", choices=["yahoo", "demo"], default="yahoo")
    ap.add_argument("--demo", action="store_true", help="오프라인 데모(=--provider demo)")
    ap.add_argument("--limit", type=int, default=50, help="소스에서 가져올 최대 종목 수")
    ap.add_argument("--min-change", type=float, default=5.0, help="최소 변동률(%%) 필터")
    ap.add_argument("--max-float", type=float, default=None, help="최대 유통주식(백만 주) 필터")
    ap.add_argument("--top", type=int, default=20, help="상위 N개만 출력")
    ap.add_argument("--out", default=None, help="결과 저장 파일명 stem(확장자 제외)")
    args = ap.parse_args(argv)

    provider = "demo" if args.demo else args.provider
    print(f"[overnight-gainers screener] provider={provider}")

    if provider == "demo":
        cands = demo_candidates()
    else:
        try:
            cands = YahooProvider().candidates(limit=args.limit)
        except Exception as e:
            print(f"[error] 라이브 데이터 실패({e}). --demo 로 시연하세요.", file=sys.stderr)
            return 1
        if not cands:
            print("[error] 후보를 못 가져왔습니다(네트워크 차단?). --demo 사용.", file=sys.stderr)
            return 1

    # 필터
    if args.min_change is not None:
        cands = [c for c in cands if (c.change_pct or 0) >= args.min_change]
    if args.max_float is not None:
        cands = [c for c in cands
                 if c.float_millions is None or c.float_millions <= args.max_float]

    # 스코어 & 정렬
    for c in cands:
        score_candidate(c)
    cands.sort(key=lambda c: c.score, reverse=True)
    cands = cands[:args.top]

    print_table(cands)
    print("점수=조건 충족도(0~100). 예측 아님. NO_CATALYST?=이유 불명(위험). "
          "교육용·투자권유 아님.")
    if args.out:
        write_outputs(cands, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
