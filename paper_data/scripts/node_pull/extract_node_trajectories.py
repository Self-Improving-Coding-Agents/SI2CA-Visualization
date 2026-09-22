# Runs on a fleet node (or locally). Reads existing per-task trajectory files only and prints
# compact records as gzip+base64 between XSTARTX/XENDX markers.
#
# spec = {node, jobs: [{tag, kind: 'sel'|'traj', root, globs, ids|null, benchmark|'auto', model, strategy}]}
#   sel  -> one record per branched turn, same fields as paper_data selection_*.jsonl.gz
#   traj -> one meta record per task plus one record per turn (reasoning, command, observation)
import json, sys, glob, os, base64, gzip, io

spec = json.loads(base64.b64decode(sys.argv[1]))
node = spec['node']
buf = io.BytesIO()
gz = gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6)


def w(o):
    gz.write((json.dumps(o, ensure_ascii=False) + '\n').encode())


def norm(s):
    return s[len('instance_'):] if s.startswith('instance_') else s


def bench(raw, b):
    if b != 'auto':
        return b
    return 'swebench_pro_python' if raw.startswith('instance_') else 'swebench_verified'


for job in spec['jobs']:
    if not os.path.isdir(job['root']):
        w({'_kind': 'error', 'tag': job['tag'], 'node': node, 'err': 'no root ' + job['root']})
        continue
    os.chdir(job['root'])
    want = set(job['ids']) if job.get('ids') is not None else None
    for p in sorted(set(x for g in job['globs'] for x in glob.glob(g))):
        if want is not None and norm(os.path.basename(p)[:-5]) not in want:
            continue
        try:
            d = json.load(open(p))
        except Exception as e:
            w({'_kind': 'error', 'tag': job['tag'], 'node': node, 'path': p, 'err': str(e)[:200]})
            continue
        raw = d.get('instance_id') or os.path.basename(p)[:-5]
        iid, b = norm(raw), bench(raw, job['benchmark'])
        T = d.get('turns') or []
        meta = {'_kind': 'meta', 'tag': job['tag'], 'instance_id': iid, 'benchmark': b, 'node': node,
                'path': os.path.join(job['root'], p), 'reward': d.get('reward'), 'n_turns': len(T),
                'mtime': os.path.getmtime(p), 'strategy_raw': d.get('strategy')}
        if job['kind'] == 'traj':
            meta['problem_statement'] = d.get('problem_statement')
        w(meta)
        for i, t in enumerate(T):
            if job['kind'] == 'sel':
                w({'_kind': 'sel', 'tag': job['tag'], '_path': meta['path'],
                   'instance_id': iid, 'benchmark': b, 'model': job['model'], 'strategy': job['strategy'],
                   'step': i, 'k': t.get('k'), 'decision': t.get('decision'),
                   'chosen_idx': t.get('chosen_idx'), 'winner_idx': t.get('chosen_idx'),
                   'mean_nll_plain': t.get('cand_mean_nll'), 'mean_nll_privileged': t.get('cand_mean_nll_privileged'),
                   'judge_calls': [{'cand_idx': c.get('cand_idx'), 'sample_idx': c.get('sample_idx'),
                                    'scores': c.get('scores'), 'usage': c.get('usage')}
                                   for c in (t.get('judge_calls') or [])],
                   'candidates': [{'command': c.get('command'), 'reasoning': c.get('reasoning'),
                                   'content': c.get('content')} for c in (t.get('candidates') or [])]})
            else:
                cands = t.get('candidates') or [{}]
                ci = t.get('chosen_idx') or 0
                cc = cands[ci] if ci < len(cands) else {}
                w({'_kind': 'turn', 'tag': job['tag'], '_path': meta['path'], 'instance_id': iid, 'step': i,
                   'reasoning': t.get('reasoning'), 'content': cc.get('content') or '',
                   'command': t.get('action'), 'observation': t.get('observation'),
                   'finish_reason': t.get('finish_reason')})

gz.close()
sys.stdout.write('XSTARTX\n' + base64.b64encode(buf.getvalue()).decode() + '\nXENDX\n')
