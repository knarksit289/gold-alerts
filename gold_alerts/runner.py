"""One alert run (called every ~15 min by GitHub Actions). Order of work:
fetch -> detect agreement events on today's recent closed bars -> maybe scheduled brief -> send -> save state.
Nothing is sent in --dry-run; state is only changed after a successful send."""
import argparse
import sys
from pathlib import Path

import pandas as pd

from . import brief, live, state as st, telegram

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state.json"
RECENT_BARS = 8  # look back 2h so a late or skipped cron run still catches an event


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print what would be sent; send nothing, save nothing")
    ap.add_argument("--test-telegram", action="store_true", help="send one test message and exit")
    a = ap.parse_args(argv)

    if a.test_telegram:
        telegram.send("✅ ทดสอบการเชื่อมต่อ Telegram สำเร็จ (ระบบแจ้งเตือนบริบททอง)")
        print("test message sent")
        return 0

    now = pd.Timestamp.now(tz="UTC")
    server_now = live.to_server_time(pd.DatetimeIndex([now]))[0]
    s = st.load(STATE_FILE, server_now)
    before = dict(s)
    fails = 0

    def deliver(text: str) -> bool:
        nonlocal fails
        if a.dry_run:
            print("---- DRY RUN (not sent) ----\n" + text + "\n")
            return True
        try:
            telegram.send(text)
            return True
        except RuntimeError as e:
            print(f"SEND FAILED: {e}")
            fails += 1
            return False

    try:
        m15, f, S = brief.build_state(now)
    except Exception as e:  # noqa: BLE001  (Yahoo blocked / schema change / network)
        print(f"DATA ERROR: {type(e).__name__}: {e}")
        if not s["error_notified"] and deliver(f"⚠️ ระบบแจ้งเตือนทองดึงข้อมูลไม่ได้ ({type(e).__name__}) — จะไม่มีสรุป/แจ้งเตือนจนกว่าจะกลับมา (แจ้งครั้งเดียวต่อวัน)"):
            s["error_notified"] = True
    else:
        today = server_now.normalize()
        ev = brief.event_flags(f, S)
        recent = ev[ev.index >= today].iloc[-RECENT_BARS:]
        fired = [k for k in ev.columns if recent[k].any()]
        new = st.new_events(s, fired)
        slot = st.due_slot(server_now, s)

        if new:
            title = "🔔 " + "; ".join(brief.EVENT_TEXT[k] for k in new)
            if deliver(brief.format_brief(title, f, S, now)):
                s["sent_events"] += new
                if slot:  # the event message already carries the full brief
                    s["sent_slots"].append(slot)
        elif slot:
            if deliver(brief.format_brief(f"สรุปบริบททอง (รอบ {slot} เวลา server)", f, S, now)):
                s["sent_slots"].append(slot)
        else:
            print(f"nothing to send (server {server_now:%d %b %H:%M})")

    if not a.dry_run and s != before:
        st.save(STATE_FILE, s)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
