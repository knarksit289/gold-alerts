"""Tests for the live path: unfinished-bar removal and the server-time conversion.
Run from GOLD-AGENTS/:  ~/.venvs/gold-agents/bin/python tests/test_live.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gold_alerts.live import drop_unfinished, to_server_time  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, info)


idx = pd.to_datetime(["2026-11-06 19:00", "2026-11-06 19:15", "2026-11-06 19:30"], utc=True)
df = pd.DataFrame({"close": [1, 2, 3]}, index=idx)
# at 19:25 the 19:15 bar (ends 19:30) is still forming; 19:30 bar not started
k = drop_unfinished(df, pd.Timestamp("2026-11-06 19:25", tz="UTC"))
check("19:25 -> only the 19:00 bar is closed", list(k.close) == [1], list(k.close))
k = drop_unfinished(df, pd.Timestamp("2026-11-06 19:30", tz="UTC"))
check("19:30 exactly -> 19:15 bar is closed", list(k.close) == [1, 2], list(k.close))
k = drop_unfinished(df, pd.Timestamp("2026-11-06 19:30:01", tz="UTC"))
check("a forming 19:30 bar is never included", 3 not in list(k.close))

# Yahoo's live-quote stub (19:16:01) must be rejected even after its 15-min window has passed
from gold_alerts.live import on_grid  # noqa: E402
idx2 = pd.to_datetime(["2026-11-06 19:00:00", "2026-11-06 19:15:00", "2026-11-06 19:16:01"], utc=True)
stub = pd.DataFrame({"close": [1, 2, 99]}, index=idx2)
k = drop_unfinished(on_grid(stub), pd.Timestamp("2026-11-06 19:45", tz="UTC"))
check("stub row 19:16:01 is not a bar", 99 not in list(k.close) and list(k.close) == [1, 2], list(k.close))

# server time = New York + 7h: summer (EDT = UTC-4) => UTC+3 ; winter (EST = UTC-5) => UTC+2
s = to_server_time(pd.to_datetime(["2026-08-28 12:00", "2026-12-15 12:00"], utc=True))
check("summer server = UTC+3", s[0] == pd.Timestamp("2026-08-28 15:00"), s[0])
check("winter server = UTC+2", s[1] == pd.Timestamp("2026-12-15 14:00"), s[1])
print("\nALL PASS" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
