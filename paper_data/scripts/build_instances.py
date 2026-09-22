#!/usr/bin/env python3
"""Export per-task benchmark metadata to paper_data/instances/ for the visualization page.

SWE-bench Verified and SWE-bench Pro come from their public Hugging Face datasets (read from the
local cache), including the reference solution (`patch`), the test patch and the fail-to-pass and
pass-to-pass tests. DeepSWE is a gated, held-out benchmark, so only its descriptive fields are
exported: no reference solution and no evaluation files.
"""
import ast, glob, gzip, json, os, re
import pyarrow.parquet as pq

PD = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PD, 'instances')
HF = os.path.expanduser('~/.cache/huggingface/hub')
# DeepSWE task metadata as kept in the main checkout (data/ is not tracked on any branch)
DEEPSWE = os.path.expanduser('~/xiao/projects/self_improve_2_coding_agent/data/deepswe113.jsonl')
# the hints the self-likelihood runs scored candidates under, and the prompt block they were
# inserted into (every run put the block right after the problem statement)
HINTS = [os.path.expanduser('~/xiao/projects/slime/training_data/gpgd_bench766_hints.jsonl'),
         os.path.expanduser('~/xiao/projects/slime/training_data/pro465_hints.jsonl')]
HINT_TEMPLATE = os.path.expanduser('~/xiao/projects/self_improve_2_coding_agent/si2ca/prompts/gold_guided_scoring_hint.md')

nid = lambda s: s[len('instance_'):] if s.startswith('instance_') else s


def as_list(v):
    if isinstance(v, list): return v
    if v in (None, ''): return []
    for parse in (json.loads, ast.literal_eval):
        try:
            x = parse(v)
            return list(x) if isinstance(x, (list, tuple)) else [x]
        except Exception:
            pass
    return [v]


def as_dict(v):
    if isinstance(v, dict): return v
    try: return ast.literal_eval(v)
    except Exception: return {}


def parquet(name):
    return pq.read_table(glob.glob(f'{HF}/datasets--{name}/snapshots/*/data/test-*.parquet')[0]).to_pylist()


def task_ids(pattern, key='instance_id'):
    return {nid(json.loads(l)[key]) for f in glob.glob(os.path.join(PD, pattern)) for l in open(f)}


hints = {}
for p in HINTS:
    if os.path.exists(p):
        for line in open(p):
            r = json.loads(line)
            hints[nid(r['instance_id'])] = r['hint']


def write(name, rows, want):
    rows = sorted((r for r in rows if r['instance_id'] in want), key=lambda r: r['instance_id'])
    for r in rows:
        if r['instance_id'] in hints: r['hint'] = hints[r['instance_id']]
    missing = want - {r['instance_id'] for r in rows}
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f'{name}.jsonl.gz')
    with gzip.open(path, 'wt', compresslevel=9) as fh:
        for r in rows: fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'{name}: {len(rows)} of {len(want)} tasks, {sum(1 for r in rows if r.get("hint"))} with hints, '
          f'{os.path.getsize(path) / 1e6:.2f} MB' + (f', missing {sorted(missing)[:3]}' if missing else ''))


if os.path.exists(HINT_TEMPLATE):
    # keep only the prompt text; the file starts with an HTML comment explaining the design
    text = re.sub(r'^<!--.*?-->\s*', '', open(HINT_TEMPLATE).read(), flags=re.S)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, 'hint_template.md'), 'w').write(text)
    print(f'hint_template.md: {len(text)} chars')


write('swebench_verified', [{
    'instance_id': r['instance_id'], 'repo': r['repo'], 'base_commit': r['base_commit'], 'version': r['version'],
    'created_at': r['created_at'], 'difficulty': r['difficulty'], 'environment_setup_commit': r['environment_setup_commit'],
    'FAIL_TO_PASS': as_list(r['FAIL_TO_PASS']), 'PASS_TO_PASS': as_list(r['PASS_TO_PASS']),
    'problem_statement': r['problem_statement'], 'hints_text': r['hints_text'],
    'patch': r['patch'], 'test_patch': r['test_patch']} for r in parquet('SWE-bench--SWE-bench_Verified')],
    task_ids('table1_main_results/qwen35b_standard/swebench_verified.jsonl'))

write('swebench_pro', [{
    'instance_id': nid(r['instance_id']), 'repo': r['repo'], 'repo_language': r['repo_language'], 'base_commit': r['base_commit'],
    'issue_specificity': as_list(r['issue_specificity']), 'issue_categories': as_list(r['issue_categories']),
    'selected_test_files_to_run': as_list(r['selected_test_files_to_run']), 'dockerhub_tag': r['dockerhub_tag'],
    'FAIL_TO_PASS': as_list(r['fail_to_pass']), 'PASS_TO_PASS': as_list(r['pass_to_pass']),
    'problem_statement': r['problem_statement'], 'requirements': r['requirements'], 'interface': r['interface'],
    'patch': r['patch'], 'test_patch': r['test_patch']} for r in parquet('ScaleAI--SWE-bench_Pro')],
    task_ids('table1_main_results/qwen35b_standard/swebench_pro_*python.jsonl'))

deepswe = []
for line in open(DEEPSWE):
    m = json.loads(line)['metadata']
    row = {'instance_id': m['instance_id'], 'display_title': m.get('display_title'), 'category': m.get('category'),
           'repo': m.get('repo'), 'language': m.get('language'), 'base_commit': m.get('base_commit'),
           'image': m.get('image'), 'workdir': m.get('workdir'), 'problem_statement': m.get('problem_statement')}
    row.update({k: v for k, v in as_dict(m.get('deepswe')).items() if isinstance(v, (str, int, float, bool))})
    deepswe.append(row)
write('deepswe_v11', deepswe, task_ids('table2_deepswe/gpt56_terra_xhigh/standard/run1/results.jsonl', key='task'))
