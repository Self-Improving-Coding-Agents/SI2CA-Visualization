#!/usr/bin/env python3
"""Export the per-task artefacts behind Table 1 (Qwen3.5-35B / 122B, Verified 500 + Pro 731).

Three sources are normalised into one schema:
  * 122B archives (merged.json)      Verified 500 and Pro-Python 266
  * fleet dumps (ns_*.tsv)           Pro non-Python 465, all six arms
  * branch logs                      per-turn candidates and judge decisions, 122B self-judgement

`turns_trusted` marks whether a row's turn count is the assistant-turn count. Two archives
record something else (segments for Standard, candidate draws for Self-likelihood); the paper's
turn statistics for those arms come from the trajectory files, so the field is flagged rather
than silently shipped as if comparable.
"""
import json, gzip, os, glob, collections, hashlib
import pyarrow.parquet as pq

SWE = os.path.expanduser('~/xiao/swe_run')
DUMP = '/path/to/scratchpad/status731'
SLIME = os.path.expanduser('~/xiao/projects/slime')
DST = os.path.expanduser('~/xiao/projects/self_improve_2_coding_agent/paper_data/table1_main_results')

ARCH = {'standard': 'naive122_final', 'self_judgement': 'sg122_final', 'self_likelihood': 'gpgd122_final'}
TURNS_TRUSTED = {'standard': False, 'self_judgement': True, 'self_likelihood': False}
FLEET = {('qwen35b', 'standard'): ['m35_std', 'q35_std'], ('qwen35b', 'self_judgement'): ['m35_sj', 'q35_sj'],
         ('qwen35b', 'self_likelihood'): ['m35_sl', 'q35_sl'],
         ('qwen122b', 'standard'): ['std', 'retry_std'], ('qwen122b', 'self_judgement'): ['sj', 'retry_sj'],
         ('qwen122b', 'self_likelihood'): ['sic', 'sl', 'retry_sic', 'retry_sl']}
MODEL_ID = {'qwen35b': 'Qwen/Qwen3.5-35B-A3B', 'qwen122b': 'Qwen/Qwen3.5-122B-A10B'}

# language per Pro instance, from the ScaleAI dataset
pqp = sorted(glob.glob(os.path.expanduser(
    '~/.cache/huggingface/hub/datasets--ScaleAI--SWE-bench_Pro/snapshots/*/data/test-00000-of-00001.parquet')))[-1]
t = pq.read_table(pqp).to_pydict()
LANG = {iid: t['repo_language'][k] for k, iid in enumerate(t['instance_id'])}
REPO = {iid: t['repo'][k] for k, iid in enumerate(t['instance_id'])}
ids465 = {json.loads(l)['instance_id'] for l in open(f'{SLIME}/training_data/pro465_hints.jsonl')}

def sha(p, n=1 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while (b := f.read(n)): h.update(b)
    return h.hexdigest()[:16]

def norm_pro_id(l):
    return l[len('instance_'):] if l.startswith('instance_') else l

def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    return len(rows), os.path.getsize(path)

manifest = {'table': 'Table 1 - Main results, SWE-bench Verified 500 and SWE-bench Pro 731', 'arms': []}

# ---------- 122B archives: Verified 500 + Pro-Python 266 ----------
arch_rows = {}
for strat, name in ARCH.items():
    d = json.load(open(f'{SWE}/{name}/merged.json'))
    rows = d.values() if isinstance(d, dict) else d
    ver, pro = [], []
    for r in rows:
        lab = str(r.get('label') or '')
        if not lab: continue
        is_pro = lab.startswith('instance_')
        iid = norm_pro_id(lab)
        rec = {'instance_id': iid, 'benchmark': 'swebench_pro_python' if is_pro else 'swebench_verified',
               'language': LANG.get(iid, 'python' if is_pro else 'python'),
               'repo': REPO.get(iid) or iid.split('__')[0].replace('_', '/'),
               'model': MODEL_ID['qwen122b'], 'strategy': strat,
               'resolved': float(r.get('reward') or 0) >= 0.999, 'reward': float(r.get('reward') or 0),
               'turns': int(float(r['turns'])) if str(r.get('turns')) not in ('None', '') else None,
               'turns_trusted': TURNS_TRUSTED[strat],
               'exit_code': r.get('exit_code'), 'abort': r.get('abort'), 'applied': r.get('applied'),
               'elapsed_sec': r.get('elapsed'), 'diff_len': r.get('diff_len'),
               'source_archive': name}
        (pro if is_pro else ver).append(rec)
    arch_rows[strat] = {'swebench_verified': sorted(ver, key=lambda x: x['instance_id']),
                        'swebench_pro_python': sorted(pro, key=lambda x: x['instance_id'])}

# ---------- fleet dumps: Pro non-Python 465 ----------
per = collections.defaultdict(dict)
for f in sorted(glob.glob(f'{DUMP}/ns_*.tsv')):
    for line in open(f):
        p = line.rstrip('\n').split('\t')
        # The upstream TSV uses a result-record tag, independent of the method.
        if len(p) < 8 or p[1] != 'R': continue
        arm, iid, rew, abort, turns, mt = p[2], p[3], p[4], p[5], p[6], p[7]
        if abort.startswith('exception:') or iid in per[arm] or iid not in ids465: continue
        try: reward = float(rew) if rew not in ('None', '') else 0.0
        except ValueError: continue
        try: tn = int(float(turns))
        except Exception: tn = None
        per[arm][iid] = (reward, tn, abort, mt)

for (model, strat), dirs in FLEET.items():
    merged = {}
    for d in dirs:
        for iid, v in per.get(d, {}).items(): merged.setdefault(iid, v)
    rows = [{'instance_id': iid, 'benchmark': 'swebench_pro_nonpython', 'language': LANG.get(iid),
             'repo': REPO.get(iid), 'model': MODEL_ID[model], 'strategy': strat,
             'resolved': v[0] >= 0.999, 'reward': v[0], 'turns': v[1], 'turns_trusted': True,
             'abort': v[2] if v[2] not in ('None', '') else None, 'source_run': 'pro465_fleet_0910'}
            for iid, v in sorted(merged.items())]
    arch_rows.setdefault(f'{model}|{strat}', {})['swebench_pro_nonpython'] = rows

# ---------- write per arm ----------
files_idx = {}
for model in ['qwen35b', 'qwen122b']:
    for strat in ['standard', 'self_judgement', 'self_likelihood']:
        base = f'{DST}/{model}_{strat}'
        got = {}
        if model == 'qwen122b':
            for bench, rows in arch_rows[strat].items():
                got[f'{bench}.jsonl'] = write(f'{base}/{bench}.jsonl', rows)
        rows = arch_rows.get(f'{model}|{strat}', {}).get('swebench_pro_nonpython', [])
        if rows: got['swebench_pro_nonpython.jsonl'] = write(f'{base}/swebench_pro_nonpython.jsonl', rows)
        files_idx[(model, strat)] = (base, got)

# ---------- 122B self-judgement per-turn selection records ----------
sgl = glob.glob(f'{SWE}/sg122_final/t*/sg122/p*/branch_logs/*.jsonl')
labels = sorted(json.load(open(f'{SWE}/sg122_final/merged.json')), key=len, reverse=True)
base = f'{DST}/qwen122b_self_judgement'
counts = {'swebench_verified': 0, 'swebench_pro_python': 0}
handles = {b: gzip.open(f'{base}/selection_{b}.jsonl.gz', 'wt', compresslevel=6) for b in counts}
for p in sorted(sgl):
    b = os.path.basename(p)[7:].rsplit('.jsonl', 1)[0]
    lab = next((l for l in labels if b.startswith(l)), None)
    if lab is None: continue
    bench = 'swebench_pro_python' if lab.startswith('instance_') else 'swebench_verified'
    iid = norm_pro_id(lab)
    for line in open(p):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except Exception: continue
        handles[bench].write(json.dumps({'instance_id': iid, 'benchmark': bench, **r}, ensure_ascii=False) + '\n')
        counts[bench] += 1
for h in handles.values(): h.close()
for b, n in counts.items():
    files_idx[('qwen122b', 'self_judgement')][1][f'selection_{b}.jsonl.gz'] = (n, os.path.getsize(f'{base}/selection_{b}.jsonl.gz'))

# ---------- manifest ----------
for (model, strat), (base, got) in sorted(files_idx.items()):
    entry = {'model': MODEL_ID[model], 'strategy': strat, 'dir': os.path.relpath(base, DST), 'files': {}, 'coverage': {}}
    for fn, (n, sz) in got.items():
        entry['files'][fn] = {'records': n, 'bytes': sz, 'sha256_16': sha(f'{base}/{fn}')}
    for fn in ['swebench_verified.jsonl', 'swebench_pro_python.jsonl', 'swebench_pro_nonpython.jsonl']:
        p = f'{base}/{fn}'
        if not os.path.exists(p): continue
        rows = [json.loads(l) for l in open(p)]
        sv = sum(1 for r in rows if r['resolved'])
        T = sorted(r['turns'] for r in rows if r.get('turns') is not None)
        entry['coverage'][fn[:-6]] = {'tasks': len(rows), 'solved': sv,
                                      'resolve_rate_pct': round(100 * sv / max(1, len(rows)), 1),
                                      'turns_mean': round(sum(T) / len(T), 1) if T else None,
                                      'turns_trusted': rows[0].get('turns_trusted')}
    manifest['arms'].append(entry)
    print(f"{model}_{strat:16s} " + '  '.join(f'{k}:{v[0]}rec/{v[1]/1e6:.1f}MB' for k, v in got.items()))
os.makedirs(DST, exist_ok=True)
json.dump(manifest, open(f'{DST}/manifest.json', 'w'), indent=1, ensure_ascii=False)
tot = sum(os.path.getsize(p) for p in glob.glob(f'{DST}/**/*', recursive=True) if os.path.isfile(p))
print('\nTotal size:', round(tot / 1e6, 1), 'MB')
