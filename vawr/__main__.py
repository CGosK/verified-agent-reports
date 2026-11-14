"""Command line: python3 -m vawr <command> ..."""

import argparse
import json
import sys

from . import chainlog
from .paths import LOG_PATH


def cmd_serve(args):
    from .receiver import serve
    serve(args.log, port=args.port)


def cmd_verify(args):
    ok, problems, count, head = chainlog.verify(args.log)
    print(json.dumps({"ok": ok, "entries": count, "head": head, "problems": problems[:20],
                      "problem_count": len(problems)}, indent=2))
    return 0 if ok else 1


def cmd_run(args):
    from .runner import run_task
    m = run_task(args.task, mode=args.mode, plant=args.plant, model=args.model,
                 max_budget_usd=args.max_budget, category_override=args.category)
    keep = ("run_id", "task", "category", "mode", "plant", "exit_code", "is_error", "num_turns",
            "cost_estimate_usd", "test_exit", "session_id", "duration_s")
    print(json.dumps({k: m.get(k) for k in keep}, indent=2))
    print("final message:", (m.get("final_message") or "")[:600])


def cmd_batch(args):
    import time
    from .runner import run_task
    with open(args.plan) as fh:
        plan = json.load(fh)[args.set]
    runs = plan["runs"][args.skip:]
    for i, r in enumerate(runs):
        if i and plan.get("gap_seconds"):
            time.sleep(plan["gap_seconds"])
        group = r.get("group") or [r]

        def one(item, delay):
            time.sleep(delay)  # stagger starts so worktree creation doesn't collide
            try:
                m = run_task(item["task"], mode=args.set, plant=item.get("plant"),
                             model=item.get("model", "sonnet"), env_mode=item.get("env", "inherited"))
                print("%s %s plant=%s exit=%s test=%s cost=%s turns=%s" % (
                    m["run_id"], m["task"], m["plant"], m["exit_code"], m["test_exit"],
                    m["cost_estimate_usd"], m["num_turns"]), flush=True)
            except Exception as exc:  # keep going; the manifest list shows what ran
                print("FAILED %s: %s" % (item, exc), flush=True)

        if len(group) == 1:
            one(group[0], 0)
        else:  # runs that overlap in time, for the concurrency test
            from concurrent.futures import ThreadPoolExecutor
            stagger = r.get("stagger_seconds", 5)
            with ThreadPoolExecutor(len(group)) as ex:
                list(ex.map(one, group, [i * stagger for i in range(len(group))]))


def cmd_verify_report(args):
    from . import check
    res = check.verify_report(args.log, args.report)
    if not res["head_found"]:
        print("FAIL  %s" % res["note"])
        return 1
    print("%s  report matches the log: head %s… is entry %d; chain %s up to it; %s" % (
        "PASS" if res["ok"] else "FAIL", res["head"][:16], res["entries_at_head"],
        "intact" if res["chain_ok_to_head"] else "BROKEN",
        "same tokens per category" if not res["differences"] else "differences: %s" % res["differences"]))
    print("Next: with an Admin key for the account, `vawr check --no-coverage --log %s --since <start> --until <end>` "
          "checks the log against Anthropic's records." % args.log)
    return 0 if res["ok"] else 1


def cmd_bundle(args):
    import os
    from datetime import datetime, timedelta, timezone
    from . import billcheck, bundle, paths
    now = datetime.now(timezone.utc)
    start = billcheck.parse_when(args.since, now)
    end = (billcheck.parse_when(args.until, now) if args.until
           else now - timedelta(minutes=billcheck.LAG_MINUTES)).replace(second=0, microsecond=0)
    admin, api_key = (None, None) if args.no_bill else billcheck.admin_and_key()
    out = args.out or "vawr-report-%s_%s.zip" % (start.strftime("%Y%m%dT%H%M"), end.strftime("%Y%m%dT%H%M"))
    try:
        m = bundle.make(out, args.log, start, end, only_projects=args.project, title=args.title,
                        admin_key=admin, key_id=args.key_id, api_key=api_key,
                        claude_projects=args.projects or paths.CLAUDE_PROJECTS,
                        previous="" if args.no_previous else None, allow_text=args.allow_text, note=args.note)
    except ValueError as exc:
        print("Not written: %s" % exc)
        return 1
    with __import__("zipfile").ZipFile(out) as z:
        res = json.loads(z.read("check.json")) if "check.json" in z.namelist() else None
    if res:
        print(__import__("vawr.check", fromlist=["render"]).render(res))
        print("")
    print("Wrote %s (%s)" % (out, "{:,} bytes".format(os.path.getsize(out))))
    print("Covers %s to %s UTC%s; log head %s…, %d entries%s." % (
        m["window"][0][:16].replace("T", " "), m["window"][1][:16].replace("T", " "),
        ", projects " + ", ".join(m["only_projects"]) if m["only_projects"] else "", m["log"]["head"][:16],
        m["log"]["entries"], "; continues from %s…" % m["previous_head"][:16] if m["previous_head"] else ""))
    others = [x for x in m["log_contents"] if m["only_projects"] and x["project"] not in m["only_projects"]]
    print("The recipient gets the whole log (the chain can only be checked whole): token counts, models, times, "
          "session IDs, tool names, project tags and categories; prompts and responses are not in it.")
    if others:
        print("It also holds these other projects' sessions, which the report leaves out: %s." % ", ".join(
            "%s (%d)" % (x["project"], x["sessions"]) for x in others))
    if not m.get("key_id"):
        print("No API key ID recorded (no Admin key here): tell the recipient which key, or pass --key-id.")
    print("The recipient runs: vawr receive %s" % os.path.basename(out))
    return 0


def cmd_receive(args):
    from . import billcheck, bundle
    admin, _ = (None, None) if args.no_bill else billcheck.admin_and_key()
    try:
        out = bundle.receive(args.bundle, admin_key=admin, key_id=args.key_id, record=not args.no_record)
    except Exception as exc:  # an untrusted file: any failure to read it is a FAILED, not a traceback
        print("FAILED  can't check %s: %s" % (bundle.clean(args.bundle), bundle.clean(exc, 400)))
        return 1
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({k: v for k, v in out.items() if k not in ("files",)}, fh, indent=1, default=str)
    if args.html:
        with open(args.html, "w") as fh:
            fh.write(bundle.receive_html(out))
    print(bundle.render_receive(out))
    if args.html:
        print("Page built here from the log and your checks: %s" % args.html)
    return 0 if out["verdict"] != "failed" else 1


def cmd_team(args):
    from datetime import datetime, timezone
    from . import billcheck, team
    admin, _ = billcheck.admin_and_key()
    if not admin:
        print("vawr team needs the organization's Admin key in ANTHROPIC_ADMIN_KEY")
        return 1
    now = datetime.now(timezone.utc)
    start = billcheck.parse_when(args.since, now) if args.since else None
    end = billcheck.parse_when(args.until, now) if args.until else None
    try:
        res = team.run(args.bundles, admin, start=start, end=end, record=not args.no_record)
    except Exception as exc:
        print("FAILED  %s" % exc)
        return 1
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=1, default=str)
    print(team.render(res))
    return 0 if all(r["status"] == "pass" for r in res["keys"]) and not res["unreadable"] else 1


def cmd_check(args):
    from datetime import datetime, timedelta, timezone
    from . import billcheck, check, paths
    now = datetime.now(timezone.utc)
    start = billcheck.parse_when(args.since or "24h", now).replace(second=0, microsecond=0)
    end = (billcheck.parse_when(args.until, now) if args.until
           else now - timedelta(minutes=billcheck.LAG_MINUTES)).replace(second=0, microsecond=0)
    admin, api_key = (None, None) if args.no_bill else billcheck.admin_and_key()
    res = check.run(start, end, args.log, args.projects or paths.CLAUDE_PROJECTS,
                    admin_key=admin, key_id=args.key_id, api_key=api_key, match=args.match,
                    coverage=not args.no_coverage, source=args.source, only_projects=args.project)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=1, default=str)
    print(check.render(res))
    return 0 if res["level"] != "failed" else 1


def cmd_categories(args):
    import glob
    import os
    from datetime import datetime, timezone
    from . import billcheck, category, paths, session_category
    from .logdata import api_requests
    now = datetime.now(timezone.utc)
    start = billcheck.parse_when(args.since or "7d", now)
    projects = args.projects or paths.CLAUDE_PROJECTS
    labels = {}
    for r in api_requests(args.log):
        if r.get("session_id"):
            labels.setdefault(r["session_id"], set()).add(r["category"])
    declared = {sid: (next(iter(c)) if len(c) == 1 else "mixed") for sid, c in labels.items()}
    files = []
    for path in glob.glob(os.path.join(projects, "*", "*.jsonl")):
        if datetime.fromtimestamp(os.path.getmtime(path), timezone.utc) < start:
            continue
        if args.match and not any(m in path for m in args.match):
            continue
        sid = os.path.basename(path)[:-len(".jsonl")]
        if sid in declared or args.all:
            files.append(path)
    if args.votes > 1:
        cache_path = os.path.join(paths.WORK, "category_sessions", "verdicts_votes%d.json" % args.votes)
        classify_fn = lambda p, d: category.classify_votes(p, d, n=args.votes)  # noqa: E731
    else:
        cache_path = os.path.join(paths.WORK, "category_sessions", "verdicts.json")
        classify_fn = category.classify
    cache = category._load_cache(cache_path)
    rows = session_category.check_sessions(sorted(files), declared, cache, classify_fn=classify_fn)
    category.save_cache(cache, cache_path)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(rows, fh, indent=1)
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("confirmed", "unconfirmed", "contradicted")}
    print("Category check on %d sessions since %s: %d confirmed, %d unconfirmed, %d contradicted"
          % (len(rows), start.isoformat()[:16], counts["confirmed"], counts["unconfirmed"], counts["contradicted"]))
    for r in rows:
        if r["verdict"] != "confirmed":
            print("  %-12s session %s… tagged %s, reads as %s: %s" % (
                r["verdict"], r["run_id"][:8], r["declared"], r["classified"], r["reason"][:140]))
    print("unconfirmed: the work doesn't show a safety or capabilities purpose (often generic code); "
          "contradicted: it shows a different one. A separate model reads each session's prompts and edits; "
          "it runs through `claude -p`, so it uses your Claude Code sign-in.")


def cmd_billcheck(args):
    from datetime import datetime, timedelta, timezone
    from . import billcheck
    now = datetime.now(timezone.utc)
    start = billcheck.parse_when(args.since or "24h", now)
    end = billcheck.parse_when(args.until, now) if args.until else now - timedelta(minutes=billcheck.LAG_MINUTES)
    admin, api_key = billcheck.admin_and_key()
    res = billcheck.check(start.replace(second=0, microsecond=0), end.replace(second=0, microsecond=0),
                          admin_key=admin, key_id=args.key_id, api_key=api_key, source=args.source,
                          **({"projects": args.projects} if args.projects else {}))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(res, fh, indent=1, default=str)
    print(billcheck.render(res))


def cmd_setup(args):
    import os
    from . import configure
    path = configure.project_settings_path(os.getcwd()) if args.project else configure.user_settings_path()
    changes, _ = configure.merge_env(path, configure.otel_env(args.port), write=args.write)
    print(configure.describe(path, changes, args.write))
    if args.write:
        print("New Claude Code sessions will send their events to the receiver. Start it with `vawr start`.")


def cmd_tag(args):
    import os
    from . import configure
    project = args.project or os.path.basename(os.getcwd())
    path = configure.project_settings_path(os.getcwd())
    changes, _ = configure.merge_env(path, configure.tag_env(args.category, project), write=args.write)
    print(configure.describe(path, changes, args.write))


def cmd_session_start(args):
    from . import configure
    out = configure.session_start(args.port)
    if out:
        print(json.dumps(out))


def cmd_start(args):
    from . import configure
    print(configure.start(args.port))


def cmd_stop(args):
    from . import configure
    print(configure.stop())


def cmd_status(args):
    import os
    from . import chainlog
    from .runner import receiver_up
    print("receiver: %s on port %d" % ("running" if receiver_up(args.port) else "not running", args.port))
    if os.path.exists(args.log):
        ok, problems, n, head = chainlog.verify(args.log)
        print("log: %s, %d entries, chain %s" % (args.log, n, "intact" if ok else "BROKEN (%s)" % problems[:3]))
        print("head: %s" % head)
    else:
        print("log: none yet at %s" % args.log)


def cmd_report(args):
    from datetime import datetime, timezone
    from . import billcheck, report
    now = datetime.now(timezone.utc)
    start = billcheck.parse_when(args.since, now) if args.since else None
    end = billcheck.parse_when(args.until, now) if args.until else None
    rep = report.build(args.log, claims_path=args.claims, start=start, end=end, only_projects=args.project)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(rep, fh, indent=2)
    print(report.render(rep))
    if args.html:
        from . import html_report

        def load(path):
            if not path:
                return None
            with open(path) as fh:
                d = json.load(fh)
            return {"rows": d} if isinstance(d, list) else d  # `vawr categories --json` writes a list

        page = html_report.render(rep, check=load(args.check), billcheck=load(args.billcheck),
                                  categories=load(args.categories), claims=load(args.claims_summary),
                                  title=args.title)
        with open(args.html, "w") as fh:
            fh.write(page)
        print("HTML report: %s" % args.html)


def cmd_audit(args):
    import os
    from datetime import datetime, timezone
    from . import auditor, paths
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
    res = auditor.audit(start=parse(args.start), end=parse(args.end), log_path=args.log,
                        report_path=args.report, shift=args.shift, provider=not args.no_provider)
    os.makedirs(os.path.join(paths.WORK, "audits"), exist_ok=True)
    out = args.out or os.path.join(paths.WORK, "audits",
                                   datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    with open(out, "w") as fh:
        json.dump(res, fh, indent=2, default=str)
    print(auditor.summarize(res))
    print("full result:", out)
    return 0 if res["ok"] else 1


def _results_dir():
    import os
    from . import paths
    d = os.path.join(paths.WORK, "results")
    os.makedirs(d, exist_ok=True)
    return d


def _save(name, obj):
    import os
    path = os.path.join(_results_dir(), name)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)
    return path


def cmd_provider_cache(args):
    from datetime import datetime
    from . import validate
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    window, minutes = validate.cache_provider(parse(args.start), parse(args.end))
    print("cached %d provider minutes with usage for %s to %s" % (len(minutes), window[0], window[1]))


def cmd_validate(args):
    from . import auditor, claims, validate
    if args.what in ("tamper", "all"):
        res = validate.tamper_trials()
        summary = validate.summarize_tamper(res)
        _save("tamper_trials.json", res)
        print("tamper:", json.dumps({"baseline_flags": res["baseline_flags"], "summary": summary}, indent=2))
        _save("tamper_summary.json", {"baseline_flags": res["baseline_flags"], "summary": summary})
    if args.what in ("flags", "all"):
        ff = validate.false_flags()
        _save("false_flags.json", ff)
        p = ff["provider"]
        print("clean log: sessions ok=%s; provider ok=%s, %d minutes checked, %d clean, gaps=%d, excess=%d"
              % (ff["sessions"]["ok"], p["ok"], p["minutes_checked"], p["clean_minutes"],
                 len(p["gaps"]), len(p["log_excess"])))
    if args.what in ("offlog", "all"):
        window, provider = validate.load_provider()
        reqs = auditor.api_requests(auditor.paths.LOG_PATH)
        audit = {"provider": auditor.check_provider(reqs, window[0], window[1], provider_minutes=provider),
                 "sessions": auditor.check_sessions(reqs, window[0], window[1])}
        import os
        conc_ids_path = os.path.join(validate.paths.WORK, "concurrency_run_ids.json")
        conc_ids = json.load(open(conc_ids_path)) if os.path.exists(conc_ids_path) else []
        scored = validate.score_off_log(audit, exclude_ids=set(conc_ids))
        _save("off_log.json", dict(scored, audit=audit))
        for r in scored["runs"]:
            print("%-14s %-17s provider=%-5s sessions=%-5s gap=%s share=%s" % (
                r["task"], r["plant"] or "logged", r["provider_flag"], r["session_flag"], r["gap_tokens"],
                "%.0f%%" % (100 * r["share_of_window"]) if r["share_of_window"] is not None else "n/a"))
        print("unassigned gaps: %d; log excess: %d; background attributed: %s over %d logged sessions"
              % (len(scored["unassigned_gaps"]), len(scored["log_excess"]), scored["background_tokens"],
                 scored["logged_sessions"]))
    if args.what in ("concurrency", "all"):
        import os
        conc_ids_path = os.path.join(validate.paths.WORK, "concurrency_run_ids.json")
        if os.path.exists(conc_ids_path):
            window, provider = validate.load_provider()
            reqs = auditor.api_requests(auditor.paths.LOG_PATH)
            audit = {"provider": auditor.check_provider(reqs, window[0], window[1], provider_minutes=provider)}
            conc = validate.score_windows(audit, json.load(open(conc_ids_path)))
            _save("concurrency.json", conc)
            print("concurrency: off-log windows flagged %s; clean windows flagged %s" % (
                conc["off_log_windows_flagged"], conc["clean_windows_flagged"]))
    if args.what in ("category", "all"):
        import os
        hist = os.path.join(validate.paths.WORK, "category_dev", "history.json")
        dev_ids = json.load(open(hist)).get("dev_run_ids") if os.path.exists(hist) else []
        res = validate.category_check(dev_ids=dev_ids)
        _save("category_check.json", res)
        print("category:", json.dumps(res["summary"], indent=2))
        cases = os.path.join(validate.paths.WORK, "category_heldout", "cases.json")
        if os.path.exists(cases):
            ho = validate.category_heldout(cases)
            _save("category_heldout.json", ho)
            print("category held-out:", json.dumps(ho["summary"], indent=2))
    if args.what in ("continuity", "all"):
        import os
        prefix = os.path.join(validate.paths.WORK, "log", "events_upto_20261114T0917Z.jsonl")
        r = validate.continuity_trials(prefix if os.path.exists(prefix) else validate.paths.LOG_PATH)
        _save("continuity_trials.json", r)
        print("continuity: edits before the earlier head caught %s; after it %s" % (
            r["caught_before_earlier_head"], r["caught_after_earlier_head"]))
    if args.what == "cc-analytics":  # needs the Admin key; not part of "all"
        from . import billcheck
        admin, _ = billcheck.admin_and_key()
        window, _ = validate.load_provider()
        key = json.load(open(validate.PROVIDER_CACHE))["key_id"]
        r = validate.cc_analytics(admin, key)
        _save("cc_analytics.json", r)
        for d, v in r["days"].items():
            c = v["comparison"]
            print(d, "Anthropic sessions", v["anthropic_sessions_by_terminal"], "| log", c["log_sessions"],
                  "| runs in manifests", v["sprint_key_runs_in_manifests"], "of which hidden",
                  v["hidden_runs_in_manifests"], "| billed minus Anthropic", v["billed_minus_anthropic"])
            for cell in c["by_terminal"]:
                print("   ", cell["terminal"], cell["status"], cell["anthropic_sessions"], cell["log_sessions"],
                      cell["token_difference"])
    if args.what in ("claims", "all"):
        real = claims.check_all(out_path=_save("claims_real.json", {}))
        cases = validate.claim_injections()
        _save("claim_injections.json", cases)
        summary = validate.summarize_claims(cases, real["detail"])
        _save("claims_summary.json", summary)
        print("claims:", json.dumps(summary, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="vawr",
        description="Checkable usage reports for Claude Code: see what Anthropic billed your API key "
                    "that Claude Code didn't record, keep a tamper-evident log of agent work, and "
                    "share a report by category with checks anyone can rerun.",
        epilog="Start here: `vawr billcheck --since 7d` (needs ANTHROPIC_ADMIN_KEY and ANTHROPIC_API_KEY). "
               "Then `vawr setup --write`, `vawr start`, work as usual, and `vawr check`.")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    s = sub.add_parser("verify-report", help="for whoever receives a report: does it match the published log")
    s.add_argument("report", help="the report JSON (`vawr report --out`)")
    s.add_argument("--log", default=LOG_PATH, help="the published log")
    s.set_defaults(func=cmd_verify_report)

    s = sub.add_parser("bundle", help="write one file to send whoever pays for the API key: report, checks and log")
    s.add_argument("--since", required=True, help="start: 30d, or a UTC ISO time such as 2026-11-01")
    s.add_argument("--until", default=None, help="end (default: now minus the usage records' lag)")
    s.add_argument("--project", action="append", default=None,
                   help="only this project tag's work (repeatable), e.g. one grant or client")
    s.add_argument("--key-id", default=None, help="the API key the work ran on (default: the key in ANTHROPIC_API_KEY)")
    s.add_argument("--title", default=None)
    s.add_argument("--note", default=None, help="a line for the recipient")
    s.add_argument("--out", default=None, help="file to write (default: vawr-report-<start>_<end>.zip)")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--projects", default=None, help="Claude Code's projects folder, for the coverage check")
    s.add_argument("--no-bill", action="store_true", help="don't check against Anthropic's records first")
    s.add_argument("--no-previous", action="store_true", help="don't link this report to the last one sent")
    s.add_argument("--allow-text", action="store_true", help="share the log even if it holds prompt or response text")
    s.set_defaults(func=cmd_bundle)

    s = sub.add_parser("receive", help="for whoever receives a bundle: check it, with your own Admin key if you own the API key")
    s.add_argument("bundle", help="the .zip from `vawr bundle`")
    s.add_argument("--key-id", default=None, help="the API key you issued (default: the one the bundle names)")
    s.add_argument("--html", default=None, help="also write a report page built from the log and your checks")
    s.add_argument("--json", default=None)
    s.add_argument("--no-bill", action="store_true", help="don't check against Anthropic's records")
    s.add_argument("--no-record", action="store_true", help="don't add this report's head hash to your ledger")
    s.set_defaults(func=cmd_receive)

    s = sub.add_parser("team", help="for an organization admin: everyone's bundles against the organization's records, key by key")
    s.add_argument("bundles", nargs="+", help="bundles from `vawr bundle`, one or more per person")
    s.add_argument("--since", default=None, help="start (default: the earliest bundle's)")
    s.add_argument("--until", default=None, help="end (default: the latest bundle's)")
    s.add_argument("--json", default=None)
    s.add_argument("--no-record", action="store_true", help="don't add the bundles' head hashes to your ledger")
    s.set_defaults(func=cmd_team)

    s = sub.add_parser("billcheck", help="what Anthropic billed an API key vs what this machine's Claude Code session files record")
    s.add_argument("--since", default="24h", help="how far back: 90m, 24h, 7d, or a UTC ISO time (default 24h)")
    s.add_argument("--until", default=None, help="end time (default: now minus the usage records' lag)")
    s.add_argument("--key-id", default=None, help="API key ID to check (default: the key in ANTHROPIC_API_KEY)")
    s.add_argument("--json", default=None, help="also write the full result here")
    s.add_argument("--source", choices=("auto", "legacy", "analytics"), default="auto",
                   help="Anthropic usage records to read: the Usage and Cost API (legacy, ~5 min behind) or the "
                        "Analytics API (beta, 4-24 h behind); auto uses legacy and falls back if it's retired")
    s.add_argument("--projects", default=None, help="Claude Code's projects folder (default: ~/.claude/projects, or under CLAUDE_CONFIG_DIR)")
    s.set_defaults(func=cmd_billcheck)

    s = sub.add_parser("setup", help="point Claude Code's telemetry at the local receiver (shows the change; --write applies it)")
    s.add_argument("--project", action="store_true", help="this project's .claude/settings.local.json instead of your user settings")
    s.add_argument("--port", type=int, default=4318)
    s.add_argument("--write", action="store_true")
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("tag", help="tag this project's Claude Code sessions with a category")
    s.add_argument("category", choices=("safety", "capabilities", "other"))
    s.add_argument("--project", default=None, help="project name to record (default: this folder's name)")
    s.add_argument("--write", action="store_true")
    s.set_defaults(func=cmd_tag)

    s = sub.add_parser("start", help="run the receiver in the background")
    s.add_argument("--port", type=int, default=4318)
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("session-start", help="[plugin hook] start the receiver if telemetry is set up, else say how")
    s.add_argument("--port", type=int, default=4318)
    s.set_defaults(func=cmd_session_start)

    s = sub.add_parser("stop", help="stop the background receiver")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("status", help="is the receiver up, and is the log's chain intact")
    s.add_argument("--port", type=int, default=4318)
    s.add_argument("--log", default=LOG_PATH)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("check", help="audit the log: chain intact, every local session logged, bill accounted for")
    s.add_argument("--since", default="24h")
    s.add_argument("--until", default=None)
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--projects", default=None)
    s.add_argument("--key-id", default=None)
    s.add_argument("--no-bill", action="store_true", help="skip the check against Anthropic's records")
    s.add_argument("--source", choices=("auto", "legacy", "analytics"), default="auto",
                   help="Anthropic usage records to read: the Usage and Cost API (legacy, ~5 min behind) or the "
                        "Analytics API (beta, 4-24 h behind); auto uses legacy and falls back if it's retired")
    s.add_argument("--no-coverage", action="store_true",
                   help="skip the session-file check, e.g. when checking someone else's log on your machine")
    s.add_argument("--match", action="append", default=None,
                   help="only session folders whose name contains this (repeatable), e.g. a repo name")
    s.add_argument("--project", action="append", default=None,
                   help="only requests tagged with this project (repeatable; see `vawr tag`)")
    s.add_argument("--json", default=None)
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("categories", help="does each logged session's work match its category tag (a separate model reads its prompts and edits)")
    s.add_argument("--since", default="7d")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--projects", default=None)
    s.add_argument("--match", action="append", default=None, help="only session folders whose path contains this")
    s.add_argument("--all", action="store_true", help="include sessions that aren't in the log (they count as untagged)")
    s.add_argument("--votes", type=int, default=1, help="majority of this many model calls per session (3 steadies generic code)")
    s.add_argument("--json", default=None)
    s.set_defaults(func=cmd_categories)

    s = sub.add_parser("report", help="allocation report from the chained log")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--claims", default=None, help="claims result JSON to fill the claims column")
    s.add_argument("--out", default=None, help="write the report JSON here")
    s.add_argument("--since", default=None, help="only requests from this time: 30d, or a UTC ISO time")
    s.add_argument("--until", default=None, help="only requests before this time")
    s.add_argument("--html", default=None, help="also write a self-contained HTML report to share")
    s.add_argument("--check", default=None, help="for --html: a `vawr check --json` result")
    s.add_argument("--billcheck", default=None, help="for --html: a `vawr billcheck --json` result")
    s.add_argument("--categories", default=None, help="for --html: a `vawr categories --json` result")
    s.add_argument("--claims-summary", default=None, help="for --html: a claims summary JSON")
    s.add_argument("--title", default=None, help="for --html: the report's title")
    s.add_argument("--project", action="append", default=None,
                   help="only requests tagged with this project (repeatable; see `vawr tag`)")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("serve", help="run the OTLP receiver that writes the chained log")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--port", type=int, default=4318)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("verify", help="recompute the hash chain")
    s.add_argument("--log", default=LOG_PATH)
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("audit", help="[research] run the auditor's four checks")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--report", default=None, help="published report JSON to check totals against")
    s.add_argument("--start", default=None, help="UTC ISO time; default 10 min before the first logged request")
    s.add_argument("--end", default=None, help="UTC ISO time; default 10 min ago")
    s.add_argument("--shift", type=int, default=2, help="minutes a logged request may sit from its provider minute")
    s.add_argument("--no-provider", action="store_true")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_audit)

    s = sub.add_parser("run", help="[research] run one task with claude -p and write its manifest")
    s.add_argument("--task", required=True)
    s.add_argument("--mode", choices=("subscription", "sprint"), default="subscription")
    s.add_argument("--plant", default=None,
                   choices=("off_log", "off_log_no_files", "prompt_overstate", "prompt_blocker"))
    s.add_argument("--model", default="sonnet")
    s.add_argument("--max-budget", type=float, default=1.0, help="per-run cap for sprint mode, USD")
    s.add_argument("--category", default=None, help="override the category tag (mislabel test)")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("batch", help="[research] run one set from a run plan in order")
    s.add_argument("--plan", default="tasks/run_plan.json")
    s.add_argument("--set", choices=("sprint", "subscription"), required=True)
    s.add_argument("--skip", type=int, default=0, help="skip the first N runs (to resume)")
    s.set_defaults(func=cmd_batch)

    s = sub.add_parser("provider-cache", help="[research] fetch the Sprint key's per-minute usage once for validation")
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.set_defaults(func=cmd_provider_cache)

    s = sub.add_parser("validate", help="[research] planted-failure experiments")
    s.add_argument("what", choices=("tamper", "flags", "offlog", "claims", "category", "concurrency",
                                    "continuity", "cc-analytics", "all"))
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("results", help="[research] write work/results/summary.md from the experiment files")
    s.set_defaults(func=lambda a: print(__import__("vawr.results", fromlist=["write"]).write()[1]))

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
