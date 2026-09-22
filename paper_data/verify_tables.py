#!/usr/bin/env python3
"""Compare available Table 1 and Table 2 records with the published paper values.

Run it from anywhere:

    python3 paper_data/verify_tables.py

Each row prints the recomputed value next to the published one. The paper is authoritative
for published values; differences in the available records do not change those references.
`MISSING` marks unavailable records; `<-` marks missing or differing Table 1 values
(see README, "Known gaps").
"""
import json, glob, gzip, os, statistics, sys

HERE = os.path.dirname(os.path.abspath(__file__))
T1, T2 = os.path.join(HERE, 'table1_main_results'), os.path.join(HERE, 'table2_deepswe')

PUBLISHED_T1 = {  # (verified resolve, pro-731 resolve) as printed in the table
    ('qwen35b', 'standard'): (65.8, 46.0), ('qwen35b', 'self_judgement'): (70.0, 53.2),
    ('qwen35b', 'self_likelihood'): (66.8, 51.2),
    ('qwen122b', 'standard'): (67.0, 48.0), ('qwen122b', 'self_judgement'): (71.0, 58.5),
    ('qwen122b', 'self_likelihood'): (69.8, 53.8),
}
PUBLISHED_T2 = {  # (resolve mean over runs, turns mean, median, p90)
    ('gpt56_terra_xhigh', 'standard'): (64.4, 59.3, 52, 98),
    ('gpt56_terra_xhigh', 'self_judgement'): (67.5, 52.3, 46, 86),
    ('gpt56_luna_max', 'standard'): (60.2, 246.8, 173, 465),
    ('gpt56_luna_max', 'self_judgement'): (64.6, 223.0, 150, 474),
}


def rows(path):
    if not os.path.exists(path): return None
    return [json.loads(l) for l in open(path) if l.strip()]


def pct(xs, p):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * p; i = int(k)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i)


def rate(rs):
    return None if not rs else round(100 * sum(1 for r in rs if r['resolved']) / len(rs), 1)


def table1():
    print('Table 1 - resolve rate (%), available records vs published paper\n')
    print(f"{'model':<10}{'strategy':<17}{'Verified':>20}{'Pro (731)':>22}")
    ok = True
    for (model, strat), (pv, pp) in PUBLISHED_T1.items():
        d = os.path.join(T1, f'{model}_{strat}')
        ver = rows(f'{d}/swebench_verified.jsonl')
        pyr = rows(f'{d}/swebench_pro_python.jsonl')
        npy = rows(f'{d}/swebench_pro_nonpython.jsonl')
        pro = (pyr or []) + (npy or [])
        v = rate(ver); p = rate(pro) if pyr and npy else None
        fv = f'{v} vs {pv}' if v is not None else f'MISSING vs {pv}'
        fp = f'{p} vs {pp} (n={len(pro)})' if p is not None else f'MISSING vs {pp}'
        mark = lambda a, b: '' if a is not None and abs(a - b) <= 0.15 else '  <-'
        ok &= v is not None and p is not None
        print(f'{model:<10}{strat:<17}{fv:>20}{mark(v,pv)}{fp:>22}{mark(p,pp)}')
    return ok


def table2():
    print('\nTable 2 - DeepSWE v1.1 (113 tasks), mean over the runs present\n')
    print(f"{'model':<20}{'strategy':<17}{'resolve':>16}{'turns mean':>14}{'med':>8}{'p90':>8}")
    for (model, strat), (pr, pm, pmed, pp90) in PUBLISHED_T2.items():
        runs = sorted(glob.glob(os.path.join(T2, model, strat, 'run*')))
        if not runs:
            print(f'{model:<20}{strat:<17}{"MISSING":>16}')
            continue
        R, M, MD, P = [], [], [], []
        for r in runs:
            rs = rows(os.path.join(r, 'results.jsonl'))
            R.append(rate(rs))
            T = [x['turns'] for x in rs if x['turns'] is not None]
            M.append(statistics.mean(T)); MD.append(statistics.median(T)); P.append(pct(T, .9))
        f = lambda got, want, d=1: f'{round(statistics.mean(got), d)} vs {want}'
        print(f'{model:<20}{strat:<17}{f(R,pr):>16}{f(M,pm):>16}{f(MD,pmed,0):>14}{f(P,pp90,0):>14}   runs={len(runs)}')


def payload():
    print('\nShipped records\n')
    tot = 0
    for p in sorted(glob.glob(os.path.join(HERE, '**', '*.jsonl*'), recursive=True)):
        n = sum(1 for _ in (gzip.open(p, 'rt') if p.endswith('.gz') else open(p)))
        tot += os.path.getsize(p)
        print(f'  {os.path.getsize(p)/1e6:8.1f} MB  {n:>8} rec  {os.path.relpath(p, HERE)}')
    print(f'  {tot/1e6:8.1f} MB  total')


if __name__ == '__main__':
    complete = table1()
    table2()
    if '--list' in sys.argv: payload()
    print('\nSome Table 1 cells have no per-task records yet.' if not complete else '')
