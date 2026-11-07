# gold-alerts

Contextual gold (XAU) brief sent to Telegram. **Not a trading signal.** Back-tests of the five rule-based
"agents" and of their agreement found no provable edge; this tool only summarises what each one currently
reads, so a human can decide.

## What it sends (≈3.9 messages/day)
- 3 scheduled briefs per server day at 10:15 / 16:00 / 22:00 (broker server time = New York + 7h)
- an event message when ≥2 agents agree in one direction with none against, first time per type per day

Prices come from Yahoo `GC=F` (futures), which sits tens of dollars away from spot brokers, so only relative
quantities are shown.

## Setup
1. Create a bot with @BotFather, send it any message, and get your chat id.
2. Set the secrets yourself in your own terminal (do not paste tokens in chat or commit them):
   ```
   gh secret set TELEGRAM_BOT_TOKEN
   gh secret set TELEGRAM_CHAT_ID
   ```
3. Actions → gold-alert → Run workflow: `dry-run` first (checks Yahoo works from GitHub's IPs), then
   `test-telegram`, then enable the schedule by leaving it on.

## Local run
```
pip install -r requirements.txt
python tests/test_live.py && python tests/test_state.py
python run_alert.py --dry-run
```

## Known limits
- Yahoo may block or throttle GitHub-hosted runners. If so the bot sends one "data unavailable" notice per day.
- Scheduled workflows can be delayed or skipped by GitHub; a 2-hour look-back and `state.json` prevent loss/duplicates.
- GitHub may pause scheduled workflows after 60 days without repository activity; state commits normally count.
- Events skew to the side the market has been on (35 of 36 recent events were bearish) — that reflects the
  regime, not a reason to trade.
