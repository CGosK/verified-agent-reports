"""Anthropic's per-minute usage records for one API key, read with the key in
ANTHROPIC_ADMIN_KEY (an Admin key or an organization-scoped personal key)."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

API = "https://api.anthropic.com"
VERSION = "2026-10-21"


def _get(admin_key, path, params, attempts=4):
    """GET with retries on timeouts, connection errors, 429 and 5xx."""
    q = urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request("%s%s?%s" % (API, path, q), headers={
        "x-api-key": admin_key, "anthropic-version": VERSION, "User-Agent": "vawr/0.1"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 and exc.code < 500 or i == attempts - 1:
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
        "starting_at": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ending_at": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bucket_width": "1m", "api_key_ids[]": [key_id], "limit": 60})
