"""Point Claude Code at the local receiver, tag projects with a category, and
start or stop the receiver in the background.

Settings changes are shown first and written only with --write; the old file
is copied next to it before anything changes.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

from . import paths
from .runner import receiver_up

CATEGORIES = ("safety", "capabilities", "other")


def otel_env(port=4318):
    """What Claude Code needs to send its events and metrics to the receiver."""
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:%d" % port,
        "OTEL_LOGS_EXPORT_INTERVAL": "1000",
        "OTEL_METRIC_EXPORT_INTERVAL": "5000",
        "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
    }


def user_settings_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(base, "settings.json")


def project_settings_path(project_dir):
    return os.path.join(project_dir, ".claude", "settings.local.json")


def merge_env(path, env, write=False):
    """(changes, settings) after adding env to the settings file's "env" block.
    changes lists (key, old, new) for every key that differs."""
    settings = {}
    if os.path.exists(path):
        with open(path) as fh:
            text = fh.read().strip()
        settings = json.loads(text) if text else {}
    current = settings.get("env") or {}
    changes = [(k, current.get(k), v) for k, v in env.items() if current.get(k) != v]
    if write and changes:
        if os.path.exists(path):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            shutil.copy2(path, "%s.vawr-backup-%s" % (path, stamp))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        settings["env"] = dict(current, **env)
        tmp = path + ".vawr-tmp"
        with open(tmp, "w") as fh:
            json.dump(settings, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    return changes, settings


def tag_env(category, project):
    if category not in CATEGORIES:
        raise SystemExit("category must be one of: %s" % ", ".join(CATEGORIES))
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in project)
    return {"OTEL_RESOURCE_ATTRIBUTES": "category=%s,project=%s" % (category, safe)}


def describe(path, changes, write):
    if not changes:
        return "%s already has these settings." % path
    lines = ["%s %s:" % ("Updated" if write else "Would change", path)]
    for k, old, new in changes:
        lines.append("  %s: %s -> %s" % (k, "(unset)" if old is None else old, new))
    if not write:
        lines.append("Run again with --write to apply (the old file is backed up first).")
    return "\n".join(lines)


# ---------- receiver in the background ----------

def _pid_path():
    return os.path.join(paths.WORK, "receiver.pid")


def start(port=4318, log_path=None):
    if receiver_up(port):
        return "The receiver is already running on port %d." % port
    os.makedirs(paths.WORK, exist_ok=True)
    out = open(os.path.join(paths.WORK, "receiver.out"), "a")
    cmd = [sys.executable, "-m", "vawr", "serve", "--port", str(port)]
    if log_path:
        cmd += ["--log", log_path]
    proc = subprocess.Popen(cmd, stdout=out, stderr=out, start_new_session=True)
    with open(_pid_path(), "w") as fh:
        fh.write(str(proc.pid))
    for _ in range(40):
        if receiver_up(port):
            return "Receiver started (pid %d), writing %s." % (proc.pid, log_path or paths.LOG_PATH)
        time.sleep(0.25)
    return "Started pid %d, but it isn't answering yet; see %s." % (
        proc.pid, os.path.join(paths.WORK, "receiver.out"))


def stop():
    try:
        with open(_pid_path()) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return "No receiver started by `vawr start` is recorded."
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    os.remove(_pid_path())
    return "Stopped the receiver (pid %d)." % pid


def telemetry_status(port=4318):
    """(configured, detail) from the user's Claude Code settings: is telemetry on and
    pointed at the local receiver? Claude Code reads these only from user settings
    (or the shell), not from project settings or plugins."""
    path = user_settings_path()
    try:
        with open(path) as fh:
            env = (json.load(fh) or {}).get("env") or {}
    except (OSError, ValueError):
        env = {}
    env = dict(env, **{k: v for k, v in os.environ.items() if k.startswith(("OTEL_", "CLAUDE_CODE_ENABLE_TELEMETRY"))})
    want = otel_env(port)
    missing = [k for k in ("CLAUDE_CODE_ENABLE_TELEMETRY", "OTEL_LOGS_EXPORTER", "OTEL_EXPORTER_OTLP_ENDPOINT")
               if str(env.get(k)) != want[k]]
    return (not missing), missing


TELEMETRY_OFF = ("DISABLE_TELEMETRY", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")


MANAGED_SETTINGS = ("/Library/Application Support/ClaudeCode/managed-settings.json",  # macOS
                    "/etc/claude-code/managed-settings.json")  # Linux


def _set(value):
    """The value as it would read in a warning, or None if unset. Any non-empty value
    counts: we only tested "1", and a warning on "0" costs less than silence on it."""
    if value is None or not str(value).strip():
        return None
    v = str(value).strip()
    return "" if v.lower() in ("1", "true") else "=%s" % json.dumps(v)


def telemetry_off_settings(environ=None, settings_path=None, project_dir=None, managed_paths=MANAGED_SETTINGS):
    """Where DISABLE_TELEMETRY or CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC is set: the
    shell, the user's Claude Code settings, this project's (.claude/settings.json and
    settings.local.json) or managed settings. Claude Code doesn't report sessions run
    with either to Anthropic (vawr still logs them), so a payer's check of Anthropic's
    session count can't confirm them."""
    environ = os.environ if environ is None else environ
    project_dir = os.getcwd() if project_dir is None else project_dir
    paths = [settings_path or user_settings_path(),
             os.path.join(project_dir, ".claude", "settings.json"), project_settings_path(project_dir)]
    paths += list(managed_paths or ())
    found = ["%s%s in the shell" % (k, _set(environ.get(k))) for k in TELEMETRY_OFF
             if _set(environ.get(k)) is not None]
    for path in dict.fromkeys(paths):
        try:
            with open(path) as fh:
                data = json.load(fh)
            env = data.get("env") if isinstance(data, dict) else None
        except (OSError, ValueError, RecursionError):
            env = None
        if isinstance(env, dict):
            found += ["%s%s in %s" % (k, _set(env.get(k)), path) for k in TELEMETRY_OFF
                      if _set(env.get(k)) is not None]
    return found


def telemetry_off_warning(environ=None, settings_path=None, project_dir=None, managed_paths=MANAGED_SETTINGS):
    found = telemetry_off_settings(environ, settings_path, project_dir, managed_paths)
    if not found:
        return ""
    return ("Note: %s is set. vawr still logs these sessions and the bill check still covers them, but Claude Code "
            "doesn't report them to Anthropic, so a payer's check of Anthropic's session count can't confirm "
            "them and their reports stop at CONSISTENT. Unset it for sessions you'll report." % " and ".join(found))


def session_start(port=4318):
    """For the plugin's SessionStart hook: start the receiver when telemetry is set
    up; otherwise say once, briefly, how to set it up. Prints hook JSON or nothing."""
    ok, missing = telemetry_status(port)
    if not ok:
        return {"systemMessage": "vawr: Claude Code isn't sending its usage events to vawr yet. "
                                 "Run /vawr:setup once and restart Claude Code. (/vawr:billcheck works without it.)"}
    if not receiver_up(port):
        msg = start(port)
        if not receiver_up(port):
            return {"systemMessage": "vawr: couldn't start the receiver: %s" % msg}
    return None
