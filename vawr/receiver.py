"""Minimal OTLP/HTTP receiver (JSON encoding) that writes Claude Code's log
events and token/cost metric data points into the hash-chained log.

Claude Code must export with:
    CLAUDE_CODE_ENABLE_TELEMETRY=1
    OTEL_LOGS_EXPORTER=otlp
    OTEL_METRICS_EXPORTER=otlp
    OTEL_EXPORTER_OTLP_PROTOCOL=http/json
    OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:<port>

/v1/logs and the token and cost metrics on /v1/metrics are recorded; other
metrics and all traces are accepted and dropped.
"""

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .chainlog import ChainLog


def any_value(v):
    """Convert an OTLP JSON AnyValue into a plain Python value."""
    if not isinstance(v, dict):
        return v
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return v["intValue"]
    if "doubleValue" in v:
        return v["doubleValue"]
    if "boolValue" in v:
        return v["boolValue"]
    if "arrayValue" in v:
        return [any_value(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return attrs(v["kvlistValue"].get("values", []))
    if "bytesValue" in v:
        return v["bytesValue"]
    return None


# Identity fields Claude Code attaches to every event, plus the account's plan
# and seat type. They are dropped before hashing so the log can be published;
# nothing the checks use depends on them. (Logs written before Nov 14, 2026
# 08:30 UTC still carry anthropic.plan and anthropic.seat_type.)
DROPPED_ATTRIBUTES = frozenset({
    "user.email", "user.account_uuid", "user.account_id", "user.id", "organization.id",
    "anthropic.plan", "anthropic.seat_type",
})


def attrs(kvs):
    """Attributes minus the dropped ones. Claude Code sends a plan attribute only
    for sessions signed in with a Claude account; that is kept as auth=account
    (otherwise auth=api_key) so the provider check knows which requests were
    billed to an API key, without recording the plan itself."""
    kvs = kvs or []
    out = {kv.get("key"): any_value(kv.get("value")) for kv in kvs
           if kv.get("key") not in DROPPED_ATTRIBUTES}
    if any(kv.get("key") == "anthropic.plan" for kv in kvs):
        out["auth"] = "account"
    elif any(kv.get("key") == "anthropic.provider" for kv in kvs):
        out["auth"] = "api_key"
    return out


def nanos_to_iso(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return datetime.fromtimestamp(n / 1e9, tz=timezone.utc).isoformat(timespec="microseconds")


def flatten_logs(payload):
    """Yield one event dict per OTLP log record."""
    for rl in payload.get("resourceLogs", []):
        resource = attrs((rl.get("resource") or {}).get("attributes"))
        for sl in rl.get("scopeLogs", []):
            scope = (sl.get("scope") or {}).get("name")
            for rec in sl.get("logRecords", []):
                a = attrs(rec.get("attributes"))
                body = any_value(rec.get("body"))
                name = a.get("event.name") or (body if isinstance(body, str) else None)
                yield {
                    "name": name,
                    "time": nanos_to_iso(rec.get("timeUnixNano")) or a.get("event.timestamp"),
                    "body": body,
                    "attributes": a,
                    "resource": resource,
                    "scope": scope,
                }


# Token and cost metrics are recorded so that any request Claude Code reports
# only in metrics (query_source "auxiliary") still counts toward the totals.
# In our runs there were none: the unreported small-model request the provider
# check allows for appears in neither events nor metrics.
KEPT_METRICS = {"claude_code.token.usage", "claude_code.cost.usage"}


def flatten_metrics(payload):
    """Yield one event dict per data point of a kept metric."""
    for rm in payload.get("resourceMetrics", []):
        resource = attrs((rm.get("resource") or {}).get("attributes"))
        for sm in rm.get("scopeMetrics", []):
            for metric in sm.get("metrics", []):
                name = metric.get("name")
                if name not in KEPT_METRICS:
                    continue
                body = metric.get("sum") or metric.get("gauge") or {}
                for dp in body.get("dataPoints", []):
                    value = dp.get("asDouble", dp.get("asInt"))
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        continue
                    yield {
                        "name": "metric",
                        "metric": name,
                        "time": nanos_to_iso(dp.get("timeUnixNano")),
                        "start": nanos_to_iso(dp.get("startTimeUnixNano")),
                        "value": value,
                        "temporality": body.get("aggregationTemporality"),
                        "attributes": attrs(dp.get("attributes")),
                        "resource": resource,
                    }


def make_handler(log):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        def _reply(self, code, body=b"{}"):
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if self.path.rstrip("/") not in ("/v1/logs", "/v1/metrics", "/v1/traces"):
                return self._reply(404)
            if ctype != "application/json":
                sys.stderr.write("rejected %s with content type %r; set "
                                 "OTEL_EXPORTER_OTLP_PROTOCOL=http/json\n" % (self.path, ctype))
                return self._reply(415)
            route = self.path.rstrip("/")
            if route == "/v1/traces":
                return self._reply(200)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                return self._reply(400)
            events = flatten_logs(payload) if route == "/v1/logs" else flatten_metrics(payload)
            for event in events:
                log.append(event)
            return self._reply(200)

        def do_GET(self):
            if self.path == "/health":
                return self._reply(200, b'{"ok":true}')
            return self._reply(404)

    return Handler


def serve(log_path, host="127.0.0.1", port=4318):
    log = ChainLog(log_path)
    server = ThreadingHTTPServer((host, port), make_handler(log))
    sys.stderr.write("receiver on http://%s:%d writing %s\n" % (host, port, log_path))
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
