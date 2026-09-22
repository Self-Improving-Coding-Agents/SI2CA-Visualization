#!/usr/bin/env python3
"""Fill the two gaps left by build_table1.py and keep every shipped file comfortably under
GitHub's blob limit.

1. Qwen3.5-122B standard on Verified: the archive holds 436 of the 500 rows; the remaining 64
   live in naive122_dev64.json (the campaign dev split, same protocol). Merge them.
2. Qwen3.5-35B self-likelihood on Verified 500 and Pro-Python 266: two local shards of the
   bench766_v2 run, identified by matching their pooled resolve rates (66.8 / 56.8) to the table.
3. Split any file above 40 MB into numbered parts.
"""
import json, glob, os, gzip

DST = os.path.expanduser('~/xiao/projects/self_improve_2_coding_agent/paper_data/table1_main_results')
SWE = os.path.expanduser('~/xiao/swe_run')

def load_jsonl(p):
    return [json.loads(l) for l in open(p) if l.strip()]

def dump_jsonl(p, rows):
    with open(p, 'w') as fh:
        for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    return len(rows)

# ---- 1. 122B standard, Verified 500 ----
p = f'{DST}/qwen122b_standard/swebench_verified.jsonl'
rows = load_jsonl(p)
have = {r['instance_id'] for r in rows}
extra = json.load(open(f'{SWE}/naive122_dev64.json'))
extra = extra.values() if isinstance(extra, dict) else extra
add = 0
for r in extra:
    iid = r.get('instance_id') or r.get('label')
    if not iid or iid in have or iid.startswith('instance_'): continue
    rows.append({'instance_id': iid, 'benchmark': 'swebench_verified', 'language': 'python',
                 'repo': r.get('repo') or iid.split('__')[0].replace('_', '/'),
                 'model': 'Qwen/Qwen3.5-122B-A10B', 'strategy': 'standard',
                 'resolved': float(r.get('reward') or 0) >= 0.999, 'reward': float(r.get('reward') or 0),
                 'turns': int(float(r['turns'])) if str(r.get('turns')) not in ('None', '') else None,
                 'turns_trusted': True, 'exit_code': None, 'abort': r.get('abort'),
                 'applied': r.get('applied'), 'elapsed_sec': r.get('elapsed'), 'diff_len': r.get('diff_len'),
                 'gen_prompt_tokens': r.get('gen_prompt_tokens'), 'gen_completion_tokens': r.get('gen_completion_tokens'),
                 'total_tokens': r.get('total_tokens'), 'n_candidates_drawn': r.get('n_candidates_drawn'),
                 'source_archive': 'naive122_dev64'})
    have.add(iid); add += 1
rows.sort(key=lambda x: x['instance_id'])
n = dump_jsonl(p, rows)
sv = sum(1 for r in rows if r['resolved'])
print(f'122B standard Verified: {n} rows ({add} added), {sv} solved = {100*sv/n:.1f}%')

# ---- 2. 35B self-likelihood, Verified 500 + Pro 266 ----
shards = sorted(glob.glob(f'{SWE}/bench766_v2/local_35b_hint_head/p814*/results.json'))
ver, pro = [], []
for s in shards:
    d = json.load(open(s))
    for r in (d.get('results') if isinstance(d, dict) else d):
        iid = r.get('instance_id') or r.get('label')
        if not iid: continue
        is_pro = iid.startswith('instance_')
        rec = {'instance_id': iid[len('instance_'):] if is_pro else iid,
               'benchmark': 'swebench_pro_python' if is_pro else 'swebench_verified',
               'language': 'python', 'repo': r.get('repo'),
               'model': 'Qwen/Qwen3.5-35B-A3B', 'strategy': 'self_likelihood',
               'resolved': float(r.get('reward') or 0) >= 0.999, 'reward': float(r.get('reward') or 0),
               'turns': int(float(r['turns'])) if str(r.get('turns')) not in ('None', '') else None,
               'turns_trusted': True, 'exit_code': r.get('exit_code'), 'abort': r.get('abort'),
               'applied': r.get('applied'), 'elapsed_sec': r.get('elapsed'), 'diff_len': r.get('diff_len'),
               'source_run': 'bench766_v2/local_35b_hint_head/' + os.path.basename(os.path.dirname(s))}
        (pro if is_pro else ver).append(rec)
for bench, rr in [('swebench_verified', ver), ('swebench_pro_python', pro)]:
    rr.sort(key=lambda x: x['instance_id'])
    n = dump_jsonl(f'{DST}/qwen35b_self_likelihood/{bench}.jsonl', rr)
    sv = sum(1 for r in rr if r['resolved'])
    print(f'35B self_likelihood {bench}: {n} rows, {sv} solved = {100*sv/n:.1f}%')

# ---- 3. split anything over 40 MB ----
LIMIT = 40 << 20
for p in sorted(glob.glob(f'{DST}/**/*.jsonl.gz', recursive=True)):
    if os.path.getsize(p) <= LIMIT: continue
    rows = [l for l in gzip.open(p, 'rt')]
    parts = (os.path.getsize(p) + LIMIT - 1) // LIMIT
    per = (len(rows) + parts - 1) // parts
    for i in range(parts):
        q = p[:-9] + f'.part{i+1}of{parts}.jsonl.gz'
        with gzip.open(q, 'wt', compresslevel=6) as fh: fh.writelines(rows[i*per:(i+1)*per])
        print(f'  Split -> {os.path.basename(q)} {os.path.getsize(q)/1e6:.1f}MB')
    os.remove(p)
print('\nLargest files:')
for p in sorted(glob.glob(f'{DST}/../**/*', recursive=True), key=lambda x: -os.path.getsize(x) if os.path.isfile(x) else 0)[:5]:
    if os.path.isfile(p): print(f'  {os.path.getsize(p)/1e6:7.1f}MB  {os.path.relpath(p, os.path.dirname(DST))}')
