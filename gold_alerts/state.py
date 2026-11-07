"""Small persistent state (state.json, committed back by the workflow only when it changes).

It exists so that (a) a delayed or skipped cron run does not lose or duplicate an alert and
(b) the same event type is sent at most once per server day. Pure functions, unit-tested."""
import json
from pathlib import Path

import pandas as pd

SLOTS = ["10:15", "16:00", "22:00"]  # scheduled briefs, broker server time (NY+7h)
GRACE_MIN = 90  # a slot is still sent up to this long after its time (cron can be late)


def _fresh(day: str) -> dict:
    return {"day": day, "sent_events": [], "sent_slots": [], "error_notified": False}


def load(path: Path, server_now: pd.Timestamp) -> dict:
    day = f"{server_now:%Y-%m-%d}"
    try:
        s = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return _fresh(day)
    if s.get("day") != day:  # new server day -> reset the per-day memory
        return _fresh(day)
    return {**_fresh(day), **s}


def save(path: Path, s: dict) -> None:
    path.write_text(json.dumps(s, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def new_events(s: dict, fired: list[str]) -> list[str]:
    return [k for k in fired if k not in s["sent_events"]]


def due_slot(server_now: pd.Timestamp, s: dict) -> str | None:
    """Latest scheduled slot that has passed (within GRACE_MIN) and was not sent yet."""
    due = None
    for slot in SLOTS:
        h, m = map(int, slot.split(":"))
        t = server_now.normalize() + pd.Timedelta(hours=h, minutes=m)
        if t <= server_now < t + pd.Timedelta(minutes=GRACE_MIN) and slot not in s["sent_slots"]:
            due = slot
    return due
