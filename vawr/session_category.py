"""Category check for interactive Claude Code sessions, which have no manifest.

The category check (category.py) needs what a piece of work was asked to do and
what it changed. Research runs save both in their manifests; an interactive
session does not, but Claude Code's own session file does hold them: the
person's typed prompts, and every Edit/MultiEdit/Write/NotebookEdit call with
its inputs (in the main file and in the session's subagent files). This module
rebuilds a task text and a pseudo diff from those and runs the same check.

Only prompts and edit inputs are read; nothing else from a session file (such
as account entries) is kept or returned.
"""
import glob
import hashlib
import json
import os
import re
import shlex

from . import category, paths

MAX_PROMPT_CHARS = 4000
MAX_DIFF_CHARS = category.MAX_DIFF_CHARS
MIN_SHARE = 200  # no prompt or file is cut below this when several share the budget
CUT = "\n[... cut ...]"
EDIT_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
# Claude Code's own folder (memory, plans, settings): writes there are not the work itself
CLAUDE_HOME = os.path.dirname(paths.CLAUDE_PROJECTS)
# A Bash call whose result says it never ran; any other failed Bash call may still have written.
_NOT_RUN = re.compile(r"Permission for this tool use was denied|doesn't want to proceed|"
                      r"tool use was rejected|PreToolUse")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)([A-Za-z_][\w.-]*)\2")
_ESCAPE = {"\\n": "\n", "\\t": "\t", "\\\\": "\\"}

# Text Claude Code or the app adds to a user turn; none of it was typed by the person.
NOISE_TAGS = ("system-reminder", "task-notification", "ci-monitor-event", "local-command-caveat",
              "local-command-stdout", "local-command-stderr", "bash-input", "bash-stdout",
              "bash-stderr", "artifact-view-context", "artifact-content-authored-by-others",
              "create-pr-command", "command-message", "cross-session-message",
              "side-sessions-event")
# Added blocks start a line; a tag named inline is the person writing about it, and is kept.
_TAGS = "|".join(map(re.escape, NOISE_TAGS))
_PAIRED = re.compile(r"^[ \t]*<(%s)\b[^>]*>.*?</\1\s*>" % _TAGS, re.S | re.M)
_SINGLE = re.compile(r"^[ \t]*<(?:%s)\b[^>]*/>" % _TAGS, re.M)
_COMMAND = re.compile(r"^[ \t]*<command-name>(.*?)</command-name>", re.S | re.M)
_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_PASTED = re.compile(r"</?pasted_content\b[^>]*>")
NOISE_STARTS = ("[Request interrupted by user", "Caveat: The messages below were generated")


def _entries(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                yield d


def _typed_text(text):
    """What the person typed in one user text, or '' for a turn Claude Code made."""
    cmd = _COMMAND.search(text)
    if cmd:  # a slash command: keep its name and arguments, drop the expansion
        args = _ARGS.search(text)
        args = args.group(1).strip() if args else ""
        return ("%s %s" % (cmd.group(1).strip(), args)) if args else ""
    while True:  # removing one block can bring the next to the start of a line
        cut = _SINGLE.sub("", _PAIRED.sub("", text))
        if cut == text:
            break
        text = cut
    text = _PASTED.sub("", text).strip()
    if text.startswith(NOISE_STARTS):
        return ""
    return text


def _prompts(entries):
    out = []
    for d in entries:
        if d.get("type") != "user":
            continue
        if d.get("isMeta") or d.get("isCompactSummary") or d.get("isVisibleInTranscriptOnly") \
                or d.get("isSidechain"):
            continue
        origin = d.get("origin")
        if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
            continue  # task notifications, subagent hand-backs
        content = (d.get("message") or {}).get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [b.get("text") or "" for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
        else:
            texts = []
        typed = "\n".join(t for t in (_typed_text(x) for x in texts) if t)
        if typed:
            out.append(typed)
    return out


def _fit(pieces, cap):
    """Cut the longest pieces first so that together they fit in `cap` characters:
    one large paste or file write does not push the rest out."""
    if sum(len(p) for p in pieces) <= cap:
        return "".join(pieces)
    out = list(pieces)
    left = cap
    order = sorted(range(len(pieces)), key=lambda i: len(pieces[i]))
    for k, i in enumerate(order):
        share = max(left // (len(order) - k), MIN_SHARE)
        if len(pieces[i]) > share:
            out[i] = pieces[i][:max(share - len(CUT) - 1, 0)] + CUT + "\n"
        left -= len(out[i])
    text = "".join(out)
    if len(text) > cap:
        text = text[:cap - len(CUT)] + CUT
    return text


def _show_path(path, base):
    """(old, new) header paths: relative to the session's folder when inside it."""
    if base and os.path.isabs(path):
        norm, root = os.path.normpath(path), os.path.normpath(base)
        if norm.startswith(root + os.sep):
            rel = os.path.relpath(norm, root)
            return "a/" + rel, "b/" + rel
    if os.path.isabs(path):
        return path, path
    return "a/" + path, "b/" + path


def _lines(sign, text):
    return [sign + ln for ln in (text or "").splitlines()]


def _hunks(name, inp):
    """Pseudo hunks for one edit call."""
    if name == "Edit":
        mark = "@@ edit (every match) @@" if inp.get("replace_all") else "@@ edit @@"
        return [mark] + _lines("-", inp.get("old_string")) + _lines("+", inp.get("new_string"))
    if name == "MultiEdit":
        out = []
        for e in inp.get("edits") or []:
            if isinstance(e, dict):
                out += _hunks("Edit", e)
        return out
    if name == "Write":
        return ["@@ write (whole file) @@"] + _lines("+", inp.get("content"))
    if name == "NotebookEdit":
        mode = inp.get("edit_mode") or "replace"
        out = ["@@ notebook cell %s (%s) @@" % (inp.get("cell_id") or "new", mode)]
        return out if mode == "delete" else out + _lines("+", inp.get("new_source"))
    return []


def _tokens(line):
    lex = shlex.shlex(line, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def _segments(tokens):
    """[(tokens, piped)] for the simple commands in one line, split at ; && || & |."""
    out, cur, piped = [], [], False
    for t in tokens:
        if t and set(t) <= set(";&|"):
            out.append((cur, piped or "|" in t))
            cur, piped = [], "|" in t
        else:
            cur.append(t)
    out.append((cur, piped))
    return out


def _target(word, cwd):
    if not word or "$" in word or "`" in word:
        return None
    word = os.path.expanduser(word)
    if not os.path.isabs(word) and cwd:
        word = os.path.join(cwd, word)
    return os.path.normpath(word)


def _printf(fmt, args):
    """What `printf fmt args...` prints, for formats with only %s; None otherwise."""
    if any(spec not in ("%s", "%%") for spec in re.findall(r"%.?", fmt)):
        return None
    n = fmt.count("%s") - fmt.count("%%s")
    out, rest = [], list(args)
    while True:
        chunk = iter(rest[:n] if n else [])
        out.append(re.sub(r"\\[nt\\]|%[s%]", lambda m: _ESCAPE.get(m.group()) or
                          ("%" if m.group() == "%%" else next(chunk, "")), fmt))
        rest = rest[n:]
        if not n or not rest:
            return "".join(out)


def _echo(args):
    newline, escapes = True, False
    while args and re.fullmatch(r"-[neE]+", args[0]):
        newline = newline and "n" not in args[0]
        escapes = "e" in args[0]
        args = args[1:]
    text = " ".join(args)
    if escapes:
        text = re.sub(r"\\[nt\\]", lambda m: _ESCAPE[m.group()], text)
    return text + ("\n" if newline else "")


def _bash_writes(command, cwd):
    """[(path, append, text)] for file writes in a Bash command that can be read
    without running it: `cat > f <<EOF`, `cat <<EOF > f`, `tee [-a] f <<EOF`, and
    `echo`/`printf ... > f` with one redirect. A `cd` to a literal folder is followed.
    Pipes, command substitution and variables are skipped."""
    out, lines, i = [], command.split("\n"), 0
    while i < len(lines):
        line, body, heredoc = lines[i], None, _HEREDOC.search(lines[i])
        i += 1
        if heredoc:
            delim, strip = heredoc.group(3), heredoc.group(1) == "-"
            end = next((j for j in range(i, len(lines))
                        if (lines[j].lstrip("\t") if strip else lines[j]).rstrip("\r") == delim), None)
            if end is not None:
                body = [ln.lstrip("\t") if strip else ln for ln in lines[i:end]]
                i = end + 1
        try:
            segments = _segments(_tokens(line))
        except ValueError:
            continue
        for seg, piped in segments:
            if not seg:
                continue
            if seg[0] == "cd":
                cwd = _target(seg[1], cwd) if len(seg) == 2 and seg[1] != "-" else (
                    os.path.expanduser("~") if len(seg) == 1 else None)
                continue
            if piped or any(t in ("(", ")", "<", "<<<") or "$" in t or "`" in t for t in seg):
                continue
            if "<<" in seg:
                k = seg.index("<<")
                if body is None or k + 1 >= len(seg) or seg[k + 1].lstrip("-") != delim:
                    continue
                rest, text = seg[:k] + seg[k + 2:], "\n".join(body) + "\n"
                body = None  # one heredoc per line
                if rest[:1] == ["cat"] and len(rest) == 3 and rest[1] in (">", ">>"):
                    out.append((_target(rest[2], cwd), rest[1] == ">>", text))
                elif rest[:1] == ["tee"]:
                    args = rest[1:]
                    append = bool(args) and args[0] in ("-a", "--append")
                    args = args[1:] if append else args
                    if args[-2:] in ([">", "/dev/null"], [">>", "/dev/null"]):
                        args = args[:-2]
                    if len(args) == 1:
                        out.append((_target(args[0], cwd), append, text))
            elif seg[0] in ("echo", "printf") and len(seg) >= 3 and seg[-2] in (">", ">>") \
                    and not any(">" in t for t in seg[:-2]):
                if seg[0] == "echo":
                    text = _echo(seg[1:-2])
                else:
                    text = _printf(seg[1], seg[2:-2]) if len(seg) > 3 else None
                if text is not None:
                    out.append((_target(seg[-1], cwd), seg[-2] == ">>", text))
    return [w for w in out if w[0]]


def _result_text(content):
    if isinstance(content, list):
        return " ".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def _edits(path, file_index):
    """[(sort key, tool_use block, cwd)] for edit and Bash calls in one file that took
    effect: a failed edit changed nothing, a failed Bash call may still have written."""
    calls, failed = [], {}
    for n, d in enumerate(_entries(path)):
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        if d.get("type") == "user":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    failed[b.get("tool_use_id")] = _result_text(b.get("content"))
        elif d.get("type") == "assistant":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use" \
                        and b.get("name") in EDIT_TOOLS + ("Bash",) and isinstance(b.get("input"), dict):
                    calls.append(((d.get("timestamp") or "", file_index, n), b, d.get("cwd")))
    return [c for c in calls if c[1].get("id") not in failed
            or (c[1]["name"] == "Bash" and not _NOT_RUN.search(failed[c[1]["id"]]))]


def _left_out(target):
    norm = os.path.normpath(target)
    return norm.startswith(CLAUDE_HOME + os.sep) or norm.startswith("/dev/")


def work_from_session(path):
    """(prompt_text, pseudo_diff) for one main session file and its subagent files.

    prompt_text: the person's typed prompts in order, cut to MAX_PROMPT_CHARS.
    pseudo_diff: one --- / +++ block per file touched (in order of first touch),
    with -/+ lines from each edit's old and new text, cut to MAX_DIFF_CHARS.
    Files written by Bash in forms that can be read without running anything
    (see _bash_writes) are added as `@@ bash write @@` hunks; other Bash changes
    are not seen. Edits whose tool call failed (rejected, string not found) and
    writes to /dev or Claude Code's own folder (memory, plans) are left out."""
    entries = list(_entries(path))
    base = next((d["cwd"] for d in entries if d.get("cwd")), None)
    prompts = _prompts(entries)
    prompt_text = _fit([p + "\n\n" for p in prompts], MAX_PROMPT_CHARS).strip()

    sid = os.path.splitext(os.path.basename(path))[0]
    files = [path] + sorted(glob.glob(os.path.join(os.path.dirname(path), sid, "subagents", "*.jsonl")))
    calls, seen = [], set()
    for i, f in enumerate(files):
        for call in _edits(f, i):
            tid = call[1].get("id")
            if tid and tid in seen:
                continue
            seen.add(tid)
            calls.append(call)
    calls.sort(key=lambda c: c[0])

    blocks = {}  # header path -> lines, in order of first touch
    for _, b, cwd in calls:
        inp = b["input"]
        if b["name"] == "Bash":
            writes = [(t, ["@@ bash write%s @@" % (" (append)" if app else "")] + _lines("+", text))
                      for t, app, text in _bash_writes(inp.get("command") or "", cwd or base)]
        else:
            target = inp.get("file_path") or inp.get("notebook_path")
            writes = [(target, _hunks(b["name"], inp))] if target else []
        for target, hunk in writes:
            if _left_out(target):
                continue
            old, new = _show_path(target, base)
            blocks.setdefault(old, ["--- " + old, "+++ " + new]).extend(hunk)
    diff = _fit(["\n".join(lines) + "\n" for lines in blocks.values()], MAX_DIFF_CHARS)
    return prompt_text, diff


def cache_key(session_id, prompt, diff):
    """A session that continues after it was checked gets a new key, so a new verdict."""
    digest = hashlib.sha256((prompt + diff).encode("utf-8")).hexdigest()[:12]
    return "session:%s:%s" % (session_id, digest)


def check_sessions(session_paths, declared, cache, classify_fn=category.classify):
    """One row per main session file, like category.check_runs: its declared label
    ({session_id: label}; 'untagged' when absent), the model's pick and whether they
    differ. Subagent files are read with their session; sessions with no prompt and
    no edit are skipped."""
    rows = []
    for path in session_paths:
        if "/subagents/" in path.replace(os.sep, "/"):
            continue
        sid = os.path.splitext(os.path.basename(path))[0]
        prompt, diff = work_from_session(path)
        if not prompt and not diff:
            continue
        label = declared.get(sid, "untagged")
        v = category.classify_cached(cache_key(sid, prompt, diff), prompt, diff, cache, classify_fn)
        rows.append({"run_id": sid, "mode": "session", "declared": label,
                     "classified": v["category"], "reason": v["reason"],
                     "flagged": v["category"] != label,
                     "verdict": category.verdict(label, v["category"])})
    return rows
