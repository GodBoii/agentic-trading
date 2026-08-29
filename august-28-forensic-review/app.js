const state = { data: null, filter: 'all', query: '' };

const fmtMoney = value => {
  const number = Number(value || 0);
  const formatted = Math.abs(number).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${number < 0 ? '-' : ''}₹${formatted}`;
};
const fmtNumber = (value, digits = 2) => Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : '—';
const fmtTime = value => value ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)) : '—';
const escapeHtml = value => String(value ?? '').replace(/[&<>"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[character]);
const titleFromPath = path => path.split('/').pop().replace(/\.png$/i, '').replaceAll('-', ' ');

function statusLabel(run) {
  return {
    trade: 'Filled · loss',
    skipped: 'Skipped',
    blocked: 'Blocked',
    tool_failed: 'Tool failed',
    model_error: 'Model error',
    unfilled_pending: 'Unfilled',
  }[run.run_class] || run.run_class;
}

function renderMetrics(report) {
  const items = [
    [report.event_count, 'signals dispatched', ''],
    [report.trade_count, 'positions filled', ''],
    [report.winning_trades, 'winning trades', 'danger'],
    [fmtMoney(report.gross_realized_pnl), 'gross realized P&L', 'danger'],
    [`${report.counts.blocked || 0}`, 'placements blocked', ''],
  ];
  document.querySelector('#summary-metrics').innerHTML = items.map(([value, label, className]) => `<div class="metric ${className}"><strong>${value}</strong><span>${label}</span></div>`).join('');
}

function chartSvg(run, compact = false) {
  const bars = run.market_bars_5m || [];
  if (!bars.length) return '<div class="error-box">No finalized market bars available.</div>';
  const width = compact ? 320 : 760;
  const height = compact ? 150 : 280;
  const pad = { left: compact ? 8 : 46, right: compact ? 8 : 54, top: 16, bottom: compact ? 8 : 28 };
  const values = bars.flatMap(bar => [bar.high, bar.low]);
  const levels = compact ? [] : [run.placement?.entry_price, run.placement?.stop_loss_price, run.placement?.target_price].map(Number).filter(Number.isFinite);
  const min = Math.min(...values, ...levels);
  const max = Math.max(...values, ...levels);
  const span = Math.max(max - min, 0.01);
  const x = index => pad.left + index * ((width - pad.left - pad.right) / Math.max(bars.length - 1, 1));
  const y = value => pad.top + (max - value) / span * (height - pad.top - pad.bottom);
  const signalIndex = bars.reduce((best, bar, index) => Math.abs(new Date(bar.time) - new Date(run.signal_time_ist)) < Math.abs(new Date(bars[best].time) - new Date(run.signal_time_ist)) ? index : best, 0);
  const candleWidth = Math.max(2, Math.min(7, (width - pad.left - pad.right) / bars.length * .64));
  const candles = bars.map((bar, index) => {
    const up = bar.close >= bar.open;
    const color = up ? '#68d89b' : '#ff6b63';
    const bodyY = y(Math.max(bar.open, bar.close));
    const bodyHeight = Math.max(1, Math.abs(y(bar.open) - y(bar.close)));
    return `<line x1="${x(index)}" y1="${y(bar.high)}" x2="${x(index)}" y2="${y(bar.low)}" stroke="${color}" stroke-width="1"/><rect x="${x(index) - candleWidth / 2}" y="${bodyY}" width="${candleWidth}" height="${bodyHeight}" fill="${color}"/>`;
  }).join('');
  const levelSpecs = compact ? [] : [
    ['Entry', Number(run.placement?.entry_price), '#77b9ff'],
    ['Stop', Number(run.placement?.stop_loss_price), '#ff6b63'],
    ['Target', Number(run.placement?.target_price), '#7ee2a8'],
  ].filter(([, value]) => Number.isFinite(value));
  const levelLines = levelSpecs.map(([label, value, color]) => `<line x1="${pad.left}" y1="${y(value)}" x2="${width - pad.right}" y2="${y(value)}" stroke="${color}" stroke-dasharray="4 4" opacity=".8"/><text x="${width - pad.right + 4}" y="${y(value) + 3}" fill="${color}" font-size="9">${label} ${value}</text>`).join('');
  const axes = compact ? '' : `<text x="2" y="${y(max) + 4}" fill="#8c9890" font-size="9">${max.toFixed(2)}</text><text x="2" y="${y(min) + 4}" fill="#8c9890" font-size="9">${min.toFixed(2)}</text><text x="${pad.left}" y="${height - 7}" fill="#8c9890" font-size="9">09:15</text><text x="${width - pad.right - 28}" y="${height - 7}" fill="#8c9890" font-size="9">15:30</text>`;
  return `<svg class="price-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(run.display_name)} five minute market chart with signal and order levels"><rect width="100%" height="100%" fill="#0c100e"/>${candles}<line x1="${x(signalIndex)}" y1="${pad.top}" x2="${x(signalIndex)}" y2="${height - pad.bottom}" stroke="#f0bd62" stroke-dasharray="3 3"/><text x="${Math.min(x(signalIndex) + 4, width - 48)}" y="12" fill="#f0bd62" font-size="9">SIGNAL</text>${levelLines}${axes}</svg>`;
}

function tradeReason(run) {
  const path = run.inferred_order_path || {};
  if (run.display_name === 'Jindal Stainless') return `Limit entry remained live for about ${fmtNumber(path.minutes_from_signal_to_entry, 0)} minutes and stopped one minute after fill.`;
  if (run.display_name.startsWith('Krishna Institute')) return 'Entry filled about eight minutes late. The ₹773.50 exit matches neither the ₹776 stop nor ₹766.50 target.';
  if (run.display_name === 'Piramal Pharma') return 'Bought 0.61% above the event close on a partial 5m candle, with a bearish engulfing event still present.';
  if (run.display_name === 'Mphasis') return 'Shorted near the session low while 1m RSI was oversold; the subsequent mean-reversion bounce hit protection.';
  return 'The breakout failed and reverted to the exact stop price before reaching the target.';
}

function renderTrades(runs) {
  document.querySelector('#trade-grid').innerHTML = runs.filter(run => run.run_class === 'trade').map(run => {
    const position = run.position || {};
    const side = String(run.placement?.side || '').toUpperCase();
    const exit = side === 'BUY' ? position.sellAvg : position.buyAvg;
    const rawDelay = run.inferred_order_path?.minutes_from_signal_to_entry;
    const delay = Number.isFinite(rawDelay) ? Math.max(0, rawDelay) : rawDelay;
    return `<article class="trade-card">
      <header><span class="badge ${run.direction.toLowerCase()}">${run.direction}</span><h3>${escapeHtml(run.display_name)}</h3></header>
      <div class="trade-pnl">${fmtMoney(position.realizedProfit)}</div>
      <dl class="trade-meta">
        <div><dt>Signal</dt><dd>${fmtTime(run.signal_time_ist)}</dd></div><div><dt>Fill delay</dt><dd>${Number.isFinite(delay) ? `${fmtNumber(delay, 0)} min` : '—'}</dd></div>
        <div><dt>Entry avg</dt><dd>${fmtNumber(position.costPrice)}</dd></div><div><dt>Exit avg</dt><dd>${fmtNumber(exit)}</dd></div>
        <div><dt>Requested stop</dt><dd>${fmtNumber(run.placement?.stop_loss_price)}</dd></div><div><dt>Requested target</dt><dd>${fmtNumber(run.placement?.target_price)}</dd></div>
      </dl>
      ${chartSvg(run, true)}
      <p class="trade-note">${tradeReason(run)}</p>
    </article>`;
  }).join('');
}

function runMatches(run) {
  const filterMatches = state.filter === 'all'
    || state.filter === 'trade' && run.run_class === 'trade'
    || state.filter === 'no-trade' && ['skipped', 'blocked', 'unfilled_pending'].includes(run.run_class)
    || state.filter === 'error' && ['model_error', 'tool_failed'].includes(run.run_class);
  const haystack = `${run.display_name} ${run.symbol} ${run.event_id} ${run.analysis} ${run.error || ''}`.toLowerCase();
  return filterMatches && haystack.includes(state.query.toLowerCase());
}

function indicatorList(run) {
  if (!run.indicator_events?.length) return '<li>No indicator event preserved.</li>';
  return run.indicator_events.map(event => `<li><code>${escapeHtml(event.event_type)}</code> · ${event.direction || 'neutral'} · ${fmtTime(event.detected_at)}</li>`).join('');
}

function gallery(run) {
  if (!run.chart_files?.length) return '<div class="error-box">Charts were generated before the model call, but no artifact path was recovered for this failed run.</div>';
  return `<div class="chart-gallery">${run.chart_files.map(path => {
    const source = `../${path}`;
    const title = titleFromPath(path);
    return `<button class="chart-button" type="button" data-chart="${escapeHtml(source)}" data-title="${escapeHtml(title)}"><img src="${escapeHtml(source)}" alt="${escapeHtml(title)}" loading="lazy"><span>${escapeHtml(title)}</span></button>`;
  }).join('')}</div>`;
}

function detailHtml(run) {
  const outcome = run.post_signal_outcome || {};
  const position = run.position || {};
  const placement = run.placement || {};
  const accuracy = run.chart_accuracy || {};
  const path = run.inferred_order_path || {};
  const error = run.error ? `<div class="error-box">${escapeHtml(run.error)}</div>` : '';
  const execution = run.run_class === 'trade' ? `
    <h4>Broker result</h4>
    <div class="detail-stats">
      <div><span>Actual entry</span><strong>${fmtNumber(position.costPrice)}</strong></div><div><span>Actual exit</span><strong>${fmtNumber(String(placement.side).toUpperCase() === 'BUY' ? position.sellAvg : position.buyAvg)}</strong></div><div><span>Realized</span><strong>${fmtMoney(position.realizedProfit)}</strong></div>
      <div><span>Entry delay</span><strong>${Number.isFinite(path.minutes_from_signal_to_entry) ? `${fmtNumber(Math.max(0, path.minutes_from_signal_to_entry), 0)} min` : '—'}</strong></div><div><span>First requested leg touch</span><strong>${path.first_protection_touch || 'none'}</strong></div><div><span>Touch time</span><strong>${fmtTime(path.first_protection_touch_ist)}</strong></div>
    </div>` : '';
  return `<div class="detail-grid">
    <div class="detail-copy">
      <h3>${escapeHtml(run.display_name)}</h3>
      ${error}
      <div class="detail-stats">
        <div><span>Event close</span><strong>${fmtNumber(run.indicator_snapshot?.close)}</strong></div><div><span>VWAP</span><strong>${fmtNumber(run.vwap)}</strong></div><div><span>1m RSI</span><strong>${fmtNumber(run.indicator_snapshot?.rsi, 1)}</strong></div>
        <div><span>5m RSI</span><strong>${fmtNumber(run.chart_contract?.technical_metadata?.rsi, 1)}</strong></div><div><span>Post-signal MFE</span><strong>${fmtNumber(outcome.max_favorable_excursion_percent)}%</strong></div><div><span>Post-signal MAE</span><strong>${fmtNumber(outcome.max_adverse_excursion_percent)}%</strong></div>
      </div>
      ${execution}
      ${chartSvg(run)}
      <h4>Why Intra Finder dispatched it</h4><ul>${indicatorList(run)}</ul>
      <h4>Agent output</h4><pre>${escapeHtml(run.analysis || 'The provider returned no usable response.')}</pre>
      <h4>Tool calls</h4><pre>${escapeHtml(JSON.stringify(run.tool_calls || [], null, 2))}</pre>
      <h4>Chart reconciliation</h4><p>${escapeHtml(accuracy.verdict)} across ${accuracy.overlap_minutes || 0} overlapping minutes. Max OHLC difference ${fmtNumber(accuracy.max_ohlc_difference_percent, 3)}%; mean close difference ${fmtNumber(accuracy.mean_close_difference_percent, 3)}%.</p>
    </div>
    <aside>${gallery(run)}</aside>
  </div>`;
}

function renderRuns() {
  const container = document.querySelector('#run-list');
  const template = document.querySelector('#run-template');
  const matches = state.data.runs.filter(runMatches);
  container.replaceChildren(...matches.map(run => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.class = run.run_class;
    node.querySelector('.run-index').textContent = String(run.ordinal).padStart(2, '0');
    node.querySelector('.run-time').textContent = fmtTime(run.signal_time_ist);
    node.querySelector('.run-name').textContent = run.display_name;
    const direction = node.querySelector('.run-direction');
    direction.textContent = run.direction;
    direction.style.color = run.direction === 'LONG' ? 'var(--green)' : 'var(--red)';
    node.querySelector('.run-score').textContent = `S ${fmtNumber(run.readiness_score, 0)}`;
    node.querySelector('.run-status').innerHTML = `<span class="badge ${run.run_class}">${statusLabel(run)}</span>`;
    const button = node.querySelector('.run-summary');
    const detail = node.querySelector('.run-detail');
    button.addEventListener('click', () => {
      const open = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', String(!open));
      detail.hidden = open;
      if (!open && !detail.dataset.rendered) {
        detail.innerHTML = detailHtml(run);
        detail.dataset.rendered = 'true';
      }
    });
    return node;
  }));
  document.querySelector('#run-empty').hidden = matches.length > 0;
}

function renderAudit(runs) {
  const order = { material_outlier: 0, review: 1, close_match: 2, unverified: 3 };
  const sorted = [...runs].sort((a, b) => order[a.chart_accuracy.verdict] - order[b.chart_accuracy.verdict] || (b.chart_accuracy.max_ohlc_difference_percent || 0) - (a.chart_accuracy.max_ohlc_difference_percent || 0));
  document.querySelector('#audit-table').innerHTML = sorted.map(run => {
    const audit = run.chart_accuracy;
    return `<tr><td>${escapeHtml(run.display_name)}</td><td><span class="badge ${audit.verdict === 'material_outlier' ? 'error' : audit.verdict}">${audit.verdict.replaceAll('_', ' ')}</span></td><td>${audit.overlap_minutes || 0}m</td><td>${fmtNumber(audit.max_ohlc_difference_percent, 3)}%</td><td>${fmtNumber(audit.mean_close_difference_percent, 3)}%</td><td>${fmtNumber(audit.mean_absolute_volume_error_percent, 1)}%</td></tr>`;
  }).join('');
}

function setupEvents() {
  document.querySelector('#run-search').addEventListener('input', event => { state.query = event.target.value; renderRuns(); });
  document.querySelector('#run-filters').addEventListener('click', event => {
    const button = event.target.closest('button[data-filter]');
    if (!button) return;
    state.filter = button.dataset.filter;
    document.querySelectorAll('#run-filters button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    renderRuns();
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-chart]');
    if (!button) return;
    const dialog = document.querySelector('#chart-dialog');
    dialog.querySelector('img').src = button.dataset.chart;
    dialog.querySelector('p').textContent = button.dataset.title;
    dialog.showModal();
  });
  const dialog = document.querySelector('#chart-dialog');
  dialog.querySelector('.dialog-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
}

async function init() {
  try {
    const response = await fetch('data.json');
    if (!response.ok) throw new Error(`Evidence request failed with ${response.status}`);
    state.data = await response.json();
    renderMetrics(state.data.report);
    renderTrades(state.data.runs);
    renderRuns();
    renderAudit(state.data.runs);
    setupEvents();
    document.querySelector('#source-state').textContent = 'Evidence loaded · 4 sources';
  } catch (error) {
    document.querySelector('#source-state').textContent = 'Evidence failed to load';
    document.querySelector('main').insertAdjacentHTML('afterbegin', `<div class="error-box">${escapeHtml(error.message)}. Serve this folder over HTTP instead of opening the file directly.</div>`);
  }
}

init();
