#!/usr/bin/env python3
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
TREASURY_XML_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
NYFED_RATES_URL = "https://markets.newyorkfed.org/api/rates"
HTTP_MAX_ATTEMPTS = 3
HTTP_RETRY_BASE_SECONDS = 1
TELEGRAM_MAX_ATTEMPTS = 5
TELEGRAM_RETRY_BASE_SECONDS = 2

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
    "WALCL": "Fed总资产",
    "RESBALNS": "准备金",
    "RRPONTSYD": "ON RRP",
    "DPCREDIT": "贴现窗口",
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
    "AMD": {"label": "AMD", "yahoo": "AMD", "decimals": 2},
    "ARM": {"label": "ARM", "yahoo": "ARM", "decimals": 2},
    "TSM": {"label": "TSM", "yahoo": "TSM", "decimals": 2},
    "AAPL": {"label": "AAPL", "yahoo": "AAPL", "decimals": 2},
    "MSFT": {"label": "MSFT", "yahoo": "MSFT", "decimals": 2},
    "AMZN": {"label": "AMZN", "yahoo": "AMZN", "decimals": 2},
    "GOOGL": {"label": "GOOGL", "yahoo": "GOOGL", "decimals": 2},
    "META": {"label": "META", "yahoo": "META", "decimals": 2},
    "ORCL": {"label": "ORCL", "yahoo": "ORCL", "decimals": 2},
    "TSLA": {"label": "TSLA", "yahoo": "TSLA", "decimals": 2},
    "AVGO": {"label": "AVGO", "yahoo": "AVGO", "decimals": 2},
    "MU": {"label": "美光", "yahoo": "MU", "decimals": 2},
    "SNDK": {"label": "闪迪", "yahoo": "SNDK", "decimals": 2},
    "WDC": {"label": "WDC", "yahoo": "WDC", "decimals": 2},
    "STX": {"label": "STX", "yahoo": "STX", "decimals": 2},
    "000660.KS": {"label": "海力士", "yahoo": "000660.KS", "decimals": 0},
    "005930.KS": {"label": "三星电子", "yahoo": "005930.KS", "decimals": 0},
    "ASML": {"label": "ASML", "yahoo": "ASML", "decimals": 2},
    "AMAT": {"label": "AMAT", "yahoo": "AMAT", "decimals": 2},
    "LRCX": {"label": "LRCX", "yahoo": "LRCX", "decimals": 2},
    "KLAC": {"label": "KLAC", "yahoo": "KLAC", "decimals": 2},
    "SNPS": {"label": "SNPS", "yahoo": "SNPS", "decimals": 2},
    "CDNS": {"label": "CDNS", "yahoo": "CDNS", "decimals": 2},
    "ANET": {"label": "ANET", "yahoo": "ANET", "decimals": 2},
    "MRVL": {"label": "MRVL", "yahoo": "MRVL", "decimals": 2},
    "COHR": {"label": "COHR", "yahoo": "COHR", "decimals": 2},
    "LITE": {"label": "LITE", "yahoo": "LITE", "decimals": 2},
    "SMCI": {"label": "SMCI", "yahoo": "SMCI", "decimals": 2},
    "DELL": {"label": "DELL", "yahoo": "DELL", "decimals": 2},
    "HPE": {"label": "HPE", "yahoo": "HPE", "decimals": 2},
    "VRT": {"label": "VRT", "yahoo": "VRT", "decimals": 2},
    "VST": {"label": "VST", "yahoo": "VST", "decimals": 2},
    "CEG": {"label": "CEG", "yahoo": "CEG", "decimals": 2},
    "ETN": {"label": "ETN", "yahoo": "ETN", "decimals": 2},
    "GEV": {"label": "GEV", "yahoo": "GEV", "decimals": 2},
    "JPM": {"label": "JPM", "yahoo": "JPM", "decimals": 2},
    "XOM": {"label": "XOM", "yahoo": "XOM", "decimals": 2},
    "UNH": {"label": "UNH", "yahoo": "UNH", "decimals": 2},
    "COIN": {"label": "COIN", "yahoo": "COIN", "decimals": 2},
    "MSTR": {"label": "MSTR", "yahoo": "MSTR", "decimals": 2},
}

INDEX_KEYS = ["SPY", "QQQ", "DIA", "IWM"]
SECTOR_KEYS = ["XLK", "XLC", "XLY", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLRE", "XLB", "SMH"]
AI_GROUPS = [
    ("AI芯片/GPU", ["NVDA", "AMD", "AVGO", "ARM", "TSM"]),
    ("存储/HBM/NAND", ["MU", "SNDK", "WDC", "STX", "000660.KS", "005930.KS"]),
    ("设备/EDA", ["ASML", "AMAT", "LRCX", "KLAC", "SNPS", "CDNS"]),
    ("网络/光模块", ["ANET", "MRVL", "COHR", "LITE"]),
    ("服务器/散热", ["SMCI", "DELL", "HPE", "VRT"]),
    ("云/平台", ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]),
    ("电力/数据中心", ["VST", "CEG", "ETN", "GEV"]),
]
AI_STOCK_KEYS = list(dict.fromkeys(key for _, keys in AI_GROUPS for key in keys))
TARGET_ET_WINDOWS = [
    (8, 40, "数据发布窗口"),
    (10, 40, "美股开盘确认"),
    (14, 40, "Fed/FOMC/拍卖窗口"),
    (20, 40, "美股收盘总结"),
]
SCHEDULE_GATE_GRACE_MINUTES = 90
EXTENDED_WINDOW_GRACE_MINUTES = {
    (14, 40): 180,
    (20, 40): 180,
}
BACKUP_TRIGGER_OFFSET_MINUTES = 30
HEALTH_CHECK_ET_WINDOW = (7, 10, "系统健康检查")
HEALTH_CHECK_GRACE_MINUTES = 35

EVENTS = [
    ("2026-09-09T08:30:00-04:00", "财政部长端美债回购加码开始"),
    ("2026-09-10T08:30:00-04:00", "PPI 发布"),
    ("2026-09-11T08:30:00-04:00", "CPI 发布"),
    ("2026-09-15T00:00:00-04:00", "FOMC 第一天"),
    ("2026-09-16T14:00:00-04:00", "FOMC 声明、Implementation Note、SEP/点阵图"),
    ("2026-09-16T14:30:00-04:00", "FOMC 记者会"),
    ("2026-09-17T16:30:00-04:00", "Fed blackout 结束；H.4.1 资产负债表"),
]


TREASURY_FALLBACKS = {
    "DGS2": ("daily_treasury_yield_curve", "BC_2YEAR"),
    "DGS10": ("daily_treasury_yield_curve", "BC_10YEAR"),
    "DGS30": ("daily_treasury_yield_curve", "BC_30YEAR"),
    "DFII10": ("daily_treasury_real_yield_curve", "TC_10YEAR"),
}
NYFED_RATE_FALLBACKS = {
    "SOFR": ("secured", "sofr"),
    "EFFR": ("unsecured", "effr"),
}
FED_BALANCE_UNITS = {
    "WALCL": "millions",
    "RESBALNS": "billions",
    "RRPONTSYD": "billions",
    "DPCREDIT": "billions",
}

FETCH_ERRORS = {}
MARKET_SOURCES = {}
DATA_SOURCES = {}
ERROR_PRIORITY = [
    "DGS2",
    "DGS10",
    "DGS30",
    "DFII10",
    "T10YIE",
    "SOFR",
    "EFFR",
    "WALCL",
    "RESBALNS",
    "RRPONTSYD",
    "DPCREDIT",
    "DTWEXBGS",
    "BAMLH0A0HYM2",
]


def read_url_text(request, timeout=25, attempts=HTTP_MAX_ATTEMPTS):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(HTTP_RETRY_BASE_SECONDS * attempt, 5))
    raise last_error


def fetch_fred_pair(series_id):
    params = urllib.parse.urlencode({"id": series_id})
    request = urllib.request.Request(
        f"{FRED_URL}?{params}",
        headers={"User-Agent": "macro-telegram-monitor/1.0"},
    )
    text = read_url_text(request)

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
        raise RuntimeError("FRED returned no usable values")
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def previous_month(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1


def recent_treasury_months():
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    year = today.year
    month = today.month
    months = []
    for _ in range(3):
        months.append(f"{year}{month:02d}")
        year, month = previous_month(year, month)
    return months


def xml_local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_treasury_values(text, field_name):
    values = []
    root = ET.fromstring(text)
    for element in root.iter():
        if xml_local_name(element.tag) != "properties":
            continue
        fields = {xml_local_name(child.tag): (child.text or "").strip() for child in list(element)}
        date_text = fields.get("NEW_DATE", "")[:10]
        raw_value = fields.get(field_name, "")
        if not date_text or not raw_value:
            continue
        try:
            values.append((date_text, float(raw_value)))
        except ValueError:
            continue
    return values


def fetch_treasury_pair(series_id):
    dataset, field_name = TREASURY_FALLBACKS[series_id]
    values = []
    for month in recent_treasury_months():
        params = urllib.parse.urlencode(
            {
                "data": dataset,
                "field_tdr_date_value_month": month,
            }
        )
        request = urllib.request.Request(
            f"{TREASURY_XML_URL}?{params}",
            headers={"User-Agent": "macro-telegram-monitor/1.0"},
        )
        text = read_url_text(request)
        values.extend(parse_treasury_values(text, field_name))

    deduped = {}
    for date_text, value in values:
        deduped[date_text] = value
    values = sorted(deduped.items())
    if not values:
        raise RuntimeError("Treasury returned no usable values")
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def fetch_nyfed_rate_pair(series_id):
    market, rate = NYFED_RATE_FALLBACKS[series_id]
    request = urllib.request.Request(
        f"{NYFED_RATES_URL}/{market}/{rate}/last/5.json",
        headers={"User-Agent": "macro-telegram-monitor/1.0"},
    )
    payload = json.loads(read_url_text(request))
    values = []
    for row in payload.get("refRates") or []:
        date_text = (row.get("effectiveDate") or "").strip()
        raw_value = row.get("percentRate")
        if not date_text or raw_value is None:
            continue
        try:
            values.append((date_text, float(raw_value)))
        except (TypeError, ValueError):
            continue
    values = sorted(values)
    if not values:
        raise RuntimeError("NY Fed returned no usable values")
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


def fetch_latest_pair(series_id):
    errors = []
    try:
        pair = fetch_fred_pair(series_id)
        DATA_SOURCES[series_id] = "FRED"
        return pair
    except Exception as exc:
        errors.append(f"FRED: {exc}")

    if series_id in TREASURY_FALLBACKS:
        try:
            pair = fetch_treasury_pair(series_id)
            DATA_SOURCES[series_id] = "Treasury"
            return pair
        except Exception as exc:
            errors.append(f"Treasury: {exc}")

    if series_id in NYFED_RATE_FALLBACKS:
        try:
            pair = fetch_nyfed_rate_pair(series_id)
            DATA_SOURCES[series_id] = "NY Fed"
            return pair
        except Exception as exc:
            errors.append(f"NY Fed: {exc}")

    FETCH_ERRORS[series_id] = "; ".join(errors)
    return None, None


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
    text = read_url_text(request)

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
    payload = json.loads(read_url_text(request))

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


def stooq_fallback_symbol(yahoo_symbol):
    if not yahoo_symbol:
        return None
    if yahoo_symbol.endswith(".KS") or "=" in yahoo_symbol or "-" in yahoo_symbol:
        return None
    return f"{yahoo_symbol.lower()}.us"


def fetch_market_pair(key):
    quote = MARKET_QUOTES[key]
    errors = []
    try:
        pair = fetch_yahoo_pair(quote["yahoo"])
        MARKET_SOURCES[key] = "Yahoo"
        return pair
    except Exception as exc:
        errors.append(f"Yahoo: {exc}")

    stooq_symbol = quote.get("stooq") or stooq_fallback_symbol(quote.get("yahoo"))
    if stooq_symbol:
        try:
            pair = fetch_stooq_pair(stooq_symbol)
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
        return "未更新"
    sign = "+" if bp >= 0 else ""
    return f"{sign}{bp:.1f}bp"


def fmt_pct(pct):
    if pct is None:
        return "未更新"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def fmt_level(pair, decimals=2):
    latest = pair[0] if pair else None
    if not latest:
        return "未更新"
    return f"{latest[1]:.{decimals}f}"


def has_latest(pair):
    latest = pair[0] if pair else None
    return latest is not None


def fmt_quote(key, pairs, changes):
    pair = pairs.get(key)
    if not has_latest(pair):
        return None
    pct = pct_for_key(key, changes)
    change = f" ({fmt_pct(pct)})" if pct is not None else ""
    return f"{label_for_key(key)} {fmt_level(pair, decimals_for_key(key))}{change}"


def fmt_quote_list(keys, pairs, changes):
    items = [fmt_quote(key, pairs, changes) for key in keys]
    items = [item for item in items if item]
    if not items:
        return "暂无可用报价"
    return "；".join(items)


def fmt_level_change(label, pair, change, decimals=2, suffix="", change_formatter=fmt_pct):
    if not has_latest(pair):
        return f"{label} 未更新"
    change_text = f" ({change_formatter(change)})" if change is not None else ""
    return f"{label} {fmt_level(pair, decimals)}{suffix}{change_text}"


def any_latest(pairs, keys):
    return any(has_latest(pairs.get(key)) for key in keys)


def fmt_rates_line(pairs, changes):
    keys = [("2Y", "DGS2"), ("10Y", "DGS10"), ("30Y", "DGS30")]
    if not any_latest(pairs, [key for _, key in keys]):
        return "1. 利率：核心美债收益率暂未取到，先不据此判断长端压力。"
    items = [
        fmt_level_change(label, pairs[key], changes[f"{key}_bp"], suffix="%", change_formatter=fmt_bp)
        for label, key in keys
    ]
    return f"1. 利率：{'；'.join(items)}。"


def fmt_real_rate_line(pairs, changes):
    keys = [("10Y real", "DFII10"), ("10Y breakeven", "T10YIE")]
    if not any_latest(pairs, [key for _, key in keys]):
        return "2. 实际利率/通胀预期：相关序列暂未取到，先看名义利率和黄金/BTC确认。"
    items = [
        fmt_level_change(label, pairs[key], changes[f"{key}_bp"], suffix="%", change_formatter=fmt_bp)
        for label, key in keys
    ]
    return f"2. 实际利率/通胀预期：{'；'.join(items)}。"


def fmt_cross_asset_line(pairs, changes):
    keys = ["DTWEXBGS", "GOLD", "BTC"]
    if not any_latest(pairs, keys):
        return "3. 跨资产：美元、黄金、BTC 报价暂未取到，先不据此判断美元信用交易。"
    items = [
        fmt_level_change("Broad USD", pairs["DTWEXBGS"], changes["DTWEXBGS_pct"]),
        fmt_level_change("黄金", pairs["GOLD"], changes["GOLD_pct"]),
        fmt_level_change("BTC", pairs["BTC"], changes["BTC_pct"], decimals=0),
    ]
    return f"3. 跨资产：{'；'.join(items)}。"


def fmt_credit_liquidity_line(pairs, changes):
    keys = ["BAMLH0A0HYM2", "SOFR", "EFFR"]
    if not any_latest(pairs, keys):
        return "8. 信用/流动性：HY OAS、SOFR、EFFR 暂未取到，先不据此判断信用扩散。"
    items = [
        fmt_level_change("HY OAS", pairs["BAMLH0A0HYM2"], changes["BAMLH0A0HYM2_bp"], suffix="%", change_formatter=fmt_bp),
        fmt_level_change("SOFR", pairs["SOFR"], changes["SOFR_bp"], suffix="%", change_formatter=fmt_bp),
        fmt_level_change("EFFR", pairs["EFFR"], changes["EFFR_bp"], suffix="%", change_formatter=fmt_bp),
    ]
    return f"8. 信用/流动性：{'；'.join(items)}。"


def fmt_usd_level(pair, unit):
    value = pair[0][1]
    if unit == "millions":
        billion = value / 1_000.0
    else:
        billion = value
    if abs(billion) >= 100:
        return f"{billion / 1_000.0:.2f}万亿美元"
    return f"{billion:.1f}十亿美元"


def fmt_fed_balance_item(label, key, pair, change):
    if not has_latest(pair):
        return None
    change_text = f" ({fmt_pct(change)})" if change is not None else ""
    return f"{label} {fmt_usd_level(pair, FED_BALANCE_UNITS[key])}{change_text}"


def fmt_fed_balance_line(pairs, changes):
    items = [
        fmt_fed_balance_item("总资产", "WALCL", pairs["WALCL"], changes["WALCL_pct"]),
        fmt_fed_balance_item("准备金", "RESBALNS", pairs["RESBALNS"], changes["RESBALNS_pct"]),
        fmt_fed_balance_item("ON RRP", "RRPONTSYD", pairs["RRPONTSYD"], changes["RRPONTSYD_pct"]),
        fmt_fed_balance_item("贴现窗口", "DPCREDIT", pairs["DPCREDIT"], changes["DPCREDIT_pct"]),
    ]
    items = [item for item in items if item]
    if not items:
        return "9. Fed表：H.4.1/FRED 周更数据暂未取到，先不据此判断准备金和QT压力。"
    return f"9. Fed表：{'；'.join(items)}。"


def visible_fetch_error_keys(pairs):
    priority = {key: index for index, key in enumerate(ERROR_PRIORITY)}
    keys = []
    for key in FETCH_ERRORS:
        if key == "SP500" and has_latest(pairs.get("SPY")):
            continue
        if key == "NASDAQCOM" and has_latest(pairs.get("QQQ")):
            continue
        keys.append(key)
    return sorted(keys, key=lambda key: (priority.get(key, 999), label_for_key(key)))


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
        return "暂无可用"
    return "、".join(f"{label_for_key(key)} {fmt_pct(pct_for_key(key, changes))}" for key in keys[:count])


def avg_pct(keys, changes):
    values = [pct_for_key(key, changes) for key in keys]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def fmt_ai_group_item(group, changes, reverse):
    label, keys = group
    average = avg_pct(keys, changes)
    leaders = ranked_keys(keys, changes, reverse=reverse)
    return f"{label} {fmt_pct(average)}（{fmt_movers(leaders, changes, 2)}）"


def fmt_ai_group_summary(changes):
    ranked = [(group, avg_pct(group[1], changes)) for group in AI_GROUPS]
    ranked = [(group, average) for group, average in ranked if average is not None]
    if not ranked:
        return "暂无可用"
    strong = [group for group, _ in sorted(ranked, key=lambda item: item[1], reverse=True)[:3]]
    weak = [group for group, _ in sorted(ranked, key=lambda item: item[1])[:2]]
    strong_text = "；".join(fmt_ai_group_item(group, changes, True) for group in strong)
    weak_text = "；".join(fmt_ai_group_item(group, changes, False) for group in weak)
    return f"强 {strong_text}；弱 {weak_text}"


def target_window_grace_minutes(hour, minute):
    return EXTENDED_WINDOW_GRACE_MINUTES.get((hour, minute), SCHEDULE_GATE_GRACE_MINUTES)


def matched_target_window(now_et):
    minutes = now_et.hour * 60 + now_et.minute
    for hour, minute, label in TARGET_ET_WINDOWS:
        target = hour * 60 + minute
        if target <= minutes <= target + target_window_grace_minutes(hour, minute):
            return {
                "alert_type": "market",
                "hour": hour,
                "minute": minute,
                "label": label,
                "window_key": f"market-{now_et:%Y%m%d}-{hour:02d}{minute:02d}",
                "is_backup": minutes >= target + BACKUP_TRIGGER_OFFSET_MINUTES,
                "should_send": True,
            }
    return None


def matched_health_check(now_et):
    hour, minute, label = HEALTH_CHECK_ET_WINDOW
    minutes = now_et.hour * 60 + now_et.minute
    target = hour * 60 + minute
    if target <= minutes <= target + HEALTH_CHECK_GRACE_MINUTES:
        return {
            "alert_type": "health",
            "hour": hour,
            "minute": minute,
            "label": label,
            "window_key": f"health-{now_et:%Y%m%d}",
            "is_backup": False,
            "should_send": True,
        }
    return None


def classify_run(now_et):
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return {
            "alert_type": "market",
            "label": report_window(now_et),
            "window_key": "",
            "is_backup": False,
            "should_send": True,
        }
    matched = matched_target_window(now_et) or matched_health_check(now_et)
    if matched:
        return matched
    return {
        "alert_type": "skip",
        "label": "跳过",
        "window_key": "",
        "is_backup": False,
        "should_send": False,
        "skip_reason": f"Scheduled run skipped: {now_et:%Y-%m-%d %H:%M %Z} is outside target New York alert windows.",
    }


def env_classification(now_et):
    alert_type = os.environ.get("MONITOR_ALERT_TYPE")
    if not alert_type:
        return None
    return {
        "alert_type": alert_type,
        "label": os.environ.get("MONITOR_WINDOW_LABEL") or report_window(now_et),
        "window_key": os.environ.get("MONITOR_WINDOW_KEY", ""),
        "is_backup": os.environ.get("MONITOR_IS_BACKUP") == "true",
        "should_send": os.environ.get("MONITOR_SHOULD_SEND", "true") == "true",
    }


def write_classification_outputs(classification):
    lines = []
    values = {
        "should_send": str(classification.get("should_send", False)).lower(),
        "alert_type": classification.get("alert_type", ""),
        "window_label": classification.get("label", ""),
        "window_key": classification.get("window_key", ""),
        "is_backup": str(classification.get("is_backup", False)).lower(),
    }
    for key, value in values.items():
        lines.append(f"{key}={str(value).replace(chr(10), ' ')}")

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def next_target_window(now_et):
    tz = now_et.tzinfo
    for day_offset in range(3):
        day = (now_et + dt.timedelta(days=day_offset)).date()
        for hour, minute, label in TARGET_ET_WINDOWS:
            candidate = dt.datetime.combine(day, dt.time(hour, minute), tzinfo=tz)
            if candidate > now_et:
                bj_time = candidate.astimezone(ZoneInfo("Asia/Shanghai"))
                return f"{candidate:%m-%d %H:%M} ET / 北京时间 {bj_time:%m-%d %H:%M} {label}"
    return "下一次美东固定观察窗口"


def report_window(now_et):
    matched = matched_target_window(now_et)
    if matched:
        return matched["label"]
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


def derive_t10y_breakeven(pairs):
    if has_latest(pairs.get("T10YIE")):
        return
    nominal = pairs.get("DGS10")
    real = pairs.get("DFII10")
    if not has_latest(nominal) or not has_latest(real):
        return
    if nominal[0][0] != real[0][0]:
        return

    latest = (nominal[0][0], nominal[0][1] - real[0][1])
    previous = None
    if nominal[1] and real[1] and nominal[1][0] == real[1][0]:
        previous = (nominal[1][0], nominal[1][1] - real[1][1])
    pairs["T10YIE"] = (latest, previous)
    DATA_SOURCES["T10YIE"] = "Treasury/FRED derived"
    FETCH_ERRORS.pop("T10YIE", None)


def fetch_all_pairs():
    FETCH_ERRORS.clear()
    MARKET_SOURCES.clear()
    DATA_SOURCES.clear()
    pairs = {}
    max_workers = min(20, len(SERIES) + len(MARKET_QUOTES))
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
    derive_t10y_breakeven(pairs)
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


def build_message(now_utc=None, classification=None):
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)
    now_bj = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
    window_label = (classification or {}).get("label") or report_window(now_et)

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
    ai_stock_winners = ranked_keys(AI_STOCK_KEYS, changes, reverse=True)
    ai_stock_losers = ranked_keys(AI_STOCK_KEYS, changes, reverse=False)
    index_line = fmt_quote_list(INDEX_KEYS, pairs, changes)

    lines = [
        "【Fed/美元信用监控】",
        f"时间：北京时间 {now_bj:%m-%d %H:%M} / 美东时间 {now_et:%m-%d %H:%M}",
        f"窗口：{window_label}",
        f"风险灯号：{risk}",
        f"结论：{conclusion}",
        "",
        "关键变化：",
        fmt_rates_line(pairs, changes),
        fmt_real_rate_line(pairs, changes),
        fmt_cross_asset_line(pairs, changes),
        f"4. 美股指数：{index_line}。",
        f"5. AI细分：{fmt_ai_group_summary(changes)}。",
        f"6. AI个股：强 {fmt_movers(ai_stock_winners, changes)}；弱 {fmt_movers(ai_stock_losers, changes)}。",
        f"7. 大类板块：强 {fmt_movers(sector_winners, changes)}；弱 {fmt_movers(sector_losers, changes)}。",
        fmt_credit_liquidity_line(pairs, changes),
        fmt_fed_balance_line(pairs, changes),
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
    visible_errors = visible_fetch_error_keys(pairs)
    if visible_errors:
        missing = "、".join(label_for_key(sid) for sid in visible_errors[:5])
        suffix = "等" if len(visible_errors) > 5 else ""
        lines.append(f"数据提示：{missing}{suffix} 暂未更新或无法读取。")
    source_notes = []
    if MARKET_SOURCES:
        sources = "、".join(sorted(set(MARKET_SOURCES.values())))
        source_notes.append(f"市场报价 {sources}")
    if DATA_SOURCES:
        sources = "、".join(sorted(set(DATA_SOURCES.values())))
        source_notes.append(f"宏观/利率序列 {sources}")
    if source_notes:
        lines.append(f"行情源：{'；'.join(source_notes)}。")
    if classification and classification.get("is_backup"):
        lines.append("触发说明：这是备用补发窗口；若主窗口已成功发送，本次会被自动跳过。")
    return "\n".join(lines)


def build_health_check_message(now_utc=None):
    if now_utc is None:
        now_utc = dt.datetime.now(dt.timezone.utc)
    now_bj = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
    return "\n".join(
        [
            "【Fed/美元信用监控｜系统健康检查】",
            f"时间：北京时间 {now_bj:%m-%d %H:%M} / 美东时间 {now_et:%m-%d %H:%M}",
            "状态：GitHub Actions 已触发，Telegram 通道可达。",
            f"下一观察窗口：{next_target_window(now_et)}。",
            "说明：关键窗口有30分钟后的备用触发；已发送窗口会自动跳过。",
        ]
    )


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
    last_error = None
    for attempt in range(1, TELEGRAM_MAX_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok"):
                return
            last_error = RuntimeError(f"Telegram API failed: {payload}")
        except Exception as exc:
            last_error = exc

        if attempt < TELEGRAM_MAX_ATTEMPTS:
            wait_seconds = min(TELEGRAM_RETRY_BASE_SECONDS ** attempt, 30)
            print(f"Telegram send attempt {attempt} failed; retrying in {wait_seconds}s: {last_error}", file=sys.stderr)
            time.sleep(wait_seconds)

    raise RuntimeError(f"Telegram send failed after {TELEGRAM_MAX_ATTEMPTS} attempts: {last_error}")


def main():
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))

    if "--classify" in sys.argv:
        write_classification_outputs(classify_run(now_et))
        return

    classification = env_classification(now_et) or classify_run(now_et)
    if not classification.get("should_send", False):
        print(classification.get("skip_reason", "Scheduled run skipped."))
        return

    if classification.get("alert_type") == "health":
        message = build_health_check_message(now_utc)
    else:
        message = build_message(now_utc, classification)
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
