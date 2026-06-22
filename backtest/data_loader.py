"""
Korean market data loader.

Data sources (all via raw.githubusercontent.com — only host allowed in sandbox):
- Index (KOSPI/KOSDAQ) yearly OHLCV — 1995~2026
- Daily listing snapshots — 2026-03-08 ~ 2026-05-27

Cache: ./data_cache/
"""

from __future__ import annotations

import os
import ssl
import io
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).parent / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

BASE = "https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/refs/heads/master/data"
_SSL_CTX = ssl._create_unverified_context()
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch(url: str, cache_name: str) -> str:
    """Fetch URL with local file cache."""
    cache_path = CACHE_DIR / cache_name
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as r:
        text = r.read().decode("utf-8", errors="replace")
    cache_path.write_text(text, encoding="utf-8")
    return text


def load_index(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Load yearly index data and concatenate.
    symbol: 'ks11' (KOSPI), 'kq11' (KOSDAQ), 'ks200', etc.
    """
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    years = range(start_dt.year, end_dt.year + 1)
    frames = []
    for y in years:
        url = f"{BASE}/index/year_{symbol}/{y}.csv"
        try:
            text = _fetch(url, f"index_{symbol}_{y}.csv")
            df = pd.read_csv(io.StringIO(text), parse_dates=["Date"])
            frames.append(df)
        except Exception as e:
            print(f"  [warn] {symbol} {y}: {e}")
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).set_index("Date").sort_index()
    df = df.loc[start_dt:end_dt]
    return df


def list_snapshot_dates(market: str = "krx") -> list[str]:
    """List available daily snapshot dates."""
    # We hard-code the discovered range. Could scrape github tree page but that
    # uses the github web frontend which is fragile.
    start = datetime(2026, 3, 8)
    end = datetime(2026, 5, 27)
    dates = []
    cur = start
    while cur <= end:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return dates


def load_daily_snapshot(date: str, market: str = "krx") -> pd.DataFrame | None:
    """
    Load one day's full market snapshot.
    Returns DataFrame with columns: Code, Name, Market, Close, Open, High, Low,
    Volume, Amount, Marcap, ChagesRatio, ...
    """
    url = f"{BASE}/listing/{market}/{date}.csv"
    try:
        text = _fetch(url, f"listing_{market}_{date}.csv")
    except urllib.error.HTTPError:
        return None
    except Exception as e:
        print(f"  [warn] snapshot {date}: {e}")
        return None
    if not text.strip():
        return None
    # First column is unnamed index
    df = pd.read_csv(io.StringIO(text), dtype={"Code": str})
    if df.empty:
        return None
    return df


def build_stock_panel(market: str = "krx", verbose: bool = True) -> dict[str, pd.DataFrame]:
    """
    Aggregate all daily snapshots into per-stock OHLCV time series.
    Returns dict: code -> DataFrame(index=Date, cols=Open/High/Low/Close/Volume/Amount/Marcap)
    """
    dates = list_snapshot_dates(market)
    by_stock: dict[str, list[dict]] = {}
    weekend_count = 0
    if verbose:
        print(f"Loading {len(dates)} daily snapshots ({market})...")
    for i, d in enumerate(dates):
        snap = load_daily_snapshot(d, market)
        if snap is None or snap.empty:
            weekend_count += 1
            continue
        date_dt = pd.to_datetime(d)
        for _, row in snap.iterrows():
            code = row["Code"]
            by_stock.setdefault(code, []).append({
                "Date": date_dt,
                "Name": row["Name"],
                "Open": float(row["Open"]) if pd.notna(row["Open"]) else None,
                "High": float(row["High"]) if pd.notna(row["High"]) else None,
                "Low": float(row["Low"]) if pd.notna(row["Low"]) else None,
                "Close": float(row["Close"]) if pd.notna(row["Close"]) else None,
                "Volume": float(row["Volume"]) if pd.notna(row["Volume"]) else 0.0,
                "Amount": float(row["Amount"]) if pd.notna(row["Amount"]) else 0.0,
                "Marcap": float(row["Marcap"]) if pd.notna(row["Marcap"]) else 0.0,
                "ChangeRatio": float(row["ChagesRatio"]) if pd.notna(row["ChagesRatio"]) else 0.0,
            })
        if verbose and (i + 1) % 10 == 0:
            print(f"  ...{i+1}/{len(dates)} ({len(by_stock)} stocks so far)")
    panels = {}
    dropped_corporate_action = 0
    for code, rows in by_stock.items():
        df = pd.DataFrame(rows).set_index("Date").sort_index()
        # Drop rows with NaN or zero OHLC (휴장/거래정지)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        df = df[(df["Open"] > 0) & (df["High"] > 0) & (df["Low"] > 0) & (df["Close"] > 0)]
        # Drop days where overnight gap exceeds ±50% — almost certainly stock
        # split / reverse split / corporate action (price limit is ±30%/day, so
        # a clean intraday move is bounded by 30%; even with extreme gap it
        # shouldn't double the price).
        if len(df) >= 2:
            prev_close = df["Close"].shift(1)
            overnight_ratio = (df["Open"] / prev_close).fillna(1.0)
            bad = (overnight_ratio < 0.5) | (overnight_ratio > 2.0)
            if bad.any():
                dropped_corporate_action += int(bad.sum())
                df = df[~bad]
        if len(df) >= 10:
            panels[code] = df
    if verbose and dropped_corporate_action:
        print(f"  dropped {dropped_corporate_action} rows from suspected corporate actions")
    if verbose:
        print(f"Built panels for {len(panels)} stocks "
              f"(skipped {weekend_count} non-trading dates)")
    return panels


def top_by_marketcap(panels: dict[str, pd.DataFrame], n: int = 100) -> list[str]:
    """Return top N stock codes by latest market cap."""
    last_marcaps = []
    for code, df in panels.items():
        last_marcaps.append((code, df["Marcap"].iloc[-1], df["Name"].iloc[-1]))
    last_marcaps.sort(key=lambda x: x[1], reverse=True)
    return [code for code, _, _ in last_marcaps[:n]]


if __name__ == "__main__":
    # Smoke test
    print("=== Index (KOSPI 2024) ===")
    ks = load_index("ks11", "2024-01-01", "2024-03-31")
    print(ks.head())
    print("shape:", ks.shape)

    print("\n=== Single snapshot (2026-03-09) ===")
    snap = load_daily_snapshot("2026-03-09")
    if snap is not None:
        print(snap.head(3))
        print("shape:", snap.shape)
