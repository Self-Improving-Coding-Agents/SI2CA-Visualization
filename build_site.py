#!/usr/bin/env python3
"""Build site/data.json from paper_data/.

The page is organised as one view per (model, benchmark) pair, so the index is shaped that way
too: each pair carries its strategies side by side, the per-task rows behind them, and pointers
to the compressed per-turn records the page streams on demand. Every task row ends with a
bitmask of the record files that hold that task, so opening a task fetches only those files.

The Overview numbers are the ones printed in the paper (PAPER below); the task lists and the
trajectories come from the per-task and per-turn records.
"""
import json, gzip, glob, hashlib, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
PD = os.path.join(HERE, 'paper_data')
OUT = os.path.join(HERE, 'site', 'data.json')
CACHE = os.path.join(HERE, '.build_cache.json')

MODELS = [
    {'id': 'qwen35b',           'label': 'Qwen3.5-35B-A3B',   'family': 'Qwen',    'dir': 'qwen35b'},
    {'id': 'qwen122b',          'label': 'Qwen3.5-122B-A10B', 'family': 'Qwen',    'dir': 'qwen122b'},
    {'id': 'gpt56_terra_xhigh', 'label': 'GPT-5.6-Terra',     'family': 'GPT-5.6'},
    {'id': 'gpt56_luna_max',    'label': 'GPT-5.6-Luna',      'family': 'GPT-5.6'},
]
BENCH = {'swebench_verified': 'SWE-bench Verified', 'swebench_pro_731': 'SWE-bench Pro',
         'deepswe_v11': 'DeepSWE v1.1'}
SUBSETS = {'swebench_verified': ['swebench_verified'],
           'swebench_pro_731': ['swebench_pro_python', 'swebench_pro_nonpython']}
STRAT = {'standard': {'label': 'Standard', 'blurb': 'one sample per turn, no privileged information'},
         'self_judgement': {'label': 'Self-judgement',
                            'blurb': 'k=2 candidates, scored by the model itself against rubrics with the privileged information in view'},
         'self_likelihood': {'label': 'Self-likelihood',
                             'blurb': 'k=4 candidates, ranked by mean token log-likelihood under a context holding privileged information'}}

# (ACC, mean turns, median turns[, ACC standard deviation over runs]) as printed in the paper
PAPER = {
    'qwen35b': {
        'standard':        {'swebench_verified': (65.8, 85.0, 76), 'swebench_pro_731': (46.0, 89.4, 80)},
        'self_judgement':  {'swebench_verified': (70.0, 73.7, 67), 'swebench_pro_731': (53.2, 79.3, 72)},
        'self_likelihood': {'swebench_verified': (66.8, 76.9, 68), 'swebench_pro_731': (51.2, 77.5, 68)}},
    'qwen122b': {
        'standard':        {'swebench_verified': (67.0, 72.1, 64), 'swebench_pro_731': (48.0, 84.6, 80)},
        'self_judgement':  {'swebench_verified': (71.0, 68.8, 61), 'swebench_pro_731': (58.5, 80.2, 74)},
        'self_likelihood': {'swebench_verified': (69.8, 69.5, 62), 'swebench_pro_731': (53.8, 69.9, 64)}},
    'gpt56_terra_xhigh': {
        'standard':        {'deepswe_v11': (64.4, 59.3, 52, 2.0)},
        'self_judgement':  {'deepswe_v11': (67.5, 52.3, 46, 2.5)}},
    'gpt56_luna_max': {
        'standard':        {'deepswe_v11': (60.2, 246.8, 173)},
        'self_judgement':  {'deepswe_v11': (64.6, 223.0, 150)}},
}
SOURCE = {'Qwen': 'Table 1', 'GPT-5.6': 'Table 2'}
# pairs shown on the Overview but left out of the Trajectory tab
NO_TRAJECTORY = {('qwen122b', 'swebench_verified')}

rel = lambda p: os.path.relpath(p, HERE)
nid = lambda s: s[len('instance_'):] if s.startswith('instance_') else s


def rows(p):
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def paper(model, strategy, bench):
    acc, mean, median, *sd = PAPER[model][strategy][bench]
    return {'resolve': acc, 'resolve_sd': sd[0] if sd else None, 'turns': {'mean': mean, 'median': median}}


# ---- per-file index: record lines per task and decision counts, cached by size and mtime ----
ID = re.compile(r'"(?:instance_id|task)": ?"([^"]+)"')
# the Terra selection records name their task only through the session id, ds-<task>-<6 hex>
SESSION = re.compile(r'"session_id": ?"ds-([^"]+)-[0-9a-f]{6}"')
META = re.compile(r'"record": ?"meta"')
DECISION = re.compile(r'"decision": ?"([^"]*)"')
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


RC = re.compile(r'<returncode>(-?\d+)</returncode>')
DS_SESSION = re.compile(r'^ds-(.+)-[0-9a-f]{6}$')


def outcome(r):
    """One character for an executed turn: '.' exit code 0, 'x' non-zero exit or no valid command, '?' unknown."""
    m = RC.search(r.get('observation') or '')
    if m: return '.' if int(m.group(1)) == 0 else 'x'
    return 'x' if not r.get('command') else '?'


def scan(path):
    st = os.stat(path); sig = [st.st_size, int(st.st_mtime)]
    hit = cache.get(rel(path))
    if hit and hit['sig'] == sig and 'rc' in hit: return hit
    full = os.path.basename(path).startswith('trajectories')  # per-turn outcomes need every line parsed
    ids, dec, rc = collections.Counter(), collections.Counter(), {}
    with gzip.open(path, 'rt') as fh:
        for line in fh:
            head = line[:600]
            m = ID.search(head) or SESSION.search(head)
            if not full and m:
                if META.search(head): continue
                ids[nid(m.group(1))] += 1
                d = DECISION.search(head)
                if d: dec[d.group(1)] += 1
                continue
            r = json.loads(line)  # trajectory lines, and the rare record whose id sits deep in the line
            if r.get('record') == 'meta': continue
            task = r.get('instance_id') or r.get('task')
            if not task:
                m2 = DS_SESSION.match(r.get('session_id') or '')
                task = m2.group(1) if m2 else None
            if not task: continue
            task = nid(task)
            ids[task] += 1
            if r.get('decision'): dec[r['decision']] += 1
            if r.get('record') == 'turn':
                rc.setdefault(task, {})[r.get('step', 0)] = outcome(r)
            elif r.get('record') == 'message':
                seq = rc.setdefault(task, [])
                if r.get('role') == 'assistant': seq.append('?' if r.get('tool_calls') else '.')
                elif r.get('role') == 'tool' and seq:
                    m3 = RC.search(r.get('content') or '')
                    if m3 and int(m3.group(1)) != 0: seq[-1] = 'x'
                    elif m3 and seq[-1] == '?': seq[-1] = '.'
    rc = {t: ''.join(v[k] for k in sorted(v)) if isinstance(v, dict) else ''.join(v) for t, v in rc.items()}
    cache[rel(path)] = hit = {'sig': sig, 'ids': dict(ids), 'dec': dict(dec), 'rc': rc}
    print(f'  indexed {rel(path)}')
    return hit


def key_in(d, i):
    # the Terra session ids carry only the first 40 characters of a task name
    return i if i in d else (i[:40] if len(i) > 40 and i[:40] in d else None)


def index(files):
    """Per task: record lines, decision counts, the bitmask of files holding it, and its turn outcomes."""
    scans = [scan(f) for f in files]
    lines, dec, rc = collections.Counter(), collections.Counter(), {}
    for s in scans: lines.update(s['ids']); dec.update(s['dec']); rc.update(s.get('rc') or {})
    mask = lambda i: sum(1 << k for k, s in enumerate(scans) if key_in(s['ids'], i))
    rc_of = lambda i: rc.get(key_in(rc, i)) if key_in(rc, i) else None
    return lines, dec, mask, rc_of


def parts(d, stem, subsets):
    out = []
    for sb in subsets:
        out += sorted(glob.glob(f'{d}/{stem}_{sb}.jsonl.gz') + glob.glob(f'{d}/{stem}_{sb}.part*of*.jsonl.gz'))
    return out


def with_deltas(e, base):
    if base is None or e is base: return
    e['d_resolve'] = round(e['resolve'] - base['resolve'], 1)
    e['d_turns'] = {'mean': round(e['turns']['mean'] - base['turns']['mean'], 1),
                    'median': e['turns']['median'] - base['turns']['median']}


data = {'models': MODELS, 'benchmarks': BENCH, 'strategies': STRAT, 'pairs': {}, 'tasks': {}, 'instances': {}}
# per-task benchmark metadata written by paper_data/scripts/build_instances.py
for b, name in {'swebench_verified': 'swebench_verified', 'swebench_pro_731': 'swebench_pro',
                'deepswe_v11': 'deepswe_v11'}.items():
    if os.path.exists(f'{PD}/instances/{name}.jsonl.gz'):
        data['instances'][b] = rel(f'{PD}/instances/{name}.jsonl.gz')
# the prompt block the self-likelihood scorer saw, with the task's hint in place of the placeholder
if os.path.exists(f'{PD}/instances/hint_template.md'):
    data['hint_template'] = open(f'{PD}/instances/hint_template.md').read()

# ---- Qwen: three strategies on Verified and on all of Pro ----
for m in [x for x in MODELS if x['family'] == 'Qwen']:
    for b, subs in SUBSETS.items():
        key = f"{m['id']}|{b}"
        traj = (m['id'], b) not in NO_TRAJECTORY
        entry = {'model': m['label'], 'benchmark': BENCH[b], 'source': SOURCE[m['family']], 'trajectory': traj,
                 'strategies': []}
        base = None
        for s in ['standard', 'self_judgement', 'self_likelihood']:
            d = f"{PD}/table1_main_results/{m['dir']}_{s}"
            rs = [r for sb in subs for r in rows(f'{d}/{sb}.jsonl')]
            if not rs: continue
            files = parts(d, 'trajectories' if s == 'standard' else 'selection', subs) if traj else []
            kind = None if not files else 'turns' if s == 'standard' else 'nll' if s == 'self_likelihood' else 'judge'
            lines, dec, mask, rc_of = index(files)
            task_rows = []
            for r in rs:
                i = nid(r['instance_id'])
                # two archives stored harness segments or candidate draws; recount from the per-turn records
                t = r.get('turns') if r.get('turns_trusted') is not False else lines.get(i)
                task_rows.append([i, 1 if r['resolved'] else 0, t, r.get('language'), r.get('repo'), mask(i), rc_of(i)])
            e = {'id': s, 'label': STRAT[s]['label'], 'tasks': len(rs), **paper(m['id'], s, b),
                 'view': {'kind': kind, 'files': [rel(f) for f in files]} if files else None,
                 'results': [rel(f'{d}/{sb}.jsonl') for sb in subs if os.path.exists(f'{d}/{sb}.jsonl')]}
            if kind in ('nll', 'judge'):
                e['sel_stats'] = {'turns': sum(lines.values()), 'decisions': dict(dec.most_common())}
            if s == 'standard': base = e
            with_deltas(e, base)
            entry['strategies'].append(e)
            data['tasks'][f'{key}|{s}'] = task_rows
        data['pairs'][key] = entry

# ---- GPT-5.6 on DeepSWE ----
for m in [x for x in MODELS if x['family'] == 'GPT-5.6']:
    key = f"{m['id']}|deepswe_v11"
    entry = {'model': m['label'], 'benchmark': BENCH['deepswe_v11'], 'source': SOURCE[m['family']], 'strategies': []}
    base = None
    for s in ['standard', 'self_judgement']:
        runs = [(os.path.basename(rd), rd, rows(f'{rd}/results.jsonl'))
                for rd in sorted(glob.glob(f"{PD}/table2_deepswe/{m['id']}/{s}/run*"))]
        runs = [x for x in runs if x[2]]
        if not runs: continue
        _, first_dir, first_rows = runs[0]
        files = sorted(glob.glob(f"{first_dir}/{'trajectories' if s == 'standard' else 'selection'}*.jsonl.gz"))
        lines, dec, mask, rc_of = index(files)
        if s == 'self_judgement':  # turn outcomes come from the message-level trajectories of the same run
            rc_of = index(sorted(glob.glob(f'{first_dir}/trajectories*.jsonl.gz')))[3]
        e = {'id': s, 'label': STRAT[s]['label'], 'n_runs': len(runs), 'tasks': len(first_rows),
             **paper(m['id'], s, 'deepswe_v11'),
             'policy_effort': first_rows[0].get('reasoning_effort'),
             'judge_effort': first_rows[0].get('judge_effort'),
             'view': {'kind': 'messages' if s == 'standard' else 'judge', 'files': [rel(f) for f in files]} if files else None,
             'results': [rel(f'{first_dir}/results.jsonl')]}
        if s == 'self_judgement' and files:
            e['sel_stats'] = {'turns': sum(lines.values()), 'decisions': dict(dec.most_common())}
        if s == 'standard': base = e
        with_deltas(e, base)
        entry['strategies'].append(e)
        for n, (run, _, rs) in enumerate(runs):
            data['tasks'][f'{key}|{s}|{run}'] = [
                [r['task'], 1 if r['resolved'] else 0, r.get('turns'), r.get('language'), None,
                 mask(r['task']) if n == 0 else 0, rc_of(r['task']) if n == 0 else None] for r in rs]
    data['pairs'][key] = entry

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(data, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
json.dump(cache, open(CACHE, 'w'), separators=(',', ':'))
print(f'wrote {OUT}  {os.path.getsize(OUT)/1e6:.2f} MB')

# Stamp index.html with content hashes of the files it loads. A browser may keep app.js or data.json
# from an earlier visit; a new hash gives the file a new URL, so a new page never runs an old script.
SITE = os.path.join(HERE, 'site')
digest = lambda name: hashlib.sha1(open(os.path.join(SITE, name), 'rb').read()).hexdigest()[:10]
page = open(os.path.join(SITE, 'index.html')).read()
for name in ['style.css', 'app.js']:
    page = re.sub(rf'"{re.escape(name)}(\?v=[0-9a-f]*)?"', f'"{name}?v={digest(name)}"', page)
page = re.sub(r'<meta name="data-version" content="[^"]*">',
              f'<meta name="data-version" content="{digest("data.json")}">', page)
open(os.path.join(SITE, 'index.html'), 'w').write(page)
print(f'stamped site/index.html  style.css {digest("style.css")}  app.js {digest("app.js")}  data.json {digest("data.json")}')
for k, v in data['pairs'].items():
    print(f'  {k:30s} ' + '  '.join(
        f"{s['label']} {s['resolve']}% turns {s['turns']['mean']}/{s['turns']['median']} "
        f"records {sum(1 for r in next(t for kk, t in data['tasks'].items() if kk.startswith(k + '|' + s['id'])) if r[5])}"
        for s in v['strategies']))
