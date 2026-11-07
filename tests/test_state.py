"""Tests for the state / scheduling logic (no network).
Run from the repo root:  python tests/test_state.py
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gold_alerts import state as st  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name, info)


T = pd.Timestamp
fresh = st._fresh("2026-11-09")

check("before first slot -> nothing", st.due_slot(T("2026-11-09 10:00"), fresh) is None)
check("exactly 10:15 -> due", st.due_slot(T("2026-11-09 10:15"), fresh) == "10:15")
check("late cron (10:50) still due", st.due_slot(T("2026-11-09 10:50"), fresh) == "10:15")
check("after grace (11:46) -> dropped, not sent stale", st.due_slot(T("2026-11-09 11:46"), fresh) is None)
check("16:00 slot due", st.due_slot(T("2026-11-09 16:07"), fresh) == "16:00")
done = {**fresh, "sent_slots": ["10:15"]}
check("sent slot not repeated", st.due_slot(T("2026-11-09 10:30"), done) is None)

check("new_events filters already-sent", st.new_events({**fresh, "sent_events": ["confluence_short"]},
                                                       ["confluence_short", "confluence_long"]) == ["confluence_long"])

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "state.json"
    check("missing file -> fresh state", st.load(p, T("2026-11-09 12:00")) == fresh)
    s = {**fresh, "sent_events": ["confluence_long"], "sent_slots": ["10:15"]}
    st.save(p, s)
    check("round trip same day", st.load(p, T("2026-11-09 23:59")) == s)
    check("new server day resets memory", st.load(p, T("2026-11-10 00:01")) == st._fresh("2026-11-10"))
    p.write_text("{not json")
    check("corrupt file -> fresh state", st.load(p, T("2026-11-09 12:00")) == fresh)

print("\nALL PASS" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
