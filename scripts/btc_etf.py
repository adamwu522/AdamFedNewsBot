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
    closed_day = closed_weekday(now_et)
    reported = [day for day in days if day.date <= closed_day and day.date.weekday() < 5
                and any(value is not None for value in day.flows.values())]
    complete = [day for day in reported if day.complete]
    notes = []
    if cached:
        notes.append("历史缓存")
    if not complete:
        return ["BTC现货ETF：近5日数据暂不可用（未报齐）。"]
    latest = complete[-1]
    history = []
    for day in reversed(reported):
        if day.date > latest.date:
            continue
        if not day.complete:
            break
        history.append(day)
        if len(history) == 5:
            break
    if len(history) < 5:
        return [f"BTC现货ETF：近5日数据未报齐，暂不汇总（完整样本{len(history)}日）。"]
    total = sum(day.total for day in history)
    direction = "净流入" if total > 0 else "净流出" if total < 0 else "净流量"
    amount = fmt_flow(abs(total)).lstrip("+")
    if reported[-1].date > latest.date:
        notes.append("最新日未报齐")
    if (closed_day - latest.date).days > 4:
        notes.append("日期偏旧")
    suffix = f"；{'、'.join(notes)}" if notes else ""
    return [f"BTC现货ETF：近5个完整披露日合计{direction} {amount}"
            f"（{history[-1].date:%Y-%m-%d}至{latest.date:%m-%d}；{source}{suffix}）。"]

def build_etf_section(now_et, read_text, cache_path=CACHE_PATH):
    try:
        days, source, cached = fetch_flows(now_et, read_text, cache_path)
        return format_flows(days, now_et, source, cached)
    except Exception as exc:
        print(f"ETF section unavailable: {type(exc).__name__}", file=sys.stderr)
        return ["BTC现货ETF：近5日数据暂不可用。"]
