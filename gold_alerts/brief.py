"""Contextual brief + stateless event detection (no edge claimed; see RESULTS.md).

Everything shown is RELATIVE (the GC=F futures price differs from XM spot by tens of dollars).
Events are computed by comparing the last CLOSED bar with the bar before it, so the job needs
no stored state (suits GitHub Actions)."""
import numpy as np
import pandas as pd

from . import data, live
from .agents import AGENTS, AGENTS_R3

ALL = {**AGENTS, **AGENTS_R3}
THETA = 0.5
NAMES = {"trend_h1": "เทรนด์ H1", "momentum_h1": "โมเมนตัม H1", "macro": "มหภาค (ดอลลาร์/ผลตอบแทนจริง)",
         "structure_smc": "โครงสร้างราคา (SMC)", "session_asian": "กรอบเอเชีย"}


def build_state(now_utc: pd.Timestamp | None = None):
    m15 = live.fetch_gold_m15(now_utc)
    f = data.build_features(m15, live.fetch_dxy(), live.fetch_real_yield())
    f.attrs["last_end_utc"] = m15.attrs["last_end_utc"]
    S = pd.DataFrame({k: fn(f) for k, fn in ALL.items()})
    return m15, f, S


def _side(x: float) -> str:
    return "หนุนทอง" if x > 0 else "กดทอง" if x < 0 else "เป็นกลาง"


def explain(name: str, r: pd.Series, s: float) -> str:
    """One line of reasoning per agent, relative quantities only."""
    if name == "trend_h1":
        d = (r.h1_ema50 - r.h1_ema200) / r.h1_atr
        return f"EMA50 {'เหนือ' if d > 0 else 'ใต้'} EMA200 {abs(d):.1f}×ATR(H1)"
    if name == "momentum_h1":
        return f"RSI(14) H1 = {r.h1_rsi:.0f}"
    if name == "macro":
        return f"ดอลลาร์ 20 วัน z={r.m_z_dxy:+.1f} · ผลตอบแทนจริง 10 ปี z={r.m_z_ry:+.1f}"
    if name == "structure_smc":
        bias = "ขาขึ้น" if r.h1_bias > 0 else "ขาลง" if r.h1_bias < 0 else "ยังไม่ชัด"
        pos = "—" if pd.isna(r.h1_pos) else f"{r.h1_pos * 100:.0f}% ของกรอบ swing ({'discount' if r.h1_pos < .5 else 'premium'})"
        return f"โครงสร้าง{bias} · ราคาอยู่ที่ {pos}"
    if name == "session_asian":
        if r.in_window <= 0:
            return "นอกช่วงลอนดอน/นิวยอร์ก (server 10:00–18:00)"
        if pd.isna(r.asia_hi):
            return "ไม่มีกรอบเอเชียที่ใช้ได้วันนี้"
        st = "ทะลุขึ้นเหนือกรอบ" if s > 0 else "ทะลุลงใต้กรอบ" if s < 0 else "อยู่ในกรอบ"
        return f"{st} (กว้าง ${r.asia_hi - r.asia_lo:.1f})"
    return ""


def format_brief(title: str, f: pd.DataFrame, S: pd.DataFrame, now_utc: pd.Timestamp) -> str:
    r, s = f.iloc[-1], S.iloc[-1]
    t_srv = f.index[-1] + live.M15
    age_h = (now_utc - f.attrs["last_end_utc"]).total_seconds() / 3600  # real age of the last closed bar
    lines = [f"📊 {title}", f"แท่งปิดล่าสุด: server {t_srv:%d %b %H:%M} (อายุ {age_h:.1f} ชม.)" + ("  ⚠️ ตลาดอาจปิดอยู่/ข้อมูลเก่า" if age_h > 1.0 else ""),
             f"ความผันผวน (ATR): M15 ${r.atr15:.1f} · H1 ${r.h1_atr:.1f} · H4 ${r.h4_atr:.1f}", ""]
    nl = int((s >= THETA).sum())
    ns = int((s <= -THETA).sum())
    for k in ALL:
        v = s[k]
        sc = "—" if pd.isna(v) else f"{v:+.2f}"
        lines.append(f"• {NAMES[k]}: {sc} {_side(0 if pd.isna(v) else v)}\n   {explain(k, r, 0 if pd.isna(v) else v)}")
    if live.STATUS.get("real_yield", "").startswith("⚠️"):
        lines += ["", f"{live.STATUS['real_yield']} → คะแนนมหภาคอาจคลาดเคลื่อน"]
    lines += ["", f"เห็นตรงกัน: หนุนทอง {nl} · กดทอง {ns} จาก {len(ALL)} agent",
              "ℹ️ เป็นบริบทประกอบการตัดสินใจ ไม่ใช่สัญญาณซื้อขาย — ทดสอบย้อนหลังแล้ว agent ทั้ง 5 และการรวมไม่มีความได้เปรียบที่พิสูจน์ได้",
              "ราคา GC=F ต่างจาก XM หลายสิบดอลลาร์ ให้ดูระดับราคาจริงใน MT5"]
    return "\n".join(lines)


def event_flags(f: pd.DataFrame, S: pd.DataFrame, first_per_day: bool = True) -> pd.DataFrame:
    """Per-bar booleans: an event is True on the FIRST bar a condition appears (stateless).
    first_per_day: each event TYPE may fire only once per server day (derived from that day's
    bars, so no stored state is needed) -- keeps the alert volume low."""
    nl, ns = (S >= THETA).sum(axis=1), (S <= -THETA).sum(axis=1)
    c_long, c_short = (nl >= 2) & (ns == 0), (ns >= 2) & (nl == 0)
    ev = pd.DataFrame(index=f.index)
    ev["confluence_long"] = c_long & ~c_long.shift(fill_value=False)
    ev["confluence_short"] = c_short & ~c_short.shift(fill_value=False)
    sa = S["session_asian"].fillna(0)
    ev["asia_break_up"] = (sa > 0) & ~(sa.shift(fill_value=0) > 0)
    ev["asia_break_down"] = (sa < 0) & ~(sa.shift(fill_value=0) < 0)
    b = f["h1_bias"]
    ev["structure_flip"] = b.notna() & b.shift().notna() & (b != b.shift())
    ev = ev[ENABLED_EVENTS]  # user's choice (2026-11-07): agreement events only
    if first_per_day:
        day = ev.index.normalize()
        for c in ev.columns:
            ev[c] = ev[c] & (ev[c].astype(int).groupby(day).cumsum() == 1)
    return ev


ENABLED_EVENTS = ["confluence_long", "confluence_short"]  # asia_break_*/structure_flip are computed but not sent
EVENT_TEXT = {"confluence_long": "≥2 agent เห็นตรงกันฝั่ง 'หนุนทอง' (ไม่มีใครค้าน)",
              "confluence_short": "≥2 agent เห็นตรงกันฝั่ง 'กดทอง' (ไม่มีใครค้าน)",
              "asia_break_up": "ราคาปิดทะลุขึ้นเหนือกรอบเอเชีย", "asia_break_down": "ราคาปิดทะลุลงใต้กรอบเอเชีย",
              "structure_flip": "โครงสร้าง H1 พลิกทิศ (BOS)"}
