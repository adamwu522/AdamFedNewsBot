# Cloud Telegram Macro Monitor

This is a GitHub Actions version of the Fed / dollar-credit monitor. It runs in GitHub's cloud, so your local computer can be off.

## What It Sends

Four times a day it sends a Telegram market message covering:

- 2Y, 10Y, and 30Y Treasury yields.
- 10Y real yield and 10Y breakeven inflation.
- Broad dollar, gold, BTC, S&P 500, and Nasdaq. Gold and BTC use public market-quote sources instead of FRED.
- Major US equity index ETFs and broad sector ETFs.
- AI-linked stocks grouped by chips/GPUs, HBM/NAND storage, semiconductor equipment/EDA, networking/optical, servers/cooling, cloud platforms, and data-center power.
- High-yield credit spread and short-term funding rates.
- Fed balance sheet proxies: total assets, reserve balances, ON RRP, and discount-window borrowing.
- A green/yellow/orange/red risk light and short implications for BTC, gold, and US equities.

It also sends one daily health-check message to confirm that GitHub Actions and Telegram delivery are still working.

## Setup

1. Create a private GitHub repository.
2. Upload these files to that repository, preserving the `.github/workflows/macro-monitor.yml` path.
3. In the repository, open `Settings` -> `Secrets and variables` -> `Actions`.
4. Add two repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Open `Actions` -> `Macro Telegram Monitor` -> `Run workflow` to send a manual test.

## Schedule

The alert windows are anchored to New York time because US macro data, Fed communication, Treasury auctions, and cash equity trading follow that clock. GitHub Actions cron uses UTC and can be delayed, so the workflow runs as a 20-minute watchdog. The script sends only when the current New York time is inside one of the target windows, which avoids daylight-saving-time drift and reduces the chance that one delayed scheduled run causes a missed alert.

Target New York windows:

- `08:40 ET`, about 10 minutes after 8:30 a.m. data releases.
- `10:40 ET`, about 70 minutes after the US cash open.
- `14:40 ET`, covering Fed/FOMC, Treasury auctions, and afternoon policy windows.
- `20:40 ET`, a post-close wake-up recap after US data vendors have settled daily quotes.
- `07:10 ET`, a short daily health check.

Beijing-time equivalents:

- During US daylight time, market messages arrive around `20:40`, `22:40`, `02:40 next day`, and `08:40 next day`; the health check arrives around `19:10`.
- During US standard time, market messages arrive around `21:40`, `23:40`, `03:40 next day`, and `09:40 next day`; the health check arrives around `20:10`.

Normal delivery should be within roughly 10-30 minutes of the listed window, depending on GitHub's queue. The workflow uses an Actions cache marker to skip duplicates if more than one watchdog run lands inside the same window.

If GitHub wakes up late, the script can still send the latest missed market window for up to 8 hours and marks it as a delayed catch-up. Pushes to `main` that change the workflow or scripts also run one immediate market check, which makes deployment tests visible without waiting for the next scheduled wake-up.

## Reliability

- Telegram sends are retried up to 5 times with short backoff.
- Data reads are retried before being marked unavailable.
- Key Treasury yield points fall back to the US Treasury XML feed if FRED is unavailable.
- SOFR and EFFR fall back to the New York Fed reference-rate API if FRED is unavailable.
- Missing data is summarized in one warning line instead of filling the report with `n/a`.
- Manual `Run workflow` always sends a market message immediately.
- Scheduled runs outside the New York target windows exit quietly.
- Late scheduled runs can catch up the latest missed market window when it has not already been sent.
- Watchdog triggers reduce the chance that a delayed or dropped scheduled run causes a missed alert, but GitHub Actions and mobile push notifications are still not a hard real-time delivery system.

## Important Limitation

This is a rules-based cloud monitor. It does not read every Fed speech or news article semantically unless you extend it with an LLM or a news API. It is designed to keep the core market signal alive while your computer is off.
