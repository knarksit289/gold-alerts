"""Feature layer for the alerts. Copied from the research code (GOLD-AGENTS/gold_agents/data.py),
minus everything that reads local backtest files (XM history, holdout handling, experiment log).

Causality rules are unchanged: decisions use CLOSED bars only; higher-timeframe values come from
bars whose END <= decision time; daily macro values are lagged (Yahoo +1d, FRED +2d).
Times are broker server time (= New York + 7h).
"""
import numpy as np
import pandas as pd

M15 = pd.Timedelta("15min")


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def htf_bars(m15: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Higher-timeframe OHLC anchored at server midnight; 'avail' = bar end."""
    out = (m15.resample(rule, label="left", closed="left")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
              .dropna())
    out["avail"] = out.index + pd.Timedelta(rule)
    return out


def attach(m15_index: pd.DatetimeIndex, src: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
    """For each M15 bar, take the latest src row with avail <= bar close (no look-ahead)."""
    left = pd.DataFrame({"T": m15_index + M15}, index=m15_index)
    right = src[["avail"] + cols].sort_values("avail")
    merged = pd.merge_asof(left, right, left_on="T", right_on="avail", direction="backward")
    merged.index = m15_index
    return merged[cols].add_prefix(prefix)


def macro_daily(dxy: pd.Series, ry: pd.Series):
    """Daily macro z-scores with 'avail' timestamps (server time)."""
    lr = np.log(dxy).diff()
    z_dxy = np.log(dxy / dxy.shift(20)) / (lr.rolling(60).std() * np.sqrt(20))
    z_ry = (ry - ry.shift(20)) / (ry.diff().rolling(60).std() * np.sqrt(20))
    a = pd.DataFrame({"z_dxy": z_dxy}).dropna()
    a["avail"] = a.index + pd.Timedelta(days=1)  # dated X -> usable from server X+1 00:00
    b = pd.DataFrame({"z_ry": z_ry}).dropna()
    b["avail"] = b.index + pd.Timedelta(days=2)  # FRED: extra day of safety
    return a, b


def smc_structure(h1: pd.DataFrame, n: int = 5):
    """H1 market structure. A fractal swing at bar k needs n bars on both sides, so it is only
    CONFIRMED at bar k+n (no look-ahead). bias = side of the last close beyond a confirmed swing
    (BOS); pos = position of the close inside [last swing low, last swing high]."""
    hi, lo, cl = h1["high"].to_numpy(), h1["low"].to_numpy(), h1["close"].to_numpy()
    N = len(h1)
    bias, pos = np.zeros(N), np.full(N, np.nan)
    last_sh = last_sl = np.nan
    b = 0
    for t in range(N):
        k = t - n
        if k >= n:
            if hi[k] >= hi[k - n:k + n + 1].max():
                last_sh = hi[k]
            if lo[k] <= lo[k - n:k + n + 1].min():
                last_sl = lo[k]
        if np.isfinite(last_sh) and cl[t] > last_sh:
            b = 1
        elif np.isfinite(last_sl) and cl[t] < last_sl:
            b = -1
        bias[t] = b
        if np.isfinite(last_sh) and np.isfinite(last_sl) and last_sh > last_sl:
            pos[t] = (cl[t] - last_sl) / (last_sh - last_sl)
    return bias, pos


def asian_range(m15: pd.DataFrame, start_h: int = 1, end_h: int = 10, win_end_h: int = 18) -> pd.DataFrame:
    """Asian-session range (server time) and whether a bar is inside the London/NY window.
    The range is complete at end_h, so bars starting at/after end_h may use it."""
    day = m15.index.normalize()
    hr = m15.index.hour
    asia = (hr >= start_h) & (hr < end_h)
    g = m15[asia].groupby(day[asia])
    cnt = g["high"].count()
    hi, lo = g["high"].max().where(cnt >= 20), g["low"].min().where(cnt >= 20)  # need most of the session
    out = pd.DataFrame(index=m15.index)
    done = hr >= end_h  # before the session ends the range is NOT yet known -> hide it
    out["asia_hi"] = np.where(done, day.map(hi).to_numpy(), np.nan)
    out["asia_lo"] = np.where(done, day.map(lo).to_numpy(), np.nan)
    out["in_window"] = ((hr >= end_h) & (hr < win_end_h)).astype(float)
    return out


def build_features(m15: pd.DataFrame, dxy: pd.Series, ry: pd.Series) -> pd.DataFrame:
    """All agent inputs, aligned to M15 bars, causal."""
    f = pd.DataFrame(index=m15.index)
    f["atr15"] = atr(m15, 14)
    h1 = htf_bars(m15, "1h")
    h1["ema50"] = h1["close"].ewm(span=50, adjust=False).mean()
    h1["ema200"] = h1["close"].ewm(span=200, adjust=False).mean()
    h1["atr"] = atr(h1, 14)
    h1["rsi"] = rsi(h1["close"], 14)
    h1["bias"], h1["pos"] = smc_structure(h1)
    f = f.join(attach(m15.index, h1, ["ema50", "ema200", "atr", "rsi", "bias", "pos"], "h1_"))
    f["close"] = m15["close"]  # decision is taken at this bar's close
    f = f.join(asian_range(m15))
    h4 = htf_bars(m15, "4h")
    h4["atr"] = atr(h4, 14)
    f = f.join(attach(m15.index, h4, ["atr"], "h4_"))
    a, b = macro_daily(dxy, ry)
    f = f.join(attach(m15.index, a, ["z_dxy"], "m_"))
    f = f.join(attach(m15.index, b, ["z_ry"], "m_"))
    return f
