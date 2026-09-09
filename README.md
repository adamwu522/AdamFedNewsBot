# Cloud Telegram Macro Monitor

This is a GitHub Actions version of the Fed / dollar-credit monitor. It runs in GitHub's cloud, so your local computer can be off.

## What It Sends

Twice a day it sends a Telegram message covering:

- 2Y, 10Y, and 30Y Treasury yields.
- 10Y real yield and 10Y breakeven inflation.
- Broad dollar, gold, BTC, S&P 500, and Nasdaq. Gold and BTC use public market-quote sources instead of FRED.
- High-yield credit spread and short-term funding rates.
- Fed balance sheet proxies: total assets, reserve balances, ON RRP, and discount-window borrowing.
- A green/yellow/orange/red risk light and short implications for BTC, gold, and US equities.

## Setup

1. Create a private GitHub repository.
2. Upload these files to that repository, preserving the `.github/workflows/macro-monitor.yml` path.
3. In the repository, open `Settings` -> `Secrets and variables` -> `Actions`.
4. Add two repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Open `Actions` -> `Macro Telegram Monitor` -> `Run workflow` to send a manual test.

## Schedule

GitHub Actions cron uses UTC:

- `12:40 UTC` = `20:40 Beijing time`, about 10 minutes after 8:30 a.m. New York data releases during US daylight time.
- `21:40 UTC` = `05:40 Beijing time`, after the US cash-market close during US daylight time.

Scheduled workflows can be delayed by GitHub during busy periods. For market monitoring this is usually acceptable, but it is not a hard real-time alerting system.

## Important Limitation

This is a rules-based cloud monitor. It does not read every Fed speech or news article semantically unless you extend it with an LLM or a news API. It is designed to keep the core market signal alive while your computer is off.
