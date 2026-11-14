"""Bill check: what Anthropic billed one API key, minute by minute, against
what Claude Code's own session files on this machine say it used.

It works on history you already have: no receiver, no setup, nothing to have
run beforehand. You need an Admin key (or an organization-scoped key) for the
usage records, and the API key to check (or its ID).

What it reports:
- matched: billed tokens that a local session file accounts for;
- background: billed small-model requests Claude Code makes once per session
  and records nowhere locally (allowed within a fixed envelope);
- unexplained: billed tokens no local session file accounts for: work from
  another machine, a script or tool using the key, a run with session files
  turned off, or a leaked key;
- local only: requests in API-key session files that this key wasn't billed
  for (another key, or files edited after the fact).

Session files signed in with a Claude account (a subscription) carry an owner
entry; those are left out, since they never bill an API key. The owner's IDs
are only used to tell the two apart and are never stored or printed.
"""
import glob
import json
import os
from datetime import datetime, timedelta, timezone

from . import auditor, paths, usage_api
from .sessions import parse_ts, session_files

LAG_MINUTES = 30  # provider usage records lagged 20-30 minutes in our tests


def parse_when(s, now=None):
    """'24h', '90m', '7d', or an ISO time (UTC if no zone)."""
    now = now or datetime.now(timezone.utc)
    s = s.strip()
    if s[-1:] in "mhd" and s[:-1].isdigit():
        n = int(s[:-1])
        return now - {"m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n)}[s[-1]]
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


# Signs that a session was signed in with a Claude account (a subscription)
# rather than an API key. Across our runs every subscription session file had
# all four and no API-key session file had any. Getting this wrong in one
# direction (an API-key session read as a subscription one) shows up as
# unexplained usage, a visible false alarm; the other direction could hide
# usage, so any one sign is enough.
ACCOUNT_SIGNS = ('"session-owner"', '"accountUuid"', '"advisorModel"', '"ttl": "1h"', '"ttl":"1h"')


def _signed_in(path):
    """True when a main session file belongs to a Claude-account (subscription) session."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if any(sign in line for sign in ACCOUNT_SIGNS):
                return True
            if '"ephemeral_1h_input_tokens"' in line and '"ephemeral_1h_input_tokens": 0' not in line \
                    and '"ephemeral_1h_input_tokens":0' not in line:
                return True
    return False


def local_requests(start, end, projects=paths.CLAUDE_PROJECTS):
    """{request_id: record} from every session file under `projects` with a
    timestamp in [start, end]. Each record says whether its session was signed
    in with a Claude account ('account') or used an API key ('api_key')."""
    out = {}
    if not os.path.isdir(projects):
        return out
    for pdir in sorted(glob.glob(os.path.join(projects, "*"))):
        if not os.path.isdir(pdir):
            continue
        auth_of = {}
        for path in session_files(pdir):
            if datetime.fromtimestamp(os.path.getmtime(path), timezone.utc) < start:
                continue  # not written since the window opened
            if "/subagents/" in path:  # <pdir>/<session>/subagents/x.jsonl
                parent = os.path.join(pdir, path[len(pdir) + 1:].split("/")[0] + ".jsonl")
            else:
                parent = path
            if parent not in auth_of:
                auth_of[parent] = "account" if os.path.exists(parent) and _signed_in(parent) else "api_key"
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if '"requestId"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") != "assistant" or not d.get("requestId"):
                        continue
                    ts = parse_ts(d.get("timestamp"))
                    if not ts or ts < start or ts > end:
                        continue
                    msg = d.get("message") or {}
                    u = msg.get("usage") or {}
                    out[d["requestId"]] = {
                        "request_id": d["requestId"], "session_id": d.get("sessionId"),
                        "project": os.path.basename(pdir), "auth": auth_of[parent],
                        "time": d.get("timestamp"), "model": msg.get("model"),
                        "tokens": {"input": u.get("input_tokens") or 0,
                                   "output": u.get("output_tokens") or 0,
                                   "cache_read": u.get("cache_read_input_tokens") or 0,
                                   "cache_creation": u.get("cache_creation_input_tokens") or 0},
                    }
    return out


def admin_and_key(env=None, files=None):
    """(admin_key, api_key) from the environment, then a .env file in this folder,
    then .env in vawr's data folder (~/.vawr/.env), which works from any project."""
    env = dict(env if env is not None else os.environ)
    for path in files if files is not None else (".env", os.path.join(paths.WORK, ".env")):
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):]
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env.get("ANTHROPIC_ADMIN_KEY"), env.get("ANTHROPIC_API_KEY")


def check(start, end, admin_key=None, key_id=None, api_key=None, provider_minutes=None,
          projects=paths.CLAUDE_PROJECTS, shift=2, source="auto"):
    if provider_minutes is None:
        if not admin_key:
            raise SystemExit("set ANTHROPIC_ADMIN_KEY (an Admin key for your Console organization) in your "
                             "environment or in ~/.vawr/.env to read Anthropic's usage records")
        if not key_id:
            if not api_key:
                raise SystemExit("pass --key-id, or set ANTHROPIC_API_KEY (the key to check) in your "
                                 "environment or in ~/.vawr/.env")
            key_id = usage_api.find_key_id(admin_key, api_key)
            if not key_id:
                raise SystemExit("that API key isn't in the Admin key's organization")
        raw, source, refreshed = usage_api.minute_usage_any(admin_key, key_id, start, end, source)
        provider_minutes = {parse_ts(k): v for k, v in raw.items()}
    else:
        source, refreshed = "saved", None
    pad = timedelta(minutes=shift + 1)
    local = local_requests(start - pad, end + pad, projects)
    key_reqs = [dict(r, mode="api_key") for r in local.values() if r["auth"] == "api_key"]
    res = auditor.check_provider(key_reqs, start, end, shift=shift, key_mode="api_key",
                                 provider_minutes=provider_minutes)
    sessions = {r["session_id"] for r in key_reqs if start <= parse_ts(r["time"]) < end}
    res.update(key_id=key_id, source=source,
               data_refreshed_at=refreshed.isoformat() if hasattr(refreshed, "isoformat") else refreshed,
               local_api_key_requests=len(key_reqs),
               local_api_key_sessions=len(sessions),
               local_account_requests=sum(1 for r in local.values() if r["auth"] == "account"))
    return res


def _total(tokens):
    return sum(tokens.values())


def render(res):
    prov = _total(res["provider_tokens"])
    bg = _total(res["background_tokens"])
    gap = sum(_total(g["tokens"]) for g in res["gaps"])
    excess = sum(_total(g["tokens"]) for g in res["log_excess"])
    matched = prov - bg - gap
    pct = (lambda v: "%5.1f%%" % (100.0 * v / prov)) if prov else (lambda v: "    -")
    start, end = res["window"]
    lines = [
        "Bill check, %s to %s UTC%s" % (start[:16].replace("T", " "), end[11:16],
                                         ", key %s" % res["key_id"] if res.get("key_id") else ""),
        "",
        "  Billed by Anthropic               %12s tokens" % "{:,}".format(prov),
        "  In this machine's session files   %12s  %s" % ("{:,}".format(matched), pct(matched)),
        "  Claude Code background requests   %12s  %s  billed, recorded nowhere locally (%d sessions)"
        % ("{:,}".format(bg), pct(bg), res["logged_sessions"]),
        "  Unexplained                       %12s  %s" % ("{:,}".format(gap), pct(gap)),
    ]
    for g in res["gaps"]:
        models = ", ".join(sorted(g["by_model"]))
        span = g["start"][11:16] + ("" if g["start"] == g["end"] else "-" + g["end"][11:16])
        lines.append("      %-11s %10s tokens  %s" % (span, "{:,}".format(_total(g["tokens"])), models))
    lines += ["  In session files, not billed here  %12s" % "{:,}".format(excess), ""]
    if gap:
        lines.append("Unexplained usage came from somewhere this machine has no record of: another "
                     "machine or script using the key, a run with session files off, or a leaked key.")
    else:
        lines.append("Every billed token is accounted for by this machine's session files, apart from "
                     "Claude Code's own background requests.")
    if res.get("source") == "analytics":
        lines.append("Records came from the Usage and Cost Analytics API, which can run 4-24 hours behind; "
                     "recent minutes may be missing.")
    else:
        lines.append("Usage records can lag about %d minutes; the newest minutes may be incomplete." % LAG_MINUTES)
    return "\n".join(lines)
