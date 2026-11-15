"""Anthropic's per-minute usage records for one API key, read with the key in
ANTHROPIC_ADMIN_KEY (an Admin key or an organization-scoped personal key).

Two sources give the same {minute_start_iso: {model: tokens}} shape:
- minute_usage: the Usage and Cost API (/v1/organizations/usage_report/messages),
  which Anthropic now calls legacy; records appear within minutes.
- minute_usage_analytics: its successor, the Usage and Cost Analytics API (beta,
  /v1/organizations/analytics/usage); records refresh within 4-24 hours, and
  usage after the response's data_refreshed_at is missing or partial.
minute_usage_any picks one, or tries the legacy source and falls back.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.anthropic.com"
VERSION = "2026-10-21"
ANALYTICS_BETA = "analytics-usage-cost-2026-08-24"
ANALYTICS_PATH = "/v1/organizations/analytics/usage"
ANALYTICS_MAX_SPAN = timedelta(hours=24)  # per request with time_bucket_width=1m
ANALYTICS_PAGE = 1000  # rows per page, the documented maximum


def _get(admin_key, path, params, attempts=4, headers=None):
    """GET with retries on timeouts, connection errors, 429 and 5xx. `headers`
    adds to (or overrides) the standard ones, e.g. an anthropic-beta header."""
    q = urllib.parse.urlencode(params, doseq=True)
    hdrs = {"x-api-key": admin_key, "anthropic-version": VERSION, "User-Agent": "vawr/0.1"}
    hdrs.update(headers or {})
    req = urllib.request.Request("%s%s?%s" % (API, path, q), headers=hdrs)
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and exc.code < 500 or i == attempts - 1:
                _keep_body(exc)
                raise
        except (OSError, ValueError):
            if i == attempts - 1:
                raise
        time.sleep(5 * 2 ** i)


def find_key_id(admin_key, api_key):
    """ID of the API key whose partial hint matches the given secret's ending."""
    data = _get(admin_key, "/v1/organizations/api_keys", {"limit": 100})
    for k in data.get("data", []):
        hint = (k.get("partial_key_hint") or "").split("...")[-1]
        if hint and api_key.endswith(hint):
            return k["id"]
    return None


def _tokens(result):
    cc = result.get("cache_creation") or {}
    if isinstance(cc, dict):
        cache_creation = sum(v for v in cc.values() if isinstance(v, (int, float)))
    else:
        cache_creation = cc or 0
    return {
        "input": result.get("uncached_input_tokens") or 0,
        "output": result.get("output_tokens") or 0,
        "cache_read": result.get("cache_read_input_tokens") or 0,
        "cache_creation": cache_creation,
    }


def minute_usage(admin_key, key_id, start, end):
    """{minute_start_iso: {model: tokens}} for the key between start and end
    (UTC datetimes). Requests are made in chunks of at most 1,440 one-minute
    buckets."""
    out = {}
    start, end = _utc(start), _utc(end)
    t = start.replace(second=0, microsecond=0)
    while t < end:
        chunk_end = min(end, t + timedelta(minutes=1440))
        params = {
            "starting_at": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ending_at": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "bucket_width": "1m",
            "api_key_ids[]": [key_id],
            "group_by[]": ["model"],
            "limit": 1440,
        }
        page = None
        while True:
            if page:
                params["page"] = page
            data = _get(admin_key, "/v1/organizations/usage_report/messages", params)
            for bucket in data.get("data", []):
                for r in bucket.get("results", []):
                    tok = _tokens(r)
                    by_model = out.setdefault(bucket["starting_at"], {})
                    acc = by_model.setdefault(r.get("model") or "*",
                                              {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
                    for k in acc:
                        acc[k] += tok[k]
            if not data.get("has_more"):
                break
            page = data.get("next_page")
        t = chunk_end
    return out


def raw_sample(admin_key, key_id, start, end):
    """One raw response, for checking field names."""
    return _get(admin_key, "/v1/organizations/usage_report/messages", {
        "starting_at": _iso(start),
        "ending_at": _iso(end),
        "bucket_width": "1m", "api_key_ids[]": [key_id], "limit": 60})


def _utc(t):
    """Aware UTC datetime: the API reads every time as UTC, so local digits would shift the window."""
    return t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _iso(t):
    return _utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    """Aware UTC datetime from an RFC 3339 string, or None if it isn't one."""
    if not isinstance(s, str) or not s:
        return None
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s.strip())
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _minute_key(s):
    """A row's starting_at in the legacy buckets' form, e.g. 2026-11-14T05:50:00Z."""
    t = _parse_iso(s)
    return _iso(t) if t else s


def minute_usage_analytics_with_refresh(admin_key, key_id, start, end):
    """(minutes, data_refreshed_at) from the Usage and Cost Analytics API (beta).

    minutes has exactly minute_usage's shape: {minute_start_iso: {model: tokens}},
    rows with no model (code execution) under "*". Requests are made in chunks of
    at most 24 hours (the limit with one-minute buckets), each paged through at
    1,000 rows a page.

    data_refreshed_at is an aware UTC datetime (the earliest across chunks), or
    None when no data is available yet for any part of the window. Usage after it
    is missing or partial, so warn when `end` is later than it.

    It is not a completeness watermark, though: on 2026-11-14 a query for
    05:50-07:40Z returned data_refreshed_at 07:41:42Z but rows only up to 05:59Z
    (the legacy API had usage through 07:38Z), and a query wholly after it
    returned no rows with a non-null data_refreshed_at. Treat recent hours as
    possibly incomplete even when the window ends before data_refreshed_at."""
    out = {}
    refreshed = []
    t = start.replace(second=0, microsecond=0)
    while t < end:
        chunk_end = min(end, t + ANALYTICS_MAX_SPAN)
        params = {
            "starting_at": _iso(t),
            "ending_at": _iso(chunk_end),
            "time_bucket_width": "1m",
            "api_key_ids[]": [key_id],
            "group_by[]": ["model"],
            "order_by": "time",
            "order": "asc",
            "limit": ANALYTICS_PAGE,
        }
        while True:
            data = _get(admin_key, ANALYTICS_PATH, params, headers={"anthropic-beta": ANALYTICS_BETA})
            r = _parse_iso(data.get("data_refreshed_at"))
            if r:
                refreshed.append(r)
            for row in data.get("data", []):
                tok = _tokens(row.get("usage") or {})
                model = (row.get("group") or {}).get("model") or "*"
                by_model = out.setdefault(_minute_key(row["starting_at"]), {})
                acc = by_model.setdefault(model, {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
                for k in acc:
                    acc[k] += tok[k]
            if not data.get("has_more"):
                break
            if not data.get("next_page"):
                raise RuntimeError("analytics usage page says has_more but gives no next_page")
            params = dict(params, page=data["next_page"])
        t = chunk_end
    return out, (min(refreshed) if refreshed else None)


def minute_usage_analytics(admin_key, key_id, start, end):
    """{minute_start_iso: {model: tokens}} for the key between start and end (UTC
    datetimes), from the Usage and Cost Analytics API; same shape as minute_usage.
    Use minute_usage_analytics_with_refresh to also get data_refreshed_at."""
    return minute_usage_analytics_with_refresh(admin_key, key_id, start, end)[0]


SOURCES = ("auto", "legacy", "analytics")
_RETIRED = re.compile(r"deprecat|sunset|no longer (?:available|supported|served)|"
                      r"(?:been|was|is) (?:removed|retired|discontinued)|end[- ]of[- ]life", re.I)


def _legacy_retired(exc):
    """True when the legacy endpoint's HTTP error says the endpoint is gone: a 410,
    or another 4xx (not 429) whose error message says it's deprecated or retired.
    A bare 404 doesn't count: the legacy endpoint can also answer 404 for an
    unknown key ID, and falling back then would report zero usage instead of the
    error. Reads the error body for the message."""
    code = getattr(exc, "code", None)
    if code == 410:
        return True
    if not isinstance(code, int) or not 400 <= code < 500 or code == 429:
        return False
    return bool(_RETIRED.search("%s %s" % (api_message(exc), getattr(exc, "reason", "") or "")))


def _keep_body(exc):
    """Read an HTTP error's body once and keep it on the exception (it can only be read once)."""
    if "vawr_body" not in vars(exc):  # hasattr on an HTTPError without a body raises KeyError
        try:
            exc.vawr_body = exc.read() or b""
        except Exception:
            exc.vawr_body = b""


def api_message(exc):
    """The error type and message from an Anthropic API error's JSON body, or its raw text."""
    _keep_body(exc)
    body = exc.vawr_body
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    try:
        err = json.loads(text).get("error") or {}
        return ("%s %s" % (err.get("type") or "", err.get("message") or "")).strip()
    except (ValueError, AttributeError):
        return text.strip()[:300]


def explain(exc):
    """One plain sentence for a failed call to Anthropic's API: what went wrong and what to do."""
    code = getattr(exc, "code", None)
    if not isinstance(exc, urllib.error.HTTPError):
        return "couldn't reach Anthropic's API (%s); check the network connection and try again." % (
            getattr(exc, "reason", None) or exc)
    said = api_message(exc)
    said = " (Anthropic says: %s)" % said if said else ""
    if code == 401:
        return ("Anthropic rejected the Admin key (HTTP 401)%s. ANTHROPIC_ADMIN_KEY must be an Admin key "
                "(it starts sk-ant-admin), made in the Claude Console under Settings > Admin keys." % said)
    if code == 403:
        return ("this Admin key can't read usage (HTTP 403)%s. The Admin API needs a Console organization: an "
                "individual account has to be turned into one first, and the key must be that organization's "
                "Admin key." % said)
    if code in (400, 404):
        return ("Anthropic refused the request (HTTP %d)%s. Most often the API key ID isn't in this Admin key's "
                "organization: pass --key-id with the ID (apikey_...) of a key on the Console's API keys page." % (code, said))
    if code == 429 or (isinstance(code, int) and code >= 500):
        return "Anthropic's API is busy or failing (HTTP %d)%s; try again in a few minutes." % (code, said)
    return "Anthropic's API returned HTTP %s%s." % (code, said)


def minute_usage_any(admin_key, key_id, start, end, source="auto"):
    """(minutes, source_used, data_refreshed_at) for the key between start and end.

    source "legacy" or "analytics" uses that API only. "auto" uses the legacy API
    (fresher: records appear within minutes) and falls back to the analytics API
    when the legacy one answers 410, or with a 4xx error saying it is
    deprecated or retired. source_used is "legacy" or "analytics";
    data_refreshed_at is None for the legacy source, else as in
    minute_usage_analytics_with_refresh (None there means no data yet)."""
    if source not in SOURCES:
        raise ValueError("source must be one of %s, not %r" % (", ".join(SOURCES), source))
    if source != "analytics":
        try:
            return minute_usage(admin_key, key_id, start, end), "legacy", None
        except urllib.error.HTTPError as exc:
            if source == "legacy" or not _legacy_retired(exc):
                raise
            # Inside the handler, so a failure here keeps the legacy error as context.
            minutes, refreshed = minute_usage_analytics_with_refresh(admin_key, key_id, start, end)
            return minutes, "analytics", refreshed
    minutes, refreshed = minute_usage_analytics_with_refresh(admin_key, key_id, start, end)
    return minutes, "analytics", refreshed


CLAUDE_CODE_PATH = "/v1/organizations/usage_report/claude_code"


def api_keys(admin_key):
    """Every API key in the organization, as the Admin API lists them (id, name, status...)."""
    out, after = [], None
    while True:
        params = {"limit": 100}
        if after:
            params["after_id"] = after
        data = _get(admin_key, "/v1/organizations/api_keys", params)
        out += data.get("data", [])
        after = data.get("last_id")
        if not data.get("has_more") or not after:
            return out


def claude_code_day(admin_key, day):
    """Anthropic's Claude Code Analytics records for one UTC day ("YYYY-MM-DD"): one
    record per actor (API key name or Console user's email) and terminal type, with
    num_sessions and tokens by model. Reported by Claude Code itself (a session with its
    own telemetry switched off isn't counted); data younger than
    an hour is left out."""
    out, page = [], None
    while True:
        params = {"starting_at": day, "limit": 1000}
        if page:
            params["page"] = page
        data = _get(admin_key, CLAUDE_CODE_PATH, params)
        out += data.get("data", [])
        page = data.get("next_page")
        if not data.get("has_more") or not page:
            return out


def org_minute_usage(admin_key, start, end):
    """{key_id: {minute_start_iso: {model: tokens}}} for every key in the organization
    between start and end; usage with no API key (e.g. the Console) is under None."""
    out = {}
    start, end = _utc(start), _utc(end)
    t = start.replace(second=0, microsecond=0)
    while t < end:
        chunk_end = min(end, t + timedelta(minutes=1440))
        params = {"starting_at": _iso(t), "ending_at": _iso(chunk_end), "bucket_width": "1m",
                  "group_by[]": ["api_key_id", "model"], "limit": 1440}
        page = None
        while True:
            if page:
                params["page"] = page
            data = _get(admin_key, "/v1/organizations/usage_report/messages", params)
            for bucket in data.get("data", []):
                for r in bucket.get("results", []):
                    tok = _tokens(r)
                    if not any(tok.values()):
                        continue
                    acc = out.setdefault(r.get("api_key_id"), {}).setdefault(bucket["starting_at"], {}) \
                        .setdefault(r.get("model") or "*", {"input": 0, "output": 0, "cache_read": 0,
                                                              "cache_creation": 0})
                    for k in acc:
                        acc[k] += tok[k]
            page = data.get("next_page")
            if not data.get("has_more") or not page:
                break
        t = chunk_end
    return out
