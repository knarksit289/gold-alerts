"""Agents v1. Each returns a score in [-1, +1] (+ = bullish gold) from CAUSAL features only.

Parameters are textbook defaults, fixed before any result was seen. Do NOT tune them on
development data; any change must be logged in experiments.log as a new configuration.
"""
import numpy as np
import pandas as pd


def trend_h1(f: pd.DataFrame) -> pd.Series:
    """Trend: EMA50 vs EMA200 on closed H1 bars, in units of H1 ATR."""
    return np.tanh((f["h1_ema50"] - f["h1_ema200"]) / f["h1_atr"])


def momentum_h1(f: pd.DataFrame) -> pd.Series:
    """Momentum: RSI(14) on closed H1 bars, centred on 50, +-20 pts = full score."""
    return ((f["h1_rsi"] - 50) / 20).clip(-1, 1)


def macro(f: pd.DataFrame) -> pd.Series:
    """Cross-market: gold likes a falling dollar and falling real yields (20d z-scores)."""
    z = (f["m_z_dxy"] + f["m_z_ry"]) / 2
    return -np.tanh(z / 2)


def structure_smc(f: pd.DataFrame) -> pd.Series:
    """Round 3A. ICT-style: with a bullish BOS bias only buy in DISCOUNT (lower half of the
    dealing range); with a bearish bias only sell in PREMIUM. Score = bias * depth in [0,1]."""
    depth = np.where(f["h1_bias"] > 0, 1 - 2 * f["h1_pos"], 2 * f["h1_pos"] - 1)
    return pd.Series(f["h1_bias"] * np.clip(depth, 0, 1), index=f.index)


def session_asian(f: pd.DataFrame) -> pd.Series:
    """Round 3B. Asian-range breakout during server 10:00-18:00: +1 above range high, -1 below low."""
    up = (f["close"] > f["asia_hi"]) & (f["in_window"] > 0)
    dn = (f["close"] < f["asia_lo"]) & (f["in_window"] > 0)
    s = pd.Series(0.0, index=f.index)
    s[up], s[dn] = 1.0, -1.0
    s[(f["in_window"] > 0) & (f["asia_hi"].isna() | f["asia_lo"].isna())] = np.nan  # no valid range that day
    return s


AGENTS = {"trend_h1": trend_h1, "momentum_h1": momentum_h1, "macro": macro}
AGENTS_R3 = {"structure_smc": structure_smc, "session_asian": session_asian}
