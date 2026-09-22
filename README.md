# SI2CA Visualization

Interactive results and archived experiment records for
[(Self-Improving)² Coding Agents](https://github.com/Self-Improving-Coding-Agents/SI2CA).
The implementation and benchmark inputs are maintained in the separate SI2CA repository;
the curated training trajectories are released on Hugging Face as
[SI2CA-Training-Trajectories](https://huggingface.co/datasets/Self-Improving-Coding-Agents/SI2CA-Training-Trajectories).

Requires Python 3.7 or later (standard library only, nothing to `pip install`) and a recent Chrome,
Edge, Firefox or Safari.

## Open the page

1\. Clone this repository (about 700 MB).

```bash
git clone --branch main --depth 1 https://github.com/Self-Improving-Coding-Agents/SI2CA-Visualization.git
cd SI2CA-Visualization
```

2\. Start the local server on port 8013 (on Windows, use `python` instead of `python3`).

```bash
python3 serve.py
```

3\. Open http://localhost:8013/site/ in the browser.

If port 8013 is taken, pass another port and open that port instead.

```bash
python3 serve.py 9000
```

If the server runs on a remote machine, forward the port from your own computer before step 3.

```bash
ssh -N -L 8013:127.0.0.1:8013 <user>@<remote-host>
```

## Update the data

1\. Add new experiment records directly to `paper_data/` on this repository's `main` branch.
The separate [SI2CA repository](https://github.com/Self-Improving-Coding-Agents/SI2CA)
contains the implementation and benchmark inputs, not the visualization archives.
Preserve existing trajectories and keep paper reference values separate from computed results.

2\. Rebuild `site/data.json` and the version stamps in `site/index.html`.

```bash
python3 build_site.py
```

3\. Commit and push.

```bash
git add paper_data site/data.json site/index.html && git commit -m "Refresh visualization data" && git push origin main
```

## Open on GitHub Pages

The page is published from this repository with GitHub Pages (branch `main`, folder `/ (root)`):

https://self-improving-coding-agents.github.io/SI2CA-Visualization/site/

`#blog` opens the blog and `#<model>/<benchmark>/<view>` opens a result, for example
`#qwen122b/swebench_pro_731/traj` for the trajectories of Qwen3.5-122B-A10B on SWE-bench Pro.
