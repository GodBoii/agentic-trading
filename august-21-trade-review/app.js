'use strict';

const DATA_URL = 'data.json';
const COLORS = {
  bg: '#0a0f12',
  grid: '#202a28',
  text: '#8e9b99',
  up: '#59cf8d',
  down: '#f2766b',
  signal: '#f1b84b',
  agent: '#6fd6df',
  target: '#59cf8d',
  stop: '#f2766b',
  volume: '#34413e',
};

const state = {
  data: null,
  selectedRun: null,
  filter: 'all',
  query: '',
  chart: null,
};

const elements = {
  summaryCopy: document.querySelector('#summary-copy'),
  summaryGrid: document.querySelector('#summary-grid'),
  runList: document.querySelector('#run-list'),
  visibleCount: document.querySelector('#visible-count'),
  search: document.querySelector('#run-search'),
  review: document.querySelector('#run-review'),
  filters: Array.from(document.querySelectorAll('.filter')),
};

function isReviewData(value) {
  return Boolean(
    value &&
    typeof value === 'object' &&
    value.summary &&
    Array.isArray(value.runs) &&
    value.candles &&
    typeof value.candles === 'object'
  );
}

async function loadData() {
  const response = await fetch(DATA_URL, { signal: AbortSignal.timeout(20000) });
  if (!response.ok) {
    throw new Error(`Could not load the review data. HTTP ${response.status}`);
  }
  const data = await response.json();
  if (!isReviewData(data)) {
    throw new Error('The review data has an unexpected shape.');
  }
  return data;
}

function formatNumber(value, maximumFractionDigits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits }).format(Number(value));
}

function formatPrice(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return `₹${new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value))}`;
}

function formatTime(value, includeSeconds = false) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined,
    hour12: false,
  }).format(date);
}

function statusGroup(run) {
  if (!run.order) return 'pass';
  if (run.order.broker_status === 'TRADED') return 'traded';
  if (run.order.broker_status === 'PENDING' || run.order.broker_status === 'TRANSIT') return 'open';
  return 'failed';
}

function statusLabel(run) {
  if (!run.order) return 'No trade';
  const labels = {
    TRADED: 'Filled',
    PENDING: 'Pending',
    TRANSIT: 'In transit',
    REJECTED: 'Rejected',
    NOT_SENT: 'Not sent',
  };
  return labels[run.order.broker_status] || run.order.broker_status;
}

function renderSummary(data) {
  const { summary } = data;
  elements.summaryCopy.textContent = `${summary.no_trade} agents passed. ${summary.trade_attempts} proposed trades, but only ${summary.broker_calls} reached the broker and ${summary.broker_statuses.TRADED || 0} were immediately reported filled.`;

  const metrics = [
    ['Agent runs', summary.agent_runs, `${summary.unique_stocks} unique stocks`],
    ['No trade', summary.no_trade, 'Analysis only'],
    ['Trade attempts', summary.trade_attempts, 'Agent called or tried order tool'],
    ['Reached broker', summary.broker_calls, `${summary.not_sent} attempts were not sent`],
    ['Filled now', summary.broker_statuses.TRADED || 0, `${summary.broker_statuses.PENDING || 0} pending · ${summary.broker_statuses.TRANSIT || 0} transit`],
  ];

  const template = document.querySelector('#metric-template');
  const fragment = document.createDocumentFragment();
  for (const [label, value, detail] of metrics) {
    const node = template.content.cloneNode(true);
    node.querySelector('dt').textContent = label;
    node.querySelector('dd').textContent = formatNumber(value);
    node.querySelector('span').textContent = detail;
    fragment.append(node);
  }
  elements.summaryGrid.replaceChildren(fragment);
}

function matchesFilter(run) {
  const query = state.query.trim().toLocaleLowerCase();
  const textMatches = !query || `${run.name} ${run.symbol} ${run.security_id}`.toLocaleLowerCase().includes(query);
  return textMatches && (state.filter === 'all' || statusGroup(run) === state.filter);
}

function renderRunList() {
  const runs = state.data.runs.filter(matchesFilter);
  elements.visibleCount.textContent = String(runs.length);
  if (runs.length === 0) {
    elements.runList.innerHTML = '<p class="empty-list">No runs match this filter.</p>';
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const run of runs) {
    const group = statusGroup(run);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `run-button${run.number === state.selectedRun.number ? ' is-selected' : ''}`;
    button.dataset.runNumber = String(run.number);
    button.setAttribute('aria-pressed', String(run.number === state.selectedRun.number));
    button.innerHTML = `
      <span class="run-number">${String(run.number).padStart(2, '0')}</span>
      <span>
        <span class="run-name">${escapeHtml(run.name)}</span>
        <span class="run-meta"><time>${formatTime(run.signal.time)}</time><span>${escapeHtml(run.signal.direction || '—')}</span></span>
      </span>
      <span class="status-dot ${group}" title="${escapeHtml(statusLabel(run))}" aria-label="${escapeHtml(statusLabel(run))}"></span>
    `;
    fragment.append(button);
  }
  elements.runList.replaceChildren(fragment);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderMarkdown(source) {
  const lines = String(source || '').split(/\r?\n/);
  const output = [];
  let inList = false;
  let paragraph = [];

  const inline = (value) => escapeHtml(value)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
  const flushParagraph = () => {
    if (paragraph.length) output.push(`<p>${inline(paragraph.join(' '))}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (inList) output.push('</ul>');
    inList = false;
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const heading = line.match(/^#{1,4}\s+(.+)$/);
    const listItem = line.match(/^[-*]\s+(.+)$/);
    if (!line) {
      flushParagraph();
      closeList();
    } else if (heading) {
      flushParagraph();
      closeList();
      output.push(`<h3>${inline(heading[1])}</h3>`);
    } else if (listItem) {
      flushParagraph();
      if (!inList) output.push('<ul>');
      inList = true;
      output.push(`<li>${inline(listItem[1])}</li>`);
    } else if (!line.startsWith('|') && !/^[-:| ]+$/.test(line)) {
      paragraph.push(line.replace(/^\d+\.\s+/, ''));
    }
  }
  flushParagraph();
  closeList();
  return output.join('');
}

function fact(label, value) {
  return `<div class="fact"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function orderMarkup(run) {
  const { order } = run;
  if (!order) {
    return '<div class="pass-box">The agent analyzed the setup and deliberately placed no order.</div>';
  }
  const blocked = order.blocked_reason ? `<p class="blocked-reason">${escapeHtml(order.blocked_reason)}</p>` : '';
  return `
    <div class="order-box">
      <div class="order-side"><strong>${escapeHtml(order.side || '—')} ${formatNumber(order.quantity)} share${Number(order.quantity) === 1 ? '' : 's'}</strong><span>${escapeHtml(order.order_type || 'ORDER')}</span></div>
      <div class="price-stack">
        <div class="price-cell"><span>Entry</span><strong>${formatPrice(order.entry)}</strong></div>
        <div class="price-cell target"><span>Take profit</span><strong>${formatPrice(order.target)}</strong></div>
        <div class="price-cell stop"><span>Stop loss</span><strong>${formatPrice(order.stop)}</strong></div>
      </div>
      ${blocked}
    </div>`;
}

function renderReview(run) {
  if (state.chart) state.chart.destroy();
  const group = statusGroup(run);
  const order = run.order;
  const brokerTime = order?.attempted_at_epoch ? new Date(order.attempted_at_epoch * 1000).toISOString() : run.completed_at;
  const brokerTitle = !order ? 'No broker call' : order.reached_broker ? statusLabel(run) : 'Order not sent';
  const brokerDetail = !order
    ? 'Agent chose to pass.'
    : order.reached_broker
      ? `${formatNumber(order.filled_quantity)} filled at response time${order.order_id ? ` · order ${order.order_id}` : ''}`
      : order.blocked_reason || 'No broker response was recorded.';
  const indicators = run.signal.indicators.length
    ? run.signal.indicators.map((indicator) => `<span class="indicator-chip">${escapeHtml(indicator.type)} · ${formatTime(indicator.time)}</span>`).join('')
    : '<span class="indicator-chip">No named indicator event</span>';

  elements.review.innerHTML = `
    <header class="review-head">
      <div>
        <p class="run-kicker">RUN ${String(run.number).padStart(2, '0')} · ${formatTime(run.signal.time, true)} SYSTEM SIGNAL</p>
        <h2>${escapeHtml(run.name)}</h2>
        <span class="symbol">${escapeHtml(run.symbol)} · NSE security ${run.security_id}</span>
      </div>
      <span class="decision-badge ${group}"><span class="status-dot ${group}" aria-hidden="true"></span>${escapeHtml(statusLabel(run))}</span>
    </header>

    <section class="chart-panel" aria-labelledby="chart-heading">
      <div class="chart-head">
        <div class="chart-title"><strong id="chart-heading">15-minute price replay</strong><span>21 AUG 2026 · IST</span></div>
        <div class="chart-legend" aria-label="Chart legend">
          <span class="legend-item"><i class="legend-swatch signal"></i>System signal</span>
          <span class="legend-item"><i class="legend-swatch agent"></i>Agent order</span>
          ${order ? '<span class="legend-item"><i class="legend-swatch target"></i>Target</span><span class="legend-item"><i class="legend-swatch stop"></i>Stop</span>' : ''}
        </div>
      </div>
      <div class="chart-wrap">
        <canvas id="price-chart" role="img" aria-label="15-minute candlestick chart for ${escapeHtml(run.name)}, with the system signal and agent order levels marked"></canvas>
        <div class="chart-tooltip" id="chart-tooltip" hidden></div>
      </div>
      <p class="chart-note">Candles are aggregated from the system's recorded one-second last-price snapshots. Broker labels show the immediate response saved inside the agent run, not final end-of-day order history.</p>
    </section>

    <section class="timeline-strip" aria-label="Run timeline">
      <div class="timeline-step signal"><div class="timeline-label">1 · System alerted agent</div><div class="timeline-value">${formatTime(run.signal.time, true)} at ${formatPrice(run.signal.price)}</div><div class="timeline-detail">${escapeHtml(run.signal.direction)} setup · score ${formatNumber(run.signal.setup_score, 1)}</div></div>
      <div class="timeline-step agent"><div class="timeline-label">2 · Agent decided</div><div class="timeline-value">${formatTime(run.completed_at, true)} · ${order ? `${escapeHtml(order.side)} ${formatNumber(order.quantity)}` : 'Passed'}</div><div class="timeline-detail">${formatNumber(run.metrics.duration_seconds, 1)}s run · ${formatNumber(run.metrics.output_tokens)} output tokens</div></div>
      <div class="timeline-step ${group === 'failed' ? 'failed' : 'broker'}"><div class="timeline-label">3 · Broker response</div><div class="timeline-value">${escapeHtml(brokerTitle)}</div><div class="timeline-detail">${escapeHtml(brokerDetail)}</div></div>
    </section>

    <div class="detail-grid">
      <section class="detail-panel" aria-labelledby="agent-decision-title">
        <h3 id="agent-decision-title">What the agent said</h3>
        <div class="agent-copy">${renderMarkdown(run.content)}</div>
        <details class="reasoning">
          <summary>Show saved reasoning</summary>
          <div class="reasoning-copy">${escapeHtml(run.reasoning || 'No reasoning text was saved.')}</div>
        </details>
      </section>

      <div>
        <section class="detail-panel" aria-labelledby="order-title">
          <h3 id="order-title">Order record</h3>
          ${orderMarkup(run)}
          <table class="metrics-table">
            <tbody>
              <tr><th>Immediate status</th><td>${escapeHtml(statusLabel(run))}</td></tr>
              <tr><th>Broker call time</th><td>${formatTime(brokerTime, true)}</td></tr>
              <tr><th>Filled quantity</th><td>${order ? formatNumber(order.filled_quantity) : '—'}</td></tr>
              <tr><th>Run cost</th><td>${run.metrics.cost_usd === null ? '—' : `$${Number(run.metrics.cost_usd).toFixed(4)}`}</td></tr>
              <tr><th>Model</th><td>${escapeHtml(run.model || '—')}</td></tr>
            </tbody>
          </table>
        </section>

        <section class="detail-panel" aria-labelledby="signal-title" style="margin-top:14px">
          <h3 id="signal-title">Why the system sent it</h3>
          <dl class="signal-facts">
            ${fact('Trigger price', formatPrice(run.signal.price))}
            ${fact('Direction', run.signal.direction || '—')}
            ${fact('Readiness score', `${formatNumber(run.signal.setup_score, 1)} / 100`)}
            ${fact('VWAP', formatPrice(run.signal.vwap))}
            ${fact('Relative volume', `${formatNumber(run.signal.relative_volume, 2)}×`)}
            ${fact('Entry zone', (run.signal.entry_zone || []).map(formatPrice).join('–') || '—')}
          </dl>
          <div class="indicator-list">${indicators}</div>
        </section>
      </div>
    </div>

    <p class="source-note">Run ${run.run_id} · signal ${run.request_id}. This page preserves the original output. “Filled” means the placement response said TRADED at that moment.</p>
  `;

  const sameStockRuns = state.data.runs.filter((candidate) => candidate.security_id === run.security_id);
  state.chart = createChart({
    canvas: document.querySelector('#price-chart'),
    tooltip: document.querySelector('#chart-tooltip'),
    candles: state.data.candles[String(run.security_id)] || [],
    runs: sameStockRuns,
    selectedRun: run,
  });
}

function createChart({ canvas, tooltip, candles, runs, selectedRun }) {
  const context = canvas.getContext('2d');
  const listeners = [];
  let geometry = null;

  function priceLevels() {
    const levels = [];
    for (const run of runs) {
      if (run.signal.price !== null) levels.push(Number(run.signal.price));
      if (run.order) levels.push(Number(run.order.entry), Number(run.order.target), Number(run.order.stop));
    }
    return levels.filter(Number.isFinite);
  }

  function draw() {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.max(1, Math.round(rect.width * ratio));
    canvas.height = Math.max(1, Math.round(rect.height * ratio));
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const width = rect.width;
    const height = rect.height;
    const margin = { top: 34, right: 76, bottom: 52, left: 58 };
    const volumeHeight = 52;
    const priceBottom = height - margin.bottom - volumeHeight - 14;
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = priceBottom - margin.top;
    const allPrices = candles.flatMap((candle) => [candle.high, candle.low]).concat(priceLevels());
    const rawMin = Math.min(...allPrices);
    const rawMax = Math.max(...allPrices);
    const padding = Math.max((rawMax - rawMin) * 0.09, rawMax * 0.002);
    const minPrice = rawMin - padding;
    const maxPrice = rawMax + padding;
    const maxVolume = Math.max(1, ...candles.map((candle) => candle.volume));
    const step = plotWidth / Math.max(candles.length, 1);
    const candleWidth = Math.max(3, Math.min(13, step * 0.58));
    const xForIndex = (index) => margin.left + step * (index + 0.5);
    const yForPrice = (price) => margin.top + ((maxPrice - price) / (maxPrice - minPrice)) * plotHeight;
    const startTime = new Date(candles[0]?.time).getTime();
    const endTime = new Date(candles[candles.length - 1]?.time).getTime() + 15 * 60 * 1000;
    const xForTime = (value) => margin.left + ((new Date(value).getTime() - startTime) / (endTime - startTime)) * plotWidth;

    context.fillStyle = COLORS.bg;
    context.fillRect(0, 0, width, height);
    context.font = '10px Consolas, monospace';
    context.textBaseline = 'middle';

    for (let index = 0; index <= 5; index += 1) {
      const y = margin.top + (plotHeight / 5) * index;
      const price = maxPrice - ((maxPrice - minPrice) / 5) * index;
      context.strokeStyle = COLORS.grid;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(margin.left, y);
      context.lineTo(width - margin.right, y);
      context.stroke();
      context.fillStyle = COLORS.text;
      context.textAlign = 'right';
      context.fillText(price.toFixed(2), margin.left - 8, y);
    }

    candles.forEach((candle, index) => {
      const x = xForIndex(index);
      const up = candle.close >= candle.open;
      const color = up ? COLORS.up : COLORS.down;
      const openY = yForPrice(candle.open);
      const closeY = yForPrice(candle.close);
      context.strokeStyle = color;
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(x, yForPrice(candle.high));
      context.lineTo(x, yForPrice(candle.low));
      context.stroke();
      context.fillStyle = color;
      context.fillRect(x - candleWidth / 2, Math.min(openY, closeY), candleWidth, Math.max(2, Math.abs(closeY - openY)));

      const volumeY = height - margin.bottom - (candle.volume / maxVolume) * volumeHeight;
      context.globalAlpha = 0.45;
      context.fillRect(x - candleWidth / 2, volumeY, candleWidth, height - margin.bottom - volumeY);
      context.globalAlpha = 1;

      if (index % 4 === 0) {
        context.fillStyle = COLORS.text;
        context.textAlign = 'center';
        context.fillText(formatTime(candle.time), x, height - 27);
      }
    });

    context.strokeStyle = COLORS.grid;
    context.beginPath();
    context.moveTo(margin.left, height - margin.bottom);
    context.lineTo(width - margin.right, height - margin.bottom);
    context.stroke();

    drawRunMarkers({ context, runs, selectedRun, xForTime, yForPrice, width, right: margin.right, top: margin.top, bottom: priceBottom });
    geometry = { margin, step, xForIndex, candles, width, height };
  }

  function pointerMove(event) {
    if (!geometry || !geometry.candles.length) return;
    const rect = canvas.getBoundingClientRect();
    const pointerX = event.clientX - rect.left;
    const rawIndex = (pointerX - geometry.margin.left) / geometry.step - 0.5;
    const index = Math.max(0, Math.min(geometry.candles.length - 1, Math.round(rawIndex)));
    const candle = geometry.candles[index];
    const x = geometry.xForIndex(index);
    tooltip.innerHTML = `${formatTime(candle.time)}<br>O ${formatPrice(candle.open)} · H ${formatPrice(candle.high)}<br>L ${formatPrice(candle.low)} · C ${formatPrice(candle.close)}`;
    tooltip.hidden = false;
    const tooltipWidth = 190;
    tooltip.style.left = `${Math.min(Math.max(x + 10, 8), geometry.width - tooltipWidth)}px`;
    tooltip.style.top = '12px';
  }

  function pointerLeave() { tooltip.hidden = true; }
  const observer = new ResizeObserver(draw);
  observer.observe(canvas);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerleave', pointerLeave);
  listeners.push(['pointermove', pointerMove], ['pointerleave', pointerLeave]);
  draw();

  return {
    destroy() {
      observer.disconnect();
      for (const [name, listener] of listeners) canvas.removeEventListener(name, listener);
    },
  };
}

function drawRunMarkers({ context, runs, selectedRun, xForTime, yForPrice, width, right, top, bottom }) {
  const levelLabels = [];
  for (const run of runs) {
    const selected = run.number === selectedRun.number;
    const signalX = xForTime(run.signal.time);
    context.save();
    context.globalAlpha = selected ? 1 : 0.35;
    context.strokeStyle = COLORS.signal;
    context.lineWidth = selected ? 1.5 : 1;
    context.setLineDash([4, 4]);
    context.beginPath();
    context.moveTo(signalX, top);
    context.lineTo(signalX, bottom);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = COLORS.signal;
    context.beginPath();
    context.arc(signalX, yForPrice(Number(run.signal.price)), selected ? 5 : 3, 0, Math.PI * 2);
    context.fill();
    if (selected) drawTag(context, signalX, top + 5, `SYSTEM ${formatTime(run.signal.time)}`, COLORS.signal, COLORS.bg);
    context.restore();

    if (!run.order) continue;
    const orderTime = run.order.attempted_at_epoch ? new Date(run.order.attempted_at_epoch * 1000).toISOString() : run.completed_at;
    const orderX = xForTime(orderTime);
    context.save();
    context.globalAlpha = selected ? 1 : 0.3;
    context.strokeStyle = COLORS.agent;
    context.lineWidth = selected ? 1.5 : 1;
    context.beginPath();
    context.moveTo(orderX, top);
    context.lineTo(orderX, bottom);
    context.stroke();
    context.fillStyle = COLORS.agent;
    context.beginPath();
    context.arc(orderX, yForPrice(Number(run.order.entry)), selected ? 5 : 3, 0, Math.PI * 2);
    context.fill();
    if (selected) {
      drawTag(context, orderX, top + 27, `AGENT ${run.order.side} ${formatTime(orderTime)}`, COLORS.agent, COLORS.bg);
      levelLabels.push(
        { label: `TARGET ${formatPrice(run.order.target)}`, price: Number(run.order.target), color: COLORS.target, dash: [6, 4] },
        { label: `ENTRY ${formatPrice(run.order.entry)}`, price: Number(run.order.entry), color: COLORS.agent, dash: [] },
        { label: `STOP ${formatPrice(run.order.stop)}`, price: Number(run.order.stop), color: COLORS.stop, dash: [3, 3] },
      );
    }
    context.restore();
  }

  for (const level of levelLabels) {
    const y = yForPrice(level.price);
    context.strokeStyle = level.color;
    context.lineWidth = 1;
    context.setLineDash(level.dash);
    context.beginPath();
    context.moveTo(58, y);
    context.lineTo(width - right, y);
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = level.color;
    context.textAlign = 'left';
    context.font = '700 9px Consolas, monospace';
    context.fillText(level.label, width - right + 6, y);
  }
}

function drawTag(context, x, y, label, background, foreground) {
  context.font = '700 9px Consolas, monospace';
  const width = context.measureText(label).width + 12;
  const left = Math.max(58, Math.min(x + 5, context.canvas.clientWidth - width - 78));
  context.fillStyle = background;
  context.fillRect(left, y, width, 17);
  context.fillStyle = foreground;
  context.textAlign = 'left';
  context.fillText(label, left + 6, y + 8.5);
}

function selectRun(number, { updateHash = true } = {}) {
  const run = state.data.runs.find((candidate) => candidate.number === number);
  if (!run) return;
  state.selectedRun = run;
  if (updateHash) history.replaceState(null, '', `#run-${number}`);
  renderRunList();
  renderReview(run);
}

function bindEvents() {
  elements.runList.addEventListener('click', (event) => {
    const button = event.target.closest('[data-run-number]');
    if (button) selectRun(Number.parseInt(button.dataset.runNumber, 10));
  });

  elements.search.addEventListener('input', () => {
    state.query = elements.search.value;
    renderRunList();
  });

  for (const button of elements.filters) {
    button.addEventListener('click', () => {
      state.filter = button.dataset.filter;
      for (const candidate of elements.filters) {
        const active = candidate === button;
        candidate.classList.toggle('is-active', active);
        candidate.setAttribute('aria-pressed', String(active));
      }
      renderRunList();
    });
  }
}

async function init() {
  try {
    state.data = await loadData();
    const hashMatch = location.hash.match(/^#run-(\d+)$/);
    const requestedNumber = hashMatch ? Number.parseInt(hashMatch[1], 10) : 1;
    state.selectedRun = state.data.runs.find((run) => run.number === requestedNumber) || state.data.runs[0];
    renderSummary(state.data);
    renderRunList();
    renderReview(state.selectedRun);
    bindEvents();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    elements.review.innerHTML = `<div class="error-state"><strong>The review could not open.</strong><br>${escapeHtml(message)}<br><br>Serve this folder through a local web server instead of opening index.html directly.</div>`;
  }
}

void init();
