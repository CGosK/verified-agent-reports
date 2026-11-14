"""Collect the paper's headline numbers from the result files into one place."""
import json, glob, os, sys
sys.path.insert(0, '/Users/operator/ClaudeWork/personal/verified-agent-reports')
os.chdir('/Users/operator/ClaudeWork/personal/verified-agent-reports')
from vawr import stats
R = 'work/results/'
L = lambda f: json.load(open(R + f))
out = {"sources": {}}
def put(key, value, source):
    out[key] = value; out["sources"][key] = source

ms = {}
for f in glob.glob('work/manifests/*.json'):
    m = json.load(open(f)); ms[m['run_id']] = m
conc = set(json.load(open('work/concurrency_run_ids.json')))
ab = set(json.load(open('work/env_ab_run_ids.json')))
bis = set(json.load(open('work/env_bisect_run_ids.json'))) if os.path.exists('work/env_bisect_run_ids.json') else set()
def batch(rid):
    if rid in conc: return 'concurrency'
    if rid in ab: return 'env_ab'
    if rid in bis: return 'env_bisect'
    return 'batch1' if rid < '20261114' else 'batch2'
counts = {}
for rid, m in ms.items():
    b = batch(rid); c = counts.setdefault(b, {"runs": 0, "key_runs": 0, "subscription_runs": 0, "off_log": 0, "tests_passed": 0, "cost_usd_est": 0.0})
    c["runs"] += 1; c["key_runs"] += m['mode'] == 'sprint'; c["subscription_runs"] += m['mode'] == 'subscription'
    c["off_log"] += bool(m.get('plant') in ('off_log', 'off_log_no_files')); c["tests_passed"] += m.get('test_exit') == 0
    c["cost_usd_est"] = round(c["cost_usd_est"] + (m.get('cost_estimate_usd') or 0), 4)
put("runs_by_batch", counts, "work/manifests/*.json (batch by run id lists in work/*_run_ids.json; batch1 = Nov 13)")

o = L('off_log.json')
off = [r for r in o['runs'] if r['plant']]; lg = [r for r in o['runs'] if not r['plant']]
put("provider_offlog_caught_batches_1_2", stats.rate(sum(r['provider_flag'] for r in off), len(off)), "off_log.json runs (sprint runs in window, concurrency excluded; plant set)")
put("provider_logged_flagged_batches_1_2_ab_bisect", stats.rate(sum(r['provider_flag'] for r in lg), len(lg)), "off_log.json runs with plant null (batches 1-2 and the A/B; bisection runs fall outside the window)")
wf = [r for r in off if r['plant'] == 'off_log']
put("session_file_offlog_caught", stats.rate(sum(r['session_flag'] for r in wf), len(wf)), "off_log.json runs with plant off_log (session files kept)")
put("offlog_gap_tokens_min_max", [min(r['gap_tokens'] for r in off), max(r['gap_tokens'] for r in off)], "off_log.json gap_tokens")
ff = L('false_flags.json'); p = ff['provider']; s = ff['sessions']
put("provider_window", p['window'], "false_flags.json provider.window")
put("provider_gaps_total", len(p['gaps']), "false_flags.json provider.gaps")
put("provider_log_excess", len(p['log_excess']), "false_flags.json provider.log_excess")
put("logged_sessions_in_window", p['logged_sessions'], "false_flags.json provider.logged_sessions")
off_sessions = {ms[r]['session_id'] for r in ms if ms[r].get('plant') == 'off_log'}
put("session_check_missing_from_log_requests", len(s['missing_from_log']), "false_flags.json sessions.missing_from_log (requests in session files not in the log; from off-log runs that kept files)")
put("session_check_missing_from_files", len(s['missing_from_files']), "false_flags.json sessions.missing_from_files")
put("session_check_token_mismatch", len(s['token_mismatch']), "false_flags.json sessions.token_mismatch")
bbs = p['background_by_session']; sess2run = {m['session_id']: m for m in ms.values() if m.get('session_id')}
inh = [sid for sid in bbs if sid in sess2run and sess2run[sid].get('env_mode', 'inherited') == 'inherited']
cln = [sid for sid in bbs if sid in sess2run and sess2run[sid].get('env_mode') == 'clean']
put("background_request_inherited_sessions", "%d/%d" % (sum(bbs[x]['cache_read'] >= 7010 for x in inh), len(inh)), "false_flags.json provider.background_by_session, env_mode from manifests")
put("background_request_clean_sessions", "%d/%d" % (sum(bbs[x]['cache_read'] >= 7010 for x in cln), len(cln)), "same")
shares = []
for sid in inh:
    bg = sum(bbs[sid].values()); lgt = sum(p['per_session'][sid]['logged_tokens'].values())
    if bbs[sid]['cache_read'] >= 7010: shares.append(bg / (bg + lgt))
put("background_share_of_session_billed_tokens_min_max", [round(min(shares), 3), round(max(shares), 3)], "background_by_session / (background + logged tokens of that session)")
c = L('concurrency.json')
put("concurrency_offlog_windows_flagged", c['off_log_windows_flagged'], "concurrency.json")
put("concurrency_clean_windows_flagged", c['clean_windows_flagged'], "concurrency.json (the one flag: 9 tokens claude-haiku-4-5 at 08:50 from interactive test startups on the same key)")
t = L('tamper_summary.json')['summary']
usage_caught = t['delete']['sessions_on_requests']['k'] + t['edit_tokens']['any']['k'] + t['rehash_tokens']['any']['k'] + t['truncate']['sessions_on_requests']['k']
usage_n = t['delete']['sessions_on_requests']['n'] + t['edit_tokens']['any']['n'] + t['rehash_tokens']['any']['n'] + t['truncate']['sessions_on_requests']['n']
put("tamper_usage_changing_caught", stats.rate(usage_caught, usage_n), "tamper_summary.json: delete touching requests + edit_tokens + rehash_tokens + truncations dropping requests")
put("tamper_relabel_rebuild_caught", t['rehash_category']['any'], "tamper_summary.json rehash_category any")
put("tamper_chain_on_unrebuilt_edits", stats.rate(t['delete']['chain']['k'] + t['edit_tokens']['chain']['k'] + t['edit_category']['chain']['k'], t['delete']['chain']['n'] + t['edit_tokens']['chain']['n'] + t['edit_category']['chain']['n']), "tamper_summary.json chain on delete/edit_tokens/edit_category")
put("tamper_trials_total", sum(v['trials'] for v in t.values()), "tamper_summary.json")
if os.path.exists(R + 'env_ab.json'):
    put("env_ab", L('env_ab.json')['by_env'], "env_ab.json")
for f, k in (('interactive_check.json', 'interactive_check'), ('interactive_billcheck.json', 'interactive_billcheck')):
    if os.path.exists(R + f):
        d = L(f)
        if k == 'interactive_billcheck':
            prov = sum(d['provider_tokens'].values()); tot = sum((d.get('recorded_totals_tokens') or {}).values())
            gap = sum(sum(g['tokens'].values()) for g in d['gaps'])
            put(k, {"billed": prov, "only_in_cost_totals": tot, "only_in_cost_totals_share": round(tot / prov, 3) if prov else None,
                    "unexplained": gap, "local_only_minutes": len(d['log_excess'])}, R + f)
        else:
            b = d['bill']
            put(k, {"chain_ok": d['chain']['ok'], "coverage_ok": d['coverage']['ok'], "local_requests": d['coverage']['local_requests'],
                    "logged_requests": d['coverage']['logged_requests_in_window'], "billed": sum(b['provider_tokens'].values()),
                    "gaps": len(b['gaps']), "log_excess_minutes": len(b['log_excess'])}, R + f)
json.dump(out, open(R + 'paper_numbers.json', 'w'), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k != 'sources'}, indent=1, default=str))

cl = L('claims_summary.json')
for k in ('false_done_caught', 'fake_blocker_caught', 'true_blocker_wrongly_flagged', 'fake_blocker_caught_held_out',
          'true_blocker_wrongly_flagged_held_out', 'negations_with_spurious_claims', 'real_runs_flagged'):
    put("claims_" + k, cl[k], "claims_summary.json " + k)
put("claims_real_runs_flagged_explained", "3 extraction errors on added_tests (descriptions of existing tests; 'I only ran the two provided tests'), 3 truthful reports of a denied shell command read as a blocker that exists", "claims_real.json detail, failed claims")
cc = L('category_check.json')['summary']; ho = L('category_heldout.json')['summary']
for name, s in (("category_dev", cc['dev']), ("category_held_out_runs", cc['held_out_runs']), ("category_cases_clear", ho['clear']), ("category_cases_borderline", ho['borderline'])):
    put(name, {k: s[k] for k in ('true_tags_flagged', 'true_tags_contradicted', 'relabels_caught', 'capabilities_to_safety_caught')} | {"n": s.get('runs', s.get('cases'))}, "category_check.json / category_heldout.json")
c2s = sum(s['capabilities_to_safety_caught']['k'] for s in (cc['dev'], cc['held_out_runs'], ho['all'])), sum(s['capabilities_to_safety_caught']['n'] for s in (cc['dev'], cc['held_out_runs'], ho['all']))
put("category_capabilities_to_safety_caught_all", "%d/%d" % c2s, "dev + held-out runs + written cases")
put("category_prompt", {"sha": cc['prompt_sha'], "model": cc['model']}, "category_check.json summary")
v = L('category_variance.json')
put("category_variance", {k: {kk: (vv['k'], vv['n']) if isinstance(vv, dict) and 'k' in vv else vv for kk, vv in v[k].items()} for k in ('runs', 'cases')}, "category_variance.json (54 runs and 36 cases, two extra calls each)")
json.dump(out, open(R + 'paper_numbers.json', 'w'), indent=1, default=str)
print('category/claims added')

eb = L('env_bisect.json')
put("env_bisect_rows", [{"env_mode": r["env_mode"], "unrecorded_cache_read": r["unrecorded_small_model"]["cache_read"]} for r in eb["rows"]], "env_bisect.json")
with_ep = [r for r in L('env_ab.json')['rows'] + eb['rows'] if ('ENTRYPOINT' in r['env_mode'] or r['env_mode'].startswith('inherited')) and 'all-but' not in r['env_mode']]
without_ep = [r for r in L('env_ab.json')['rows'] + eb['rows'] if r not in with_ep]
put("entrypoint_runs_with_request", "%d/%d (A/B + bisection) + 62/62 window sessions = %d/%d" % (sum(r['has_unrecorded_request'] for r in with_ep), len(with_ep), sum(r['has_unrecorded_request'] for r in with_ep) + 58, len(with_ep) + 58), "env_ab.json + env_bisect.json; the 62 window sessions include the 4 inherited A/B runs, so 58 are added")
put("no_entrypoint_runs_with_request", "%d/%d" % (sum(r['has_unrecorded_request'] for r in without_ep), len(without_ep)), "env_ab.json clean + env_bisect.json runs without CLAUDE_CODE_ENTRYPOINT")
json.dump(out, open(R + 'paper_numbers.json', 'w'), indent=1, default=str)
print(out["entrypoint_runs_with_request"], '|', out["no_entrypoint_runs_with_request"])
