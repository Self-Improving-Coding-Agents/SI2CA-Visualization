'use strict';
// Reads site/data.json for everything aggregate. Per-turn records stay in paper_data/ as gzipped
// JSON lines; opening a task streams only the files that hold that task and keeps only its lines.

const $ = s => document.querySelector(s);
const el = (t, a = {}, ...kids) => {
  const n = document.createElement(t);
  for (const [k, v] of Object.entries(a)) {
    if (k === 'class') n.className = v; else if (k.startsWith('on')) n[k] = v;
    else if (v !== null && v !== undefined && v !== false) n.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) n.append(k?.nodeType ? k : String(k));
  return n;
};
const ROOT = document.querySelector('meta[name="data-root"]').content;
const SWATCH = ['var(--pink)', 'var(--blue)', 'var(--green)', 'var(--yellow)'];
const num = v => (typeof v === 'number' && isFinite(v) ? v : null);
const f1 = v => (num(v) === null ? '–' : v.toFixed(1));
const i0 = v => (num(v) === null ? '–' : String(Math.round(v)));
const signed = (v, fmt) => `${v > 0 ? '+' : ''}${fmt(v)}`;
const nid = s => (String(s || '').startsWith('instance_') ? String(s).slice(9) : String(s || ''));
const mean = xs => { const v = xs.map(num).filter(x => x !== null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
let D, model, bench, ownHash = '', openSeq = 0, listScroll = null;
// The pair the site opens on when the URL names no model: Qwen3.5-122B-A10B on SWE-bench Pro,
// where the paper's gains are largest. Links that name a model keep their own pair.
const DEFAULT_MODEL = 'qwen122b', DEFAULT_BENCH = 'swebench_pro_731';

// build_site.py writes the hash of data.json into the page, so a rebuilt index is never read from cache
fetch('data.json?v=' + (document.querySelector('meta[name="data-version"]')?.content || ''))
  .then(r => r.json()).then(d => { D = d; boot(); })
  .catch(e => document.body.prepend(el('div', { class: 'wrap' }, 'Could not load data.json: ' + e)));

function boot() {
  D.models.forEach((m, i) => $('#models').append(el('button', {
    class: 'mcard', 'data-m': m.id, onclick: () => pick(m.id, null)
  }, el('div', { class: 'swatch', style: `background:${SWATCH[i % 4]}` }),
     el('div', { class: 'fam' }, m.family), el('div', { class: 'name' }, m.label))));
  document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => show(b.dataset.v));
  // links inside the blog that open another tab
  document.querySelectorAll('#v-blog a[data-goto]').forEach(a => a.onclick = e => {
    e.preventDefault(); show(a.dataset.goto); scrollTo({ top: 0, behavior: 'instant' });
  });
  ['#trajoutcome', '#trajq'].forEach(x => $(x).addEventListener('input', fillTasks));
  addEventListener('hashchange', fromHash);
  fromHash();
}
const setHash = h => { ownHash = h; location.hash = h; };

function fromHash() {
  const h = location.hash.slice(1);
  if (h && h === ownHash) return;
  ownHash = h;
  if (h === 'blog') {  // the blog is not tied to a model; the pickers still need a pair to render behind it
    if (model) show('blog', true); else pick(DEFAULT_MODEL, DEFAULT_BENCH, 'blog', true);
    return;
  }
  const [m, b, v0, strat, task] = h.split('/');
  const v0b = ['selection', 'tasks'].includes(v0) ? 'traj' : v0;  // older links pointed at separate selection and tasks tabs
  const v = ['overview', 'traj'].includes(v0b) ? v0b : 'overview';
  const known = D.models.some(x => x.id === m);
  pick(known ? m : DEFAULT_MODEL, b || (known ? null : DEFAULT_BENCH), v, true);
  if (b && b !== bench) { setHash(`${model}/${bench}/${v}`); return; }  // the link named a benchmark this view does not offer
  if (v !== 'traj' || !strat || !stratOf(strat)) return;
  $('#trajstrat').value = strat; onTrajStrat();
  if (task) openTask(decodeURIComponent(task));
  else if (listScroll !== null) { scrollTo({ top: listScroll, behavior: 'instant' }); listScroll = null; }  // back from a task to the list
}
// a pair marked trajectory:false (Qwen3.5-122B-A10B on Verified) stays on the Overview only
function benchesOf(m, v) {
  const all = Object.keys(D.pairs).filter(k => k.startsWith(m + '|')).map(k => k.split('|')[1]);
  const withTraj = all.filter(b => D.pairs[`${m}|${b}`].trajectory !== false);
  return v === 'traj' && withTraj.length ? withTraj : all;
}
function pick(m, b, view, fromhash) {
  const v = view || currentView();
  model = m;
  const list = benchesOf(m, v);
  bench = list.includes(b) ? b : list[0];
  document.querySelectorAll('.mcard').forEach(c => c.classList.toggle('on', c.dataset.m === m));
  render();
  show(v, fromhash);
}
const currentView = () => (document.querySelector('#tabs button.on') || {}).dataset?.v || 'overview';
function show(v, silent) {
  if (v !== 'blog' && !benchesOf(model, v).includes(bench)) return pick(model, null, v, silent);
  const host = $('#benches'); host.innerHTML = '';
  benchesOf(model, v).forEach(x => host.append(el('button', {
    class: 'pill-btn' + (x === bench ? ' on' : ''), onclick: () => pick(model, x)
  }, D.benchmarks[x] || x)));
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.v === v));
  ['overview', 'blog', 'traj'].forEach(x => $('#v-' + x).classList.toggle('hidden', x !== v));
  $('#pickers').classList.toggle('hidden', v === 'blog');  // the blog does not depend on a model or benchmark
  $('.hero').classList.toggle('hidden', v !== 'overview');
  $('#promo').classList.toggle('hidden', v !== 'overview');  // the video sits under the hero, overview only
  if (!silent) setHash(v === 'blog' ? 'blog' : `${model}/${bench}/${v}`);
}

// ------------------------------------------------------------------ overview
const pair = () => D.pairs[`${model}|${bench}`];
const stratOf = id => pair().strategies.find(s => s.id === id);

function render() {
  const p = pair(), n = p.strategies[0];
  $('#pairTitle').textContent = `${p.model} on ${p.benchmark} (${n.tasks} tasks)`;
  const host = $('#strats'); host.innerHTML = '';
  p.strategies.forEach(s => host.append(scard(s)));
  summaryTable(p);
  fillSelect($('#trajstrat'), p.strategies.map(s => [s.id, s.label]), onStratPicked);
  onTrajStrat();
}
// picking a strategy keeps the address in step, so reloading or going back lands on the same list
function onStratPicked() {
  onTrajStrat();
  const h = `${model}/${bench}/traj/${$('#trajstrat').value}`;
  ownHash = h; history.replaceState(null, '', '#' + h);
}

const delta = (v, fmt, lowerIsBetter) => num(v) === null ? null
  : el('span', { class: 'delta ' + ((lowerIsBetter ? v <= 0 : v >= 0) ? 'up' : 'dn') }, '  ' + signed(v, fmt));

function scard(s) {
  const dt = s.d_turns || {};
  return el('div', { class: 'scard' },
    el('div', { class: 'top' }, el('span', { class: 'nm' }, s.label),
      s.policy_effort ? el('span', { class: 'tag' }, 'policy ' + s.policy_effort) : null),
    el('div', { class: 'blurb' }, D.strategies[s.id].blurb + (s.judge_effort ? ` · judge at ${s.judge_effort} effort` : '')),
    el('div', { class: 'acc' }, el('div', { class: 'k' }, 'ACC'),
      el('div', {}, el('span', { class: 'big' }, f1(s.resolve),
        el('small', {}, '%' + (s.resolve_sd ? ` ± ${f1(s.resolve_sd)}` : ''))), delta(s.d_resolve, f1))),
    el('div', { class: 'kv' },
      el('span', { class: 'k' }, 'Average turns'),
      el('span', { class: 'v' }, s.turns ? f1(s.turns.mean) : '–', delta(dt.mean, f1, true)),
      el('span', { class: 'k' }, 'Median turns'),
      el('span', { class: 'v' }, s.turns ? i0(s.turns.median) : '–', delta(dt.median, i0, true))),
    s.turns_note ? el('p', { class: 'legend' }, s.turns_note) : null,
    canOpen(s) ? el('button', { class: 'open', onclick: () => toTrajectory(s.id) }, 'Open trajectories →') : null);
}

function summaryTable(p) {
  const t = $('#summary'); t.innerHTML = '';
  t.append(el('thead', {}, el('tr', {}, el('th', {}, 'Strategy'), el('th', { class: 'num' }, 'ACC'),
    el('th', { class: 'num' }, 'Average turns'), el('th', { class: 'num' }, 'Median turns'))));
  const body = el('tbody');
  p.strategies.forEach(s => body.append(el('tr',
    canOpen(s) ? { class: 'rowlink', title: 'Open trajectories', onclick: () => toTrajectory(s.id) } : {},
    el('td', {}, s.label),
    el('td', { class: 'num' }, f1(s.resolve) + '%' + (s.resolve_sd ? ` ± ${f1(s.resolve_sd)}` : ''), delta(s.d_resolve, f1)),
    el('td', { class: 'num' }, s.turns ? f1(s.turns.mean) : '–', delta(s.d_turns?.mean, f1, true)),
    el('td', { class: 'num' }, s.turns ? i0(s.turns.median) : '–', delta(s.d_turns?.median, i0, true)))));
  t.append(body);
}

function fillSelect(sel, pairs, onchange) {
  sel.innerHTML = '';
  pairs.forEach(([v, l]) => sel.append(el('option', { value: v }, l)));
  sel.onchange = onchange;
}

// ------------------------------------------------------------------ task rows
// row: [instance id, resolved, turns, language, repo, bitmask of record files holding the task]
const taskKey = s => `${model}|${bench}|${s}`;
function taskRows(s) {
  if (D.tasks[taskKey(s)]) return D.tasks[taskKey(s)];
  const k = Object.keys(D.tasks).find(x => x.startsWith(taskKey(s) + '|'));
  return k ? D.tasks[k] : [];
}
const canOpen = s => Boolean(s.view) && pair().trajectory !== false;
// from a strategy card or summary row straight to that strategy's trajectories
function toTrajectory(id) {
  show('traj');
  $('#trajstrat').value = id; onTrajStrat();
  const h = `${model}/${bench}/traj/${id}`;
  ownHash = h; history.replaceState(null, '', '#' + h);
  $('#v-traj').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ------------------------------------------------------------------ record streaming
const recCache = new Map();
// the Terra selection records name their task only through the session id, ds-<task>-<6 hex>
const taskOf = r => nid(r.instance_id ?? r.task ?? (String(r.session_id || '').match(/^ds-(.+)-[0-9a-f]{6}$/) || [])[1]);
// those session ids keep only the first 40 characters of a task name
const sameTask = (a, b) => a === b || (a.length === 40 && b.length > 40 && b.startsWith(a));
async function recordsFor(files, mask, task, st) {
  const key = files.join('|') + '#' + task;
  if (recCache.has(key)) return recCache.get(key);
  const needle = task.slice(0, 40), out = [];
  const picks = files.map((f, i) => [f, i]).filter(([, i]) => mask < 0 || (mask >> i) & 1);
  for (const [n, [f]] of picks.entries()) {
    const label = picks.length > 1 ? `file ${n + 1} of ${picks.length}` : 'records';
    const res = await fetch(ROOT + f);
    if (!res.ok) throw new Error(`${res.status} ${f}`);
    const total = +res.headers.get('content-length') || 0;
    const reader = res.body.getReader();
    const first = await reader.read();
    const head = first.done ? new Uint8Array() : first.value;
    let got = head.length, shown = 0;
    let stream = new ReadableStream({
      start(c) { if (head.length) c.enqueue(head); if (first.done) c.close(); },
      async pull(c) {
        const { done, value } = await reader.read();
        if (done) { c.close(); return; }
        got += value.length;
        if (st && got - shown > 1 << 20) {
          shown = got;
          st.textContent = `reading ${label} · ${(got / 1e6).toFixed(0)}${total ? ' / ' + (total / 1e6).toFixed(0) : ''} MB`;
        }
        c.enqueue(value);
      }
    });
    // a host may already have undone the gzip layer in transit; only gunzip bytes that are still gzip
    if (head[0] === 0x1f && head[1] === 0x8b) stream = stream.pipeThrough(new DecompressionStream('gzip'));
    const text = stream.pipeThrough(new TextDecoderStream()).getReader();
    const take = line => {
      if (!line.includes(needle)) return;
      const r = JSON.parse(line);
      if (sameTask(taskOf(r), task)) out.push(r);
    };
    let buf = '';
    for (;;) {
      const { done, value } = await text.read();
      if (done) break;
      buf += value;
      let a = 0, b;
      while ((b = buf.indexOf('\n', a)) >= 0) { take(buf.slice(a, b)); a = b + 1; }
      buf = buf.slice(a);
    }
    if (buf) take(buf);
  }
  recCache.set(key, out);
  if (recCache.size > 24) recCache.delete(recCache.keys().next().value);
  return out;
}

// ------------------------------------------------------------------ trajectory
const LEAD = {
  messages: 'One sample per turn. Each card is one assistant turn: its message, the commands it ran, and what they returned.',
  turns: 'One sample per turn. Each card is one turn: the thinking, the command that was run, and what it returned.',
  nll: 'Four candidates are drawn at every turn. Each is scored by its mean negative log-likelihood twice: plainly, and under a context that also holds a hint (privileged). The candidate with the lowest privileged NLL is executed.',
  judge: 'Two candidates are drawn at every turn. The model scores each against eight rubrics with the reference solution in view, over several judge samples. The candidate with the higher weighted total is executed; the weighted total is 0.7 × the weighted sum of R1–A4 plus 0.3 × G1.',
};
const DECISION = {
  score_comparison: 'higher weighted total', rubrics_score: 'higher weighted total',
  identical_command: 'same command in every candidate',
  identical_command_null_control: 'same command, scored anyway, first taken', rubrics_tie_first: 'tie, first taken',
  random_tie: 'tie, random pick', only_valid_toolcall: 'only one valid tool call',
  both_invalid: 'no valid tool call', parse_fallback: 'judge reply unparsable',
  parse_fallback_random: 'judge reply unparsable, random pick', single_candidate: 'single candidate',
  priv_nll_argmin: 'lowest privileged NLL', priv_nll_unavailable_first: 'privileged NLL unavailable, first taken',
};
const RUBRIC = [['R1', 'Groundedness'], ['R2', 'Diagnostic insight'], ['R3', 'Plan coherence'],
  ['A1', 'Analysis-action alignment'], ['A2', 'Correctness & specificity'], ['A3', 'Expected progress'],
  ['A4', 'Efficiency & safety'], ['G1', 'Goal alignment']];
const W7 = { R1: .15, R2: .15, R3: .10, A1: .15, A2: .20, A3: .15, A4: .10 };

function onTrajStrat() {
  const s = stratOf($('#trajstrat').value), v = s?.view;
  showList();
  $('#trajLead').textContent = v
    ? LEAD[v.kind] + (s.n_runs > 1 ? ` Shown for run 1 of ${s.n_runs}.` : '')
    : 'No per-turn records were kept for this strategy on this benchmark.';
  const rows = s ? taskRows(s.id) : [];
  fillTasks();
  const st = $('#trajstats'); st.innerHTML = '';
  if (!v) return;
  const have = rows.filter(r => r[5]).length;
  const bits = [have === rows.length ? `per-turn records for all ${rows.length} tasks`
    : `per-turn records for ${have} of ${rows.length} tasks; the ${rows.length - have} tasks without records are listed last, in grey, and cannot be opened`];
  if (s.sel_stats?.turns) {
    const d = s.sel_stats, byLabel = {};
    // the Python and non-Python archives name the same decision differently
    Object.entries(d.decisions).forEach(([k, n]) => { const l = DECISION[k] || k.replace(/_/g, ' '); byLabel[l] = (byLabel[l] || 0) + n; });
    bits.push(`${d.turns.toLocaleString()} branch points`, ...Object.entries(byLabel).sort((a, b) => b[1] - a[1]).slice(0, 4)
      .map(([l, n]) => `${l} ${(100 * n / d.turns).toFixed(1)}%`));
  }
  st.append(el('p', { class: 'legend' }, bits.join(' · ')));
}

function showList() {
  openSeq++;  // drop a trajectory that is still loading
  $('#trajbody').innerHTML = ''; $('#trajstatus').textContent = '';
  $('#trajlist').classList.remove('hidden'); $('#trajview').classList.add('hidden');
}

// every task of the strategy, narrowed by outcome and by a search over id, repo and language;
// each id links to its trajectory, so it also opens in a new tab
function fillTasks() {
  const s = stratOf($('#trajstrat').value), v = s?.view, rows = s ? taskRows(s.id) : [];
  const q = $('#trajq').value.trim().toLowerCase(), o = $('#trajoutcome').value;
  const keep = rows.filter(r => (o === '' || String(r[1]) === o) &&
    (!q || `${r[0]} ${r[4] || ''} ${r[3] || ''}`.toLowerCase().includes(q)));
  // tasks that can be opened first; the Python subset would otherwise fill the top of the 122B standard list
  keep.sort((a, b) => (b[5] ? 1 : 0) - (a[5] ? 1 : 0));
  $('#trajcount').textContent = keep.length === rows.length ? `${rows.length} tasks` : `${keep.length} of ${rows.length} tasks`;
  const t = $('#tasktable'); t.innerHTML = '';
  if (!s) return;
  const lang = rows.some(r => r[3]), repo = rows.some(r => r[4]);
  t.append(el('thead', {}, el('tr', {}, el('th', {}, 'Instance'), el('th', {}, 'Outcome'),
    el('th', { class: 'num' }, 'Turns'), lang ? el('th', {}, 'Language') : null, repo ? el('th', {}, 'Repo') : null)));
  const b = el('tbody');
  keep.forEach(r => b.append(el('tr', {},
    el('td', { class: 'mono' }, v && r[5]
      ? el('a', { class: 'tlink', href: `#${model}/${bench}/traj/${s.id}/${encodeURIComponent(r[0])}`,
                  onclick: () => { listScroll = scrollY; } }, r[0])
      : el('span', { class: 'muted', title: 'no per-turn record was kept for this task' }, r[0])),
    el('td', { class: r[1] ? 'ok' : 'no' }, r[1] ? 'resolved' : 'unresolved'),
    el('td', { class: 'num' }, num(r[2]) !== null ? r[2] : '–'),
    lang ? el('td', {}, r[3] || '–') : null, repo ? el('td', {}, r[4] || '–') : null)));
  t.append(b);
}

async function openTask(task) {
  const s = stratOf($('#trajstrat').value), v = s?.view;
  if (!v || !task) return;
  const st = $('#trajstatus'), body = $('#trajbody'), seq = ++openSeq;
  body.innerHTML = '';
  $('#trajlist').classList.add('hidden'); $('#trajview').classList.remove('hidden');
  $('#trajback').href = `#${model}/${bench}/traj/${s.id}`;
  $('#trajtitle').textContent = task;
  scrollTo({ top: $('#v-traj').getBoundingClientRect().top + scrollY - 70, behavior: 'instant' });
  const row = taskRows(s.id).find(r => r[0] === task);
  if (row) body.append(el('div', { class: 'outcome' },
    el('span', { class: 'tag ' + (row[1] ? 'win' : 'lose') }, row[1] ? 'resolved' : 'unresolved'),
    num(row[2]) !== null ? el('span', { class: 'tag' }, `${row[2]} turns`) : null));
  const kept = !row || Boolean(row[5]);
  st.textContent = 'loading…';
  try {
    // the per-turn records, the task's own result record, and the benchmark's description of the task
    const inst = D.instances?.[bench];
    const [recs, results, instances] = await Promise.all([
      kept ? recordsFor(v.files, row ? row[5] : -1, task, st) : [],
      s.results?.length ? recordsFor(s.results, -1, task, null) : [],
      inst ? recordsFor([inst], -1, task, null) : []]);
    if (seq !== openSeq) return;
    const boxes = [detailsCard(results[0], instances[0], recs.find(r => r.record === 'meta')),
                   ...(instances[0] ? instanceBoxes(instances[0], v.kind) : [])];
    if (!kept) {
      body.append(...boxes, el('p', { class: 'legend' }, 'No per-turn record was kept for this task.'));
      st.textContent = '';
      return;
    }
    let shown = recs, note = null;
    if (v.kind === 'judge' || v.kind === 'nll') {
      const pick = latestSession(recs);
      shown = pick.recs;
      if (pick.dropped) note = `The log holds ${pick.sessions} attempts at this task. The last attempt (${shown.length} turns) is shown; the ${pick.dropped} turns of the earlier attempts are not.`;
    }
    const cards = { messages: renderMessages, turns: renderTurns, nll: renderBranches, judge: renderBranches }[v.kind](shown, v.kind);
    if (!cards.length) { st.textContent = 'no records for this task'; return; }
    let reveal = () => {};
    body.append(turnBar(cards, row ? row[6] : null, t => reveal(t)));
    if (note) body.append(el('p', { class: 'legend' }, note));
    body.append(...boxes);
    reveal = paged(body, cards).reveal;
    st.textContent = '';
  } catch (e) { if (seq === openSeq) st.textContent = 'failed: ' + e.message; }
}

const withTurn = (turn, b) => { b.turn = turn; return b; };
function paged(body, builders, n = 40) {
  let i = 0;
  const more = el('button', { class: 'more' });
  const build = b => {
    const node = b();
    if (b.turn) { node.id = 'turn-' + b.turn; node.dataset.turn = b.turn; }
    body.insertBefore(node, more);
  };
  const step = (count = n) => {
    builders.slice(i, i + count).forEach(build);
    i = Math.min(builders.length, i + count);
    const left = builders.length - i;
    more.hidden = left <= 0;
    more.textContent = `Show the next ${Math.min(n, left)} (${left} left)`;
  };
  more.onclick = () => step();
  body.append(more);
  step();
  // builds every card up to the one carrying this turn number, plus a page beyond it: with nothing below
  // the target the page cannot scroll far enough to bring the card to the top
  return { reveal: turn => {
    const k = builders.findIndex(b => b.turn === turn);
    if (k < 0) return;
    const need = Math.min(builders.length, k + 1 + n);
    if (need > i) step(need - i);
  } };
}

// ------------------------------------------------------------------ turn bar
// one chip per turn; a cross marks a turn whose command exited with a non-zero code or that issued no
// valid command, from the outcome string build_site.py derived for the task (null where the records
// hold no command outputs)
function turnBar(builders, flags, jump) {
  const turns = builders.filter(b => b.turn);
  const chips = el('div', { class: 'chips' });
  let failed = 0;
  turns.forEach(b => {
    const fail = Boolean(flags) && flags[b.turn - 1] === 'x';
    if (fail) failed++;
    chips.append(el('button', {
      class: 'chip' + (fail ? ' fail' : ''), 'data-turn': b.turn,
      title: fail ? `turn ${b.turn}: the command exited with a non-zero code` : `turn ${b.turn}`,
      onclick: () => {
        jump(b.turn);
        const c = document.getElementById('turn-' + b.turn);
        // an instant scroll: a smooth one over tens of thousands of pixels stops short of the card
        if (c) { c.scrollIntoView({ block: 'start', behavior: 'instant' }); setChip(b.turn); }
      }
    }, String(b.turn), fail ? el('b', {}, '✕') : null));
  });
  const legend = flags
    ? `${turns.length} turns · ✕ marks the ${failed} turn${failed === 1 ? '' : 's'} whose command exited with a non-zero code or that issued no valid command · click a turn to jump to it`
    : `${turns.length} turns · exit codes are not in the per-turn records of this strategy · click a turn to jump to it`;
  return el('div', { class: 'turnbar' }, el('p', { class: 'legend' }, legend), chips);
}
function setChip(turn) {
  const bar = $('#trajbody .turnbar');
  if (!bar) return;
  bar.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', +c.dataset.turn === turn));
  const c = bar.querySelector(`.chip[data-turn="${turn}"]`), strip = bar.querySelector('.chips');
  if (c) strip.scrollLeft += c.getBoundingClientRect().left - strip.getBoundingClientRect().left - strip.clientWidth / 2 + c.offsetWidth / 2;
}
// keep the chip of the turn under the sticky bar highlighted while the page scrolls
let spyPending = false;
addEventListener('scroll', () => {
  if (spyPending || $('#trajview').classList.contains('hidden')) return;
  spyPending = true;
  requestAnimationFrame(() => {
    spyPending = false;
    let cur = null;
    for (const c of document.querySelectorAll('#trajbody .turncard[data-turn]')) {
      if (c.getBoundingClientRect().top <= 130) cur = c; else break;
    }
    if (cur) setChip(+cur.dataset.turn);
  });
}, { passive: true });

// a task attempted more than once has records from each attempt under its own session id; the last
// attempt is the one the trajectory file and the result record describe
function latestSession(recs) {
  const by = new Map();
  recs.forEach(r => { const k = r.session_id || ''; if (!by.has(k)) by.set(k, []); by.get(k).push(r); });
  if (by.size <= 1) return { recs, dropped: 0, sessions: by.size };
  const last = r => Math.max(...r.map(x => num(x.ts) ?? 0));
  const latest = [...by.values()].sort((a, b) => last(b) - last(a))[0];
  return { recs: latest, dropped: recs.length - latest.length, sessions: by.size };
}

const tag = (text, cls = '', title) => el('span', { class: 'tag ' + cls, title }, text);
const card = heads => el('div', { class: 'turncard' }, el('div', { class: 'turnhead' }, ...heads));
const block = (label, text, cls) => el('div', { class: 'blk ' + cls }, el('div', { class: 'lab' }, label), el('pre', {}, text));
const decisionTag = d => d ? tag(DECISION[d] || d.replace(/_/g, ' '), d.startsWith('identical') ? 'skip' : '', d) : null;
const promptBox = (title, parts) => el('details', { class: 'prompt' }, el('summary', {}, title),
  ...parts.map(([role, text]) => block(role, text || '', 'why')));

// ------------------------------------------------------------------ task details
// fields shown elsewhere on the page, or internal to the harness
const HIDE = new Set(['instance_id', 'task', 'benchmark', 'model', 'strategy', 'turns_trusted', 'record', '_type',
  'problem_statement', 'hints_text', 'requirements', 'interface', 'patch', 'test_patch', 'FAIL_TO_PASS', 'PASS_TO_PASS',
  'detail', 'elapsed', 'endpoint']);
const FIELD = {
  resolved: 'resolved', reward: 'reward', turns: 'turns', exit_code: 'exit code', abort: 'abort', applied: 'patch applied',
  elapsed_sec: 'elapsed (s)', diff_len: 'diff length', grade_status: 'grade status', grading_detail: 'grading',
  gen_prompt_tokens: 'prompt tokens', gen_completion_tokens: 'completion tokens', total_tokens: 'total tokens',
  n_candidates_drawn: 'candidates drawn', privileged_source: 'privileged source', privileged_position: 'privileged position',
  privileged_chars: 'privileged characters', strategy_impl: 'strategy implementation', reasoning_effort: 'reasoning effort',
  judge_effort: 'judge effort', source_run: 'source run', source_archive: 'source archive', source: 'trajectory file',
  repo_language: 'language', base_commit: 'base commit', environment_setup_commit: 'environment setup commit',
  created_at: 'created', issue_specificity: 'issue specificity', issue_categories: 'issue categories',
  selected_test_files_to_run: 'test files', dockerhub_tag: 'image tag', display_title: 'title',
  agent_timeout_sec: 'agent timeout (s)', verifier_timeout_sec: 'verifier timeout (s)', budget: 'budget (s)',
};
function fieldValue(k, v) {
  if (v === null || v === undefined || v === '' || (Array.isArray(v) && !v.length)) return null;
  if (k === 'grading_detail' && typeof v === 'object' && 'f2p_total' in v)
    return `fail-to-pass ${v.f2p_passed} of ${v.f2p_total} passed, pass-to-pass ${v.p2p_passed} of ${v.p2p_total} passed`;
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (Array.isArray(v)) return v.join(', ');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}
// the benchmark's facts about the task first, then this run's result, then the trajectory header
function detailsCard(result, inst, meta) {
  const merged = {};
  [inst, result, meta].forEach(o => o && Object.entries(o).forEach(([k, v]) => {
    if (!HIDE.has(k) && !(k in merged)) merged[k] = v;
  }));
  if (inst?.FAIL_TO_PASS) merged['fail-to-pass tests'] = inst.FAIL_TO_PASS.length;
  if (inst?.PASS_TO_PASS) merged['pass-to-pass tests'] = inst.PASS_TO_PASS.length;
  const g = el('div', { class: 'kvgrid' });
  Object.entries(merged).forEach(([k, v]) => {
    const text = fieldValue(k, v);
    if (text !== null) g.append(el('span', { class: 'k' }, FIELD[k] || k.replace(/_/g, ' ')), el('span', { class: 'v' }, text));
  });
  return el('details', { class: 'prompt', open: '' }, el('summary', {}, 'Task details'), g);
}
// the benchmark's problem statement, reference solution, test patch and test lists
function instanceBoxes(inst, kind) {
  const box = (title, ...nodes) => el('details', { class: 'prompt' }, el('summary', {}, title), ...nodes);
  const out = [];
  // standard trajectories open with the prompt that already holds the problem statement
  if (kind === 'nll' || kind === 'judge') out.push(box('Problem statement',
    ...[['issue', inst.problem_statement], ['requirements', inst.requirements], ['interface', inst.interface]]
      .filter(([, t]) => t && t.trim()).map(([label, t]) => block(label, t, 'why'))));
  if (kind === 'nll' && inst.hint) out.push(hintBox(inst.hint));
  if (inst.patch) out.push(box('Reference solution (gold patch)', diffBlock(inst.patch)));
  if (inst.test_patch) out.push(box('Test patch', diffBlock(inst.test_patch)));
  [['FAIL_TO_PASS', 'Fail-to-pass tests'], ['PASS_TO_PASS', 'Pass-to-pass tests']].forEach(([k, title]) => {
    if (inst[k]?.length) out.push(box(`${title} (${inst[k].length})`, el('ul', { class: 'tests mono' }, inst[k].map(x => el('li', {}, x)))));
  });
  return out;
}
// the hint the self-likelihood scorer saw, inside the prompt block it was inserted into
function hintBox(hint) {
  const text = (D.hint_template || '{{reference_patch}}').replace('{{reference_patch}}', hint);
  return el('details', { class: 'prompt', open: '' }, el('summary', {}, 'Privileged information (hint)'),
    el('p', { class: 'legend', style: 'padding:10px 16px 0' },
      `${hint.length} characters, derived from the reference solution. The block below was inserted right after the ` +
      'problem statement in the scoring context only: the four candidates are generated without it, and their ' +
      'privileged NLL is measured with it.'),
    block('scoring context', text, 'why'));
}
function diffBlock(patch) {
  const kind = l => (l.startsWith('diff --git') || l.startsWith('+++') || l.startsWith('---') ? 'file'
    : l.startsWith('@@') ? 'hunk' : l.startsWith('+') ? 'add' : l.startsWith('-') ? 'del' : '');
  return el('pre', { class: 'diff mono' }, patch.replace(/\n$/, '').split('\n').map(l => el('span', { class: kind(l) }, l || ' ')));
}

function toolCommand(c) {
  const a = c?.function?.arguments;
  try { const o = typeof a === 'string' ? JSON.parse(a) : a; return o?.command ?? JSON.stringify(o, null, 1); }
  catch (e) { return String(a ?? JSON.stringify(c)); }
}

// standard strategy, GPT-5.6: message-level records
function renderMessages(recs) {
  const msgs = recs.filter(r => r.record === 'message').sort((a, b) => a.index - b.index);
  const intro = [], turns = [];
  let cur = null;
  for (const m of msgs) {
    if (m.role === 'assistant') { cur = { a: m, after: [] }; turns.push(cur); }
    else if (cur) cur.after.push(m); else intro.push(m);
  }
  const out = intro.length ? [() => promptBox('Prompt', intro.map(m => [m.role, m.content]))] : [];
  return out.concat(turns.map((t, i) => withTurn(i + 1, () => {
    const box = card([tag('turn ' + (i + 1))]);
    if (t.a.reasoning_content?.trim()) box.append(block('thinking', t.a.reasoning_content, 'why'));
    if (t.a.content?.trim()) box.append(block('message', t.a.content, 'why'));
    const calls = t.a.tool_calls || [], n = calls.length, of = i => (n > 1 ? ` ${i + 1} of ${n}` : '');
    calls.forEach((c, i) => box.append(block('command' + of(i), toolCommand(c), 'cmd')));
    let seen = 0;
    t.after.forEach(m => {
      if (m.role !== 'tool') { box.append(block(m.role, m.content || '', 'why')); return; }
      const i = calls.findIndex(c => c.id && c.id === m.tool_call_id);  // outputs name the call they answer
      box.append(block('output' + of(i >= 0 ? i : seen), m.content || '', 'obs'));
      seen++;
    });
    return box;
  })));
}

// standard strategy, Qwen: turn-level records
function renderTurns(recs) {
  const meta = recs.find(r => r.record === 'meta');
  const turns = recs.filter(r => r.record === 'turn').sort((a, b) => a.step - b.step);
  const out = meta?.problem_statement ? [() => promptBox('Problem statement', [['issue', meta.problem_statement]])] : [];
  return out.concat(turns.map(t => withTurn(t.step + 1, () => {
    const box = card([tag('turn ' + (t.step + 1))]);
    if (t.reasoning?.trim()) box.append(block('thinking', t.reasoning, 'why'));
    if (t.content?.trim()) box.append(block('message', t.content, 'why'));
    if (t.command) box.append(block('command', t.command, 'cmd'));
    if (t.observation) box.append(block('output', t.observation, 'obs'));
    return box;
  })));
}

// self-likelihood and self-judgement: one card per branch point, every candidate side by side
function renderBranches(recs, kind) {
  return recs.slice().sort((a, b) => (a.step ?? 0) - (b.step ?? 0))
    .map((r, i) => withTurn((r.step ?? i) + 1, () => (kind === 'nll' ? nllTurn(r) : judgeTurn(r))));
}

// Thinking first, then the command, each under its own label. GPT-5.6 keeps its reasoning hidden,
// so the text it shows before a command is labelled as its message.
function candBody(c) {
  const text = t => (t && t.trim() ? t : null);
  const part = (label, node) => el('div', { class: 'cpart' }, el('div', { class: 'clab' }, label), node);
  const think = text(c.reasoning_content) || text(c.reasoning), msg = text(c.content);
  const words = [think && part('Thinking', el('p', { class: 'why' }, think)),
                 msg && part('Message', el('p', { class: 'why' }, msg))].filter(Boolean);
  const cmds = candCommands(c);
  return [
    el('div', {}, words.length ? words : part('Thinking', el('p', { class: 'why none' }, '(empty)'))),
    el('div', {}, cmds.length
      ? cmds.map((x, i) => part(cmds.length > 1 ? `Command ${i + 1} of ${cmds.length}` : 'Command', el('pre', { class: 'cmd mono' }, x)))
      : part('Command', el('pre', { class: 'cmd mono' }, '(no command)'))),
  ];
}
// every command the candidate issued; the `command` field of the GPT-5.6 and Qwen Python records
// holds only the first tool call, so the tool calls are read whenever they are present
function candCommands(c) {
  const calls = (c.tool_calls || []).map(toolCommand).filter(Boolean);
  return calls.length ? calls : c.command ? [c.command] : [];
}

function nllTurn(r) {
  const cands = r.candidates || [];
  const priv = cands.map((_, i) => num(r.mean_nll_privileged?.[i]));
  const plain = cands.map((_, i) => num(r.mean_nll_plain?.[i]));
  const known = priv.filter(v => v !== null);
  const lo = known.length ? Math.min(...known) : null, hi = known.length ? Math.max(...known) : null;
  const same = (r.decision || '').startsWith('identical');
  const box = card([tag('turn ' + ((r.step ?? 0) + 1)), tag('executed candidate ' + r.chosen_idx, 'win'), decisionTag(r.decision)]);
  const bar = (v, arr, cls) => {
    const k = arr.filter(x => x !== null);
    if (v === null || !k.length) return el('div', { class: 'track ' + cls });
    const a = Math.min(...k), b = Math.max(...k);
    return el('div', { class: 'track ' + cls }, el('i', { style: `width:${6 + 94 * (b > a ? (v - a) / (b - a) : 0)}%` }));
  };
  const f4 = v => (v === null ? '–' : v.toFixed(4));
  const g = el('div', { class: 'cgrid k' + Math.min(Math.max(cands.length, 1), 4) });
  cands.forEach((c, i) => {
    const chosen = i === r.chosen_idx;
    g.append(el('div', { class: 'cand' + (chosen ? ' chosen' : ''), style: 'grid-row:span 4' },
      el('div', { class: 'chd' }, el('span', { class: 'idx' }, 'candidate ' + i),
        chosen ? el('span', { class: 'check' }, '✓') : null,
        !same && priv[i] !== null && priv[i] === lo && known.length > 1 ? tag('lowest') : null),
      el('div', { class: 'nll' },
        el('span', { class: 'lab' }, 'privileged NLL'), bar(priv[i], priv, 'priv'), el('span', { class: 'val' }, f4(priv[i])),
        el('span', { class: 'lab' }, 'plain NLL'), bar(plain[i], plain, ''), el('span', { class: 'val' }, f4(plain[i]))),
      ...candBody(c)));
  });
  box.append(g);
  const argmin = lo === null ? -1 : priv.indexOf(lo);
  box.append(el('p', { class: 'legend pad' },
    !known.length ? 'No privileged NLL was recorded for this turn, so the first candidate was taken.'
      : same ? `All ${cands.length} candidates issued the same command, so the scores decided nothing and the first was taken. Privileged NLL still ranges ${lo.toFixed(4)} to ${hi.toFixed(4)} because the reasoning around the command differs.`
        : argmin === r.chosen_idx ? `Privileged NLL ranges ${lo.toFixed(4)} to ${hi.toFixed(4)}; candidate ${argmin} is the lowest and was executed.`
          : `Privileged NLL ranges ${lo.toFixed(4)} to ${hi.toFixed(4)}; the lowest is candidate ${argmin}, and candidate ${r.chosen_idx} was executed (${DECISION[r.decision] || r.decision}).`));
  return box;
}

// Three record shapes carry the judge's marks. GPT-5.6 keeps them under candidate.judge, the Qwen
// Verified and Pro (Python) archives under candidate.teacher, and the Qwen fleet runs as a flat
// judge_calls list. All are normalised to per-candidate samples plus their means.
function weighted(s) {
  if (!RUBRIC.every(([k]) => num(s?.[k]) !== null)) return null;
  return 0.7 * Object.entries(W7).reduce((a, [k, w]) => a + w * s[k], 0) + 0.3 * s.G1;
}
function summarise(samples, recorded) {
  if (!samples.length) return null;
  const out = { samples, mean: {} };
  RUBRIC.forEach(([k]) => out.mean[k] = mean(samples.map(x => x.scores[k])));
  out.total = mean(samples.map(x => x.total));
  out.weighted = num(recorded) ?? mean(samples.map(x => x.weighted));
  return out;
}
function judgeScores(r) {
  const cands = r.candidates || [];
  if (Array.isArray(r.judge_calls) && r.judge_calls.length) {
    const per = cands.map(() => []);
    r.judge_calls.forEach(c => {
      const s = c.scores;
      if (s && typeof s === 'object' && per[c.cand_idx]) {
        per[c.cand_idx].push({ scores: s, total: num(s.total), weighted: weighted(s) });
      }
    });
    return per.map(x => summarise(x));
  }
  return cands.map(c => {
    const j = c.judge || c.teacher;
    const samples = (j?.samples || []).filter(x => x && x.scores).map(x => ({
      scores: x.scores, total: num(x.judge_total ?? x.teacher_total), weighted: num(x.weighted_total),
    }));
    return summarise(samples, j?.weighted_total);
  });
}

function scoreTable(sc, win) {
  const k = sc.length;
  const cls = i => 'num' + (i === win ? ' win' : '');
  const samples = (x, key) => x && x.samples.length > 1
    ? el('small', {}, ' ' + x.samples.map(s => (num(s.scores[key]) === null ? '–' : String(+s.scores[key].toFixed(1)))).join(' · '))
    : null;
  const t = el('table', { class: 'scoretab' });
  t.append(el('thead', {}, el('tr', {}, el('th', {}, 'Rubric'),
    ...sc.map((_, i) => el('th', { class: cls(i) }, `candidate ${i}${i === win ? ' ✓' : ''}`)))));
  const tb = el('tbody');
  RUBRIC.forEach(([key, name]) => tb.append(el('tr', {},
    el('td', {}, el('b', {}, key), ' ', name),
    ...sc.map((x, i) => el('td', { class: cls(i) }, x ? f1(x.mean[key]) : '–', samples(x, key))))));
  tb.append(el('tr', { class: 'sum' }, el('td', {}, 'Judge total'),
    ...sc.map((x, i) => el('td', { class: cls(i) }, x ? f1(x.total) : '–',
      x && x.samples.length > 1 ? el('small', {}, ' ' + x.samples.map(s => (s.total === null ? '–' : s.total.toFixed(1))).join(' · ')) : null))));
  tb.append(el('tr', { class: 'sum main' }, el('td', {}, 'Weighted total'),
    ...sc.map((x, i) => el('td', { class: cls(i) }, x && x.weighted !== null ? x.weighted.toFixed(2) : '–'))));
  t.append(tb);
  const n = [...new Set(sc.filter(Boolean).map(x => x.samples.length))];
  return el('div', { class: 'scorewrap' }, t, el('p', { class: 'legend' },
    `Each cell is the mean over ${n.length === 1 ? n[0] : n.join(' or ')} judge sample${n.length === 1 && n[0] === 1 ? '' : 's'}` +
    `${n.some(x => x > 1) ? ', followed by the individual samples' : ''}. Scores run 0 to 10.`));
}

function judgeTurn(r) {
  const cands = r.candidates || [];
  const win = r.winner_idx ?? r.chosen_idx ?? 0;
  const sc = judgeScores(r);
  const box = card([tag('turn ' + ((r.step ?? 0) + 1)), tag('executed candidate ' + win, 'win'), decisionTag(r.decision),
    num(r.student_gen_sec) > 0 ? tag(`generate ${f1(r.student_gen_sec)} s`) : null,
    num(r.judge_sec ?? r.teacher_sec) > 0 ? tag(`judge ${f1(r.judge_sec ?? r.teacher_sec)} s`) : null]);
  if (sc.some(Boolean)) box.append(scoreTable(sc, win));
  else box.append(el('p', { class: 'legend pad' }, (r.decision || '').startsWith('identical')
    ? `Both candidates issued the same command, so the judge was not called and candidate ${win} was executed.`
    : 'No judge scores were recorded for this turn.'));
  const g = el('div', { class: 'cgrid k' + Math.min(Math.max(cands.length, 1), 4) });
  cands.forEach((c, i) => {
    const chosen = i === win;
    g.append(el('div', { class: 'cand' + (chosen ? ' chosen' : ''), style: 'grid-row:span 3' },
      el('div', { class: 'chd' }, el('span', { class: 'idx' }, 'candidate ' + i),
        chosen ? el('span', { class: 'check' }, '✓') : null),
      ...candBody(c)));
  });
  box.append(g);
  return box;
}
