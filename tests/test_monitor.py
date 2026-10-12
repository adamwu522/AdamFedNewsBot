import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import btc_etf as etf
import macro_monitor as monitor

BJ = ZoneInfo("Asia/Shanghai")
ET = ZoneInfo("America/New_York")


def at_bj(value):
    return dt.datetime.fromisoformat(value).replace(tzinfo=BJ).astimezone(ET)


def table(rows, markdown=False):
    header = ["Date", "IBIT", "FBTC", "GBTC", "BTC", "Total"]
    if markdown:
        return "\n".join("| " + " | ".join(row) + " |" for row in [header] + rows)
    return "<table>" + "".join("<tr>" + "".join(f"<td><span>{cell}</span></td>" for cell in row) + "</tr>" for row in [header] + rows) + "</table>"


def history(totals):
    start = dt.date(2026, 8, 3)
    rows = []
    while len(rows) < len(totals):
        if start.weekday() < 5:
            value = totals[len(rows)]
            rows.append(etf.FlowDay(start, {"IBIT": value, "FBTC": 0, "GBTC": 0, "BTC": 0}, value, True))
        start += dt.timedelta(days=1)
    return rows


def after_close(day):
    return dt.datetime.combine(day, dt.time(21), tzinfo=ET)


class ScheduleTests(unittest.TestCase):
    def classify(self, when, event="repository_dispatch"):
        with patch.dict("os.environ", {"GITHUB_EVENT_NAME": event}):
            return monitor.classify_run(at_bj(when))

    def test_morning_fixed_in_both_seasons(self):
        for date in ("2026-07-15", "2026-12-15"):
            result = self.classify(date + "T08:40")
            self.assertTrue(result["should_send"])
            self.assertIn("morning", result["window_key"])
            self.assertFalse(self.classify(date + "T08:39")["should_send"])

    def test_evening_follows_new_york_in_both_seasons(self):
        for date, hour in (("2026-07-15", 22), ("2026-12-15", 23)):
            self.assertIn("evening", self.classify(f"{date}T{hour}:40")["window_key"])
            self.assertFalse(self.classify(f"{date}T{hour}:39")["should_send"])
            self.assertFalse(self.classify(date + "T00:05")["should_send"])
        self.assertFalse(self.classify("2026-12-15T22:40")["should_send"])

    def test_dst_transition_dates_have_two_windows_only(self):
        for date in ("2026-03-08", "2026-11-01", "2026-11-02"):
            keys = set()
            for minute in range(0, 1440, 10):
                now = f"{date}T{minute // 60:02d}:{minute % 60:02d}"
                result = self.classify(now)
                if result["should_send"]:
                    keys.add(result["window_key"])
            self.assertEqual(len(keys), 2, (date, keys))

    def test_no_overnight_opening_or_health_alert(self):
        for when in ("2026-10-12T02:40", "2026-10-12T19:10", "2026-10-12T12:30"):
            self.assertFalse(self.classify(when)["should_send"])
        self.assertFalse(self.classify("2026-10-12T20:40")["should_send"])
        primary = self.classify("2026-10-12T22:40")
        backup = self.classify("2026-10-12T23:40")
        self.assertEqual(primary["window_key"], backup["window_key"])

    def test_catchup_boundary_and_duplicate_key(self):
        primary = self.classify("2026-10-12T08:40")
        late = self.classify("2026-10-12T11:40")
        self.assertEqual(primary["window_key"], late["window_key"])
        self.assertIn("延迟补发", late["label"])
        self.assertFalse(self.classify("2026-10-12T11:41")["should_send"])

    def test_external_native_and_push_share_keys(self):
        keys = [self.classify("2026-10-12T08:50", event)["window_key"] for event in ("schedule", "repository_dispatch", "push")]
        self.assertEqual(len(set(keys)), 1)
        self.assertFalse(self.classify("2026-10-12T02:00", "push")["should_send"])
        manual = self.classify("2026-10-12T02:00", "workflow_dispatch")
        self.assertTrue(manual["should_send"])
        self.assertEqual(manual["window_key"], "")

    def test_next_target_uses_beijing_morning(self):
        result = monitor.next_target_window(at_bj("2026-12-15T00:30"))
        self.assertIn("12-15 08:40", result)


class ETFTests(unittest.TestCase):
    def test_html_and_reader_equivalent(self):
        rows = [["08 Oct 2026", "120.0", "(30.0)", "0.0", "0.0", "90.0"]]
        html = etf.parse_flows(table(rows))
        reader = etf.parse_flows(table(rows, True), markdown=True)
        self.assertEqual(html, reader)
        self.assertEqual(html[0].total, 90)
        self.assertEqual(html[0].flows["FBTC"], -30)
        self.assertTrue(html[0].complete)

    def test_dash_is_pending_not_zero_even_with_total(self):
        rows = [["08 Oct 2026", "20", "10", "0", "0", "30"], ["09 Oct 2026", "25", "-", "0", "0", "25"]]
        days = etf.parse_flows(table(rows))
        self.assertIsNone(days[-1].flows["FBTC"])
        self.assertFalse(days[-1].complete)
        rendered = "\n".join(etf.format_flows(days, after_close(dt.date(2026, 10, 9)), "test"))
        self.assertIn("未报齐", rendered)
        self.assertNotIn("合计", rendered)

    def test_all_pending_zero_total_is_not_final(self):
        days = etf.parse_flows(table([["09 Oct 2026", "-", "-", "-", "-", "0.0"]]))
        self.assertFalse(days[0].complete)
        rendered = "\n".join(etf.format_flows(days, after_close(days[0].date), "test"))
        self.assertNotIn("合计", rendered)
        self.assertIn("暂不可用", rendered)

    def test_zero_is_real_and_prelaunch_missing_is_not_pending(self):
        days = etf.parse_flows(table([["08 Oct 2026", "0", "0", "0", "-", "0"], ["09 Oct 2026", "1", "0", "0", "2", "3"]]))
        self.assertTrue(all(day.complete for day in days))

    def test_total_must_reconcile_allowing_rounding(self):
        for total, expected in (("4.1", True), ("9.0", False)):
            day = etf.parse_flows(table([["09 Oct 2026", "1", "1", "1", "1", total]]))[0]
            self.assertEqual(day.complete, expected)

    def test_schema_drift_and_invalid_numbers_fail_closed(self):
        with self.assertRaises(ValueError):
            etf.parse_flows(table([["09 Oct 2026", "1", "2"]]))
        for raw in ("NaN", "Infinity", "pending?"):
            with self.assertRaises(ValueError):
                etf.flow_number(raw)
        self.assertEqual(etf.flow_number("(1,234.5)"), -1234.5)

    def test_five_daily_values_without_sum_analysis_or_funds(self):
        days = history([-10] * 15 + [20, -30, 0, 40, -50])
        rendered = "\n".join(etf.format_flows(days, after_close(days[-1].date), "test"))
        self.assertEqual(len(rendered.splitlines()), 6)
        expected = ["净流入 2,000万美元", "净流出 3,000万美元", "净流量 0万美元", "净流入 4,000万美元", "净流出 5,000万美元"]
        for line, day, value in zip(rendered.splitlines()[1:], days[-5:], expected):
            self.assertEqual(line, f"{day.date}：{value}")
        for omitted in ("合计", "汇总", "趋势", "连续", "IBIT", "FBTC", "较前"):
            self.assertNotIn(omitted, rendered)

    def test_partial_day_is_marked_without_hiding_other_days(self):
        days = history([10] * 20)
        days[-3].complete = False
        rendered = "\n".join(etf.format_flows(days, after_close(days[-1].date), "test"))
        self.assertIn(f"{days[-3].date}：未报齐", rendered)
        self.assertEqual(rendered.count("净流入 1,000万美元"), 4)
        self.assertEqual(len(rendered.splitlines()), 6)

    def test_unreported_day_not_counted_as_zero(self):
        days = history([10] * 6)
        days[-2] = etf.FlowDay(days[-2].date, {"IBIT": None}, 0, False)
        rendered = "\n".join(etf.format_flows(days, after_close(days[-1].date), "test"))
        self.assertEqual(rendered.count("净流入 1,000万美元"), 5)
        self.assertNotIn("净流量 0", rendered)

    def test_weekend_and_not_yet_closed_data(self):
        days = history([10] * 5)
        friday = days[-1].date
        saturday = after_close(friday) + dt.timedelta(days=1)
        self.assertEqual(etf.closed_weekday(saturday), friday)
        before_close = after_close(friday).replace(hour=15)
        rendered = "\n".join(etf.format_flows(days, before_close, "test"))
        self.assertIn("未报齐", rendered)

    def test_stale_history_is_explicit(self):
        days = history([10] * 5)
        now = after_close(days[-1].date) + dt.timedelta(days=12)
        rendered = "\n".join(etf.format_flows(days, now, "test", cached=True))
        self.assertIn("历史缓存", rendered)
        self.assertIn("日期偏旧", rendered)

    def test_reader_fallback_and_cache_on_outage(self):
        text = table([["09 Oct 2026", "20", "10", "0", "0", "30"]], True)
        now = after_close(dt.date(2026, 10, 9))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "etf.json"
            calls = []
            def read(request, **kwargs):
                calls.append(request.full_url)
                if request.full_url == etf.FARSIDE_URL:
                    raise OSError("blocked")
                return text
            days, source, cached = etf.fetch_flows(now, read, path)
            self.assertEqual(calls, [etf.FARSIDE_URL, etf.READER_URL])
            self.assertIn("备用", source)
            self.assertFalse(cached)
            self.assertEqual(json.loads(path.read_text())["days"][0]["total"], 30)
            def offline(*args, **kwargs):
                raise OSError("offline")
            cached_days, _, cached = etf.fetch_flows(now, offline, path)
            self.assertEqual(days, cached_days)
            self.assertTrue(cached)

    def test_outage_without_cache_still_returns_section(self):
        with tempfile.TemporaryDirectory() as directory:
            def offline(*args, **kwargs):
                raise OSError("offline")
            result = etf.build_etf_section(after_close(dt.date(2026, 10, 9)), offline, Path(directory) / "absent.json")
            self.assertIn("暂不可用", "\n".join(result))

    def test_older_live_snapshot_cannot_overwrite_newer_cache(self):
        now = after_close(dt.date(2026, 10, 9))
        newer = etf.parse_flows(table([["09 Oct 2026", "20", "10", "0", "0", "30"]]))
        older = [["08 Oct 2026", "10", "0", "0", "0", "10"]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "etf.json"
            etf.save_cache(newer, now, path)
            def read(request, **kwargs):
                return table(older, request.full_url == etf.READER_URL)
            days, _, cached = etf.fetch_flows(now, read, path)
            self.assertTrue(cached)
            self.assertEqual(days, newer)
            self.assertEqual(etf.load_cache(path), newer)

    def test_integrated_digest_fits_one_telegram_message(self):
        pair = (("2026-10-09", 110), ("2026-10-08", 100))
        pairs = {key: pair for key in list(monitor.SERIES) + list(monitor.MARKET_QUOTES)}
        days = history([-10] * 15 + [20] * 5)
        section = etf.format_flows(days, after_close(days[-1].date), "Farside")
        with patch.object(monitor, "fetch_all_pairs", return_value=pairs), patch.object(monitor, "build_etf_section", return_value=section):
            report = monitor.build_message(after_close(days[-1].date))
        self.assertIn("BTC现货ETF", report)
        for omitted in ("AI细分", "AI个股", "信用/流动性", "Fed表", "下一观察点", "数据发布", "风险灯号", "结论：", "跨资产"):
            self.assertNotIn(omitted, report)
        self.assertIn("1. 美元：", report)
        self.assertIn("美元指数DXY", report)
        self.assertNotIn("自定义本币等权", report)
        self.assertFalse(any(line.startswith("AI组合") for line in report.splitlines()))
        self.assertIn("大类板块", report)
        self.assertLessEqual(len(report), 4096)


class BasketTests(unittest.TestCase):
    def setUp(self):
        self.pair = (("2026-10-12", 105), ("2026-10-09", 100))
        self.pairs = {key: self.pair for key in monitor.AI_BASKET_KEYS + ["SPY"]}
        self.changes = {f"{key}_pct": 1.0 for key in monitor.AI_BASKET_KEYS}

    def test_fixed_equal_weights_and_sector_ranking(self):
        self.changes["NVDA_pct"] = 17.0
        value, count = monitor.ai_basket_change(self.pairs, self.changes)
        self.assertEqual(count, 16)
        self.assertEqual(value, 2.0)
        changes = {"AI_BASKET_pct": value, "XLK_pct": 1.0}
        self.assertEqual(monitor.ranked_keys(["XLK", "AI_BASKET"], changes, True)[0], "AI_BASKET")

    def test_missing_or_stale_us_quote_does_not_reweight(self):
        del self.changes["SNDK_pct"]
        self.assertEqual(monitor.ai_basket_change(self.pairs, self.changes), (None, 15))
        self.changes["SNDK_pct"] = 1.0
        self.pairs["SNDK"] = (("2026-10-09", 105), ("2026-10-08", 100))
        self.assertEqual(monitor.ai_basket_change(self.pairs, self.changes), (None, 15))

    def test_dxy_missing_is_not_replaced_with_broad_dollar(self):
        pairs = {key: self.pair for key in ["DGS2", "DGS10", "DGS30", "DTWEXBGS"]}
        changes = {f"{key}_bp": 2.0 for key in ["DGS2", "DGS10", "DGS30"]}
        line = monitor.fmt_rates_line(pairs, changes)
        self.assertIn("美元指数DXY 未更新", line)
        self.assertNotIn("Broad", line)


if __name__ == "__main__":
    unittest.main()
