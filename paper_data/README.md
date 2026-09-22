# Paper data

Per-task records, per-turn selection records and full trajectories behind the two main tables
of *(Self-Improving)² Coding Agents*. Everything here is JSONL: one JSON object per line, so a
trajectory viewer can read a file directly and a one-line `jq` filter is enough to slice it.

Compare the available records with the published paper values:

```bash
python3 paper_data/verify_tables.py          # add --list to print record counts and sizes
```

The paper is the source of truth for published table values. The script prints available-record
values alongside the paper references and marks differences; it does not overwrite either.
The visualization's `published` entries follow the same rule. Per-task results, trajectories,
selection logs and computed aggregates retain their recorded values, even when they differ.

## Layout

```
paper_data/
├── verify_tables.py
├── table1_main_results/
│   ├── manifest.json
│   └── <model>_<strategy>/
│       ├── swebench_verified.jsonl          500 tasks
│       ├── swebench_pro_python.jsonl        266 tasks
│       ├── swebench_pro_nonpython.jsonl     465 tasks  (Go 280, JS 165, TS 20)
│       └── selection_<benchmark>.jsonl.gz   self-judgement only: one record per branched turn
└── table2_deepswe/
    ├── manifest.json
    └── gpt56_terra_xhigh/<strategy>/run{1..4}/
        ├── results.jsonl                    113 tasks
        ├── trajectories.jsonl.gz            every chat message of every trajectory
        └── selection.jsonl.gz               self-judgement only
```

`<model>` is `qwen35b` or `qwen122b`; `<strategy>` is `standard`, `self_judgement` or
`self_likelihood`. SWE-bench Pro is reported in the paper over its full 731-task public test
split, which is the union of the two Pro files.

## Record schemas

**Per-task** (`*.jsonl`, one line per task)

| field | meaning |
|---|---|
| `instance_id`, `benchmark`, `language`, `repo` | task identity |
| `model`, `strategy`, `run` | which table row the record belongs to |
| `resolved`, `reward` | graded outcome; `resolved` is `reward >= 0.999` |
| `turns` | assistant turns; see the caveat below |
| `turns_trusted` | `false` when the source archive recorded a different quantity |
| `exit_code`, `abort`, `applied`, `elapsed_sec`, `diff_len` | run metadata |
| `grading_detail` | DeepSWE only: fail-to-pass and pass-to-pass counts |
| `source_archive` / `source_run` | which run produced the row |

**Trajectory** (`trajectories.jsonl.gz`): one `record: "meta"` line per task carrying its grade,
image and turn count, then one `record: "message"` line per chat message with `role`, `content`
and `tool_calls`, in order. Filter one task with `zcat trajectories.jsonl.gz | jq -c 'select(.task=="...")'`.

**Selection** (`selection.jsonl.gz`): one line per branched turn, holding every candidate the
policy drew (reasoning, content, tool calls), the judge's decision, the winning index, and the
wall-clock split between generation and judging. `decision: "identical_command"` marks a turn
where the candidates issued the same command and the judge was skipped.

## Turn counts

Three of the archived Qwen runs recorded something other than the assistant-turn count: the
standard arm stored harness segments and the self-likelihood arm stored candidate draws. Those
rows carry `turns_trusted: false`, and the turn statistics printed in the paper for them come
from the trajectory files rather than from these fields. The self-judgement turn counts are
assistant turns, but their recomputed aggregates can differ from the paper; for the 122B arm they can also be
recounted from `selection_*.jsonl.gz`, which holds one record per turn.

## Known gaps

The published code now uses a [unified execution protocol](https://github.com/Self-Improving-Coding-Agents/SI2CA/blob/main/docs/HARNESS.md)
for new runs. These archived records retain their original mixed harness sources;
they have not been converted into unified-harness results or rerun. Historical
API-driver failures are flagged as incomplete by `si2ca.results`, without changing
raw records or the paper's reported values.

| missing | why | where it lives |
|---|---|---|
| GPT-5.6-Luna-xHigh, both rows of Table 2 | the runs were executed on a different machine | that machine's `runs/` directory |
| Trajectories for the Qwen runs | not retained locally; only per-task records and the self-judgement per-turn records survive | node-side `traj/` directories |

All six Qwen arms now carry their per-task records for both benchmarks. Two of them were
pulled from the machines that ran them on 2026-09-11: the 35B standard arm from
`b766_naive`, and the 35B self-judgement arm from `b766_35b/sgr` across six nodes plus two
local shards. Both are complete at 766 tasks with no duplicates.

The two benchmarks of the 122B self-likelihood row come from two arms of the same eight-arm
sweep, which is how the paper reports them. Verified is the `hint_head` arm: hint as the
privileged text, inserted before the trajectory, k=4, argmin mean NLL. Pro-Python is the
archived hint arm whose 60.5 matches that cell exactly. Both files record the arm they came
from in `source_run` / `source_archive`.

Two Verified cells differ between the paper and the available records. The published values
remain **65.8 for 35B Standard** and **69.8 for 122B Self-Likelihood**, as used by the main
README and `verify_tables.py`. The available 35B Standard records yield 67.0 (335 of 500);
the paper's 65.8 comes from an older run that is no longer on disk. The available 122B
Self-Likelihood records yield 69.4 (347 of 500); the paper's 69.8 comes from a snapshot before
two tasks were re-run. These differences remain visible in the comparison output; the raw
records are unchanged. The 35B Standard Pro-Python cell, 50.4, still matches these records.

Turn statistics on Pro 731 are pooled over the per-task records of both subsets, except for
the 122B standard and self-likelihood rows. Those two archives recorded harness segments and
candidate draws instead of assistant turns, so their Pro-Python turn statistics are taken from
the paper (computed from trajectories at the time) and combined with the measured non-Python
values weighted by task count. That interpolation was checked against the one arm where the
pooled distribution is available and reproduced its median and P90 exactly.
