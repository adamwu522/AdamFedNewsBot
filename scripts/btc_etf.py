"""US spot BTC ETF flows in USD millions; missing disclosures are never zero."""

import csv
import datetime as dt
import json
import math
import sys
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

FARSIDE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
READER_URL = f"https://r.jina.ai/{FARSIDE_URL}"
CACHE_PATH = Path(".monitor-data/btc-etf.json")


@dataclass
class FlowDay:
    date: dt.date
    flows: dict
    total: float | None
    complete: bool = False


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def flow_number(raw):
    value = raw.strip().replace(",", "").replace("\u2212", "-")
    if value in {"", "-", "\u2013", "\u2014", "N/A"}:
        return None
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite ETF flow")
    return result


def parse_flows(text, markdown=False):
    if markdown:
        rows = [
            [cell.strip() for cell in row[1:-1]]
            for row in csv.reader(
                (line.strip() for line in text.splitlines() if line.strip().startswith("|")),
                delimiter="|",
            )
        ]
    else:
        parser = TableParser()
        parser.feed(text)
        rows = parser.rows
    header = None
    days = {}
    for row in rows:
        if row and row[0] == "Date" and {"IBIT", "FBTC", "GBTC", "Total"}.issubset(row):
            header = row
            continue
        if not header or not row:
            continue
        try:
            date = dt.datetime.strptime(row[0], "%d %b %Y").date()
        except ValueError:
            continue
        if len(row) != len(header):
            raise ValueError("ETF table column count changed")
        values = dict(zip(header[1:], (flow_number(raw) for raw in row[1:])))
        total = values.pop("Total")
        days[date] = FlowDay(date, values, total)
    if not days:
        raise ValueError("No dated BTC ETF flow rows found")

    # A dash before a fund's first disclosure is not a missing active fund.
    first_report = {}
    for day in sorted(days.values(), key=lambda day: day.date):
        for ticker, value in day.flows.items():
            if value is not None:
                first_report.setdefault(ticker, day.date)
    for day in days.values():
        active = [ticker for ticker, debut in first_report.items() if debut <= day.date]
        reported = [value for value in day.flows.values() if value is not None]
        coverage = active and all(day.flows[ticker] is not None for ticker in active)
        reconciled = day.total is not None and abs(sum(reported) - day.total) <= 0.051 * len(reported) + 0.05
        day.complete = bool(coverage and reported and reconciled)
    return sorted(days.values(), key=lambda day: day.date)


def save_cache(days, now_et, path):
    recent = [day for day in days if now_et.date() - dt.timedelta(days=90) <= day.date <= now_et.date()]
    payload = {
        "version": 1,
        "fetched_at": now_et.isoformat(),
        "days": [dict(date=day.date.isoformat(), flows=day.flows, total=day.total, complete=day.complete) for day in recent],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def load_cache(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["version"] != 1:
            raise ValueError("Unknown ETF cache version")
        return [FlowDay(dt.date.fromisoformat(day["date"]), day["flows"], day["total"], day["complete"]) for day in payload["days"]]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def fetch_flows(now_et, read_text, cache_path=CACHE_PATH):
    cached_days = load_cache(cache_path)
    cached_date = max((day.date for day in cached_days if day.complete), default=dt.date.min)
    errors = []
    for url, markdown, source in (
        (FARSIDE_URL, False, "Farside"),
        (READER_URL, True, "Farside（备用读取）"),
    ):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "macro-telegram-monitor/1.0"})
            days = parse_flows(read_text(request, timeout=25, attempts=2), markdown)
            live_date = max((day.date for day in days if day.complete), default=dt.date.min)
            if live_date < cached_date:
                errors.append("SourceOlderThanCache")
                continue
            try:
                save_cache(days, now_et, cache_path)
            except OSError as exc:
                print(f"ETF cache write failed: {type(exc).__name__}", file=sys.stderr)
            return days, source, False
        except Exception as exc:
            errors.append(type(exc).__name__)
    print(f"ETF live sources unavailable: {', '.join(errors)}", file=sys.stderr)
    if cached_days:
        return cached_days, "Farside（历史缓存）", True
    return [], "Farside", False


def fmt_flow(millions):
    if abs(millions) >= 100:
        return f"{millions / 100:+.2f}亿美元"
    return f"{millions * 100:+,.0f}万美元"


def closed_weekday(now_et):
    day = now_et.date()
    if now_et.hour < 16:
        day -= dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day


def format_flows(days, now_et, source, cached=False):
    lines = ["BTC现货ETF（美国，净申赎资金）："]
    closed_day = closed_weekday(now_et)
    visible = [day for day in days if day.date <= closed_day and day.date.weekday() < 5]
    reported = [day for day in visible if any(value is not None for value in day.flows.values())]
    complete = [day for day in reported if day.complete]
    if cached:
        lines.append("实时抓取失败，以下为历史缓存；本次不确认趋势更新。")
    if not complete:
        lines.append("暂未取得完整日数据，资金趋势暂不判断。")
    if reported and (not complete or reported[-1].date > complete[-1].date):
        partial = reported[-1]
        subtotal = sum(value for value in partial.flows.values() if value is not None)
        count = sum(value is not None for value in partial.flows.values())
        lines.append(f"{partial.date:%m-%d} 尚未报齐或合计待核对：已报{count}只，小计 {fmt_flow(subtotal)}；不计入趋势。")
    if complete:
        latest = complete[-1]
        lines.append(f"最新完整日 {latest.date:%Y-%m-%d}：合计 {fmt_flow(latest.total)}。")
        if latest.date < closed_day:
            lines.append(f"截至本次抓取，{closed_day:%m-%d} 无完整记录（休市或待更新）；沿用上述统计日。")
        if (closed_day - latest.date).days > 4:
            lines.append("数据日期偏旧，以下仅为历史统计。")

        # Stop at an incomplete trading row instead of stitching a rolling window across it.
        history = []
        for day in reversed(reported):
            if day.date > latest.date:
                continue
            if not day.complete:
                break
            history.append(day)
        history.reverse()
        if len(history) >= 2:
            delta = latest.total - history[-2].total
            lines.append(f"较前一统计日净流量变化 {fmt_flow(delta)}（金额差）。")

        totals = {}
        for length in (5, 20):
            if len(history) >= length:
                totals[length] = sum(day.total for day in history[-length:])
        rolling = [f"近{length}个完整披露日 {fmt_flow(total)}" for length, total in totals.items()]
        if rolling:
            lines.append("；".join(rolling) + "。")
        if len(history) < 20:
            lines.append(f"连续完整样本仅{len(history)}个交易日，不足的周期不作统计。")
        if latest.total:
            positive = latest.total > 0
            streak = 0
            streak_rows = [day for day in visible if day.date <= latest.date]
            for day in reversed(streak_rows):
                if not day.complete or day.total == 0 or (day.total > 0) != positive:
                    break
                streak += 1
            lines.append(f"截至统计日，至少连续{streak}个交易日净{'流入' if positive else '流出'}（遇缺报不跨日推断）。")
        else:
            lines.append("当日净流量为零，连续流入/流出中断。")

        tickers = [ticker for ticker in ("IBIT", "FBTC", "GBTC", "BTC") if latest.flows.get(ticker) is not None]
        others = sorted(
            (ticker for ticker, value in latest.flows.items() if value is not None and ticker not in tickers),
            key=lambda ticker: abs(latest.flows[ticker]), reverse=True,
        )
        tickers.extend(ticker for ticker in others[:2] if latest.flows[ticker] != 0)
        lines.append("基金：" + "；".join(f"{ticker} {fmt_flow(latest.flows[ticker])}" for ticker in tickers) + "。")
        if len(history) >= 10:
            previous = sum(day.total for day in history[-10:-5])
            current = totals[5]
            if current > 0 and previous <= 0:
                trend = "近5日由净流出/持平转为净流入"
            elif current < 0 and previous >= 0:
                trend = "近5日由净流入/持平转为净流出"
            elif current > previous:
                trend = "近5日净流入扩大" if current > 0 else "近5日净流出收窄"
            elif current < previous:
                trend = "近5日净流出扩大" if current < 0 else "近5日净流入收窄"
            else:
                trend = "近5日净流量持平"
            lines.append(f"趋势（截至{latest.date:%m-%d}，按完整披露日）：{trend}，较前5日 {fmt_flow(current - previous)}。")
        lines.append("ETF流向仅反映该渠道资金，不等于全部机构需求，也不单独预测BTC涨跌。")
    lines.append(f"来源：{source} {FARSIDE_URL}")
    return lines


def build_etf_section(now_et, read_text, cache_path=CACHE_PATH):
    try:
        days, source, cached = fetch_flows(now_et, read_text, cache_path)
        return format_flows(days, now_et, source, cached)
    except Exception as exc:
        print(f"ETF section unavailable: {type(exc).__name__}", file=sys.stderr)
        return ["BTC现货ETF：数据暂不可用，本次不判断资金趋势；其他监控继续。"]
