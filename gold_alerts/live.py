"""Live data for the contextual alerts (stdlib HTTP only; no API keys).

Source: Yahoo GC=F 15m (gold FUTURES). It differs from XM spot by tens of dollars (basis), so
only RELATIVE quantities are shown to the user. Bars are converted UTC -> broker server time
(= New York + 7h) so the Asian-range agent sees the same clock as in the backtests.
The still-forming bar is always dropped: a decision may only use CLOSED bars.
"""
import csv
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

UA = {"User-Agent": "Mozilla/5.0"}
M15 = pd.Timedelta("15min")


def _get(url: str, timeout: int = 30) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def to_server_time(idx_utc: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """UTC -> naive broker server time (= New York wall clock + 7h)."""
    ny = idx_utc.tz_convert("America/New_York").tz_localize(None)
    return ny + pd.Timedelta(hours=7)


def drop_unfinished(df: pd.DataFrame, now_utc: pd.Timestamp) -> pd.DataFrame:
    """Keep only bars whose END (start + 15 min) is <= now. df index is UTC-aware bar starts."""
    return df[(df.index + M15) <= now_utc]


def on_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Yahoo appends a live-quote stub (e.g. 19:16:01, flat OHLC). Real bars start exactly on :00/:15/:30/:45."""
    return df[(df.index.minute % 15 == 0) & (df.index.second == 0)]


def fetch_gold_m15(now_utc: pd.Timestamp | None = None) -> pd.DataFrame:
    now_utc = now_utc or pd.Timestamp.now(tz="UTC")
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote("GC=F") + "?range=60d&interval=15m"
    r = json.loads(_get(url))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"]},
                      index=pd.to_datetime(r["timestamp"], unit="s", utc=True)).dropna()
    df = drop_unfinished(on_grid(df), now_utc)
    df.attrs["last_end_utc"] = df.index[-1] + M15  # kept in UTC for the staleness warning
    df.index = to_server_time(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df["spread"] = 0.0  # unknown for futures; only used by the backtester
    return df


def fetch_dxy() -> pd.Series:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote("DX-Y.NYB") + "?range=1y&interval=1d"
    r = json.loads(_get(url))["chart"]["result"][0]
    s = pd.Series(r["indicators"]["quote"][0]["close"], index=pd.to_datetime(r["timestamp"], unit="s").normalize(), dtype=float)
    return s.dropna()[lambda x: ~x.index.duplicated()]


ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "dfii10.csv"
SEED = ROOT / "data" / "raw" / "fred_DFII10.csv"
STATUS: dict = {}  # filled by fetchers so the brief can warn about stale inputs


def _parse_fred(txt: str) -> pd.Series:
    rows = [(r["observation_date"], r["DFII10"]) for r in csv.DictReader(io.StringIO(txt)) if r["DFII10"] not in ("", ".")]
    return pd.Series({pd.Timestamp(d): float(v) for d, v in rows}).sort_index()


def fetch_real_yield(retries: int = 2) -> pd.Series:
    """FRED can drop connections; retry, then fall back to the last good cache (and say so)."""
    start = (pd.Timestamp.now() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10&cosd={start}"
    for i in range(retries):
        try:
            txt = _get(url, timeout=12).decode()
            s = _parse_fred(txt)
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(txt)
            STATUS["real_yield"] = f"สด (ล่าสุด {s.index[-1]:%d %b})"
            return s
        except Exception as e:  # noqa: BLE001
            err = type(e).__name__
            time.sleep(2)
    src = CACHE if CACHE.exists() else SEED
    s = _parse_fred(src.read_text())
    STATUS["real_yield"] = f"⚠️ FRED ไม่ตอบ ({err}) ใช้ข้อมูลเก่า ล่าสุด {s.index[-1]:%d %b}"
    return s
