#!/usr/bin/env python3
import csv
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

SERIES = {
    "DGS2": "2Y",
    "DGS10": "10Y",
    "DGS30": "30Y",
    "DFII10": "10Y real",
    "T10YIE": "10Y breakeven",
    "BAMLH0A0HYM2": "HY OAS",
    "SP500": "S&P 500",
    "NASDAQCOM": "Nasdaq",
    "CBBTCUSD": "BTC",
    "GOLDAMGBD228NLBM": "Gold",
    "DTWEXBGS": "Broad USD",
    "SOFR": "SOFR",
    "EFFR": "EFFR",
    "WALCL": "Fed assets",
    "RESBALNS": "Reserve balances",
    "RRPONTSYD": "ON RRP",
    "DPCREDIT": "Discount window",
}

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


def latest_pair(rows, series_id):
    values = []
    for row in rows:
        raw = row.get(series_id, "").strip()
        if not raw or raw == ".":
            continue
        try:
            values.append((row["observation_date"], float(raw)))
        except ValueError:
            continue
    if not values:
        return None, None
    if len(values) == 1:
        return values[-1], None
    return values[-1], values[-2]


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
    gold = changes.get("GOLDAMGBD228NLBM_pct")
    btc = changes.get("CBBTCUSD_pct")
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
    btc = changes.get("CBBTCUSD_pct")
    gold = changes.get("GOLDAMGBD228NLBM_pct")
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


def build_message():
    now_utc = dt.datetime.now(dt.timezone.utc)
    now_bj = now_utc.astimezone(ZoneInfo("Asia/Shanghai"))
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))

    pairs = {sid: fetch_latest_pair(sid) for sid in SERIES}
    changes = {
        "DGS2_bp": change_bp(pairs["DGS2"]),
        "DGS10_bp": change_bp(pairs["DGS10"]),
        "DGS30_bp": change_bp(pairs["DGS30"]),
        "DFII10_bp": change_bp(pairs["DFII10"]),
        "T10YIE_bp": change_bp(pairs["T10YIE"]),
        "BAMLH0A0HYM2_bp": change_bp(pairs["BAMLH0A0HYM2"]),
        "SP500_pct": change_pct(pairs["SP500"]),
        "NASDAQCOM_pct": change_pct(pairs["NASDAQCOM"]),
        "CBBTCUSD_pct": change_pct(pairs["CBBTCUSD"]),
        "GOLDAMGBD228NLBM_pct": change_pct(pairs["GOLDAMGBD228NLBM"]),
        "DTWEXBGS_pct": change_pct(pairs["DTWEXBGS"]),
        "SOFR_bp": change_bp(pairs["SOFR"]),
        "EFFR_bp": change_bp(pairs["EFFR"]),
        "WALCL_pct": change_pct(pairs["WALCL"]),
        "RESBALNS_pct": change_pct(pairs["RESBALNS"]),
        "RRPONTSYD_pct": change_pct(pairs["RRPONTSYD"]),
        "DPCREDIT_pct": change_pct(pairs["DPCREDIT"]),
    }

    risk, conclusion = risk_and_conclusion(changes)
    btc_line, gold_line, stock_line = asset_implications(risk, changes)

    lines = [
        "【Fed/美元信用监控】",
        f"时间：北京时间 {now_bj:%m-%d %H:%M} / 美东时间 {now_et:%m-%d %H:%M}",
        f"风险灯号：{risk}",
        f"结论：{conclusion}",
        "",
        "关键变化：",
        f"1. 利率：2Y {fmt_level(pairs['DGS2'])}% ({fmt_bp(changes['DGS2_bp'])})；10Y {fmt_level(pairs['DGS10'])}% ({fmt_bp(changes['DGS10_bp'])})；30Y {fmt_level(pairs['DGS30'])}% ({fmt_bp(changes['DGS30_bp'])})。",
        f"2. 实际利率/通胀预期：10Y real {fmt_level(pairs['DFII10'])}% ({fmt_bp(changes['DFII10_bp'])})；10Y breakeven {fmt_level(pairs['T10YIE'])}% ({fmt_bp(changes['T10YIE_bp'])})。",
        f"3. 跨资产：Broad USD {fmt_pct(changes['DTWEXBGS_pct'])}；黄金 {fmt_pct(changes['GOLDAMGBD228NLBM_pct'])}；BTC {fmt_pct(changes['CBBTCUSD_pct'])}；标普 {fmt_pct(changes['SP500_pct'])}；纳指 {fmt_pct(changes['NASDAQCOM_pct'])}。",
        f"4. 信用/流动性：HY OAS {fmt_level(pairs['BAMLH0A0HYM2'])}% ({fmt_bp(changes['BAMLH0A0HYM2_bp'])})；SOFR {fmt_level(pairs['SOFR'])}%；EFFR {fmt_level(pairs['EFFR'])}%。",
        f"5. Fed表：总资产 {fmt_pct(changes['WALCL_pct'])}；准备金 {fmt_pct(changes['RESBALNS_pct'])}；ON RRP {fmt_pct(changes['RRPONTSYD_pct'])}；贴现窗口 {fmt_pct(changes['DPCREDIT_pct'])}。",
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
        missing = "、".join(SERIES.get(sid, sid) for sid in sorted(FETCH_ERRORS)[:5])
        suffix = "等" if len(FETCH_ERRORS) > 5 else ""
        lines.append(f"数据提示：{missing}{suffix} 暂未更新或无法读取。")
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
    message = build_message()
    print(message)
    send_telegram(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
