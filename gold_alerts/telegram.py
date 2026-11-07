"""Telegram sender (stdlib only). Secrets come from the environment, never from files.

Errors are re-raised WITHOUT the original exception: urllib's messages can contain the request
URL, and the URL contains the bot token. Logs on a public repo must never show it."""
import json
import os
import urllib.error
import urllib.request


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")
    body = json.dumps({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ok = json.load(r).get("ok")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram HTTP {e.code}") from None
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Telegram {type(e).__name__}") from None
    if not ok:
        raise RuntimeError("Telegram returned ok=false")
