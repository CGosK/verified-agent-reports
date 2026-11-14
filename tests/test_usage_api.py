import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest import mock

from vawr import usage_api

LEGACY = "/v1/organizations/usage_report/messages"
ANALYTICS = "/v1/organizations/analytics/usage"
KEY = "apikey_test"
T0 = datetime(2026, 11, 14, 5, 50, tzinfo=timezone.utc)
SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def m(i):
    return T0 + timedelta(minutes=i)


def usage(inp, out, read=0, c5m=0, c1h=0):
    return {"uncached_input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation": {"ephemeral_5m_input_tokens": c5m, "ephemeral_1h_input_tokens": c1h},
            "total_tokens": inp + out + read + c5m + c1h,
            "server_tool_use": {"web_search_requests": 0}, "requests": 1}


def row(minute, model, **kw):
    group = dict.fromkeys(["product", "workspace_id", "service_tier", "api_key_id", "actor"])
    group["model"] = model
    return {"starting_at": iso(m(minute)), "ending_at": iso(m(minute + 1)),
            "group": group, "usage": usage(**kw)}


def page(rows, refreshed="2026-11-14T08:02:11Z", next_page=None):
    return {"data": rows, "has_more": bool(next_page), "next_page": next_page,
            "data_refreshed_at": refreshed}


def http_error(code, body=None):
    fp = io.BytesIO(json.dumps(body).encode()) if body is not None else io.BytesIO(b"")
    return urllib.error.HTTPError("https://api.anthropic.com" + LEGACY, code, "err", {}, fp)


class FakeGet:
    """Stands in for usage_api._get: records each call and answers from
    `handlers`, a dict of path -> callable(params) returning a response dict
    (or raising)."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.calls = []

    def __call__(self, admin_key, path, params, attempts=4, headers=None):
        self.calls.append({"path": path, "params": dict(params), "headers": dict(headers or {})})
        if path not in self.handlers:
            raise AssertionError("unexpected request to %s" % path)
        return self.handlers[path](dict(params))

    def to(self, path):
        return [c for c in self.calls if c["path"] == path]


def patched(handlers):
    fake = FakeGet(handlers)
    return fake, mock.patch.object(usage_api, "_get", fake)


class AnalyticsTest(unittest.TestCase):
    def test_maps_fields_groups_by_model_and_sends_beta_header(self):
        rows = [row(0, SONNET, inp=8, out=828, read=4159, c5m=3000, c1h=23),
                row(0, HAIKU, inp=340, out=264, read=7010),
                row(1, None, inp=5, out=1)]
        rows[0]["starting_at"] = "2026-11-14T05:50:00+00:00"  # other RFC 3339 spellings normalise
        fake, p = patched({ANALYTICS: lambda params: page(rows)})
        with p:
            minutes, refreshed = usage_api.minute_usage_analytics_with_refresh("adm", KEY, m(0), m(5))
        self.assertEqual(minutes, {
            iso(m(0)): {SONNET: {"input": 8, "output": 828, "cache_read": 4159, "cache_creation": 3023},
                        HAIKU: {"input": 340, "output": 264, "cache_read": 7010, "cache_creation": 0}},
            iso(m(1)): {"*": {"input": 5, "output": 1, "cache_read": 0, "cache_creation": 0}},
        })
        self.assertEqual(refreshed, datetime(2026, 11, 14, 8, 2, 11, tzinfo=timezone.utc))
        (call,) = fake.calls
        self.assertEqual(call["headers"], {"anthropic-beta": "analytics-usage-cost-2026-08-24"})
        self.assertEqual(call["params"], {
            "starting_at": "2026-11-14T05:50:00Z", "ending_at": "2026-11-14T05:55:00Z",
            "time_bucket_width": "1m", "api_key_ids[]": [KEY], "group_by[]": ["model"],
            "order_by": "time", "order": "asc", "limit": 1000})

    def test_pages_through_with_next_page(self):
        pages = {None: page([row(0, SONNET, inp=1, out=2)], next_page="pg_2"),
                 "pg_2": page([row(0, HAIKU, inp=3, out=4)], next_page="pg_3"),
                 "pg_3": page([row(2, SONNET, inp=5, out=6)])}
        fake, p = patched({ANALYTICS: lambda params: pages[params.get("page")]})
        with p:
            minutes = usage_api.minute_usage_analytics("adm", KEY, m(0), m(10))
        self.assertEqual([c["params"].get("page") for c in fake.calls], [None, "pg_2", "pg_3"])
        self.assertEqual(set(minutes), {iso(m(0)), iso(m(2))})
        self.assertEqual(set(minutes[iso(m(0))]), {SONNET, HAIKU})
        self.assertEqual(minutes[iso(m(2))][SONNET]["output"], 6)

    def test_has_more_without_cursor_raises(self):
        broken = dict(page([]), has_more=True, next_page=None)
        _, p = patched({ANALYTICS: lambda params: broken})
        with p, self.assertRaises(RuntimeError):
            usage_api.minute_usage_analytics("adm", KEY, m(0), m(10))

    def test_thirty_hours_go_in_24_hour_chunks(self):
        start = datetime(2026, 11, 12, 0, 0, 30, tzinfo=timezone.utc)  # seconds are dropped
        end = start.replace(second=0) + timedelta(hours=30)
        refreshed = {"2026-11-12T00:00:00Z": "2026-11-13T09:00:00Z",
                     "2026-11-13T00:00:00Z": "2026-11-13T08:59:00Z"}

        def answer(params):
            first = datetime.fromisoformat(params["starting_at"].replace("Z", "+00:00"))
            return page([{"starting_at": iso(first), "ending_at": iso(first + timedelta(minutes=1)),
                          "group": {"model": SONNET}, "usage": usage(10, 1)}],
                        refreshed=refreshed[params["starting_at"]])

        fake, p = patched({ANALYTICS: answer})
        with p:
            minutes, when = usage_api.minute_usage_analytics_with_refresh("adm", KEY, start, end)
        spans = [(c["params"]["starting_at"], c["params"]["ending_at"]) for c in fake.calls]
        self.assertEqual(spans, [("2026-11-12T00:00:00Z", "2026-11-13T00:00:00Z"),
                                 ("2026-11-13T00:00:00Z", "2026-11-13T06:00:00Z")])
        self.assertEqual(sorted(minutes), ["2026-11-12T00:00:00Z", "2026-11-13T00:00:00Z"])
        # the earliest refresh across chunks: anything after it may be partial
        self.assertEqual(when, datetime(2026, 11, 13, 8, 59, tzinfo=timezone.utc))

    def test_no_data_yet_gives_none(self):
        _, p = patched({ANALYTICS: lambda params: page([], refreshed=None)})
        with p:
            self.assertEqual(usage_api.minute_usage_analytics_with_refresh("adm", KEY, m(0), m(10)), ({}, None))

    def test_same_shape_as_legacy(self):
        legacy = {"data": [
            {"starting_at": iso(m(0)), "ending_at": iso(m(1)), "results": [
                {"model": SONNET, "uncached_input_tokens": 8, "output_tokens": 828,
                 "cache_read_input_tokens": 4159,
                 "cache_creation": {"ephemeral_5m_input_tokens": 3000, "ephemeral_1h_input_tokens": 23}}]},
            {"starting_at": iso(m(1)), "ending_at": iso(m(2)), "results": []}],
            "has_more": False, "next_page": None}
        analytics = page([row(0, SONNET, inp=8, out=828, read=4159, c5m=3000, c1h=23)])
        _, p = patched({LEGACY: lambda params: legacy, ANALYTICS: lambda params: analytics})
        with p:
            self.assertEqual(usage_api.minute_usage("adm", KEY, m(0), m(2)),
                             usage_api.minute_usage_analytics("adm", KEY, m(0), m(2)))


LEGACY_PAGE = {"data": [{"starting_at": iso(m(0)), "ending_at": iso(m(1)), "results": [
    {"model": SONNET, "uncached_input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 0,
     "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}}]}],
    "has_more": False, "next_page": None}
ANALYTICS_PAGE = page([row(0, SONNET, inp=1, out=2)], refreshed="2026-11-14T07:00:00Z")


def raiser(exc):
    def f(params):
        raise exc
    return f


class SourceChoiceTest(unittest.TestCase):
    def run_any(self, legacy, source="auto"):
        fake, p = patched({LEGACY: legacy, ANALYTICS: lambda params: ANALYTICS_PAGE})
        with p:
            res = usage_api.minute_usage_any("adm", KEY, m(0), m(5), source=source)
        return res, fake

    def test_auto_uses_legacy_when_it_answers(self):
        (minutes, used, refreshed), fake = self.run_any(lambda params: LEGACY_PAGE)
        self.assertEqual((used, refreshed), ("legacy", None))
        self.assertEqual(minutes[iso(m(0))][SONNET]["output"], 2)
        self.assertEqual(fake.to(ANALYTICS), [])

    def test_auto_falls_back_on_410(self):
        (minutes, used, refreshed), fake = self.run_any(raiser(http_error(410)))
        self.assertEqual(used, "analytics")
        self.assertEqual(refreshed, datetime(2026, 11, 14, 7, 0, tzinfo=timezone.utc))
        self.assertEqual(minutes, {iso(m(0)): {SONNET: {"input": 1, "output": 2, "cache_read": 0,
                                                        "cache_creation": 0}}})
        self.assertEqual(len(fake.to(LEGACY)), 1)
        self.assertEqual(len(fake.to(ANALYTICS)), 1)

    def test_auto_keeps_a_bare_404(self):
        # a 404 can mean an unknown key ID; falling back would report zero usage instead
        with self.assertRaises(urllib.error.HTTPError):
            self.run_any(raiser(http_error(404)))

    def test_auto_falls_back_on_404_saying_retired(self):
        body = {"type": "error", "error": {"type": "not_found_error",
                                           "message": "This endpoint has been retired."}}
        (_, used, _), _ = self.run_any(raiser(http_error(404, body)))
        self.assertEqual(used, "analytics")

    def test_auto_falls_back_on_410(self):
        (_, used, _), _ = self.run_any(raiser(http_error(410)))
        self.assertEqual(used, "analytics")

    def test_auto_falls_back_on_deprecation_message(self):
        body = {"type": "error", "error": {"type": "invalid_request_error",
                                           "message": "This endpoint is deprecated; use /v1/organizations/analytics/usage."}}
        (_, used, _), _ = self.run_any(raiser(http_error(400, body)))
        self.assertEqual(used, "analytics")

    def test_auto_keeps_other_errors(self):
        for code, body in [(400, {"type": "error", "error": {"type": "invalid_request_error",
                                                               "message": "starting_at must be before ending_at"}}),
                           (401, {"type": "error", "error": {"type": "authentication_error",
                                                               "message": "invalid x-api-key"}}),
                           (429, None), (500, None)]:
            with self.subTest(code=code):
                fake, p = patched({LEGACY: raiser(http_error(code, body)),
                                   ANALYTICS: lambda params: ANALYTICS_PAGE})
                with p, self.assertRaises(urllib.error.HTTPError) as cm:
                    usage_api.minute_usage_any("adm", KEY, m(0), m(5))
                self.assertEqual(cm.exception.code, code)
                self.assertEqual(fake.to(ANALYTICS), [])

    def test_forced_legacy_does_not_fall_back(self):
        fake, p = patched({LEGACY: raiser(http_error(410)), ANALYTICS: lambda params: ANALYTICS_PAGE})
        with p, self.assertRaises(urllib.error.HTTPError):
            usage_api.minute_usage_any("adm", KEY, m(0), m(5), source="legacy")
        self.assertEqual(fake.to(ANALYTICS), [])

    def test_forced_analytics_skips_legacy(self):
        (_, used, refreshed), fake = self.run_any(lambda params: LEGACY_PAGE, source="analytics")
        self.assertEqual(used, "analytics")
        self.assertIsNotNone(refreshed)
        self.assertEqual(fake.to(LEGACY), [])

    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):
            usage_api.minute_usage_any("adm", KEY, m(0), m(5), source="cost")


class GetHeadersTest(unittest.TestCase):
    def test_extra_headers_are_sent_alongside_the_standard_ones(self):
        seen = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout=None):
            seen.append(req)
            return Resp(b'{"data": []}')

        with mock.patch.object(usage_api.urllib.request, "urlopen", urlopen):
            usage_api._get("adm", ANALYTICS, {"limit": 1}, headers={"anthropic-beta": "b1"})
            usage_api._get("adm", LEGACY, {"limit": 1})
        self.assertEqual(seen[0].get_header("Anthropic-beta"), "b1")
        self.assertEqual(seen[0].get_header("Anthropic-version"), usage_api.VERSION)
        self.assertEqual(seen[0].get_header("X-api-key"), "adm")
        self.assertIsNone(seen[1].get_header("Anthropic-beta"))


if __name__ == "__main__":
    unittest.main()
