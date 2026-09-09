# Cloud Telegram Macro Monitor

This is a GitHub Actions version of the Fed / dollar-credit monitor. It runs in GitHub's cloud, so your local computer can be off.

## What It Sends

Four times a day it sends a Telegram message covering:

- 2Y, 10Y, and 30Y Treasury yields.
- 10Y real yield and 10Y breakeven inflation.
- Broad dollar, gold, BTC, S&P 500, and Nasdaq. Gold and BTC use public market-quote sources instead of FRED.
- Major US equity index ETFs, sector ETFs, and a watchlist of large/high-signal stocks.
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

The alert windows are anchored to New York time because US macro data, Fed communication, Treasury auctions, and cash equity trading follow that clock. GitHub Actions cron uses UTC, so the workflow includes both US daylight-time and standard-time UTC schedules. The script sends only when the current New York time is inside one of the target windows, which avoids duplicate alerts around daylight-saving changes.

Target New York windows:

- `08:40 ET`, about 10 minutes after 8:30 a.m. data releases.
- `10:40 ET`, about 70 minutes after the US cash open.
- `14:40 ET`, covering Fed/FOMC, Treasury auctions, and afternoon policy windows.
- `20:40 ET`, a post-close wake-up recap after US data vendors have settled daily quotes.

Beijing-time equivalents:

- During US daylight time: `20:40`, `22:40`, `02:40 next day`, `08:40 next day`.
- During US standard time: `21:40`, `23:40`, `03:40 next day`, `09:40 next day`.

Scheduled workflows can be delayed by GitHub during busy periods. For market monitoring this is usually acceptable, but it is not a hard real-time alerting system.

## Important Limitation

This is a rules-based cloud monitor. It does not read every Fed speech or news article semantically unless you extend it with an LLM or a news API. It is designed to keep the core market signal alive while your computer is off.
