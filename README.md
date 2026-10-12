# Cloud Telegram Macro Monitor

This is a GitHub Actions version of the Fed / dollar-credit monitor. It runs in GitHub's cloud, so your local computer can be off.

## What It Sends

Twice a day it sends a Telegram market message covering:

- 2Y, 10Y, and 30Y Treasury yields.
- 10Y real yield and 10Y breakeven inflation.
- Broad dollar, gold, BTC, S&P 500, and Nasdaq. Gold and BTC use public market-quote sources instead of FRED.
- Major US equity index ETFs and broad sector ETFs.
- AI-linked stocks grouped by chips/GPUs, HBM/NAND storage, semiconductor equipment/EDA, networking/optical, servers/cooling, cloud platforms, and data-center power.
- High-yield credit spread and short-term funding rates.
- Fed balance sheet proxies: total assets, reserve balances, ON RRP, and discount-window borrowing.
- A green/yellow/orange/red risk light and short implications for BTC, gold, and US equities.
- US spot BTC ETF daily net flows, change from the previous reported session, 5/20-session totals, flow streak, major funds, and the latest 5-session trend versus the preceding five.

There is no separate health-check message or overnight Fed/opening-bell alert. ETF data is refreshed in both digests, so the evening edition can include disclosures missing from the morning edition.

## Setup

1. Create a private GitHub repository.
2. Upload these files to that repository, preserving the `.github/workflows/macro-monitor.yml` path.
3. In the repository, open `Settings` -> `Secrets and variables` -> `Actions`.
4. Add two repository secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
5. Open `Actions` -> `Macro Telegram Monitor` -> `Run workflow` to send a manual test.

## Schedule

The morning recap is fixed to Beijing time; the evening data-release recap follows New York time. GitHub Actions cron uses UTC and can be delayed, so the workflow runs as a 20-minute watchdog. Frequent watchdog runs do not mean frequent Telegram messages: both native and external triggers use the same two daily send markers.

Target windows (every calendar day):

- Morning: `08:40 Asia/Shanghai`, US close recap and BTC ETF flows. This stays at 08:40 all year.
- Evening: `08:40 America/New_York`, about 10 minutes after 8:30 a.m. data releases, plus updated ETF disclosures.

Beijing-time equivalents:

- During US daylight time: `08:40` and `20:40`.
- During US standard time: `08:40` and `21:40`.

Normal delivery should be within roughly 10-30 minutes of the listed window, depending on GitHub's queue. The workflow uses an Actions cache marker to skip duplicates if more than one watchdog run lands inside the same window.

If GitHub wakes up late, the script can catch up for at most 3 hours, never beyond midnight in Beijing. Pushes run tests and obey the same delivery windows; deploying code no longer creates an extra immediate alert. Manual `Run workflow` remains an explicit immediate-send override. Reducing frequency means Fed announcements between these windows are covered by the next digest rather than an immediate notification.

## BTC ETF Data

The source is [Farside Investors' all-data table](https://farside.co.uk/bitcoin-etf-flow-all-data/), in USD millions. If direct access fails, a public Jina Reader rendering of the same page is tried. This is an alternate access route, not an independent second data provider. No additional API secret is required.

- Reports label the US trading date, not the fetch date, and never turn an unreported dash into a zero flow.
- Partial days show only a reported subtotal and do not enter trend calculations. Complete days require all active funds and a reconciled total (allowing the source's rounding).
- Rolling totals use the latest 5/20 fully disclosed sessions, explicitly labeled as such. They stop at partially reported rows; streaks also stop at wholly unreported rows, so an undisclosed day cannot extend a claimed streak.
- Weekends and empty holiday rows are not zero-flow trading days. If no new complete row is available, the last complete date is shown explicitly. Missing dates may reflect a holiday or delayed disclosure; the monitor does not infer a holiday from absent data.
- History is cached separately from delivery markers. A source outage can display dated history with a clear cache warning; it does not interrupt the macro report or claim a fresh trend.
- Flows describe ETF creations/redemptions, not AUM price changes or all institutional BTC demand.

Run checks with `python3 -m unittest discover -s tests -v`. To preview a full report without sending Telegram, set `GITHUB_EVENT_NAME=workflow_dispatch` and run `python3 scripts/macro_monitor.py --dry-run`.

## Reliability

- Telegram sends are retried up to 5 times with short backoff.
- Data reads are retried before being marked unavailable.
- Key Treasury yield points fall back to the US Treasury XML feed if FRED is unavailable.
- SOFR and EFFR fall back to the New York Fed reference-rate API if FRED is unavailable.
- Missing data is summarized in one warning line instead of filling the report with `n/a`.
- Manual `Run workflow` always sends a market message immediately.
- Scheduled runs outside the two target/catch-up windows exit quietly.
- Late scheduled runs can catch up the latest missed market window when it has not already been sent.
- For more reliable timing, use an external cron service to trigger the `macro-monitor-watchdog` repository dispatch event every 10-20 minutes. GitHub's own schedule can then remain as a backup.
- Watchdog triggers reduce the chance that a delayed or dropped scheduled run causes a missed alert, but GitHub Actions and mobile push notifications are still not a hard real-time delivery system.

## External Watchdog Trigger

GitHub's built-in schedule is best-effort. For stronger timing, create a fine-grained GitHub token for this repository, then configure an external cron service to call:

`POST https://api.github.com/repos/adamwu522/AdamFedNewsBot/dispatches`

Headers:

- `Accept: application/vnd.github+json`
- `Authorization: Bearer YOUR_GITHUB_TOKEN`
- `X-GitHub-Api-Version: 2022-11-28`

Body:

```json
{"event_type":"macro-monitor-watchdog"}
```

The external cron can run every 10-20 minutes. The script still sends only inside target or catch-up windows, and the Actions cache marker skips duplicate alerts.

## Important Limitation

This is a rules-based cloud monitor. It does not read every Fed speech or news article semantically unless you extend it with an LLM or a news API. It is designed to keep the core market signal alive while your computer is off.
