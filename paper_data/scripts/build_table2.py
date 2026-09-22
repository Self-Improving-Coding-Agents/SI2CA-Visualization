#!/usr/bin/env python3
"""Export every artefact behind Table 2 (DeepSWE v1.1, 113 tasks) into the SI2CA repo.

Per run we ship three files:
  results.jsonl        one line per task: grade, turns, timing, image, grading detail
  trajectories.jsonl.gz  one line per chat message, tagged with its task (visualizer input)
  selection.jsonl.gz   self-judgement runs only: per-turn candidates, judge scores, winner

Run -> table row mapping was established by recomputing each directory's resolve rate and
turn statistics and matching them against the published cells, not by directory name.
"""
import json, gzip, os, glob, shutil, hashlib

SRC = os.path.expanduser('~/xiao/runs')
DST = os.path.expanduser('~/xiao/projects/self_improve_2_coding_agent/paper_data/table2_deepswe')
RUNS = {
    'gpt56_terra_xhigh/standard': ['terra_minimal_ctrl', 'terra_naive_r2', 'terra_naive_r3', 'terra_naive_r4'],
    'gpt56_terra_xhigh/self_judgement': ['terra_sgxh_r1', 'terra_sgxh_r2', 'terra_sgxh_r3', 'terra_sgxh_r4'],
}

def sha(path, n=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while (b := f.read(n)): h.update(b)
    return h.hexdigest()[:16]

def export_run(src, dst, arm, run_idx):
    os.makedirs(dst, exist_ok=True)
    files = {}
    # --- results ---
    out = os.path.join(dst, 'results.jsonl')
    seen, n = set(), 0
    with open(out, 'w') as fh:
        for line in open(os.path.join(src, 'results.jsonl')):
            line = line.strip()
            if not line: continue
            r = json.loads(line)
            t = r.get('task')
            if not t or t in seen: continue
            seen.add(t); n += 1
            det = r.get('detail')
            if isinstance(det, str):
                try: det = eval(det, {'__builtins__': {}}, {})
                except Exception: pass
            fh.write(json.dumps({
                'task': t, 'benchmark': 'deepswe_v1.1', 'model': 'gpt-5.6-terra',
                'reasoning_effort': 'xhigh', 'strategy': arm, 'run': run_idx,
                'resolved': float(r.get('reward') or 0) >= 0.999,
                'reward': float(r.get('reward') or 0),
                'turns': int(float(r['turns'])) if r.get('turns') not in (None, 'None') else None,
                'elapsed_sec': float(r['elapsed']) if r.get('elapsed') not in (None, 'None') else None,
                'language': r.get('language'), 'image': r.get('image'),
                'grade_status': r.get('grade_status'), 'exit_code': r.get('exit_code'),
                'grading_detail': det,
            }, ensure_ascii=False) + '\n')
    files['results.jsonl'] = (n, os.path.getsize(out))
    # --- trajectories ---
    out = os.path.join(dst, 'trajectories.jsonl.gz')
    ntask = nmsg = 0
    with gzip.open(out, 'wt', compresslevel=6) as fh:
        for p in sorted(glob.glob(os.path.join(src, 'traj', '*.jsonl'))):
            task = os.path.basename(p)[:-6]; ntask += 1; idx = 0
            for line in open(p):
                line = line.strip()
                if not line: continue
                try: r = json.loads(line)
                except Exception: continue
                if r.get('_type') == 'meta':
                    fh.write(json.dumps({'task': task, 'record': 'meta', **r}, ensure_ascii=False) + '\n')
                else:
                    fh.write(json.dumps({'task': task, 'record': 'message', 'index': idx, **r}, ensure_ascii=False) + '\n')
                    idx += 1; nmsg += 1
    files['trajectories.jsonl.gz'] = (ntask, os.path.getsize(out))
    # --- selection (self-judgement only) ---
    bl = sorted(glob.glob(os.path.join(src, 'branch_logs', '*.jsonl')))
    if bl:
        out = os.path.join(dst, 'selection.jsonl.gz')
        nrec = 0
        with gzip.open(out, 'wt', compresslevel=6) as fh:
            for p in bl:
                for line in open(p):
                    line = line.strip()
                    if not line: continue
                    try: r = json.loads(line)
                    except Exception: continue
                    fh.write(json.dumps({'log_file': os.path.basename(p), **r}, ensure_ascii=False) + '\n')
                    nrec += 1
        files['selection.jsonl.gz'] = (nrec, os.path.getsize(out))
    return files

manifest = {'table': 'Table 2 - Frontier GPT-5.6 models on DeepSWE v1.1 (113 tasks)', 'runs': []}
for key, dirs in RUNS.items():
    model_dir, arm = key.split('/')
    for i, d in enumerate(dirs, 1):
        src = os.path.join(SRC, d)
        dst = os.path.join(DST, model_dir, arm, f'run{i}')
        files = export_run(src, dst, arm, i)
        rows = [json.loads(l) for l in open(os.path.join(dst, 'results.jsonl'))]
        solved = sum(1 for r in rows if r['resolved'])
        T = sorted(r['turns'] for r in rows if r['turns'] is not None)
        p90 = T[min(len(T) - 1, int(round(.9 * (len(T) - 1))))]
        manifest['runs'].append({
            'model': 'GPT-5.6-Terra-xHigh', 'strategy': arm, 'run': i,
            'source_dir': d, 'tasks': len(rows), 'solved': solved,
            'resolve_rate_pct': round(100 * solved / len(rows), 1),
            'turns_mean': round(sum(T) / len(T), 1), 'turns_median': T[len(T) // 2], 'turns_p90': p90,
            'files': {k: {'records': v[0], 'bytes': v[1], 'sha256_16': sha(os.path.join(dst, k))} for k, v in files.items()},
        })
        print(f"{d:20s} -> {os.path.relpath(dst, DST):45s} " +
              '  '.join(f'{k} {v[0]}rec {v[1]/1e6:.1f}MB' for k, v in files.items()))
os.makedirs(DST, exist_ok=True)
json.dump(manifest, open(os.path.join(DST, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
print('\nTotal size:', round(sum(os.path.getsize(p) for p in glob.glob(f'{DST}/**/*', recursive=True) if os.path.isfile(p)) / 1e6, 1), 'MB')
