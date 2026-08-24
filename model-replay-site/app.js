'use strict';

const body = document.body;
const dataUrl = body.dataset.data || 'data.json';
const state = { data: null, selected: null, filter: 'all', query: '', chartObserver: null };
const colors = { bg: '#090e10', grid: '#222c2e', text: '#8d9a97', up: '#58cf8b', down: '#f2786d', signal: '#f1b84b', model: '#61d7e2', original: '#a99bdc', target: '#58cf8b', stop: '#f2786d' };

const el = {
  title: document.querySelector('#model-title'),
  mark: document.querySelector('#model-mark'),
  overview: document.querySelector('#overview'),
  metrics: document.querySelector('#metrics'),
  list: document.querySelector('#run-list'),
  review: document.querySelector('#review'),
  search: document.querySelector('#search'),
  filters: Array.from(document.querySelectorAll('.filter')),
};

function validData(value) { return Boolean(value && typeof value === 'object' && Array.isArray(value.runs) && value.summary && value.candles); }
function esc(value) { return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;'); }
function price(value) { return Number.isFinite(Number(value)) ? `₹${Number(value).toFixed(2)}` : '—'; }
function num(value) { return Number.isFinite(Number(value)) ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(Number(value)) : '—'; }
function time(value) { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false }).format(date); }
function shortModel(value) { return String(value || '').split('/').at(-1) || 'model'; }

function outcomeClass(run) {
  const outcome = run.path_evaluation?.outcome;
  if (outcome === 'TARGET') return 'target';
  if (outcome === 'STOP') return 'stop';
  return run.order ? 'trade' : 'wait';
}
function decisionLabel(run) {
  if (!run.order) return 'No trade';
  const outcome = run.path_evaluation?.outcome;
  return outcome === 'TARGET' ? 'Target touched' : outcome === 'STOP' ? 'Stop touched' : `${run.order.side} simulated`;
}
function matches(run) {
  const query = state.query.trim().toLowerCase();
  const text = `${run.name} ${run.symbol} ${run.security_id}`.toLowerCase();
  if (query && !text.includes(query)) return false;
  if (state.filter === 'all') return true;
  if (state.filter === 'trade') return Boolean(run.order);
  if (state.filter === 'pass') return !run.order;
  if (state.filter === 'target') return run.path_evaluation?.outcome === 'TARGET';
  if (state.filter === 'stop') return run.path_evaluation?.outcome === 'STOP';
  return true;
}

function renderTop() {
  const data = state.data;
  const score = data.vision_test?.grade?.score ?? 0;
  const maximum = data.vision_test?.grade?.maximum ?? 12;
  const pass = Boolean(data.vision_test?.grade?.passed);
  const model = data.model;
  el.title.textContent = shortModel(model);
  el.mark.textContent = shortModel(model).slice(0, 3).toUpperCase();
  document.title = `${shortModel(model)} · August 21 replay`;
  el.overview.innerHTML = `<p class="eyebrow">Historical model replay</p><h2>${esc(shortModel(model))} decisions against the August 21 tape.</h2><p class="overview-copy"><span class="${pass ? 'vision-pass' : ''}">Vision test ${score}/${maximum}.</span> Every order below is simulated. The chart compares the model's choice with the original live agent and the recorded price path.</p>`;
  const outcomes = data.summary.outcomes_from_one_second_prices || data.summary.outcomes_from_15m_bars || {};
  const metrics = [
    ['Completed', data.summary.completed_runs, 'of 44 scenarios'],
    ['No trade', data.summary.no_trade, 'model passed'],
    ['Trade calls', data.summary.trade_calls, 'simulated only'],
    ['Targets', outcomes.TARGET || 0, 'one-second sequence'],
    ['Stops', outcomes.STOP || 0, 'one-second sequence'],
  ];
  el.metrics.innerHTML = metrics.map(([label, value, note]) => `<div class="metric"><span>${esc(label)}</span><strong>${num(value)}</strong><small>${esc(note)}</small></div>`).join('');
}

function renderList() {
  const runs = state.data.runs.filter(matches);
  if (!runs.length) { el.list.innerHTML = '<p class="empty">No completed runs match this view.</p>'; return; }
  el.list.innerHTML = runs.map((run) => `<button type="button" class="run${run.number === state.selected.number ? ' selected' : ''}" data-run="${run.number}" aria-pressed="${run.number === state.selected.number}"><span class="run-no">${String(run.number).padStart(2, '0')}</span><span><span class="run-name">${esc(run.name)}</span><span class="run-time">${time(run.signal.time)} · ${run.order ? esc(run.order.side) : 'PASS'}</span></span><span class="dot ${outcomeClass(run)}" aria-label="${esc(decisionLabel(run))}"></span></button>`).join('');
}

function orderBlock(order) {
  if (!order) return '<p class="outcome">No order tool call. The model chose not to trade.</p>';
  return `<div class="order"><div><span>Entry</span><strong>${price(order.entry)}</strong></div><div><span>Target</span><strong>${price(order.target)}</strong></div><div><span>Stop</span><strong>${price(order.stop)}</strong></div></div>`;
}
function outcomeText(run) {
  const evaluation = run.path_evaluation;
  if (!run.order) return 'No simulated order to evaluate.';
  if (!evaluation) return 'Order was invalid and was not evaluated.';
  const labels = { TARGET: 'Recorded price touched the target after entry.', STOP: 'Recorded price touched the stop after entry.', ENTRY_NOT_TOUCHED: 'The recorded 15-minute range never touched the entry.', NO_EXIT: 'Entry was touched, but neither exit level was touched before close.', AMBIGUOUS_SAME_CANDLE: 'Target and stop were both inside one 15-minute candle, so sequence is unknown.' };
  return labels[evaluation.outcome] || evaluation.outcome;
}

function renderReview(run) {
  if (state.chartObserver) state.chartObserver.disconnect();
  const original = run.original || {};
  const modelOrder = run.order;
  const originalOrder = original.order;
  const cls = outcomeClass(run);
  el.review.innerHTML = `
    <header class="review-head"><div><p class="eyebrow">Run ${String(run.number).padStart(2, '0')} · ${time(run.signal.time)} signal</p><h2>${esc(run.name)}</h2><span class="subline">${esc(run.symbol)} · NSE ${run.security_id}</span></div><span class="badge ${cls}">${esc(decisionLabel(run))}</span></header>
    <section class="chart" aria-labelledby="chart-title"><div class="chart-head"><strong id="chart-title">15-minute decision replay</strong><div class="legend"><span><i class="sig"></i>System signal</span><span><i class="model"></i>Replay order</span><span><i class="orig"></i>Original order</span></div></div><canvas id="chart-canvas" role="img" aria-label="15-minute chart for ${esc(run.name)} with replay and original trade levels"></canvas><p class="chart-note">OHLC is aggregated from recorded one-second prices. Target-before-stop results use the exact recorded one-second sequence, not candle ordering or broker fills.</p></section>
    <div class="compare">
      <section class="decision"><h3>${esc(shortModel(state.data.model))} replay</h3>${orderBlock(modelOrder)}<p class="outcome ${cls}">${esc(outcomeText(run))}</p><div class="copy">${esc(run.analysis || 'No final response was returned.')}</div></section>
      <section class="decision"><h3>Original live agent · ${esc(shortModel(original.model))}</h3>${orderBlock(originalOrder)}<div class="copy">${esc(original.analysis || 'No archived response.')}</div></section>
    </div>
    <p class="safety">${esc(state.data.safety)} · Vision gate ${state.data.vision_test.grade.score}/${state.data.vision_test.grade.maximum}.</p>`;
  drawChart(document.querySelector('#chart-canvas'), state.data.candles[String(run.security_id)] || [], run);
}

function drawChart(canvas, candles, run) {
  const context = canvas.getContext('2d');
  const draw = () => {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio); context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const w = rect.width, h = rect.height, m = { t: 32, r: 76, b: 42, l: 54 }, volume = 44, bottom = h - m.b - volume - 10, pw = w - m.l - m.r, ph = bottom - m.t;
    const levels = candles.flatMap(c => [c.low, c.high]);
    for (const order of [run.order, run.original?.order]) if (order) levels.push(Number(order.entry), Number(order.target), Number(order.stop));
    const rawMin = Math.min(...levels), rawMax = Math.max(...levels), pad = Math.max((rawMax - rawMin) * .08, rawMax * .002), min = rawMin - pad, max = rawMax + pad;
    const step = pw / Math.max(candles.length, 1), cw = Math.max(3, Math.min(12, step * .58)), y = p => m.t + ((max - p) / (max - min)) * ph, x = i => m.l + step * (i + .5), maxVol = Math.max(1, ...candles.map(c => c.volume));
    context.fillStyle = colors.bg; context.fillRect(0, 0, w, h); context.font = '9px Consolas'; context.textBaseline = 'middle';
    for (let i = 0; i <= 5; i++) { const gy = m.t + ph / 5 * i, p = max - (max - min) / 5 * i; context.strokeStyle = colors.grid; context.beginPath(); context.moveTo(m.l, gy); context.lineTo(w - m.r, gy); context.stroke(); context.fillStyle = colors.text; context.textAlign = 'right'; context.fillText(p.toFixed(2), m.l - 7, gy); }
    candles.forEach((c, i) => { const cx = x(i), color = c.close >= c.open ? colors.up : colors.down; context.strokeStyle = color; context.beginPath(); context.moveTo(cx, y(c.high)); context.lineTo(cx, y(c.low)); context.stroke(); context.fillStyle = color; context.fillRect(cx - cw / 2, Math.min(y(c.open), y(c.close)), cw, Math.max(2, Math.abs(y(c.close) - y(c.open)))); context.globalAlpha = .35; const vy = h - m.b - c.volume / maxVol * volume; context.fillRect(cx - cw / 2, vy, cw, h - m.b - vy); context.globalAlpha = 1; if (i % 4 === 0) { context.fillStyle = colors.text; context.textAlign = 'center'; context.fillText(time(c.time), cx, h - 22); } });
    const start = new Date(candles[0]?.time).getTime(), end = new Date(candles.at(-1)?.time).getTime() + 900000, tx = value => m.l + (new Date(value).getTime() - start) / (end - start) * pw;
    const sx = tx(run.signal.time); context.strokeStyle = colors.signal; context.setLineDash([4, 4]); context.beginPath(); context.moveTo(sx, m.t); context.lineTo(sx, bottom); context.stroke(); context.setLineDash([]); context.fillStyle = colors.signal; context.beginPath(); context.arc(sx, y(run.signal.price), 4, 0, Math.PI * 2); context.fill(); tag(context, sx, m.t + 4, `SIGNAL ${time(run.signal.time)}`, colors.signal, w);
    drawOrder(context, run.order, 'MODEL', colors.model, y, w, m, bottom);
    drawOrder(context, run.original?.order, 'ORIGINAL', colors.original, y, w, m, bottom, true);
  };
  state.chartObserver = new ResizeObserver(draw); state.chartObserver.observe(canvas); draw();
}
function drawOrder(ctx, order, label, color, y, width, margin, bottom, dashed = false) {
  if (!order) return;
  const entries = [['ENTRY', order.entry, color], ['TARGET', order.target, colors.target], ['STOP', order.stop, colors.stop]];
  entries.forEach(([name, value, lineColor], index) => { const py = y(Number(value)); ctx.strokeStyle = lineColor; ctx.globalAlpha = dashed ? .42 : .85; ctx.setLineDash(dashed ? [5, 5] : index ? [3, 3] : []); ctx.beginPath(); ctx.moveTo(margin.l, py); ctx.lineTo(width - margin.r, py); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = lineColor; ctx.textAlign = 'left'; ctx.fillText(`${label} ${name} ${price(value)}`, width - margin.r + 5, py); ctx.globalAlpha = 1; });
}
function tag(ctx, x, y, text, color, width) { ctx.font = '700 8px Consolas'; const tw = ctx.measureText(text).width + 10, left = Math.max(54, Math.min(x + 4, width - tw - 78)); ctx.fillStyle = color; ctx.fillRect(left, y, tw, 16); ctx.fillStyle = colors.bg; ctx.textAlign = 'left'; ctx.fillText(text, left + 5, y + 8); }

function select(number) { const run = state.data.runs.find(item => item.number === number); if (!run) return; state.selected = run; history.replaceState(null, '', `#run-${number}`); renderList(); renderReview(run); }
async function init() {
  try {
    const response = await fetch(dataUrl, { signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error(`Replay data is not ready. HTTP ${response.status}`);
    const data = await response.json(); if (!validData(data)) throw new Error('Replay data has an unexpected shape.');
    state.data = data; const match = location.hash.match(/^#run-(\d+)$/); const requested = match ? Number(match[1]) : data.runs[0]?.number; state.selected = data.runs.find(run => run.number === requested) || data.runs[0];
    renderTop(); renderList(); if (state.selected) renderReview(state.selected); else el.review.innerHTML = '<p class="loading">No completed model runs yet.</p>';
    el.list.addEventListener('click', event => { const button = event.target.closest('[data-run]'); if (button) select(Number(button.dataset.run)); });
    el.search.addEventListener('input', () => { state.query = el.search.value; renderList(); });
    el.filters.forEach(button => button.addEventListener('click', () => { state.filter = button.dataset.filter; el.filters.forEach(item => item.classList.toggle('active', item === button)); renderList(); }));
  } catch (error) { el.review.innerHTML = `<div class="error"><strong>Replay not ready.</strong><br>${esc(error instanceof Error ? error.message : error)}</div>`; }
}
void init();
