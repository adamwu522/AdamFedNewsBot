#!/usr/bin/env python3
import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"

SERIES = {
    "DGS2": "2Y",
    "DGS10": "10Y",
    "DGS30": "30Y",
    "DFII10": "10Y real",
    "T10YIE": "10Y breakeven",
    "BAMLH0A0HYM2": "HY OAS",
    "SP500": "S&P 500",
    "NASDAQCOM": "Nasdaq",
    "DTWEXBGS": "Broad USD",
    "SOFR": "SOFR",
    "EFFR": "EFFR",
    "WALCL": "Fed assets",
    "RESBALNS": "Reserve balances",
    "RRPONTSYD": "ON RRP",
    "DPCREDIT": "Discount window",
}

MARKET_QUOTES = {
    "GOLD": {"label": "Gold", "stooq": "xauusd", "yahoo": "GC=F", "decimals": 2},
    "BTC": {"label": "BTC", "stooq": "btcusd", "yahoo": "BTC-USD", "decimals": 0},
    "SPY": {"label": "S&P 500", "yahoo": "SPY", "decimals": 2},
    "QQQ": {"label": "Nasdaq 100", "yahoo": "QQQ", "decimals": 2},
    "DIA": {"label": "Dow", "yahoo": "DIA", "decimals": 2},
    "IWM": {"label": "Russell 2000", "yahoo": "IWM", "decimals": 2},
    "XLK": {"label": "科技", "yahoo": "XLK", "decimals": 2},
    "XLC": {"label": "通信", "yahoo": "XLC", "decimals": 2},
    "XLY": {"label": "可选消费", "yahoo": "XLY", "decimals": 2},
    "XLF": {"label": "金融", "yahoo": "XLF", "decimals": 2},
    "XLE": {"label": "能源", "yahoo": "XLE", "decimals": 2},
    "XLV": {"label": "医疗", "yahoo": "XLV", "decimals": 2},
    "XLI": {"label": "工业", "yahoo": "XLI", "decimals": 2},
    "XLP": {"label": "必需消费", "yahoo": "XLP", "decimals": 2},
    "XLU": {"label": "公用事业", "yahoo": "XLU", "decimals": 2},
    "XLRE": {"label": "地产", "yahoo": "XLRE", "decimals": 2},
    "XLB": {"label": "材料", "yahoo": "XLB", "decimals": 2},
    "SMH": {"label": "半导体", "yahoo": "SMH", "decimals": 2},
    "NVDA": {"label": "NVDA", "yahoo": "NVDA", "decimals": 2},
    "AAPL": {"label": "AAPL", "yahoo": "AAPL", "decimals": 2},
    "MSFT": {"label": "MSFT", "yahoo": "MSFT", "decimals": 2},
    "AMZN": {"label": "AMZN", "yahoo": "AMZN", "decimals": 2},
    "GOOGL": {"label": "GOOGL", "yahoo": "GOOGL", "decimals": 2},
    "META": {"label": "META", "yahoo": "META", "decimals": 2},
    "TSLA": {"label": "TSLA", "yahoo": "TSLA", "decimals": 2},
    "AVGO": {"label": "AVGO", "yahoo": "AVGO", "decimals": 2},
    "JPM": {"label": "JPM", "yahoo": "JPM", "decimals": 2},
    "XOM": {"label": "XOM", "yahoo": "XOM", "decimals": 2},
    "UNH": {"label": "UNH", "yahoo": "UNH", "decimals": 2},
    "COIN": {"label": "COIN", "yahoo": "COIN", "decimals": 2},
    "MSTR": {"label": "MSTR", "yahoo": "MSTR", "decimals": 2},
}

INDEX_KEYS = ["SPY", "QQQ", "DIA", "IWM"]
SECTOR_KEYS = ["XLK", "XLC", "XLY", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLRE", "XLB", "SMH"]
STOCK_KEYS = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "XOM", "UNH", "COIN", "MSTR"]
TARGET_ET_WINDOWS = [
    (8, 40, "数据发布窗口"),
    (10, 40, "美股开盘确认"),
    (14, 40, "Fed/FOMC/拍卖窗口"),
    (20, 40, "美股收盘总结"),
]
SCHEDULE_GATE_GRACE_MINUTES = 50

EVENTS = [
    ("2026-09-09T08:30:00-04:00", "财政部长端美债回购加码开始"),
    ("2026-09-10T08:30:00-04:00", "PPI 发布"),
    ("2026-09-11T08:30:00-04:00", "CPI 发布"),
    ("2026-09-15T00:00:00-04:00", "FOMC 第一天"),
    ("2026-09-16T14:00:00-04:00", "FOMC 声明、Implementation Note、SEP/点阵图"),
    ("2026-09-16T14:30:00-04:00", "FOMC 记者会"),
    ("2026-09-17T16:30:00-04:00", "Fed blackout 结束；H.4.1 资产负债表"),
]


FETCH_ERRORS = {}
MARKET_SOURCES = {}


def fetch_latest_pair(series_id):
    params = urllib.parse.urlencode({"id": series_id})
    try:
        request = urllib.request.Request(
            f"{FRED_URL}?{params}",
            headers={"User-Agent": "macro-telegram-monitor/1.0"},
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            text = response.read().decode("utf-8")
    except Exception as exc:
        FETCH_ERRORS[series_id] = str(exc)
        return None, None

    values = []
    for row in csv.DictReader(text.splitlines()):
        raw = row.get(series_id, "").strip()
        if not raw or raw == ".":
            continue
        try:
            values.append((row["observation_date"], float(raw)))
        except (KeyError, ValueError):
            continue

    if not values:
        FETCH_ERRORS[series_id] = "no usable values"
        return None, None
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def label_for_key(key):
    if key in SERIES:
        return SERIES[key]
    if key in MARKET_QUOTES:
        return MARKET_QUOTES[key]["label"]
    return key


def decimals_for_key(key):
    if key in MARKET_QUOTES:
        return MARKET_QUOTES[key].get("decimals", 2)
    return 2


def fetch_stooq_pair(symbol):
    params = urllib.parse.urlencode({"s": symbol, "i": "d"})
    request = urllib.request.Request(
        f"{STOOQ_DAILY_URL}?{params}",
        headers={"User-Agent": "macro-telegram-monitor/1.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        text = response.read().decode("utf-8")

    values = []
    for row in csv.DictReader(text.splitlines()):
        raw = row.get("Close", "").strip()
        date_text = row.get("Date", "").strip()
        if not raw or raw.lower() in {"null", "n/a"} or not date_text:
            continue
        try:
            values.append((date_text, float(raw)))
        except ValueError:
            continue

    if not values:
        raise RuntimeError("Stooq returned no usable values")
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def fetch_yahoo_pair(symbol):
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    params = urllib.parse.urlencode({"range": "10d", "interval": "1d"})
    request = urllib.request.Request(
        f"{YAHOO_CHART_URL}{encoded_symbol}?{params}",
        headers={"User-Agent": "macro-telegram-monitor/1.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError("Yahoo returned no chart result")
    closes = (((result[0].get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    timestamps = result[0].get("timestamp") or []
    values = []
    for timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        date_text = dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date().isoformat()
        values.append((date_text, float(close)))
    if not values:
        raise RuntimeError("Yahoo returned no usable values")
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def fetch_market_pair(key):
    quote = MARKET_QUOTES[key]
    errors = []
    try:
        pair = fetch_yahoo_pair(quote["yahoo"])
        MARKET_SOURCES[key] = "Yahoo"
        return pair
    except Exception as exc:
        errors.append(f"Yahoo: {exc}")

    if quote.get("stooq"):
        try:
            pair = fetch_stooq_pair(quote["stooq"])
            MARKET_SOURCES[key] = "Stooq"
            return pair
        except Exception as exc:
            errors.append(f"Stooq: {exc}")

    FETCH_ERRORS[key] = "; ".join(errors)
    return None, None


def change_bp(pair):
    latest, previous = pair
    if not latest or not previous:
        return None
    return (latest[1] - previous[1]) * 100.0


def change_pct(pair):
    latest, previous = pair
    if not latest or not previous or previous[1] == 0:
        return None
    return (latest[1] / previous[1] - 1.0) * 100.0


def fmt_bp(bp):
    if bp is None:
        return "n/a"
    sign = "+" if bp >= 0 else ""
    return f"{sign}{bp:.1f}bp"


def fmt_pct(pct):
    if pct is None:
        return "n/a"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def fmt_level(pair, decimals=2):
    latest = pair[0] if pair else None
    if not latest:
        return "n/a"
    return f"{latest[1]:.{decimals}f}"


def fmt_quote(key, pairs, changes):
    return f"{label_for_key(key)} {fmt_level(pairs.get(key), decimals_for_key(key))} ({fmt_pct(changes.get(f'{key}_pct'))})"


def pct_for_key(key, changes):
    pct = changes.get(f"{key}_pct")
    if pct is None:
        return None
    return pct


def ranked_keys(keys, changes, reverse):
    usable = [(key, pct_for_key(key, changes)) for key in keys]
    usable = [(key, pct) for key, pct in usable if pct is not None]
    return [key for key, _ in sorted(usable, key=lambda item: item[1], reverse=reverse)]


def fmt_movers(keys, changes, count=3):
    if not keys:
        return "n/a"
    return "、".join(f"{label_for_key(key)} {fmt_pct(pct_for_key(key, changes))}" for key in keys[:count])


def matched_target_window(now_et):
    minutes = now_et.hour * 60 + now_et.minute
    for hour, minute, label in TARGET_ET_WINDOWS:
        target = hour * 60 + minute
        if target <= minutes <= target + SCHEDULE_GATE_GRACE_MINUTES:
            return label
    return None


def schedule_skip_reason(now_et):
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return None
    if matched_target_window(now_et):
        return None
    return f"Scheduled run skipped: {now_et:%Y-%m-%d %H:%M %Z} is outside target New York alert windows."


def report_window(now_et):
    matched = matched_target_window(now_et)
    if matched:
        return matched
    minutes = now_et.hour * 60 + now_et.minute
    if 8 * 60 <= minutes <= 9 * 60 + 20:
        return "数据发布窗口"
    if 9 * 60 + 30 <= minutes <= 11 * 60 + 30:
        return "美股开盘确认"
    if 13 * 60 + 45 <= minutes <= 15 * 60 + 15:
        return "Fed/FOMC/拍卖窗口"
    if minutes >= 16 * 60 or minutes <= 7 * 60:
        return "美股收盘总结"
    return "盘中更新"


def fetch_all_pairs():
    pairs = {}
    max_workers = min(10, len(SERIES) + len(MARKET_QUOTES))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_key = {}
        for sid in SERIES:
            future_to_key[executor.submit(fetch_latest_pair, sid)] = sid
        for key in MARKET_QUOTES:
            future_to_key[executor.submit(fetch_market_pair, key)] = key
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            try:
                pairs[key] = future.result()
            except Exception as exc:
                FETCH_ERRORS[key] = str(exc)
                pairs[key] = (None, None)
    return pairs


def next_event(now_et):
    for date_text, label in EVENTS:
        event_time = dt.datetime.fromisoformat(date_text)
        if event_time >= now_et:
            bj_time = event_time.astimezone(ZoneInfo("Asia/Shanghai"))
            return f"{event_time:%Y-%m-%d %H:%M} ET / 北京时间 {bj_time:%m-%d %H:%M} {label}"
    return "9月 FOMC 后续市场反应与资产负债表数据"


def risk_and_conclusion(changes):
    d30 = changes.get("DGS30_bp")
    d10 = changes.get("DGS10_bp")
    d2 = changes.get("DGS2_bp")
    usd = changes.get("DTWEXBGS_pct")
    gold = changes.get("GOLD_pct")
    btc = changes.get("BTC_pct")
    spx = changes.get("SPY_pct")
    if spx is None:
        spx = changes.get("SP500_pct")
    hy = changes.get("BAMLH0A0HYM2_bp")

    long_pressure = (d30 is not None and d30 > 5) or (d10 is not None and d10 > 5)
    short_following = d2 is not None and d2 > 4
    dollar_down = usd is not None and usd < -0.15
    hard_assets_up = (gold is not None and gold > 0.4) or (btc is not None and btc > 1.0)
    risk_off = spx is not None and spx < -0.6
    credit_wider = hy is not None and hy > 3

    if long_pressure and dollar_down and hard_assets_up and credit_wider:
        return "红", "长端上行、美元走弱、黄金/BTC走强且信用利差扩大，接近美元长期债权信用折价交易。"
    if long_pressure and dollar_down and hard_assets_up:
        return "橙", "长端压力没有带来美元走强，市场更像在交易财政主导或长期美元债权折价。"
    if long_pressure and not short_following:
        return "黄", "长端压力上升但短端没有明显跟随，期限溢价/财政压力信号需要继续观察。"
    if short_following and not dollar_down:
        return "绿", "短端跟随上行且美元未转弱，更像市场相信 Fed 会兑现鹰派。"
    if risk_off and not hard_assets_up:
        return "黄", "风险资产承压，但避险/稀缺资产未同步确认，暂时仍是信号混杂。"
    return "黄", "信号混杂，尚不能确认是 Fed 软化还是美元信用重定价。"


def asset_implications(risk, changes):
    btc = changes.get("BTC_pct")
    gold = changes.get("GOLD_pct")
    spx = changes.get("SPY_pct")
    if spx is None:
        spx = changes.get("SP500_pct")
    d30 = changes.get("DGS30_bp")
    usd = changes.get("DTWEXBGS_pct")

    if risk in ("橙", "红"):
        btc_line = "BTC：中期叙事偏利多，但若长端冲击触发去杠杆，短线仍可能剧烈回撤。"
        gold_line = "黄金：最直接受益于美元长期债权折价，除非实际利率继续快速上行。"
        stock_line = "美股：估值和风险溢价受压，若信用利差继续扩大，压力会从成长股扩散。"
    elif d30 is not None and d30 > 5 and usd is not None and usd >= 0:
        btc_line = "BTC：更像被高利率和美元偏强压制，短线利多不清晰。"
        gold_line = "黄金：受到实际利率/美元约束，只有美元信用叙事增强时才更顺。"
        stock_line = "美股：长端折现率上行压估值，成长股更敏感。"
    else:
        btc_line = "BTC：等待美元与真实利率方向确认，暂时更受流动性情绪牵引。"
        gold_line = "黄金：关注美元是否转弱和实际利率是否见顶。"
        stock_line = "美股：主要看2年利率和长端期限溢价谁在主导。"

    if btc is None:
        btc_line += " 当前 BTC 数据源未更新。"
    if gold is None:
        gold_line += " 当前黄金数据源未更新。"
    if spx is None:
        stock_line += " 当前美股指数数据源未更新。"
    return btc_line, gold_line, stock_line


def build_message(now_utc=None):
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)
    now_bj = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))

    pairs = fetch_all_pairs()
    changes = {
        "DGS2_bp": change_bp(pairs["DGS2"]),
        "DGS10_bp": change_bp(pairs["DGS10"]),
        "DGS30_bp": change_bp(pairs["DGS30"]),
        "DFII10_bp": change_bp(pairs["DFII10"]),
        "T10YIE_bp": change_bp(pairs["T10YIE"]),
        "BAMLH0A0HYM2_bp": change_bp(pairs["BAMLH0A0HYM2"]),
        "SP500_pct": change_pct(pairs["SP500"]),
        "NASDAQCOM_pct": change_pct(pairs["NASDAQCOM"]),
        "BTC_pct": change_pct(pairs["BTC"]),
        "GOLD_pct": change_pct(pairs["GOLD"]),
        "DTWEXBGS_pct": change_pct(pairs["DTWEXBGS"]),
        "SOFR_bp": change_bp(pairs["SOFR"]),
        "EFFR_bp": change_bp(pairs["EFFR"]),
        "WALCL_pct": change_pct(pairs["WALCL"]),
        "RESBALNS_pct": change_pct(pairs["RESBALNS"]),
        "RRPONTSYD_pct": change_pct(pairs["RRPONTSYD"]),
        "DPCREDIT_pct": change_pct(pairs["DPCREDIT"]),
    }
    changes.update({f"{key}_pct": change_pct(pairs[key]) for key in MARKET_QUOTES})

    risk, conclusion = risk_and_conclusion(changes)
    btc_line, gold_line, stock_line = asset_implications(risk, changes)
    sector_winners = ranked_keys(SECTOR_KEYS, changes, reverse=True)
    sector_losers = ranked_keys(SECTOR_KEYS, changes, reverse=False)
    stock_winners = ranked_keys(STOCK_KEYS, changes, reverse=True)
    stock_losers = ranked_keys(STOCK_KEYS, changes, reverse=False)
    index_line = "；".join(fmt_quote(key, pairs, changes) for key in INDEX_KEYS)

    lines = [
        "【Fed/美元信用监控】",
        f"时间：北京时间 {now_bj:%m-%d %H:%M} / 美东时间 {now_et:%m-%d %H:%M}",
        f"窗口：{report_window(now_et)}",
        f"风险灯号：{risk}",
        f"结论：{conclusion}",
        "",
        "关键变化：",
        f"1. 利率：2Y {fmt_level(pairs['DGS2'])}% ({fmt_bp(changes['DGS2_bp'])})；10Y {fmt_level(pairs['DGS10'])}% ({fmt_bp(changes['DGS10_bp'])})；30Y {fmt_level(pairs['DGS30'])}% ({fmt_bp(changes['DGS30_bp'])})。",
        f"2. 实际利率/通胀预期：10Y real {fmt_level(pairs['DFII10'])}% ({fmt_bp(changes['DFII10_bp'])})；10Y breakeven {fmt_level(pairs['T10YIE'])}% ({fmt_bp(changes['T10YIE_bp'])})。",
        f"3. 跨资产：Broad USD {fmt_pct(changes['DTWEXBGS_pct'])}；黄金 {fmt_level(pairs['GOLD'])} ({fmt_pct(changes['GOLD_pct'])})；BTC {fmt_level(pairs['BTC'], 0)} ({fmt_pct(changes['BTC_pct'])})。",
        f"4. 美股指数：{index_line}。",
        f"5. 美股板块：强 {fmt_movers(sector_winners, changes)}；弱 {fmt_movers(sector_losers, changes)}。",
        f"6. 重点个股：强 {fmt_movers(stock_winners, changes)}；弱 {fmt_movers(stock_losers, changes)}。",
        f"7. 信用/流动性：HY OAS {fmt_level(pairs['BAMLH0A0HYM2'])}% ({fmt_bp(changes['BAMLH0A0HYM2_bp'])})；SOFR {fmt_level(pairs['SOFR'])}%；EFFR {fmt_level(pairs['EFFR'])}%。",
        f"8. Fed表：总资产 {fmt_pct(changes['WALCL_pct'])}；准备金 {fmt_pct(changes['RESBALNS_pct'])}；ON RRP {fmt_pct(changes['RRPONTSYD_pct'])}；贴现窗口 {fmt_pct(changes['DPCREDIT_pct'])}。",
        "",
        "对资产：",
        btc_line,
        gold_line,
        stock_line,
        "",
        f"下一观察点：{next_event(now_et)}。",
        "",
        "注：这是云端规则版快报，侧重公开数据和阈值判断；Fed讲话/新闻语义仍建议用人工或LLM复核。",
    ]
    if FETCH_ERRORS:
        missing = "、".join(label_for_key(sid) for sid in sorted(FETCH_ERRORS)[:5])
        suffix = "等" if len(FETCH_ERRORS) > 5 else ""
        lines.append(f"数据提示：{missing}{suffix} 暂未更新或无法读取。")
    if MARKET_SOURCES:
        sources = "、".join(sorted(set(MARKET_SOURCES.values())))
        lines.append(f"行情源：市场报价 {sources}；宏观/利率序列 FRED。")
    return "\n".join(lines)


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API failed: {payload}")


def main():
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
    skip_reason = schedule_skip_reason(now_et)
    if skip_reason:
        print(skip_reason)
        return

    message = build_message(now_utc)
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
