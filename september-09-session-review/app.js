(() => {
  'use strict';
  const report = window.SESSION_REPORT;
  if (!report || !Array.isArray(report.stocks) || !Array.isArray(report.trades)) {
    document.querySelector('#metrics').textContent = 'Report data could not load. Keep data.js beside index.html.';
    return;
  }
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = (value, digits = 2) => value == null ? '—' : Number(value).toLocaleString('en-IN', {minimumFractionDigits:digits, maximumFractionDigits:digits});
  const clock = (seconds) => seconds == null ? '—' : new Date(seconds * 1000).toLocaleTimeString('en-GB', {timeZone:'Asia/Kolkata',hour12:false});
  const money = (value) => value == null ? 'Open' : `${value < 0 ? '−' : '+'}₹${num(Math.abs(value))}`;
  const issues = new Set(['unprotected_open','cancelled_protection','orphan_pending','missing_legs','unverified']);
  const labels = {stop_exit:'SL exit confirmed',target_exit:'Target exit confirmed',unfilled:'Entry never filled',unprotected_open:'Open, SL cancelled',cancelled_protection:'Separate exit, SL cancelled',orphan_pending:'Closed, legs still pending',missing_legs:'Missing protective leg',unverified:'Lifecycle unverified'};
  const reasonLabels = {account_analysis_capacity_in_use:'Analysis capacity occupied',maximum_concurrent_trade_slots_in_use:'Trade slots full',assigned_stock_open_intraday_position_exists:'Position already open',assigned_stock_analysis_already_active:'Analysis already active',assigned_stock_active_order_exists:'Order already active',margin_allocation_too_small:'Insufficient allocation',user_depth_unavailable:'Depth unavailable',dhan_authorization_or_ip_unavailable:'Broker authorization/IP blocked',not_dispatched:'Dispatch capacity blocked',ai_ran:'AI analysed'};
  const stockByKey = new Map(report.stocks.map(s => [s.key,s]));
  const tradeById = new Map(report.trades.map(t => [t.order_id,t]));
  let selectedKey = stockByKey.has('BSE_EQ|509488') ? 'BSE_EQ|509488' : report.stocks[0].key;
  let selectedSignal = null;
  let selectedTrade = null;
  let filteredStocks = report.stocks;
  const badge = (trade) => `<span class="badge ${issues.has(trade.protection) ? (trade.protection === 'orphan_pending' ? 'warn' : 'bad') : ''}">${esc(labels[trade.protection] || trade.protection)}</span>`;

  function overview() {
    const s = report.stats;
    const metrics = [[s.signals,'Signals',`${s.stocks} unique stocks`],[s.ai_runs,'AI runs','659 workflow dispatches'],[s.filled_entries,'Filled entries',`${s.submitted_orders} submitted orders`],[`${s.wins} / ${s.losses}`,'Wins / losses','22 closed entries'],[money(s.realized_pnl),'Realized P&L','Before fees; TCC excluded'],['26 / 26','Initial TP + SL','Prices match broker']];
    $('metrics').innerHTML = metrics.map(([v,l,n]) => `<div class="metric"><span class="metric-value">${esc(v)}</span><span class="metric-label">${esc(l)}</span><small class="metric-sub">${esc(n)}</small></div>`).join('');
    const points = [
      `Signal to actual AI start: median ${num(s.signal_to_ai_median_seconds,1)} seconds, maximum ${num(s.signal_to_ai_max_seconds,1)} seconds. Median first order attempt: ${num(s.signal_to_first_order_attempt_median_seconds,1)} seconds after signal.`,
      `${num(s.packet_delay_over250_pct,1)}% of packets waited over 250 ms. Session maximum was ${num(report.stage2.max_ingress_delay_ms / 1000,2)} seconds, with one reconnect at 14:27.`,
      `All 660 durable signals agree with the daily counter. Longest confirmation was ${num(s.max_confirmation_seconds,2)} seconds; the hour-long armed timers seen previously did not recur.`,
      `${report.stage2.opening_range_complete} / ${report.stage2.expected_instruments} opening ranges were verified. Recovery succeeded 785 times and failed 2,989 times, mostly because the full opening window was missing.`,
      `Today used the September 8 universe. The morning scan did not publish in time; the September 9 profile report was generated after market close.`,
      `For ${s.outcome_count} signals with follow-up, median next-five-minute price range was ${num(s.median_next_5m_range_pct)}%. ${num(s.positive_direction_5m_pct,1)}% ended in the detector's direction. These are price observations, not trade profits.`,
      `64 later events were blocked by authorization/IP checks, starting at 14:28. Successful feed collection did not mean the account could continue trading.`
    ];
    $('observations').innerHTML = points.map(p => `<li>${esc(p)}</li>`).join('');
    $('funnel').innerHTML = [['Trade slots already full',417],['Analysis capacity occupied',114],['Authorization / IP unavailable',64],['Actual AI analyses',35],['Other admission blocks',29],['Not dispatched',1]].map(([label,count]) => `<div class="funnel-row"><span>${label}</span><strong>${count}</strong></div>`).join('');
    $('open-positions').innerHTML = report.open_positions.map(p => `<div class="position-row"><strong>${esc(p.tradingSymbol)} · ${esc(p.exchangeSegment)} · ${esc(p.securityId)}</strong><span>${p.netQty > 0 ? 'LONG' : 'SHORT'} ${Math.abs(p.netQty)} shares</span><span>Open P&L ${money(p.unrealizedProfit)}</span></div>`).join('');
    $('limitations').innerHTML = report.limitations.map(t => `<li>${esc(t)}</li>`).join('');
    $('source-links').innerHTML = report.sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noreferrer">${esc(s.name)} ↗</a>`).join('');
    $('provenance').textContent = `Broker snapshot: ${new Date(report.broker_as_of).toLocaleString('en-GB',{timeZone:'Asia/Kolkata'})} IST. ${report.chart_files} recorded-price files. Signal, order and trade-book identifiers are preserved in the audit. Account credentials and identifiers are excluded from this report.`;
  }

  function selectStock(key, signalId = null, orderId = null, scroll = false) {
    const stock = stockByKey.get(key);
    if (!stock) return;
    selectedKey = key;
    selectedSignal = signalId || stock.signals.find(s => s.run.agent_start)?.id || stock.signals[0]?.id;
    selectedTrade = orderId || stock.trades[0] || null;
    $('stock-identity').textContent = `${stock.exchange} · Security ${key.split('|')[1]}`;
    $('stock-name').textContent = stock.name;
    $('stock-meta').textContent = `${stock.signals.length} signals · ${stock.signals.filter(s => s.run.agent_start).length} AI runs · ${stock.trades.length} submitted orders · ${stock.observations.toLocaleString()} recorded observations`;
    const problemTrades = stock.trades.map(id => tradeById.get(id)).filter(t => issues.has(t.protection));
    $('stock-warning').innerHTML = problemTrades.map(t => `<div class="stock-alert"><strong>${esc(labels[t.protection])}.</strong> ${esc(t.explanation)}</div>`).join('');
    $('trade-select').innerHTML = '<option value="">No levels</option>' + stock.trades.map(id => {const t=tradeById.get(id);return `<option value="${esc(id)}">${clock(t.entry_time || t.submitted)} · ${t.side} ${t.quantity}${t.filled_quantity ? '' : ' · unfilled'}</option>`;}).join('');
    $('trade-select').value = selectedTrade || '';
    $('trade-select').disabled = stock.trades.length === 0;
    $('only-runs').checked = false;
    filterStocks();
    renderSignals();
    renderChart();
    renderSelectedEvent();
    if (scroll) $('explorer').scrollIntoView({block:'start'});
  }

  function filterStocks() {
    const query = $('stock-search').value.toLowerCase().trim();
    const mode = $('stock-filter').value;
    filteredStocks = report.stocks.filter(s => `${s.name} ${s.symbol} ${s.key}`.toLowerCase().includes(query)
      && (mode !== 'runs' || s.signals.some(e => e.run.agent_start))
      && (mode !== 'trades' || s.trades.length > 0)
      && (mode !== 'issues' || s.trades.some(id => issues.has(tradeById.get(id).protection))));
    $('stock-count').textContent = `${filteredStocks.length} of ${report.stocks.length} stocks`;
    $('stock-list').innerHTML = filteredStocks.length ? filteredStocks.map(s => `<button class="stock-item" data-key="${esc(s.key)}" aria-pressed="${s.key === selectedKey}">${esc(s.name)} ${s.trades.some(id => issues.has(tradeById.get(id).protection)) ? '<b class="alert-dot">!</b>' : ''}<span>${s.exchange.replace('_EQ','')} · ${s.signals.length} signals · ${s.trades.length} orders</span></button>`).join('') : '<p class="empty">No stocks match this filter.</p>';
    const index = filteredStocks.findIndex(s => s.key === selectedKey);
    $('previous-stock').disabled = index <= 0;
    $('next-stock').disabled = index < 0 || index >= filteredStocks.length - 1;
  }

  function renderSignals() {
    const stock = stockByKey.get(selectedKey);
    const rows = stock.signals.filter(s => !$('only-runs').checked || s.run.agent_start);
    $('signal-rows').innerHTML = rows.length ? rows.map(s => `<tr class="${s.id === selectedSignal ? 'selected-row' : ''}"><td><button data-signal="${s.id}">${clock(s.time)}</button></td><td>${esc(s.family.replaceAll('_',' '))}<br><span class="muted">Detector ${s.direction.toLowerCase()} · rank ${s.rank ?? '—'}</span></td><td>${num(s.price)}</td><td>${clock(s.run.agent_start)}</td><td>${s.run.agent_start ? `${num(s.run.agent_start - s.time,1)}s` : '—'}</td><td>${esc(s.run.agent_start ? s.run.decision.execution_status : reasonLabels[s.run.reason] || s.run.reason)}</td></tr>`).join('') : '<tr><td colspan="6" class="empty">No AI analyses for this stock.</td></tr>';
  }

  function renderSelectedEvent() {
    const stock = stockByKey.get(selectedKey);
    const event = stock.signals.find(s => s.id === selectedSignal);
    if (!event) { $('selected-event').textContent = 'Select a signal to inspect its timeline.'; return; }
    const trade = stock.trades.map(id => tradeById.get(id)).find(t => t.event_id === event.id);
    $('selected-event').innerHTML = `<div class="event-top"><strong>${esc(event.family.replaceAll('_',' '))} · ${clock(event.time)}</strong><span>${esc(event.run.agent_start ? `AI: ${event.run.decision.trade_side || event.run.decision.action}` : reasonLabels[event.run.reason] || event.run.reason)}</span></div><div class="timing-strip"><div><small>Signal at ₹${num(event.price)}</small><strong>${clock(event.time)}</strong></div><div><small>Preparation started</small><strong>${clock(event.run.preparation_start)}</strong></div><div><small>Actual AI run started</small><strong>${clock(event.run.agent_start)}</strong></div><div><small>${trade?.filled_quantity ? 'First entry fill' : 'Order submitted'}</small><strong>${clock(trade?.entry_time || trade?.submitted)}</strong></div></div>${event.run.report ? `<details><summary>Read the AI report and order attempts</summary><pre>${esc(event.run.report)}</pre>${(event.run.attempts || []).map(a => `<details><summary>${clock(a.tool_time)} · ${esc(a.args.side)} · ${esc(a.status)}${a.reason ? ` · ${esc(a.reason)}` : ''}</summary><pre>${esc(JSON.stringify(a.args,null,2))}\n\n${esc(a.result)}</pre></details>`).join('')}</details>` : ''}`;
  }

  function groupedBars(bars, interval) {
    if (interval === 1) return bars;
    const groups = new Map();
    for (const b of bars) {
      const bucket = Math.floor(b.t / (interval * 60)) * interval * 60;
      const current = groups.get(bucket);
      if (!current) groups.set(bucket,{...b,t:bucket});
      else { current.h=Math.max(current.h,b.h);current.l=Math.min(current.l,b.l);current.c=b.c;current.vwap=b.vwap;current.volume+=b.volume; }
    }
    return [...groups.values()];
  }

  function renderChart() {
    const stock = stockByKey.get(selectedKey);
    const event = stock.signals.find(s => s.id === selectedSignal);
    const trade = selectedTrade ? tradeById.get(selectedTrade) : null;
    const interval = Number($('chart-interval').value);
    const dayStart = Date.parse(`${report.date}T09:15:00+05:30`) / 1000;
    const dayEnd = Date.parse(`${report.date}T15:30:00+05:30`) / 1000;
    let start=dayStart,end=dayEnd;
    if ($('chart-window').value === 'signal' && event) {start=Math.max(dayStart,event.time-900);end=Math.min(dayEnd,event.time+900);}
    if ($('chart-window').value === 'trade' && trade) {start=Math.max(dayStart,(trade.entry_time || trade.submitted)-600);end=Math.min(dayEnd,(trade.exit_time || dayEnd)+600);}
    const bars = groupedBars(stock.bars,interval).filter(b => b.t >= start - interval*60 && b.t <= end);
    if (!bars.length) { $('chart').innerHTML='<p class="empty">No recorded candles in this window. Select the full session.</p>';return; }
    const width=1040,height=485,left=65,right=92,top=68,priceBottom=370,volumeTop=392,bottom=438;
    const values=bars.flatMap(b=>[b.h,b.l]);
    if (trade) values.push(trade.stop,trade.target,trade.entry_price || trade.planned_entry);
    let low=Math.min(...values.filter(Number.isFinite)),high=Math.max(...values.filter(Number.isFinite));
    const pad=Math.max((high-low)*.1,high*.002);low-=pad;high+=pad;
    const x=t=>left+(t-start)/(end-start)*(width-left-right);
    const y=p=>top+(high-p)/(high-low)*(priceBottom-top);
    const candleWidth=Math.max(1,Math.min(12,(width-left-right)/(end-start)*interval*60*.65));
    const parts=[`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(stock.name)} price chart with signal, AI and fill markers"><title>${esc(stock.name)} · ${report.date} · ${interval}-minute observed candles</title><defs><clipPath id="plot"><rect x="${left}" y="${top}" width="${width-left-right}" height="${priceBottom-top}"/></clipPath></defs>`];
    for(let i=0;i<=5;i++){const p=low+(high-low)*i/5;parts.push(`<line x1="${left}" x2="${width-right}" y1="${y(p)}" y2="${y(p)}" stroke="#e2e7df"/><text x="${left-10}" y="${y(p)+3}" text-anchor="end" fill="#647065">${num(p)}</text>`);}
    const step=end-start>7200?3600:600;
    for(let t=Math.ceil(start/step)*step;t<=end;t+=step){parts.push(`<line x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${bottom}" stroke="#eef0eb"/><text x="${x(t)}" y="${bottom+23}" text-anchor="middle" fill="#647065">${clock(t).slice(0,5)}</text>`);}
    const maxVolume=Math.max(1,...bars.map(b=>b.volume||0));
    for(const b of bars){if(b.t<start || b.t>end)continue;const colour=b.c>=b.o?'#2a8561':'#bc5960';const xx=x(b.t);parts.push(`<g><title>${clock(b.t)} IST\nO ${num(b.o)} H ${num(b.h)} L ${num(b.l)} C ${num(b.c)}\nObserved volume change ${num(b.volume,0)}</title><line x1="${xx}" x2="${xx}" y1="${y(b.h)}" y2="${y(b.l)}" stroke="${colour}"/><rect x="${xx-candleWidth/2}" y="${Math.min(y(b.o),y(b.c))}" width="${candleWidth}" height="${Math.max(1,Math.abs(y(b.o)-y(b.c)))}" fill="${colour}"/><rect x="${xx-candleWidth/2}" y="${bottom-(b.volume||0)/maxVolume*(bottom-volumeTop)}" width="${candleWidth}" height="${(b.volume||0)/maxVolume*(bottom-volumeTop)}" fill="${colour}" opacity=".25"/></g>`);}
    let path='';let previous=null;
    for(const b of bars){if(!Number.isFinite(b.vwap)||b.vwap<low||b.vwap>high){previous=null;continue;}path+=`${previous !== null && b.t-previous<=interval*90?'L':'M'}${x(b.t).toFixed(1)},${y(b.vwap).toFixed(1)} `;previous=b.t;}
    parts.push(`<path d="${path}" fill="none" stroke="#ad924f" stroke-width="1.2" clip-path="url(#plot)"/>`);
    if(trade){const from=Math.max(start,trade.entry_time || trade.submitted),to=Math.min(end,trade.exit_time || dayEnd);for(const [label,price,colour] of [['Initial TP',trade.target,'#176d4e'],['Initial SL',trade.stop,'#b52d34'],['Entry',trade.entry_price || trade.planned_entry,'#526465']]){if(price!=null&&from<=to)parts.push(`<line x1="${x(from)}" x2="${x(to)}" y1="${y(price)}" y2="${y(price)}" stroke="${colour}" stroke-dasharray="5 4"/><text x="${width-right+6}" y="${y(price)+3}" fill="${colour}">${label} ${num(price)}</text>`);}}
    const markers=[];
    for(const s of stock.signals){markers.push({t:s.time,p:s.price,lane:0,kind:'signal',label:`Signal · ${s.family} · detector ${s.direction}`,id:s.id});if(s.run.agent_start)markers.push({t:s.run.agent_start,lane:1,kind:'ai',label:'AI run started',id:s.id});}
    for(const id of stock.trades){const t=tradeById.get(id);if(t.entry_time)markers.push({t:t.entry_time,p:t.entry_price,lane:2,kind:'entry',label:`${t.side} ${t.filled_quantity} · entry fill · ${t.order_id}`});if(t.exit_time)markers.push({t:t.exit_time,p:t.exit_price,lane:3,kind:'exit',label:`Exit fill${t.standalone_exit?' · separate order':''} · ${t.order_id}`});}
    const colours={signal:'#ab750d',ai:'#2468b4',entry:'#176d4e',exit:'#526465'};
    for(const m of markers){if(m.t<start||m.t>end)continue;const xx=x(m.t),yy=16+m.lane*12,colour=colours[m.kind];const selected=m.id===selectedSignal;parts.push(`<g ${m.id?`data-chart-signal="${esc(m.id)}" style="cursor:pointer"`:''}><title>${esc(m.label)}\n${clock(m.t)} IST${m.p!=null?` · ₹${num(m.p)}`:''}</title><line x1="${xx}" x2="${xx}" y1="${yy+4}" y2="${m.p!=null?Math.max(top,Math.min(priceBottom,y(m.p))):priceBottom}" stroke="${colour}" opacity="${selected ? .5 : .16}" stroke-dasharray="2 4"/>`);if(m.kind==='signal')parts.push(`<path d="M${xx} ${yy-4}l4 4 -4 4 -4 -4z" fill="${colour}"/>`);else if(m.kind==='ai')parts.push(`<circle cx="${xx}" cy="${yy}" r="4" fill="${colour}"/>`);else if(m.kind==='entry')parts.push(`<rect x="${xx-4}" y="${yy-4}" width="8" height="8" fill="${colour}"/>`);else parts.push(`<path d="M${xx-4} ${yy-4}l8 8m-8 0l8 -8" stroke="${colour}" stroke-width="2"/>`);if(m.p!=null && m.p>=low && m.p<=high)parts.push(`<circle cx="${xx}" cy="${y(m.p)}" r="${selected?4:2.5}" fill="${colour}" stroke="white" stroke-width="1"/>`);parts.push('</g>');}
    parts.push(`<text x="${left}" y="${height-7}" fill="#647065">Time · IST</text><text x="${left}" y="${volumeTop-4}" fill="#647065">Observed volume</text></svg>`);
    $('chart').innerHTML=parts.join('');
  }

  function renderAudit() {
    const mode=$('audit-filter').value;
    const rows=report.trades.filter(t=>mode==='all'||mode==='issues'&&issues.has(t.protection)||mode==='filled'&&t.filled_quantity>0||mode==='unfilled'&&!t.filled_quantity);
    $('audit-rows').innerHTML=rows.map(t=>`<tr><td><strong>${esc(t.name)}</strong><small>${esc(t.key)}</small></td><td>${t.side} ${t.filled_quantity} / ${t.quantity}<small>${t.order_type}</small></td><td>${t.entry_time?`₹${num(t.entry_price)}`:'Unfilled'}<small>${clock(t.entry_time)}</small></td><td>TP ${num(t.target)}<br>SL ${num(t.stop)}${t.trailing_jump?`<small>Trail jump ${num(t.trailing_jump)}</small>`:''}</td><td>${esc(t.stop_status)}<br>${esc(t.target_status)}</td><td>${badge(t)}</td><td class="${t.realized_pnl<0?'negative':'positive'}">${t.filled_quantity?money(t.realized_pnl):'—'}</td><td><button data-order="${esc(t.order_id)}">Evidence</button></td></tr>`).join('');
  }

  function renderOrder(id,scroll=false) {
    const t=tradeById.get(id);if(!t)return;
    const attempt=stockByKey.get(t.key).signals.find(s=>s.id===t.event_id)?.run.attempts?.find(a=>a.order_id===id);
    const waits=t.linked_orders.filter(o=>o.orderStatus==='TRADED').map(o=>`${o.orderId}: ${num((timestampFromBroker(o.updateTime)-timestampFromBroker(o.createTime)),0)} seconds from recorded order creation to last update.`);
    $('order-evidence').innerHTML=`<div class="event-top"><h3>${esc(t.name)} · ${t.side} ${t.quantity}</h3>${badge(t)}</div><p>${esc(t.explanation)}</p><dl class="order-facts"><div><dt>Order ID</dt><dd>${t.order_id}</dd></div><div><dt>Submitted / first fill</dt><dd>${clock(t.submitted)} / ${clock(t.entry_time)}</dd></div><div><dt>Initial target / stop</dt><dd>${num(t.target)} / ${num(t.stop)}</dd></div><div><dt>Same-venue net quantity now</dt><dd>${t.same_venue_open_quantity}</dd></div></dl><p><strong>Entry checks:</strong> ${t.geometry_valid?'Correct price geometry':'Invalid price geometry'} · ${t.broker_prices_match?'Broker TP/SL match request':'Broker price mismatch'} · ${t.initial_legs_confirmed?'Both legs returned PENDING at submission':'Initial pending legs not confirmed'}.</p><p><strong>Exit:</strong> ${t.exit_time?`${clock(t.exit_time)} at ₹${num(t.exit_price)}${t.standalone_exit?' through a separate order, not a linked protective fill':''}.`:'No confirmed same-venue exit fill.'} ${t.realized_pnl!=null?`Realized ${money(t.realized_pnl)} before fees.`:''}</p>${waits.length?`<p class="fine">${esc(waits.join(' '))} These timestamps do not prove the exact trigger or modification time.</p>`:''}<button data-trade-chart="${t.order_id}">Show this trade on the chart ↑</button><details><summary>Broker entry, linked child orders and fills</summary><pre>${esc(JSON.stringify({entry:t.broker_entry,linked_orders:t.linked_orders,fills:t.fills},null,2))}</pre></details>${attempt?`<details><summary>AI order request and returned protection evidence</summary><pre>${esc(JSON.stringify(attempt.args,null,2))}\n\n${esc(attempt.result)}</pre></details>`:''}${t.symbol==='TCC'?`<details open><summary>Separate NSE orders, not a BSE exit</summary><pre>${esc(JSON.stringify(report.additional_orders,null,2))}</pre></details>`:''}`;
    if(scroll)$('order-evidence').scrollIntoView({block:'start'});
  }
  function timestampFromBroker(value){return Date.parse(`${value.replace(' ','T')}+05:30`)/1000;}
  function downloadCsv(){const keys=['name','key','order_id','side','quantity','filled_quantity','planned_entry','entry_price','stop','target','stop_status','target_status','initial_legs_confirmed','geometry_valid','broker_prices_match','protection','exit_price','realized_pnl','same_venue_open_quantity'];const csv=[keys.join(','),...report.trades.map(t=>keys.map(k=>`"${String(t[k]??'').replaceAll('"','""')}"`).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='2026-09-09-trade-protection-audit.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  document.addEventListener('click',event=>{const button=event.target.closest('[data-stock],[data-key],[data-signal],[data-chart-signal],[data-order],[data-trade-chart]');if(!button)return;if(button.dataset.stock)selectStock(button.dataset.stock,null,null,true);else if(button.dataset.key)selectStock(button.dataset.key);else if(button.dataset.signal||button.dataset.chartSignal){selectedSignal=button.dataset.signal||button.dataset.chartSignal;renderSignals();renderSelectedEvent();renderChart();}else if(button.dataset.order)renderOrder(button.dataset.order,true);else if(button.dataset.tradeChart){const t=tradeById.get(button.dataset.tradeChart);$('chart-window').value='trade';selectStock(t.key,t.event_id,t.order_id,true);}});
  $('stock-search').addEventListener('input',filterStocks);$('stock-filter').addEventListener('change',filterStocks);
  $('only-runs').addEventListener('change',renderSignals);$('chart-window').addEventListener('change',renderChart);$('chart-interval').addEventListener('change',renderChart);
  $('trade-select').addEventListener('change',()=>{selectedTrade=$('trade-select').value||null;if(selectedTrade){selectedSignal=tradeById.get(selectedTrade).event_id;renderSignals();renderSelectedEvent();}renderChart();});
  $('audit-filter').addEventListener('change',renderAudit);$('download-csv').addEventListener('click',downloadCsv);
  for(const [id,delta] of [['previous-stock',-1],['next-stock',1]])$(id).addEventListener('click',()=>{const index=filteredStocks.findIndex(s=>s.key===selectedKey);const next=filteredStocks[index+delta];if(next)selectStock(next.key);});
  overview();selectStock(selectedKey);renderAudit();renderOrder('23326090913072');
})();
