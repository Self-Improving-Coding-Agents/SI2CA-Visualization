#!/usr/bin/env python3
"""Rebuild the per-turn record files recovered from the fleet machines on 2026-09-11.

Input: the per-machine pulls made by pull_node_trajectories.sh, one gzip JSON-lines file per machine
and job (A_n1.jsonl.gz, B_n3.jsonl.gz, C_local.jsonl.gz, ...), holding the records that
extract_node_trajectories.py printed: a `meta` line per task file and, depending on the job, one
`sel` line per branched turn or one `turn` line per executed turn. Records carry a `tag` naming
the arm they belong to.

For every task the machine copy whose outcome and turn count match the per-task record in
paper_data/table1_main_results/ is kept; where several machines hold such a copy, the earliest
machine in ORDER wins. Records are keyed by (pull file, path): the same path exists on several
machines, so the path alone does not identify a copy.

    python3 merge_node_records.py /path/to/pull   # writes into paper_data/table1_main_results/
"""
import collections, glob, gzip, json, os, statistics, sys, zlib

PULL = sys.argv[1] if len(sys.argv) > 1 else 'pull'
T1 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'table1_main_results')
ORDER = {n: i for i, n in enumerate(['n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7', 'n8', 's2', 'sc', 'local'])}
LIMIT = 20_000_000  # compressed bytes per output part
nid = lambda s: s[len('instance_'):] if s.startswith('instance_') else s


def results(arm, benches):
    R = {}
    for b in benches:
        for l in open(f'{T1}/{arm}/{b}.jsonl'):
            r = json.loads(l); R[nid(r['instance_id'])] = r
    return R


def read_pull(pattern, tag):
    """metas by task, and records by (pull file, path)."""
    metas, recs = collections.defaultdict(list), collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(PULL, pattern))):
        src = os.path.basename(f)
        for l in gzip.open(f, 'rt'):
            r = json.loads(l)
            if r.get('tag') != tag: continue
            if r['_kind'] == 'meta': r['_src'] = src; metas[r['instance_id']].append(r)
            elif r['_kind'] in ('sel', 'turn'): recs[(src, r['_path'])].append(r)
    return metas, recs


def choose(metas, R):
    out = {}
    for iid, ms in metas.items():
        r = R[iid]
        ok = [m for m in ms if ((m['reward'] or 0) >= 0.999) == r['resolved'] and m['n_turns'] == r.get('turns')]
        assert ok, iid
        out[iid] = sorted(ok, key=lambda m: (ORDER[m['node']], m['path']))[0]
    assert set(out) == set(R), (len(out), len(R))
    return out


def write_parts(d, stem, groups):
    """groups: sorted (task, [json lines]); split into parts under LIMIT compressed bytes each."""
    for old in glob.glob(f'{d}/{stem}.jsonl.gz') + glob.glob(f'{d}/{stem}.part*.jsonl.gz'): os.remove(old)
    sizes = [len(zlib.compress(''.join(ls).encode(), 6)) for _, ls in groups]
    parts, acc = [[]], 0
    for g, s in zip(groups, sizes):
        if parts[-1] and acc + s > LIMIT: parts.append([]); acc = 0
        parts[-1].append(g); acc += s
    for i, p in enumerate(parts):
        name = f'{stem}.jsonl.gz' if len(parts) == 1 else f'{stem}.part{i + 1}of{len(parts)}.jsonl.gz'
        with gzip.open(f'{d}/{name}', 'wt', compresslevel=6) as fh:
            for _, ls in p: fh.writelines(ls)
        print(f'   {os.path.basename(d)}/{name}: {sum(len(ls) for _, ls in p)} records, {len(p)} tasks, '
              f'{os.path.getsize(f"{d}/{name}") / 1e6:.1f} MB')


SEL_KEYS = ['instance_id', 'benchmark', 'model', 'strategy', 'step', 'k', 'decision', 'chosen_idx', 'winner_idx',
            'mean_nll_plain', 'mean_nll_privileged', 'judge_calls', 'candidates']
sel_line = lambda r: json.dumps({k: r[k] for k in SEL_KEYS}, ensure_ascii=False) + '\n'


def sel_groups(chosen, recs):
    return [(i, [sel_line(r) for r in sorted(recs[(chosen[i]['_src'], chosen[i]['path'])], key=lambda x: x['step'])])
            for i in sorted(chosen)]


def traj_groups(chosen, recs, bench):
    out = []
    for i in sorted(chosen):
        m = chosen[i]
        ls = [json.dumps({'record': 'meta', 'instance_id': i, 'benchmark': bench(m), 'reward': m['reward'], 'turns': m['n_turns'],
                          'problem_statement': m.get('problem_statement'), 'source': f"{m['node']}:{m['path']}"}, ensure_ascii=False) + '\n']
        T = recs[(m['_src'], m['path'])]
        steps = [t['step'] for t in T]
        assert len(steps) == len(set(steps)) == m['n_turns'], (i, len(steps), len(set(steps)), m['n_turns'])
        for t in sorted(T, key=lambda x: x['step']):
            ls.append(json.dumps({'record': 'turn', 'instance_id': i, 'step': t['step'], 'reasoning': t['reasoning'], 'content': t['content'],
                                  'command': t['command'], 'observation': t['observation'], 'finish_reason': t['finish_reason']},
                                 ensure_ascii=False) + '\n')
        out.append((i, ls))
    return out


# ---- 1. 122B self-judgement, Pro non-Python: the existing file keeps its 122B records, and the tasks
# pulled from the machines replace whatever it held for them
print('== 122B self-judgement non-Python')
d = f'{T1}/qwen122b_self_judgement'
R = results('qwen122b_self_judgement', ['swebench_pro_nonpython'])
metas, recs = read_pull('A_n*.jsonl.gz', '122b_sj_nonpy')
chosen = {}
for iid, ms in metas.items():
    r = R[iid]
    ok = [m for m in ms if ((m['reward'] or 0) >= 0.999) == r['resolved'] and m['n_turns'] == r['turns']]
    chosen[iid] = sorted(ok, key=lambda m: (ORDER[m['node']], m['path']))[0]
by = collections.defaultdict(list)
for f in sorted(glob.glob(f'{d}/selection_swebench_pro_nonpython*.jsonl.gz')):
    for l in gzip.open(f, 'rt'):
        r = json.loads(l)
        if r.get('model') != 'Qwen/Qwen3.5-122B-A10B' or r['instance_id'] in chosen: continue
        by[r['instance_id']].append(r)
for iid, m in chosen.items(): by[iid] = recs[(m['_src'], m['path'])]
bad = [i for i in R if len({x['step'] for x in by.get(i, [])}) != R[i]['turns']]
print('   tasks', len(by), '/', len(R), ' step count != per-task turns:', len(bad))
write_parts(d, 'selection_swebench_pro_nonpython',
            [(i, [sel_line(r) for r in sorted(by[i], key=lambda x: x['step'])]) for i in sorted(by)])

# ---- 2. 35B self-judgement, Verified and Pro-Python (b766_35b/sgr on the machines plus two local shards)
print('== 35B self-judgement Verified / Pro-Python')
d = f'{T1}/qwen35b_self_judgement'
for b in ['swebench_verified', 'swebench_pro_python']:
    R = results('qwen35b_self_judgement', [b])
    metas, recs = read_pull('C*.jsonl.gz', '35b_sj_766')
    metas = {i: ms for i, ms in metas.items() if i in R}
    write_parts(d, f'selection_{b}', sel_groups(choose(metas, R), recs))

# ---- 3. standard trajectories, turn by turn
print('== 122B standard trajectories, non-Python')
R = results('qwen122b_standard', ['swebench_pro_nonpython']); metas, recs = read_pull('B_n*.jsonl.gz', '122b_std_nonpy')
write_parts(f'{T1}/qwen122b_standard', 'trajectories_swebench_pro_nonpython',
            traj_groups(choose(metas, R), recs, lambda m: 'swebench_pro_nonpython'))
print('== 35B standard trajectories, non-Python')
R = results('qwen35b_standard', ['swebench_pro_nonpython']); metas, recs = read_pull('[AD]_*.jsonl.gz', '35b_std_nonpy')
write_parts(f'{T1}/qwen35b_standard', 'trajectories_swebench_pro_nonpython',
            traj_groups(choose(metas, R), recs, lambda m: 'swebench_pro_nonpython'))
for b in ['swebench_verified', 'swebench_pro_python']:
    print('== 35B standard trajectories,', b)
    R = results('qwen35b_standard', [b]); metas, recs = read_pull('E*_sc.jsonl.gz', '35b_std_766')
    metas = {i: ms for i, ms in metas.items() if i in R}
    write_parts(f'{T1}/qwen35b_standard', f'trajectories_{b}', traj_groups(choose(metas, R), recs, lambda m, b=b: b))

# ---- 4. the judge rule on the 35B records: 0.7 x weighted R1..A4 + 0.3 x G1 picks the executed candidate
W = {'R1': .15, 'R2': .15, 'R3': .10, 'A1': .15, 'A2': .20, 'A3': .15, 'A4': .10}
agree = collections.Counter()
for f in glob.glob(f'{T1}/qwen35b_self_judgement/selection_swebench_verified*.jsonl.gz'):
    for l in gzip.open(f, 'rt'):
        r = json.loads(l)
        if r['decision'] != 'rubrics_score': continue
        per = collections.defaultdict(list)
        for c in r['judge_calls']:
            s = c.get('scores')
            if isinstance(s, dict) and all(isinstance(s.get(k), (int, float)) for k in list(W) + ['G1']):
                per[c['cand_idx']].append(.7 * sum(W[k] * s[k] for k in W) + .3 * s['G1'])
        if len(per) == 2:
            mw = {i: statistics.mean(v) for i, v in per.items()}
            agree['n'] += 1; agree['gold_weighted'] += max(mw, key=mw.get) == r['chosen_idx']
print('judge rule check (35B Verified):', dict(agree))
