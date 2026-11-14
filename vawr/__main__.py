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
                             model=item.get("model", "sonnet"))
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


def cmd_report(args):
    from . import report
    rep = report.build(args.log, claims_path=args.claims)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(rep, fh, indent=2)
    print(report.render(rep))


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
        scored = validate.score_off_log(audit)
        _save("off_log.json", dict(scored, audit=audit))
        for r in scored["runs"]:
            print("%-14s %-17s provider=%-5s sessions=%-5s gap=%s share=%s" % (
                r["task"], r["plant"] or "logged", r["provider_flag"], r["session_flag"], r["gap_tokens"],
                "%.0f%%" % (100 * r["share_of_window"]) if r["share_of_window"] is not None else "n/a"))
        print("unassigned gaps: %d; log excess: %d; background attributed: %s over %d logged sessions"
              % (len(scored["unassigned_gaps"]), len(scored["log_excess"]), scored["background_tokens"],
                 scored["logged_sessions"]))
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
    if args.what in ("claims", "all"):
        real = claims.check_all(out_path=_save("claims_real.json", {}))
        cases = validate.claim_injections()
        _save("claim_injections.json", cases)
        summary = validate.summarize_claims(cases, real["detail"])
        _save("claims_summary.json", summary)
        print("claims:", json.dumps(summary, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(prog="vawr")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the OTLP receiver that writes the chained log")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--port", type=int, default=4318)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("verify", help="recompute the hash chain")
    s.add_argument("--log", default=LOG_PATH)
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("run", help="run one task with claude -p and write its manifest")
    s.add_argument("--task", required=True)
    s.add_argument("--mode", choices=("subscription", "sprint"), default="subscription")
    s.add_argument("--plant", default=None,
                   choices=("off_log", "off_log_no_files", "prompt_overstate", "prompt_blocker"))
    s.add_argument("--model", default="sonnet")
    s.add_argument("--max-budget", type=float, default=1.0, help="per-run cap for sprint mode, USD")
    s.add_argument("--category", default=None, help="override the category tag (mislabel test)")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("batch", help="run one set from a run plan in order")
    s.add_argument("--plan", default="tasks/run_plan.json")
    s.add_argument("--set", choices=("sprint", "subscription"), required=True)
    s.add_argument("--skip", type=int, default=0, help="skip the first N runs (to resume)")
    s.set_defaults(func=cmd_batch)

    s = sub.add_parser("provider-cache", help="fetch the Sprint key's per-minute usage once for validation")
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.set_defaults(func=cmd_provider_cache)

    s = sub.add_parser("validate", help="planted-failure experiments")
    s.add_argument("what", choices=("tamper", "flags", "offlog", "claims", "category", "all"))
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("results", help="write work/results/summary.md from the experiment files")
    s.set_defaults(func=lambda a: print(__import__("vawr.results", fromlist=["write"]).write()[1]))

    s = sub.add_parser("report", help="allocation report from the chained log")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--claims", default=None, help="claims result JSON to fill the claims column")
    s.add_argument("--out", default=None, help="write the report JSON here")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("audit", help="run the auditor's four checks")
    s.add_argument("--log", default=LOG_PATH)
    s.add_argument("--report", default=None, help="published report JSON to check totals against")
    s.add_argument("--start", default=None, help="UTC ISO time; default 10 min before the first logged request")
    s.add_argument("--end", default=None, help="UTC ISO time; default 10 min ago")
    s.add_argument("--shift", type=int, default=2, help="minutes a logged request may sit from its provider minute")
    s.add_argument("--no-provider", action="store_true")
    s.add_argument("--out", default=None)
    s.set_defaults(func=cmd_audit)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
