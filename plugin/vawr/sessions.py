"""Read Claude Code's local session files (~/.claude/projects/<dir>/*.jsonl,
plus subagent files) and return one record per API request.

One request can appear in several assistant entries (one per content block),
so entries are deduplicated by requestId; the last entry's usage is kept.
"""

import glob
import json
import os
from datetime import datetime

from . import paths


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def scope_dirs(runs_dir=paths.RUNS_DIR, projects=paths.CLAUDE_PROJECTS):
    """Project folders for working directories under runs_dir."""
    prefix = paths.project_dir_name(runs_dir) + "-"
    if not os.path.isdir(projects):
        return []
    return sorted(os.path.join(projects, d) for d in os.listdir(projects) if d.startswith(prefix))


def session_files(project_dir):
    return sorted(glob.glob(os.path.join(project_dir, "*.jsonl"))
                  + glob.glob(os.path.join(project_dir, "*", "subagents", "*.jsonl")))


def requests_in_scope(start=None, end=None, runs_dir=paths.RUNS_DIR):
    """{request_id: record} for requests in scope whose timestamp is in [start, end]."""
    out = {}
    for pdir in scope_dirs(runs_dir):
        for path in session_files(pdir):
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("type") != "assistant" or not d.get("requestId"):
                        continue
                    msg = d.get("message") or {}
                    u = msg.get("usage") or {}
                    ts = parse_ts(d.get("timestamp"))
                    if start and ts and ts < start:
                        continue
                    if end and ts and ts > end:
                        continue
                    out[d["requestId"]] = {
                        "request_id": d["requestId"],
                        "session_id": d.get("sessionId"),
                        "project_dir": os.path.basename(pdir),
                        "file": path,
                        "subagent": "/subagents/" in path,
                        "time": d.get("timestamp"),
                        "model": msg.get("model"),
                        "tokens": {
                            "input": u.get("input_tokens") or 0,
                            "output": u.get("output_tokens") or 0,
                            "cache_read": u.get("cache_read_input_tokens") or 0,
                            "cache_creation": u.get("cache_creation_input_tokens") or 0,
                        },
                    }
    return out


def final_message(session_id, project_dir):
    """Text of the last assistant message in a session's main file."""
    path = os.path.join(paths.CLAUDE_PROJECTS, project_dir, session_id + ".jsonl")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") == "assistant":
                parts = (d.get("message") or {}).get("content") or []
                text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
                if text.strip():
                    last = text
    return last
