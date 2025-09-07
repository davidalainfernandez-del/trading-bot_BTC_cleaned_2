// --- i18n ultra-light ---
const I18N = {
  fr: {
    "autotrader_title": "Autotrader — En direct",
    "position": "Position",
    "last_decision": "Dernière décision",
    "hold": "attente",
    "buy": "achat",
    "sell": "vente",
    "tp": "take profit",
    "sl": "stop loss",
    "be_exit": "sortie break-even",
    "time_exit": "sortie temps",
    "tech_exit": "sortie technique",
    "p_up": "Probabilité de hausse",
    "ev": "Espérance (brute)",
    "ev_net": "Espérance nette",
    "cash": "Trésorerie",
    "btc": "BTC",
    "valuation": "Valorisation",
    "enabled": "Activé",
    "alive": "Vivant",
    // ...ajoute les quelques étiquettes que tu vois sur ta page
  }
};

function t(key){ return (I18N.fr && I18N.fr[key]) || key; }

// Applique automatiquement aux éléments ayant data-i18n
function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const k = el.getAttribute("data-i18n");
    el.textContent = t(k);
  });
}
document.addEventListener("DOMContentLoaded", applyI18n);


(function () {
  // Namespace commun
  if (!window.API) window.API = {};
  const NS = window.API;

  // ==========================
  // Patch global Chart.js (plafonne le DPR)
  // ==========================
  if (window.Chart && !window.__chartDprPatched) {
    Chart.defaults.devicePixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
    window.__chartDprPatched = true;
  }

  // ==========================
  // Utilitaires génériques
  // ==========================
 async function fetchPerfDay(){
  try{
    const r = await fetch('/api/perf/day', {credentials:'same-origin'});
    const j = await r.json();
    return (j && j.ok) ? j : null;
  }catch(_){ return null; }
}

function fmtUsd(v){
  if (v == null) return '—';
  const sign = (v > 0 ? '+' : (v < 0 ? '−' : ''));
  return `${sign}${Math.abs(+v).toFixed(2)} $`;
}
function fmtPct(v){ // v en fraction (0.0123 = 1.23 %)
  if (v == null) return '—';
  const sign = (v > 0 ? '+' : (v < 0 ? '−' : ''));
  return `${sign}${Math.abs(+v*100).toFixed(2)} %`;
}
function setTxt(id, val){
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function paintPosNeg(el, value){
  if (!el) return;
  el.style.color = (value == null) ? '' : (value > 0 ? '#2ecc71' : (value < 0 ? '#e74c3c' : ''));
}

async function refreshPerfPanel(){
  const j = await fetchPerfDay();
  if (!j) return;

  // trades
  const t = j.trades_today || {};
  const total = t.total ?? 0, buys = t.buys ?? 0, sells = t.sells ?? 0;
  setTxt('perf-trades', `${total} / ${buys} / ${sells}`);

  // pnl (usd & %)
  setTxt('perf-pnl-usd', fmtUsd(j.pnl_day_usd));
  setTxt('perf-pnl-pct', fmtPct(j.pnl_day_pct));
  paintPosNeg(document.getElementById('perf-pnl-usd'), j.pnl_day_usd);
  paintPosNeg(document.getElementById('perf-pnl-pct'), j.pnl_day_pct);

  // hit-rate (si dispo)
  const hr = (t.hit_rate == null ? '—' : `${(t.hit_rate*100).toFixed(1)} %`);
  setTxt('perf-hit', hr);

  // max drawdown (positif = amplitude de baisse)
  setTxt('perf-dd', fmtPct(j.dd_max_pct ?? 0));

  // horodatage
  const d = new Date();
  setTxt('perf-updated', d.toLocaleTimeString());

  // bouton reset base (optionnel)
  const btn = document.getElementById('perfResetBase');
  if (btn && !btn.dataset.bound){
    btn.dataset.bound = '1';
    btn.addEventListener('click', async ()=>{
      try{
        await fetch('/api/perf/reset_base', {method:'POST', credentials:'same-origin'});
        await refreshPerfPanel();
      }catch(_){}
    });
  }
}

  async function getJSON(url, opts) {
    const res = await fetch(url, Object.assign({ headers: { 'Accept': 'application/json' } }, opts));
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`[${res.status}] ${url} -> ${text.slice(0, 200)}`);
    }
    return res.json();
  }

  function $(sel) { return document.querySelector(sel); }
  function create(tag, attrs) {
    const el = document.createElement(tag);
    if (attrs) Object.assign(el, attrs);
    return el;
  }
  function fmtNum(x, d = 2) {
    if (x === null || x === undefined || Number.isNaN(x)) return '—';
    return Number(x).toFixed(d);
  }
  function fmtDate(ts) {
    try {
      const d = (typeof ts === 'number') ? new Date(ts) : new Date(ts);
      return d.toLocaleString();
    } catch { return String(ts); }
  }

  // --- Mini scheduler Auto (global) ---
  window.Auto = window.Auto || (() => {
    const timers = [];
    return {
      every(ms, fn) {
        try { fn(); } catch(_) {}
        const id = setInterval(() => { try { fn(); } catch(_) {} }, ms);
        timers.push(id);
        return id;
      },
      clear() { while (timers.length) clearInterval(timers.pop()); }
    };
  })();

  // ==========================
  // Endpoints Flask réels (sentiment/timeline/corr/social)
  // ==========================
  NS.fetchSentimentSnapshot = function () { return getJSON('/api/sentiment'); };
  NS.fetchSentimentTimeline = function () { return getJSON('/api/sentiment_price'); };
  NS.fetchCorrelation       = function () { return getJSON('/api/sentiment_correlation'); };
  NS.fetchSocialSentiments  = function () { return getJSON('/tweets-sentiment'); };

  // ==========================
  // Rendu DOM (best-effort)
  // ==========================
  function renderSnapshot(data) {
    const target = $('#sentiment-snapshot') || $('[data-sentiment-snapshot]');
    if (!target) return;

    target.innerHTML = '';
    const table = create('table', { className: 'sentiment-snapshot-table' });
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';

    function row(k, v) {
      const tr = create('tr');
      const tdK = create('td'); tdK.textContent = k; tdK.style.fontWeight = '600';
      const tdV = create('td'); tdV.textContent = (typeof v === 'number') ? fmtNum(v) : (v ?? '');
      tdK.style.borderBottom = tdV.style.borderBottom = '1px solid #ddd';
      tdK.style.padding = tdV.style.padding = '6px 8px';
      tr.append(tdK, tdV);
      table.append(tr);
    }

    if (data && typeof data === 'object') {
      Object.keys(data).forEach(k => row(k, data[k]));
    } else {
      row('raw', JSON.stringify(data));
    }

    target.append(table);
  }

function renderCorrelation(obj){
  const el = document.querySelector("#correlation_card h5");
  if (!el) return;
  const v = obj?.correlation ?? obj?.corr ?? obj?.value ?? obj?.v; // <-- ajoute obj.corr
  el.textContent = (Number.isFinite(v) ? v.toFixed(4) : "—");
}

  function renderSocial(list) {
    const box = $('#socialList') || $('[data-social-list]');
    if (!box) return;
    box.innerHTML = '';

    const ul = create('ul');
    ul.style.listStyle = 'none';
    ul.style.padding = '0';

    (Array.isArray(list) ? list : []).slice(0, 50).forEach(item => {
      const li = create('li');
      li.style.borderBottom = '1px solid #eee';
      li.style.padding = '8px 6px';
      const score = typeof item.score === 'number' ? fmtNum(item.score, 2) : '—';
      const text = item.text || item.tweet || item.content || '';
      li.textContent = `[${score}] ${text}`;
      ul.append(li);
    });

    if (!ul.childElementCount) {
      const li = create('li', { textContent: 'Aucune donnée sociale.' });
      ul.append(li);
    }

    box.append(ul);
  }

  // --- Timeline -> graphique (Chart.js direct, mais avec tailles sûres) ---
  let chartInstance = null;
  function renderTimeline(series) {
    const data = Array.isArray(series) ? series : [];
    const canvas = $('#sentimentChart') || $('#lstmCanvas') || document.querySelector('canvas[data-sentiment-chart]');
    const tableTarget = $('#timelineTable') || $('[data-timeline-table]');

    if (canvas && window.Chart) {
      // Tailles CSS sûres
      if (!canvas.style.height)    canvas.style.height = '260px';
      if (!canvas.style.maxHeight) canvas.style.maxHeight = '420px';
      if (!canvas.style.width)     canvas.style.width = '100%';

      const ctx = canvas.getContext('2d');
      const labels = data.map(d => fmtDate(d.time ?? d.timestamp ?? d.t));
      const sentiments = data.map(d => Number(d.sentiment ?? d.s ?? null));
      const prices = data.map(d => Number(d.price ?? d.p ?? null));

      const ds = [
        { label: 'Sentiment', data: sentiments, yAxisID: 'y1' },
        { label: 'Price',     data: prices,    yAxisID: 'y2' }
      ];

      const conf = {
        type: 'line',
        data: { labels, datasets: ds.map(o => ({ ...o, fill: false, tension: 0.2 })) },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          devicePixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
          interaction: { mode: 'index', intersect: false },
          elements: { point: { radius: 1 } },
          stacked: false,
          scales: {
            y1: { type: 'linear', position: 'left' },
            y2: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } }
          },
          plugins: {
            legend: { display: true },
            tooltip: {
              callbacks: {
                title: (ctx) => ctx?.[0]?.label || '',
                label: (ctx) => {
                  const lab = ctx.dataset.label || '';
                  const v = Number(ctx.parsed.y);
                  if (!Number.isFinite(v)) return `${lab}: —`;
                  if (lab.toLowerCase().includes('sentiment')) return `${lab}: ${v.toFixed(3)}`;
                  if (lab.toLowerCase().includes('price')) return `${lab}: ${v.toLocaleString('fr-FR',{ maximumFractionDigits: 2 })}`;
                  return `${lab}: ${v}`;
                }
              }
            }
          }
        }
      };

      if (chartInstance) { try { chartInstance.destroy(); } catch(_) {} }
      chartInstance = new Chart(ctx, conf);
      return;
    }

    // Fallback table si pas de Chart.js / pas de canvas
    if (tableTarget) {
      tableTarget.innerHTML = '';
      const table = create('table');
      table.style.width = '100%';
      table.style.borderCollapse = 'collapse';
      const thead = create('thead');
      const trH = create('tr');
      ['Time', 'Sentiment', 'Price'].forEach(h => {
        const th = create('th', { textContent: h });
        th.style.textAlign = 'left';
        th.style.padding = '6px 8px';
        th.style.borderBottom = '2px solid ' + '#ccc';
        trH.append(th);
      });
      thead.append(trH);
      const tbody = create('tbody');

      data.slice(-200).forEach(d => {
        const tr = create('tr');
        const tdT = create('td', { textContent: fmtDate(d.time ?? d.timestamp ?? d.t) });
        const tdS = create('td', { textContent: fmtNum(d.sentiment ?? d.s) });
        const tdP = create('td', { textContent: fmtNum(d.price ?? d.p) });
        [tdT, tdS, tdP].forEach(td => {
          td.style.padding = '6px 8px';
          td.style.borderBottom = '1px solid ' + '#eee';
        });
        tr.append(tdT, tdS, tdP);
        tbody.append(tr);
      });

      table.append(thead, tbody);
      tableTarget.append(table);
    }
  }

  // === Corrélation — auto refresh & interactions ===
  const byId = (id) => document.getElementById(id);
  const num  = (v, d=6) => (v==null || isNaN(v)) ? 0 : Number(v);

  function renderCorrDetail(canvas, rows) {
    if (!canvas || !rows || !rows.length) return;

    const xs = rows.map((r,i)=> i);
    const prices = rows.map(r => num(r.price));
    const sentiments = rows.map(r => num(r.sentiment));
    const rets = [];
    for (let i=1;i<prices.length;i++){
      const prev = prices[i-1] || 1;
      rets.push((prices[i] - prev) / prev);
    }
    rets.unshift(0);

    const minMax = (arr) => {
      const vals = arr.filter(v => isFinite(v));
      return [Math.min(...vals), Math.max(...vals)];
    };
    const norm = (arr) => {
      const [mn,mx] = minMax(arr); const span = Math.max(1e-9, mx - mn);
      return arr.map(v => (v - mn)/span);
    };

    const priceN = norm(prices);
    const the_sentN = norm(sentiments);

    const ctx = canvas.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const W = canvas.clientWidth * dpr;
    const H = canvas.clientHeight * dpr;
    if (canvas.width !== W) canvas.width = W;
    if (canvas.height !== H) canvas.height = H;

    const pad = 16 * dpr;
    const xMin = 0, xMax = xs.length - 1;
    const [retMin, retMax] = minMax(rets);
    const retSpan = Math.max(1e-9, retMax - retMin);
    const px = (x) => pad + (W - pad*2) * ((x - xMin) / Math.max(1e-9, xMax - xMin));
    const pyL = (y) => (H - pad) - (H - pad*2) * ((y - retMin) / retSpan);
    const pyR = (y01) => (H - pad) - (H - pad*2) * y01;

    ctx.clearRect(0,0,W,H);

    ctx.lineWidth = 1 * dpr;
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.beginPath();
    ctx.moveTo(pad, pad); ctx.lineTo(pad, H - pad); ctx.lineTo(W - pad, H - pad); ctx.stroke();

    if (retMin < 0 && retMax > 0) {
      ctx.strokeStyle = 'rgba(255,255,255,0.15)';
      ctx.beginPath();
      ctx.moveTo(pad, pyL(0));
      ctx.lineTo(W - pad, pyL(0));
      ctx.stroke();
    }

    const barW = Math.max(1, (W - pad*2) / Math.max(1, xs.length) * 0.8);
    for (let i=0;i<xs.length;i++){
      const x = px(xs[i]);
      const y0 = pyL(0);
      const y1 = pyL(rets[i]);
      ctx.fillStyle = rets[i] >= 0 ? 'rgba(34,197,94,0.55)' : 'rgba(239,68,68,0.55)';
      const top = Math.min(y0, y1);
      const h = Math.abs(y1 - y0);
      ctx.fillRect(x - barW/2, top, barW, h);
    }

    ctx.lineWidth = 2 * dpr;
    ctx.strokeStyle = 'hsl(50,90%,60%)';
    ctx.beginPath();
    let started = false;
    for (let i=0;i<xs.length;i++){
      const x = px(xs[i]), y = pyR(priceN[i]);
      if (!started){ ctx.moveTo(x,y); started = true; } else { ctx.lineTo(x,y); }
    }
    ctx.stroke();

    ctx.lineWidth = 2 * dpr;
    ctx.strokeStyle = 'hsl(210,80%,65%)';
    ctx.beginPath();
    started = false;
    for (let i=0;i<xs.length;i++){
      const x = px(xs[i]), y = pyR(the_sentN[i]);
      if (!started){ ctx.moveTo(x,y); started = true; } else { ctx.lineTo(x,y); }
    }
    ctx.stroke();

    ctx.fillStyle = 'rgba(231,238,251,0.7)';
    ctx.font = `${11*dpr}px system-ui, -apple-system, Segoe UI, Roboto, Arial`;
    const fmtPct = (v)=> (Math.abs(v) < 0.001 ? (v*100).toFixed(3)+'%' : (v*100).toFixed(2)+'%');
    const yTicks = 4;
    for (let i=0;i<=yTicks;i++){
      const t = retMin + (i*(retSpan)/yTicks);
      const yy = pyL(t);
      ctx.fillText(fmtPct(t), 4*dpr, yy-2*dpr);
    }

    const legendY = pad - 4*dpr;
    const leg = (x, color, text) => {
      ctx.fillStyle = color; ctx.fillRect(x, legendY-8*dpr, 14*dpr, 3*dpr);
      ctx.fillStyle = 'rgba(231,238,251,0.8)'; ctx.fillText(text, x + 20*dpr, legendY);
    };
    leg(pad, 'rgba(34,197,94,0.7)', 'Returns BTC (barres)');
    leg(pad + 170*dpr, 'hsl(50,90%,60%)', 'Prix BTC (norm.)');
    leg(pad + 330*dpr, 'hsl(210,80%,65%)', 'Sentiment (norm.)');
  }

  // Récupère les contrôles UI
  const corrEls = {
    source: byId('corrSource'),
    interval: byId('corrInterval'),
    hours: byId('corrHours'),
    lag: byId('corrLag'),
    runBtn: byId('corrRunBtn'),
    outCorr: byId('corrValue'),
    outNPairs: byId('corrNPairs'),
    outLagEcho: byId('corrLagEcho'),
    canvas: byId('corrDetailChart'),
  };

  // Charge et affiche la série détaillée
  async function refreshCorrDetail() {
    try {
      const src = corrEls.source?.value || 'combined';
      const interval = corrEls.interval?.value || '5m';
      const hours = Math.max(1, parseInt(corrEls.hours?.value || '24', 10));
      const lag = Math.max(0, parseInt(corrEls.lag?.value || '0', 10));

      const series = await NS.fetchSentimentTimeline();
      if (!Array.isArray(series) || series.length < 3) return;

      const bucketMin = interval === '1m' ? 1 : interval === '5m' ? 5 : interval === '15m' ? 15 : 60;
      const approxPoints = Math.max(10, Math.floor((hours*60)/bucketMin));
      const rows = series.slice(-approxPoints);

      let rowsLagged = rows;
      if (lag > 0) {
        rowsLagged = rows.map((r,i) => ({
          time: r.time, price: r.price,
          sentiment: (i-lag >= 0) ? rows[i-lag].sentiment : rows[0].sentiment
        }));
      }

      renderCorrDetail(corrEls.canvas, rowsLagged);

      const prices = rowsLagged.map(r=>num(r.price));
      const sentiments = rowsLagged.map(r=>num(r.sentiment));
      const returns = prices.map((p,i,arr)=> i===0 ? 0 : (p - arr[i-1]) / (arr[i-1]||1));
      const n = Math.min(returns.length, sentiments.length);
      const a = returns.slice(1,n), b = sentiments.slice(1,n);
      const avg = (arr)=> arr.reduce((s,v)=>s+v,0)/Math.max(1,arr.length);
      const ma = avg(a), mb = avg(b);
      const cov = a.reduce((s,v,i)=> s + (v-ma)*(b[i]-mb), 0) / Math.max(1,a.length-1);
      const sa = Math.sqrt(a.reduce((s,v)=> s + Math.pow(v-ma,2), 0) / Math.max(1,a.length-1));
      const sb = Math.sqrt(b.reduce((s,v)=> s + Math.pow(v-mb,2), 0) / Math.max(1,b.length-1));
      const corr = (!sa || !sb) ? 0 : (cov/(sa*sb));

      if (corrEls.outCorr)   corrEls.outCorr.textContent = (Math.abs(corr)<1e-6? '0.000' : corr.toFixed(3));
      if (corrEls.outNPairs) corrEls.outNPairs.textContent = String(n);
      if (corrEls.outLagEcho) corrEls.outLagEcho.textContent = String(lag);
    } catch (e) {
      console.error('Corr refresh error:', e);
    }
  }

  // Rafraîchissement automatique (toutes les 30s)
  Auto.every(30000, refreshCorrDetail);

  // Rafraîchir sur interactions UI
  ['change','input'].forEach(ev => {
    corrEls.source?.addEventListener(ev, refreshCorrDetail);
    corrEls.interval?.addEventListener(ev, refreshCorrDetail);
    corrEls.hours?.addEventListener(ev, refreshCorrDetail);
    corrEls.lag?.addEventListener(ev, refreshCorrDetail);
  });
  corrEls.runBtn?.addEventListener('click', refreshCorrDetail);

  // Premier affichage
  refreshCorrDetail();

  // === Auto-refresh SEURO — démarre seulement quand API est prêt ===
  (function () {
    const fmt = (n) => (n==null ? '—' : (typeof n==='number'
                      ? n.toLocaleString('fr-FR',{maximumFractionDigits:6})
                      : String(n)));
    const el = (id) => document.getElementById(id);

    function waitForApi(methods = [], tries = 40, interval = 250) {
      return new Promise((resolve, reject) => {
        const ok = () => (window.API && methods.every(m => typeof window.API[m] === 'function'));
        if (ok()) return resolve();
        const t = setInterval(() => {
          if (ok()) { clearInterval(t); resolve(); }
          else if (--tries <= 0) { clearInterval(t); reject(new Error('API not ready')); }
        }, interval);
      });
    }

    async function fetchSentSnapshot(sym){
  // on élargit la fenêtre et on demande cb
  const url = `/api/sentiment/series?symbol=${encodeURIComponent(sym)}&window=3d&fields=tw,rd,nw,tr,cb`;
  const j = await fetch(url, {credentials:'same-origin'}).then(r=>r.json()).catch(()=>null);
  const arr = (j && j.series) || [];
  const last = arr[arr.length-1] || {};

  const vTw = Number.isFinite(+last.tw) ? +last.tw : null;
  const vRd = Number.isFinite(+last.rd) ? +last.rd : null;
  const vNw = Number.isFinite(+last.nw) ? +last.nw : null;
  const vTr = Number.isFinite(+last.tr) ? +last.tr : null;

  // NEW: combiné fiable
  const vCb = Number.isFinite(+last.cb)
    ? +last.cb
    : (vTw!=null && vRd!=null ? (vTw+vRd)/2 : (vTw ?? vRd ?? vNw ?? vTr));

  return { tw: vTw, rd: vRd, nw: vNw, tr: vTr, cb: vCb, ts: +((last && last.t) || 0) };
}

async function loadQuickSentiment(symbols){
  const url = `/api/sentiment/series?symbols=${encodeURIComponent(symbols.join(','))}&window=3d&fields=tw,rd,nw,tr,cb`;
  const j = await fetch(url, {credentials:'same-origin'}).then(r=>r.json()).catch(()=>null);
  const items = (j && j.items) || {};
  const out = {};

  const pickLast = (arr) => arr && arr.length ? arr[arr.length-1] : null;

  for (const sym of symbols){
    const arr = items[sym] || [];
    const last = pickLast(arr) || {};
    // Valeurs brutes
    const tw = Number.isFinite(+last.tw) ? +last.tw : null;
    const rd = Number.isFinite(+last.rd) ? +last.rd : null;
    const nw = Number.isFinite(+last.nw) ? +last.nw : null;
    const tr = Number.isFinite(+last.tr) ? +last.tr : null;
    const cb = Number.isFinite(+last.cb) ? +last.cb : null;

    // Fallback combiné “propre” : favorise TW/RD, sinon NW, sinon TR
    const cbFallback = (()=>{
      if (tw!=null && rd!=null) return (tw+rd)/2;
      if (tw!=null) return tw;
      if (rd!=null) return rd;
      if (nw!=null) return nw;
      if (tr!=null) return (tr); // déjà normalisé si tu l’as fait côté API (sinon tu peux transformer 0..100 -> -1..1)
      return null;
    })();

    out[sym] = {
      tw, rd, nw, tr,
      cb: (cb!=null ? cb : cbFallback),
      ts: +(last.t || last.ts || 0)
    };
  }
  return out;
}

const fmtSent = v => (v==null ? '—' : (Math.round(v*1000)/1000).toFixed(3));
const fmtAge  = (ts) => {
  if (!ts) return '—';
  const sec = Math.max(0, Math.floor((Date.now()-ts)/1000));
  if (sec < 60) return sec + 's';
  const m = Math.floor(sec/60);
  if (m < 60) return m + 'm';
  const h = Math.floor(m/60);
  return h + 'h';
};

async function refreshQuickStats(){
  const symbols = (window.SYMBOLS || ['BTCUSDT','ETHUSDT','SOLUSDT']); // ajuste ta liste
  const data = await loadQuickSentiment(symbols);

  for (const sym of symbols){
    const d = data[sym] || {};
    const set = (sel, val) => {
      const el = document.querySelector(sel);
      if (el) el.textContent = val;
    };
    set(`#row-${sym}-tw`, fmtSent(d.tw));
    set(`#row-${sym}-rd`, fmtSent(d.rd));
    // NEW: colonne combinée (ajoute-la si tu veux dans ton HTML)
    set(`#row-${sym}-cb`, fmtSent(d.cb));
    // (optionnel) âge du dernier point
    set(`#row-${sym}-age`, fmtAge(d.ts));
  }
}




    async function startAuto() {
      await waitForApi([
        'fetchAccount',
        'fetchStatus',
        'fetchLogs',
        'fetchDecisionTrace',
        'fetchLstmPredictions'
      ]).catch(() => {});

      // ===== Ticker + Compte (30s) =====
      Auto.every(30000, async () => {
        try {
          if (!API || typeof API.fetchAccount!=='function' || typeof API.fetchStatus!=='function') return;
          const [acc, status] = await Promise.all([
            API.fetchAccount().catch(()=>null),
            API.fetchStatus().catch(()=>null)
          ]);

          if (acc) {
            const set = (id, v) => { const x = el(id); if (x) x.textContent = fmt(v); };
            set('topCash', acc.cash); set('topBtc', acc.btc); set('topVal', acc.valuation);
            set('cashNow', acc.cash); set('btcNow', acc.btc); set('valNow', acc.valuation);
          }
          if (status) {
            const setTxt = (id, v) => { const x = el(id); if (x) x.textContent = v; };
            setTxt('priceNow', fmt(status.price));
            setTxt('statusPaper', status.paper ? 'PAPER' : 'LIVE');
            setTxt('statusSymbol', status.symbol || 'BTCUSDT');
            setTxt('priceDir', status.direction || '…');

            const b = el('sentBadge');
            if (b && typeof status.sentiment === 'number') {
              b.textContent = `Sentiment : ${status.sentiment.toFixed(3)}`;
              b.className = 'badge ' + (status.sentiment>0.05 ? 'up' : (status.sentiment<-0.05 ? 'down' : 'neutral'));
            }
          }
        } catch(e) { console.error('Refresh ticker error:', e); }
      });

      // ===== KPIs + Decision trace (20s) =====
      Auto.every(20000, async () => {
        try {
          if (!API || typeof API.fetchStatus !== 'function') return;

          // KPIs
          const status = await API.fetchStatus().catch(() => null);
          // MAJ KPI: Prix BTC moyen (20)
          try { const ap = Number(status?.avg_price_20 || 0); const n = document.getElementById('avgPrice20'); if (n) n.textContent = FMT.n(ap, 2); } catch (e) {}

          if (status) {
            const set = (id, v) => { const x = el(id); if (x) x.textContent = fmt(v); };
            if (status.p_up != null) set('pUpVal', status.p_up);
            if (status.ev != null) set('evVal', status.ev);
            if (status.min_ev_effective != null) set('effMinEvVal', status.min_ev_effective);
            const inPos = el('inPosVal'); if (inPos) inPos.textContent = status.in_position ? 'LONG' : 'FLAT';
            const ld = el('lastDecisionVal'); if (ld && status.last_decision) ld.textContent = status.last_decision;
          }

          // Decision trace
          if (typeof API.fetchDecisionTrace === 'function') {
            const tc = document.getElementById('traceCount');
            const nWanted = Number(tc?.value || 50);

            const trace = await API.fetchDecisionTrace(nWanted).catch(() => null);
            const items = Array.isArray(trace) ? trace : (trace?.items || []);

            const tb = el('traceBody');
            if (tb) {
              tb.innerHTML = '';

              items.slice(-nWanted).reverse().forEach(row => {
                const tr = document.createElement('tr');
                const cell = (v) => { const td = document.createElement('td'); td.textContent = (v == null ? '—' : String(v)); return td; };

                const priceNum = parseFloat(String(row.price).replace(/[^\d.\-]/g, ''));

                tr.append(cell(row.time || row.t || '—'));
                tr.append(cell(row.side || row.action || row.decision || '—'));
                tr.append(cell(fmt(priceNum)));
                tr.append(cell(fmt(Number(row.size || row.qty))));
                tr.append(cell(fmt(Number(row.p_up))));
                tr.append(cell(fmt(Number(row.ev))));
                tr.append(cell(row.min_ev ?? row.min_ev_effective ?? '—'));
                tr.append(cell(row.exec || row.mode || ((row.decision === 'buy' || row.decision === 'sell') ? 'yes' : '—')));
                tb.appendChild(tr);
              });

              if (!tb.childElementCount) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = 8;
                td.style.padding = '8px 10px';
                td.style.opacity = '0.8';
                td.textContent = 'Aucune décision pour le moment.';
                tr.appendChild(td);
                tb.appendChild(tr);
              }

              const ts = el('traceSize');
              if (ts) ts.textContent = String(items.length);
            }

            // listener pour changement immédiat
            if (tc && !tc._bound) {
              tc.addEventListener('change', async () => {
                const wanted = Number(tc.value || 50);
                const trace2 = await API.fetchDecisionTrace(wanted).catch(()=>null);
                const items2 = Array.isArray(trace2) ? trace2 : (trace2?.items || []);
                const tb2 = document.getElementById('traceBody');
                if (!tb2) return;
                tb2.innerHTML = '';
                items2.slice(-wanted).reverse().forEach(row => {
                  const tr = document.createElement('tr');
                  const cell = (v) => { const td = document.createElement('td'); td.textContent = (v==null?'—':String(v)); return td; };
                  const priceNum = parseFloat(String(row.price).replace(/[^\d.\-]/g, ''));
                  tr.append(cell(row.time || row.t || '—'));
                  tr.append(cell(row.side || row.action || row.decision || '—'));
                  tr.append(cell(fmt(priceNum)));
                  tr.append(cell(fmt(Number(row.size || row.qty))));
                  tr.append(cell(fmt(Number(row.p_up))));
                  tr.append(cell(fmt(Number(row.ev))));
                  tr.append(cell(row.min_ev ?? row.min_ev_effective ?? '—'));
                  tr.append(cell(row.exec || row.mode || ((row.decision === 'buy' || row.decision === 'sell') ? 'yes' : '—')));
                  tb2.appendChild(tr);
                });
                if (!tb2.childElementCount) {
                  const tr = document.createElement('tr');
                  const td = document.createElement('td');
                  td.colSpan = 8; td.style.padding = '8px 10px'; td.style.opacity = '0.8';
                  td.textContent = 'Aucune décision pour le moment.';
                  tr.appendChild(td); tb2.appendChild(tr);
                }
              });
              tc._bound = true;
            }
          }
        } catch (_) {}
      });

      // ===== Logs (30s) =====
      Auto.every(30000, async () => {
        try {
          if (!API || typeof API.fetchLogs !== 'function') return;

          const logs = await API.fetchLogs({ tail: 200 }).catch(() => null);
          const pre = document.getElementById('logsPre');
          const lbl = document.getElementById('logsCount');
          if (!pre) return;

          let out = '';
          let totalCount = 0;
          let shownCount = 0;

          if (Array.isArray(logs)) {
            totalCount = logs.length;
            out = logs.slice(-200).join('\n');
            shownCount = Math.min(totalCount, 200);
          } else if (typeof logs === 'string') {
            const arr = logs.split('\n');
            totalCount = arr.length;
            out = arr.slice(-200).join('\n');
            shownCount = Math.min(totalCount, 200);
          } else if (logs) {
            const s = JSON.stringify(logs, null, 2);
            const arr = s.split('\n');
            totalCount = arr.length;
            out = arr.slice(-200).join('\n');
            shownCount = Math.min(totalCount, 200);
          }

          pre.textContent = out;

          if (!pre.textContent || pre.textContent.trim() === '') {
            pre.textContent = 'Aucun log récent.';
            totalCount = 0; shownCount = 0;
          }

          if (lbl) {
            if (totalCount === 0) lbl.textContent = '(0 ligne)';
            else if (totalCount > shownCount) lbl.textContent = `(${shownCount} / ${totalCount}, max 200)`;
            else lbl.textContent = `(${shownCount} ligne${shownCount>1?'s':''})`;
          }
        } catch (_) {}
      });

      // ===== Actions récentes (30s) =====
      Auto.every(30000, async () => {
        try {
          if (!API || typeof API.fetchTrades !== 'function') return;
          const ul = document.getElementById('actionsList');
          if (!ul) return;

          const trades = await API.fetchTrades().catch(() => null);
          const arr = Array.isArray(trades) ? trades : (trades?.items || []);
          ul.innerHTML = '';

          const fmtTime = (ts) => {
            let d;
            if (typeof ts === 'number') {
              // if seconds, convert to ms
              d = new Date(ts < 1e12 ? ts * 1000 : ts);
            } else {
              // support ISO / sqlite strings
              const s = String(ts).trim();
              // add Z if looks like UTC without timezone
              d = new Date(/\dZ$/.test(s) || /[\+\-]\d{2}:?\d{2}$/.test(s) ? s : s.replace(' ', 'T') + 'Z');
            }
            return isNaN(d.getTime()) ? String(ts) :
              d.toLocaleTimeString('fr-FR', {hour12:false, timeZone:'Europe/Zurich'});
          };
          const fmt = (x, d = 6) => (x == null || isNaN(x)) ? '—' : Number(x).toFixed(d);

          arr.slice(-50).reverse().forEach(t => {
            const time = t.time || t.t || t.ts || t.timestamp;
            const side = (t.side || t.action || '').toUpperCase() || '—';
            const qty  = t.qty != null ? t.qty : (t.size != null ? t.size : null);
            const price = t.price != null ? t.price : t.p;
            const fee  = t.fee != null ? t.fee : t.f;

            const li = document.createElement('li');
            li.style.borderBottom = '1px solid var(--border)';
            li.style.padding = '6px 4px';
            li.innerHTML = `
              <span style="opacity:.8">${fmtTime(time)}</span>
              — <strong>${side}</strong>
              · qty <span class="num">${fmt(Number(qty), 6)}</span>
              · px <span class="num">${fmt(Number(price), 2)}</span>
              ${fee != null ? `· fee <span class="num">${fmt(Number(fee), 6)}</span>` : ''}
            `;
            ul.appendChild(li);
          });

          if (!ul.childElementCount) {
            const li = document.createElement('li');
            li.style.opacity = '.8';
            li.textContent = 'Aucune action récente.';
            ul.appendChild(li);
          }
        } catch(_) {}
      });

      // ===== Courbe LSTM lissée (30s) =====
      Auto.every(30000, async () => {
        try {
          if (!API || typeof API.fetchLstmPredictions!=='function') return;
          const data = await API.fetchLstmPredictions().catch(()=>null);
          if (!data) return;

          let arr = [];
          if (Array.isArray(data)) {
            if (typeof data[0] === 'number') {
              arr = data.map((v,i)=>({x:i, y:Number(v)}));
            } else {
              arr = data.map((o,i)=>({x:(o.t ?? i), y:Number(o.y ?? o.value ?? o.v ?? 0)}));
            }
          } else if (data && Array.isArray(data.ts) && Array.isArray(data.y)) {
            arr = data.ts.map((t,i)=>({x:i, y:Number(data.y[i])}));
          }
          const canvas = document.getElementById('lstmCanvas');
          if (canvas && arr.length && typeof window.drawLineChart === 'function') {
            const series = [{name:'LSTM', data: arr, color: 'hsl(200,80%,60%)', width:2}];
            window.drawLineChart(canvas, series, { padding: 16 });
          }
        } catch(e) {
          console.error('Refresh LSTM error:', e);
        }
      });
    }

    // lance quand le DOM est prêt
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startAuto, {once:true});
    } else {
      startAuto();
    }
  })();

  // ==========================
  // Cycle de vie (bloc sentiment/timeline/social/corr)
  // ==========================
  async function refreshAll() {
    try {
      const snap = await NS.fetchSentimentSnapshot();
      renderSnapshot(snap);
      window.dispatchEvent(new CustomEvent('sentiment:snapshot', { detail: snap }));
    } catch (e) { console.error('Snapshot error:', e); }

    try {
      const series = await NS.fetchSentimentTimeline();
      renderTimeline(series);
      window.dispatchEvent(new CustomEvent('sentiment:timeline', { detail: series }));
    } catch (e) { console.error('Timeline error:', e); }

    try {
      const corr = await NS.fetchCorrelation();
      renderCorrelation(corr);
      window.dispatchEvent(new CustomEvent('sentiment:correlation', { detail: corr }));
    } catch (e) { console.error('Correlation error:', e); }

    try {
      const social = await NS.fetchSocialSentiments();
      renderSocial(social);
      window.dispatchEvent(new CustomEvent('sentiment:social', { detail: social }));
    } catch (e) { console.error('Social error:', e); }
  }

  NS.refreshAll = refreshAll;
  NS.start = function start(intervalMs = 30000) {
    refreshAll();
    if (start._timer) clearInterval(start._timer);
    start._timer = setInterval(refreshAll, intervalMs);
    return () => clearInterval(start._timer);
  };

  document.addEventListener('DOMContentLoaded', () => {
    const hasTargets = $('#sentiment-snapshot') || $('[data-sentiment-snapshot]') ||
                       $('#correlationValue') || $('[data-correlation]') ||
                       $('#socialList') || $('[data-social-list]') ||
                       $('#sentimentChart') || $('#lstmCanvas') || document.querySelector('canvas[data-sentiment-chart]') ||
                       $('#timelineTable') || $('[data-timeline-table]');
    if (hasTargets) NS.start(30000);
  });
})(); // ← fin du premier grand IIFE


// ---- Facade API robuste (unique)
(function () {
  const API = (window.API = window.API || {});
  const jsonHeaders = { 'Accept': 'application/json', 'Content-Type': 'application/json' };

  async function apiFetch(url, opts = {}) {
    const r = await fetch(url, { cache: 'no-store', ...opts });
    if (!r.ok) {
      let errMsg = `${url} HTTP ${r.status}`;
      try {
        const ct = r.headers.get('content-type') || '';
        if (ct.includes('application/json')) {
          const j = await r.json();
          if (j && (j.error || j.message)) errMsg = j.error || j.message;
          else errMsg = JSON.stringify(j).slice(0, 200);
        } else {
          const t = await r.text();
          if (t) errMsg = t.slice(0, 200);
        }
      } catch (_) {}
      const e = new Error(errMsg);
      e.status = r.status;
      throw e;
    }
    return r.json();
  }

  API.fetchParams = async function () {
    const j = await apiFetch('/api/params');
    return j?.params || j || {};
  };

  API.updateParams = async function (body) {
    const j = await apiFetch('/api/params/update', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(body || {}),
    });
    return j?.params || {};
  };

  API.fetchStatus = async function () {
    const st = await apiFetch('/api/status');
    if (typeof st?.in_position === 'undefined' && typeof st?.position === 'string') {
      st.in_position = (st.position || '').toUpperCase() === 'LONG';
    }
    return st;
  };

  API.fetchAccount = async function () { return apiFetch('/api/account'); };

  API.fetchDecisionTrace = async function (n = 200) {
    const j = await apiFetch(`/api/decision_trace?n=${encodeURIComponent(n)}`);
    return Array.isArray(j) ? j : (j?.items || []);
  };

  API.fetchLogs = async function ({ tail = 200 } = {}) {
    return apiFetch(`/api/logs?tail=${encodeURIComponent(tail)}`);
  };

  API.fetchTrades = async function () { return apiFetch('/api/trades'); };

  API.runStrategy = async function (opts = {}) {
    return apiFetch('/api/strategy/run', {
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify(opts),
    });
  };

  API.manualBuy = async function (symbol, usdt) {
    try {
      return await apiFetch('/api/manual/buy', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({ usdt: Number(usdt) }),
      });
    } catch (e) { (API.showToast || alert)(e.message || 'Buy failed'); throw e; }
  };

  // SELL: 'all' -> {all:true}, nombre -> {qty:number}
  API.manualSell = async function (symbol, qtyOrAll) {
    const body = (qtyOrAll === 'all' || qtyOrAll === -1) ? { all: true } : { qty: Number(qtyOrAll) };
    try {
      return await apiFetch('/api/manual/sell', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify(body),
      });
    } catch (e) { (API.showToast || alert)(e.message || 'Sell failed'); throw e; }
  };

  // OHLC alias -> [{t,open,high,low,close}]
  API.fetchOhlc = async function (symbol = 'BTCUSDT', interval = '1m', limit = 120) {
    const sym = String(symbol).replace('/', '');
   return apiFetch(`/api/ohlc?symbol=${encodeURIComponent(sym)}&interval=${encodeURIComponent(interval)}&limit=${encodeURIComponent(limit)}`); 
  };

  API.fetchLstmPredictions = async function () { return apiFetch('/api/lstm_predictions'); };
  API.fetchSentimentSnapshot = async function () { return apiFetch('/api/sentiment'); };

  API.fetchNews = async function () {
    const j = await apiFetch('/api/news');
    return j?.items || [];
  };

  // Toast minimal (si inexistant)
  API.showToast = API.showToast || function (msg, { type = 'info' } = {}) {
    try {
      const el = document.createElement('div');
      el.textContent = msg;
      el.style.cssText = 'position:fixed;right:12px;bottom:12px;padding:10px 12px;border-radius:8px;background:#1a2140;color:#e7eefb;border:1px solid #29304d;z-index:9999';
      document.body.appendChild(el);
      setTimeout(()=>el.remove(), 2200);
    } catch(_) {}
  };
})(); // fin Facade API


// === Graphiques du panneau "📈 Graphiques — Sentiments & Trends" ===
(function () {
  const has = (id) => document.getElementById(id);

  // Expose ensureChart globalement, une seule fois (évite les redéclarations)
  if (typeof window.ensureChart !== 'function') {
    window.ensureChart = function ensureChart(canvasEl, kind, labels, datasets, options = {}) {
      if (!canvasEl || !window.Chart) return null;

      // Détruit proprement l’ancien chart s’il existe
      if (canvasEl._chart) {
        try { canvasEl._chart.destroy(); } catch (_) {}
        canvasEl._chart = null;
      }

      // Tailles CSS sûres
      if (!canvasEl.style.height)    canvasEl.style.height = '260px';
      if (!canvasEl.style.maxHeight) canvasEl.style.maxHeight = '420px';
      if (!canvasEl.style.width)     canvasEl.style.width = '100%';
      canvasEl.style.maxWidth = '100%';

      // DPR plafonné (fallback)
      const DPR = Math.min(window.devicePixelRatio || 1, 1.5);

      // “Reset” éventuel
      try {
        const ctx0 = canvasEl.getContext('2d');
        if (ctx0 && typeof ctx0.resetTransform === 'function') ctx0.resetTransform();
      } catch (_) {}

      // Garde-fou taille interne
      const MAX_DIM = 8192;
      const wPx = (canvasEl.clientWidth  || 600) * DPR;
      const hPx = (canvasEl.clientHeight || 260) * DPR;
      if (wPx > MAX_DIM || hPx > MAX_DIM) {
        canvasEl.style.height = '260px';
        canvasEl.style.width  = '100%';
      }

      const fmt = (v) => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 2 });

      canvasEl._chart = new Chart(canvasEl.getContext('2d'), {
        type: kind,
        data: { labels, datasets },
        options: Object.assign({
          responsive: true,
          maintainAspectRatio: false,
          devicePixelRatio: DPR,
          animation: false,
          interaction: { mode: 'index', intersect: false },
          ...(kind === 'line' ? { elements: { point: { radius: 1 } } } : {}),
          plugins: {
            legend: { display: true },
            tooltip: {
              callbacks: {
                title: (items) => items?.[0]?.label || '',
                label: (ctx) => {
                  const lab = ctx.dataset.label || '';
                  const y = ctx.parsed?.y ?? ctx.raw;
                  if (!Number.isFinite(Number(y))) return `${lab}: —`;
                  return `${lab}: ${fmt(y)}`;
                }
              }
            }
          },
          scales: { x: { display: true }, y: { display: true } }
        }, options)
      });

      return canvasEl._chart;
    };
  }

  // 2.1 — Sentiments Reddit/Twitter (barres)
  async function refreshSentimentsBars() {
    if (!window.API || typeof API.fetchStatus !== 'function') return;
    const canvas = has('chartSentiments');
    if (!canvas) return;
    try {
      const st = await API.fetchStatus();
      const labels = ['Reddit', 'Twitter'];
      const vals = [Number(st?.reddit_avg ?? 0), Number(st?.twitter_avg ?? 0)];

      window.ensureChart(canvas, 'bar', labels, [{
        label: 'Sentiment (actuel)',
        data: vals
      }], {
        scales: { y: { suggestedMin: -1, suggestedMax: 1 } }
      });
    } catch (e) {
      console.error('chartSentiments error:', e);
    }
  }

  // 2.2 — Google Trends BTC (ligne)
  async function refreshTrends() {
    const canvas = document.getElementById('trendsChart');
    if (!canvas || !window.Chart) return;

    // Taille CSS sûre (au cas où)
    if (!canvas.style.height) canvas.style.height = '240px';
    if (!canvas.style.maxHeight) canvas.style.maxHeight = '400px';
    if (!canvas.style.width) canvas.style.width = '100%';

    // petit fetch JSON local
    const gget = async (url) => {
      const r = await fetch(url, { headers: { 'Accept':'application/json' }, cache: 'no-store' });
      return r.ok ? r.json().catch(() => null) : null;
    };

    // 1) série complète si dispo
    let labels = ['—'], values = [0];
    const data = await gget('/api/google_trends');
    if (data && Array.isArray(data.data)) {
      labels = data.data.map(d => {
        const dt = new Date(d.t);
        return isNaN(dt.getTime()) ? '' : dt.toLocaleTimeString();
      });
      values = data.data.map(d => Number(d.score ?? 0));
    } else {
      // 2) fallback: snapshot unique
      const snap = await gget('/trends');
      if (snap && (snap.last_update || snap.prediction != null)) {
        labels = [String(snap.last_update || 'now')];
        values = [Number(snap.prediction ?? 0)];
      }
    }

    // rendu via helper sécurisé
    window.ensureChart(canvas, 'line', labels, [{
      label: 'Google Trends BTC',
      data: values,
      borderWidth: 2
    }], {
      elements: { point: { radius: 1 } },
      plugins: {
        legend: { display: true },
        tooltip: {
          callbacks: {
            title: (items) => items?.[0]?.label || '',
            label: (ctx) => `Score: ${Number(ctx.parsed.y).toFixed(2)}`
          }
        }
      }
    });
  }

  // 2.3 — BTC & Sentiment (overlay)
  async function refreshBtcSentOverlay() {
    const canvas = document.getElementById('chartBtcSent');
    if (!canvas || !window.Chart) return;

    try {
      // Données via Facade si dispo, sinon fallback direct
      let series = [];
      if (window.API && typeof API.fetchSentimentTimeline === 'function') {
        series = await API.fetchSentimentTimeline();
      } else {
        const r = await fetch('/api/sentiment_price', { headers: { 'Accept':'application/json' }, cache:'no-store' });
        if (!r.ok) return;
        series = await r.json().catch(() => []);
      }

      if (!Array.isArray(series) || series.length < 3) return;

      const labels = series.map(d => {
        const t = d.time ?? d.t ?? d.timestamp;
        const dt = typeof t === 'number' ? new Date(t) : new Date(String(t));
        return isNaN(dt.getTime()) ? '' : dt.toLocaleTimeString();
      });
      const price = series.map(d => Number(d.price ?? d.p ?? 0));
      const senti = series.map(d => Number(d.sentiment ?? d.s ?? 0));

      // normalisation 0..1
      const minMax = (arr) => {
        const vals = arr.filter(v => Number.isFinite(v));
        return [Math.min(...vals), Math.max(...vals)];
      };
      const norm = (arr) => {
        const [mn, mx] = minMax(arr); const span = Math.max(1e-9, mx - mn);
        return arr.map(v => (v - mn) / span);
      };

      const priceN = norm(price);
      const sentiN = norm(senti);

      // garantir une hauteur css
      if (!canvas.style.height) canvas.style.height = '260px';
      if (!canvas.style.width) canvas.style.width = '100%';

      window.ensureChart(canvas, 'line', labels, [
        { label: 'BTC (normalisé)',       data: priceN, yAxisID: 'y1' },
        { label: 'Sentiment (normalisé)', data: sentiN, yAxisID: 'y2' },
      ], {
        scales: {
          y1: { type: 'linear', position: 'left',  min: 0, max: 1 },
          y2: { type: 'linear', position: 'right', min: 0, max: 1, grid: { drawOnChartArea: false } }
        },
        elements: { point: { radius: 0 } },
        plugins: {
          tooltip: {
            callbacks: {
              title: (items) => items?.[0]?.label || '',
              label: (ctx) => {
                const lab = ctx.dataset.label || '';
                const y = Number(ctx.parsed?.y);
                if (!Number.isFinite(y)) return `${lab}: —`;
                return `${lab}: ${(y * 100).toFixed(1)}%`;
              }
            }
          }
        }
      });
    } catch (e) {
      console.error('chartBtcSent error:', e);
    }
  }

  // Lancer + Auto-refresh (30s)
  function kickCharts() {
    refreshSentimentsBars();
    refreshTrends();
    refreshBtcSentOverlay();
  }
  document.addEventListener('DOMContentLoaded', () => {
    kickCharts();
    Auto.every(30000, kickCharts);
  });
})(); // ← fermeture OK du bloc Graphiques


// ===== News & Sentiments (60s) =====
(function () {
  const ul = document.getElementById('newsList');
  const sortSel = document.getElementById('newsSort');
  if (!ul) return;

  const scoreBadge = (s) => {
    const v = Number(s);
    const cls = (v > 0.05) ? 'up' : (v < -0.05 ? 'down' : 'neutral');
    const txt = Number.isFinite(v) ? v.toFixed(3) : '—';
    return `<span class="badge ${cls}">sent: ${txt}</span>`;
  };

  const fmtTime = (ts) => {
    try {
      const d = (typeof ts === 'number') ? new Date(ts) : new Date(String(ts));
      return isNaN(d.getTime()) ? '' : d.toLocaleString('fr-FR');
    } catch { return ''; }
  };

  async function refreshNews() {
    try {
      if (!window.API || typeof API.fetchNews !== 'function') return;
      const items = await API.fetchNews().catch(() => []);
      const arr = Array.isArray(items) ? items.slice() : [];

      const mode = sortSel?.value || 'time';
      arr.sort((a,b) => {
        const sa = Number(a.score ?? a.sentiment ?? 0);
        const sb = Number(b.score ?? b.sentiment ?? 0);
        const ta = +new Date(a.publishedAt || a.time || a.date || 0);
        const tb = +new Date(b.publishedAt || b.time || b.date || 0);
        return (mode === 'score') ? (Math.abs(sb) - Math.abs(sa)) : (tb - ta);
      });

      ul.innerHTML = '';
      (arr.slice(0,50)).forEach(n => {
        const title = n.title || n.headline || n.text || 'Sans titre';
        const url   = n.url || n.link || '#';
        const src   = n.source || n.site || n.domain || '';
        const time  = n.publishedAt || n.time || n.date || '';
        const score = n.score ?? n.sentiment;

        const li = document.createElement('li');
        li.className = 'news-item';
        li.innerHTML = `
          <div class="news-title"><a href="${url}" target="_blank" rel="noopener">${title}</a></div>
          <div class="news-meta">
            ${scoreBadge(score)}
            ${src ? `<span>${src}</span>` : ''}
            ${time ? `<span>${fmtTime(time)}</span>` : ''}
          </div>
        `;
        ul.appendChild(li);
      });

      if (!ul.childElementCount) {
        const li = document.createElement('li');
        li.className = 'news-item';
        li.style.opacity = '.8';
        li.textContent = 'Aucune news disponible.';
        ul.appendChild(li);
      }
    } catch (e) {
      console.error('news refresh error:', e);
    }
  }

  document.addEventListener('DOMContentLoaded', refreshNews, { once:true });
  Auto.every(60000, refreshNews);
  sortSel?.addEventListener('change', refreshNews);
})(); // fin IIFE News


// === Bouton "Vendre tout" ===
document.addEventListener('DOMContentLoaded', () => {
  const btnAll = document.getElementById('sellAllBtn') || document.querySelector('[data-action="sell-all"]');
  if (btnAll) {
    btnAll.addEventListener('click', async () => {
      try {
        await API.manualSell('BTCUSDT', 'all');
        API.showToast && API.showToast('Vente totale exécutée', { type: 'success' });
        if (typeof API.fetchAccount === 'function') {
          const acc = await API.fetchAccount().catch(()=>null);
          const set = (id, v) => { const x = document.getElementById(id); if (x) x.textContent = (v==null?'—':String(v)); };
          if (acc) { set('cashNow', acc.cash); set('btcNow', acc.btc); set('valNow', acc.valuation); }
        }
      } catch (_) { /* toast déjà montré par manualSell */ }
    });
  }

  // Bouton "Copier les logs"
  document.getElementById('copyLogsBtn')?.addEventListener('click', () => {
    const pre = document.getElementById('logsPre');
    const btn = document.getElementById('copyLogsBtn');
    if (!pre) return;
    navigator.clipboard.writeText(pre.textContent || '').then(
      () => {
        (API.showToast || alert)('Logs copiés');
        if (btn) { const t = btn.textContent; btn.textContent = 'Copié !'; setTimeout(() => btn.textContent = t, 800); }
      },
      () => (API.showToast || alert)('Impossible de copier')
    );
  });
});
document.addEventListener('DOMContentLoaded', () => {
  const badge = document.getElementById('autoBadge');
  const ageEl = document.getElementById('autoAge');
  const updEl = document.getElementById('autoUpdated');

  const checkAuto = async () => {
    try {
      const r = await fetch('/api/health', { cache: 'no-store' });
      const j = await r.json();

      const alive = !!j.ok;
      if (badge) {
        badge.textContent = alive ? 'Autotrade : ON' : 'Autotrade : OFF';
        badge.className = 'badge ' + (alive ? 'up' : 'down');
      }
      if (ageEl) {
        const age = (j.last_tick_age_s == null) ? '—' : `${j.last_tick_age_s}s`;
        ageEl.textContent = `tick : ${age}`;
      }
      if (updEl) {
        updEl.textContent = j.updated_at || '—';
      }
    } catch (e) {
      if (badge) { badge.textContent = 'Autotrade : N/A'; badge.className = 'badge'; }
      if (ageEl) ageEl.textContent = 'tick : —';
      if (updEl) updEl.textContent = '—';
      console.error('auto health error:', e);
    }
  };

  // lance une fois puis toutes les 10s (utilise ton Auto.every global)
  checkAuto();
  (window.Auto && typeof Auto.every === 'function')
    ? Auto.every(10000, checkAuto)
    : setInterval(checkAuto, 10000);
});
fetch('/api/sentiment_twitter')
  .then(r=>r.json())
  .then(d => {
    if (d.rate_limited && d.reset_epoch) {
      const when = new Date(d.reset_epoch * 1000).toLocaleTimeString();
      const b = document.getElementById('sentBadge');
      if (b) b.title = `Twitter limité. Prochain essai vers ${when}.`;
    }
  });
  (function(){
  const el = id => document.getElementById(id);
  const FMT = {
    n: (x,d=2)=> (x==null||!isFinite(x))?'—':Number(x).toLocaleString('fr-FR',{maximumFractionDigits:d})
  };

  async function refreshQuickStats(){
    try{
      // snapshot global
      const snap = await fetch('/api/sentiment', {headers:{'Accept':'application/json'}}).then(r=>r.json());
      el('lastUpdate').textContent   = snap?.last_update || '—';
      el('predPrice').textContent    = FMT.n(snap?.prediction,2);
      el('lastPredAction').textContent = (snap?.last_action||'—');

      // reddit & twitter
      const [rd, tw] = await Promise.allSettled([
        fetch('/api/sentiment_reddit').then(r=>r.json()),
        fetch('/api/sentiment_twitter').then(r=>r.json())
      ]);

      const r = (rd.status==='fulfilled') ? rd.value : null;
      const t = (tw.status==='fulfilled') ? tw.value : null;

      el('sentiRedditNow').textContent   = FMT.n(r?.avg,3);
      // approx "moy. 20" = moyenne glissante depuis /api/sentiment_price quand dispo
      // on retombe sur le snapshot si indispo
      el('sentiRedditAvg20').textContent = FMT.n(snap?.avg_sentiment_20,3);

      el('sentiTwitterNow').textContent  = FMT.n(t?.avg,3);
      // si tu veux une vraie moyenne 20 points Twitter, tu peux la calculer côté backend plus tard
      el('sentiTwitterAvg20').textContent= FMT.n((t?.avg ?? 0),3);
    }catch(e){
      console.error('quick stats error', e);
    }
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    refreshQuickStats();
    setInterval(refreshQuickStats, 20000);
  });
})();
(function(){
  const el = id => document.getElementById(id);

  function setVal(id, v){ const x=el(id); if(x) x.value = (v??''); }
  function num(x){ const n = Number(x); return isFinite(n)?n:undefined; }

  async function loadParams(){
    const j = await fetch('/api/params').then(r=>r.json());
    const p = j?.params || j; // selon ton endpoint
    setVal('inputPbuy',                  p.PBUY);
    setVal('inputPsell',                 p.PSELL);
    setVal('inputMinEv',                 p.MIN_EV_NET);
    setVal('inputBuyPct',                p.BUY_PCT);
    setVal('inputFeeBuy',                p.FEE_RATE_BUY);
    setVal('inputFeeSell',               p.FEE_RATE_SELL);
    setVal('inputSlippage',              p.SLIPPAGE);
    if (el('inputPreferMaker')) el('inputPreferMaker').value = String(!!p.PREFER_MAKER);
    setVal('inputMaxOrdersPerHour',      p.MAX_ORDERS_PER_HOUR);
    setVal('inputMinSecondsBetween_Orders', p.MIN_SECONDS_BETWEEN_ORDERS);
    setVal('inputDailyLossPct',          p.DAILY_LOSS_LIMIT_PCT);
    setVal('inputDailyLossQuote',        p.DAILY_LOSS_LIMIT_QUOTE);
    setVal('inputA0Bias',                p.A0_BIAS);
    setVal('inputLstmWeight',            p.LSTM_WEIGHT);
    setVal('inputSentiWeight',           p.SENTI_WEIGHT);
    setVal('inputTrendsWeight',          p.TRENDS_WEIGHT);
    setVal('inputSigmoidScale',          p.SIGMOID_SCALE);
    setVal('inputLstmEma',               p.LSTM_SMOOTH_EMA);
    setVal('inputNewsWeight',            p.NEWS_WEIGHT);
    setVal('inputRedditWeight',          p.REDDIT_WEIGHT);
  }

  async function saveParams(){
    const body = {
      PBUY: num(el('inputPbuy')?.value),
      PSELL: num(el('inputPsell')?.value),
      MIN_EV_NET: num(el('inputMinEv')?.value),
      BUY_PCT: num(el('inputBuyPct')?.value),
      FEE_RATE_BUY: num(el('inputFeeBuy')?.value),
      FEE_RATE_SELL: num(el('inputFeeSell')?.value),
      SLIPPAGE: num(el('inputSlippage')?.value),
      PREFER_MAKER: String(el('inputPreferMaker')?.value) === 'true',
      MAX_ORDERS_PER_HOUR: num(el('inputMaxOrdersPerHour')?.value),
      MIN_SECONDS_BETWEEN_ORDERS: num(el('inputMinSecondsBetween_Orders')?.value),
      DAILY_LOSS_LIMIT_PCT: num(el('inputDailyLossPct')?.value),
      DAILY_LOSS_LIMIT_QUOTE: num(el('inputDailyLossQuote')?.value),
      A0_BIAS: num(el('inputA0Bias')?.value),
      LSTM_WEIGHT: num(el('inputLstmWeight')?.value),
      SENTI_WEIGHT: num(el('inputSentiWeight')?.value),
      TRENDS_WEIGHT: num(el('inputTrendsWeight')?.value),
      SIGMOID_SCALE: num(el('inputSigmoidScale')?.value),
      LSTM_SMOOTH_EMA: num(el('inputLstmEma')?.value),
      NEWS_WEIGHT: num(el('inputNewsWeight')?.value),
      REDDIT_WEIGHT: num(el('inputRedditWeight')?.value),
    };
    await fetch('/api/params/update',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    el('paramsMsg').textContent = 'Paramètres enregistrés.';
    setTimeout(()=> el('paramsMsg').textContent = '', 3000);
  }

  function applyPreset(name){
    const presets = {
      aggressive:{PBUY:0.60,PSELL:0.40,MIN_EV_NET:0.000, BUY_PCT:0.35, SIGMOID_SCALE:3.5},
      neutral:   {PBUY:0.62,PSELL:0.40,MIN_EV_NET:0.001, BUY_PCT:0.25, SIGMOID_SCALE:3.0},
      secure:    {PBUY:0.66,PSELL:0.38,MIN_EV_NET:0.002, BUY_PCT:0.15, SIGMOID_SCALE:2.8},
    };
    const p = presets[name]; if(!p) return;
    setVal('inputPbuy', p.PBUY); setVal('inputPsell', p.PSELL);
    setVal('inputMinEv', p.MIN_EV_NET); setVal('inputBuyPct', p.BUY_PCT);
    setVal('inputSigmoidScale', p.SIGMOID_SCALE);
  }

  document.addEventListener('DOMContentLoaded', ()=>{
  refreshQuickStats();
  setInterval(refreshQuickStats, 30_000); // toutes les 30s
});

  document.addEventListener('DOMContentLoaded', ()=>{
    loadParams();
    document.getElementById('btnSaveParams')?.addEventListener('click', saveParams);
    document.getElementById('btnApplyPreset')?.addEventListener('click', ()=>{
      const v = document.getElementById('presetSelect')?.value || '';
      applyPreset(v);
    });
  });
})();

(function(){
  const el = id => document.getElementById(id);
  async function runSim(){
    try{
      const days = Math.max(1, parseInt(el('simDays').value||'7',10));
      const paths = Math.max(10, parseInt(el('simPaths').value||'100',10));
      const priceNow = Number((await fetch('/api/status').then(r=>r.json()))?.price || 25000);
      const mu = 0.0, sigma = 0.04; // drift ~0, 4%/jour
      const dt = 1.0;
      let finals = [];
      for (let p=0;p<paths;p++){
        let s = priceNow;
        for (let d=0; d<days; d++){
          const z = Math.sqrt(dt) * (Math.random()*2-1); // bruit simple
          s = s * Math.exp((mu - 0.5*sigma*sigma)*dt + sigma*z);
        }
        finals.push(s);
      }
      finals.sort((a,b)=>a-b);
      const pct = q=> finals[Math.floor((q/100)*finals.length)];
      el('simMsg').textContent =
        `Prix now=${priceNow.toFixed(2)} · J+${days} -> P10=${pct(10).toFixed(2)} / P50=${pct(50).toFixed(2)} / P90=${pct(90).toFixed(2)} (N=${paths})`;
    }catch(e){
      el('simMsg').textContent = 'Erreur simulation.';
      console.error(e);
    }
  }
  document.addEventListener('DOMContentLoaded', ()=>{
    document.getElementById('btnRunSim')?.addEventListener('click', runSim);
  });
})();

function fmtPct(x){ return (x*100).toFixed(2) + "%"; }
function fmtBps(x){ return (x*10000).toFixed(1) + " bps"; }

function chipClass(id){
  if (id === "ev_below" || id === "kill_switch") return "chip err";
  if (id === "low_vol" || id === "cooldown" || id === "trend_not_ok") return "chip warn";
  return "chip";
}

function renderWhy(data){
  const el = document.getElementById("why-body");
  if(!el) return;
  el.innerHTML = "";
  if(!data || !data.ok){
    const s = document.createElement("span");
    s.className = "chip";
    s.textContent = "—";
    el.appendChild(s);
    return;
  }
  const rs = data.reasons || [];
  if (data.in_position){
    const s = document.createElement("span");
    s.className = "chip ok";
    s.textContent = "Déjà en position";
    el.appendChild(s);
  }
  rs.forEach(r => {
    const s = document.createElement("span");
    s.className = chipClass(r.id);
    if(r.id === "cooldown")         s.textContent = `Cooldown ${Math.ceil(r.remaining_s)}s`;
    else if(r.id === "max_per_hour") s.textContent = `Plafond d'ordres: ${r.count}/${r.max}`;
    else if(r.id === "kill_switch")  s.textContent = `Kill-switch: ${r.reason}`;
    else if(r.id === "low_vol")      s.textContent = `Vol basse: ATR/px ${fmtPct(r.atr_pct)} < VOL_MIN ${fmtPct(r.vol_min)}`;
    else if(r.id === "p_up_below")   s.textContent = `p_up ${fmtPct(r.p_up)} < PBUY ${fmtPct(r.pbuy)}`;
    else if(r.id === "ev_below")     s.textContent = `EV_net ${fmtBps(r.ev_net)} < seuil ${fmtBps(r.min_ev)}`;
    else if(r.id === "trend_not_ok") s.textContent = `Tendance faible (EMA12<EMA48 / sig<min / RSI bas)`;
    else                             s.textContent = r.id;
    el.appendChild(s);
  });
  if (rs.length === 0 && !data.in_position){
    const s = document.createElement("span");
    s.className = "chip";
    s.textContent = "Aucune contrainte — en attente d'entrée";
    el.appendChild(s);
  }
}
function addChip(el, txt, cls="chip"){
  const s = document.createElement("span");
  s.className = cls;
  s.textContent = txt;
  el.appendChild(s);
}

function renderWhyNow(data){
  const cont = document.getElementById("why-now");
  if(!cont) return;
  cont.innerHTML = "";
  if(!data || !data.ok || !data.now){
    addChip(cont, "—");
    return;
  }
  const now = data.now;
  const reasons = Array.isArray(now.reasons) ? now.reasons : [];
  if (reasons.length === 0){
    // show no-trade explanation if provided
    const nt = now.no_trade_explanation;
    if (nt && nt.line) addChip(cont, nt.line);
    (nt && Array.isArray(nt.bullets) ? nt.bullets : []).forEach(b => addChip(cont, b));
    if (!cont.childElementCount) addChip(cont, "Rien à signaler");
    return;
  }
  reasons.forEach(r => {
    const ok = !!r.pass;
    const label = (r.name || r.id || "règle") + (typeof r.value!=="undefined" && typeof r.threshold!=="undefined"
      ? ` : ${Number(r.value).toFixed(3)} / seuil ${Number(r.threshold).toFixed(3)}`
      : "");
    addChip(cont, label, ok ? "chip ok" : "chip warn");
  });
}

function renderLastActions(data){
  const buyEl = document.getElementById("why-buy");
  const sellEl = document.getElementById("why-sell");
  if (buyEl){
    buyEl.innerHTML = "";
    if (data && data.last_buy){
      if (data.last_buy.line) addChip(buyEl, data.last_buy.line, "chip ok");
      (data.last_buy.bullets || []).forEach(b => addChip(buyEl, b));
    } else {
      addChip(buyEl, "Aucun achat récent");
    }
  }
  if (sellEl){
    sellEl.innerHTML = "";
    if (data && data.last_sell){
      if (data.last_sell.line) addChip(sellEl, data.last_sell.line, "chip warn");
      (data.last_sell.bullets || []).forEach(b => addChip(sellEl, b));
    } else {
      addChip(sellEl, "Aucune vente récente");
    }
  }
}

async function refreshWhySuite(){
  try{
    const [nowR, actsR] = await Promise.all([
      fetch("/api/why/now"),
      fetch("/api/why/last_actions")
    ]);
    const nowJ  = await nowR.json();
    const actsJ = await actsR.json();
    renderWhyNow(nowJ);
    renderLastActions(actsJ);
  }catch(e){ /* ignore UI errors */ }
}
setInterval(refreshWhySuite, 5000);
document.addEventListener("DOMContentLoaded", refreshWhySuite);

let learningMode = false; // false = anciens paramètres

function toggleMode() {
    learningMode = !learningMode;

    const btn = document.getElementById("toggleMode");
    if (learningMode) {
        btn.textContent = "Mode apprentissage : ON";
        // envoyer au backend pour activer les nouveaux paramètres
        fetch('/api/set_params', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: "learning"})
        });
    } else {
        btn.textContent = "Mode apprentissage : OFF";
        // envoyer au backend pour revenir aux anciens paramètres
        fetch('/api/set_params', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({mode: "normal"})
        });
    }
}

async function fetchJson(url, opts = {}) {
  try {
    const r = await fetch(url, { cache: 'no-store', ...opts });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } catch (e) {
    console.warn('fetchJson error:', url, e);
    return null; // ou {}
  }
}

// Exemple d'usage
async function fetchAutotradeState() {
  const data = await fetchJson('/api/autotrade');
  if (!data) return; // éviter de planter l’UI
  // ...mise à jour de l’UI
}

async function fetchAutotradeState() {
  try {
    const r = await fetch('/api/autotrade', { cache: 'no-store' });
    const j = await r.json();

    const elNew = document.getElementById('autotrade-status'); // nouveau badge
    const elOld = document.getElementById('autoBadge');         // ancien badge
    const last  = document.getElementById('autotrade-last');

    const text = j.ok ? (j.paused ? 'OFF (paused)' : 'ON (running)') : 'ERREUR';

    if (elNew) elNew.textContent = text;
    if (elOld) elOld.textContent = 'Autotrade : ' + text;
    if (last)  last.textContent  = new Date().toISOString();

    // (optionnel) style visuel
    if (elOld) {
      elOld.classList.remove('badge-ok','badge-off');
      elOld.classList.add(j.paused ? 'badge-off' : 'badge-ok');
    }
  } catch (e) {
    console.error(e);
    const elNew = document.getElementById('autotrade-status');
    const elOld = document.getElementById('autoBadge');
    if (elNew) elNew.textContent = 'ERREUR réseau';
    if (elOld) elOld.textContent = 'Autotrade : ERREUR réseau';
  }
}

let toggleBusy = false;

async function toggleAutotrade() {
  if (toggleBusy) return;
  toggleBusy = true;
  try {
    const r = await fetch('/api/autotrade/toggle', { method: 'POST', headers: {'Content-Type':'application/json'} });
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || 'toggle failed');

    // Applique immédiatement la réponse du backend
    const text = j.paused ? 'OFF (paused)' : 'ON (running)';
    const elNew = document.getElementById('autotrade-status');
    const elOld = document.getElementById('autoBadge');
    if (elNew) elNew.textContent = text;
    if (elOld) elOld.textContent = 'Autotrade : ' + text;

    // Laisse 800ms avant le prochain poll pour éviter un “rebond” visuel
    setTimeout(fetchAutotradeState, 800);
  } catch (e) {
    console.error(e);
    alert('Impossible de basculer: ' + e.message);
  } finally {
    toggleBusy = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('autotrade-toggle')?.addEventListener('click', toggleAutotrade);
  fetchAutotradeState();
  // rafraîchit toutes les 5s pour rester sync
  setInterval(fetchAutotradeState, 5000);
});



// ===== Historique de trades + KPIs (20s) =====
(function(){
  const tbody = document.getElementById('tradesTableBody');
  const setTxt = (id, v) => { const x = document.getElementById(id); if(x) x.textContent = v; };

  function fmtNum(n, d=2){ return (n==null||isNaN(n)) ? '—' : Number(n).toLocaleString('fr-FR',{maximumFractionDigits:d}); }
  function fmtTs(ts){
    let d;
    if (typeof ts === 'number'){ d = new Date(ts < 1e12 ? ts*1000 : ts); }
    else { const s=String(ts).trim(); d = new Date(/\dZ$/.test(s)||/[\+\-]\d{2}:?\d{2}$/.test(s)?s:s.replace(' ','T')+'Z'); }
    return isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('fr-FR', {hour12:false, timeZone:'Europe/Zurich'});
  }

  async function refreshTrades(){
    if (!tbody || !window.API || typeof API.fetchTrades!=='function') return;
    const [trades, status] = await Promise.all([
      API.fetchTrades().catch(()=>null),
      (typeof API.fetchStatus==='function' ? API.fetchStatus().catch(()=>null) : null)
    ]);
    const arr = Array.isArray(trades) ? trades : (trades?.items || []);
    const px  = Number(status?.price || 0);

    // Render table (latest first, up to 200)
    tbody.innerHTML='';
    arr.slice(-200).reverse().forEach(row => {
      const tr = document.createElement('tr');
      const td = (t) => { const x = document.createElement('td'); x.textContent = t; return x; };
      tr.append(td(String(row.id ?? '—')));
      tr.append(td(String((row.side||row.type||row.action||'').toUpperCase()||'—')));
      tr.append(td(fmtNum(Number(row.price), 2)));
      tr.append(td(fmtNum(Number(row.qty ?? row.size), 6)));
      tr.append(td(fmtNum(Number(row.fee ?? row.f), 6)));
      tr.append(td(fmtTs(row.time || row.ts || row.t || row.timestamp)));
      tr.append(td('—'));
      tbody.appendChild(tr);
    });
    if(!tbody.childElementCount){
      const tr = document.createElement('tr'); const td = document.createElement('td');
      td.colSpan=7; td.style.opacity='.8'; td.style.padding='8px'; td.textContent='Aucun trade.'; tr.appendChild(td); tbody.appendChild(tr);
    }

    // Compute KPIs
    // simple FIFO inventory with realized/unrealized PnL
    const inv = [];
    let realized = 0;
    let maxEquity = 0;
    let equity = 0;
    let winners=0, losers=0;

    const addLot = (qty, price, fee=0) => inv.push({qty, cost:price, fee});
    const removeLot = (qty, price, fee=0) => {
      let remaining = qty;
      while(remaining>1e-12 && inv.length){
        const lot = inv[0];
        const dq = Math.min(remaining, lot.qty);
        const pnl = (price - lot.cost) * dq - fee*(dq/qty); // apportion sell fee
        realized += pnl;
        equity = realized; // equity on realized curve
        maxEquity = Math.max(maxEquity, equity);
        const pnlSign = pnl >= 0 ? 1 : -1;
        if (dq === qty){ if (pnlSign>0) winners++; else if (pnlSign<0) losers++; } // count by fill
        lot.qty -= dq;
        remaining -= dq;
        if (lot.qty <= 1e-12) inv.shift();
      }
    };

    arr.forEach(t => {
      const side=(t.side||t.type||t.action||'').toUpperCase();
      const q=Number(t.qty ?? t.size ?? 0); const p=Number(t.price ?? t.p ?? 0); const f=Number(t.fee ?? t.f ?? 0);
      if (!q || !p) return;
      if (side==='BUY') addLot(q, p, f);
      else if (side==='SELL') removeLot(q, p, f);
    });

    const posQty = inv.reduce((s,l)=>s+l.qty,0);
    const avgCost = posQty>0 ? inv.reduce((s,l)=>s + l.qty*l.cost,0)/posQty : 0;
    const unrealized = (posQty>0 && px>0) ? (px - avgCost) * posQty : 0;

    setTxt('pnlCurrent', fmtNum(realized + unrealized, 2));
    setTxt('positionCurrent', posQty>0 ? `LONG ${fmtNum(posQty,6)} BTC` : 'FLAT');
    setTxt('mddVal', fmtNum((maxEquity - equity) || 0, 2));
    const wl = (winners+losers)>0 ? (winners/(winners+losers)) : 0;
    setTxt('wlRatioVal', (winners+losers)>0 ? `${fmtNum(winners,0)} / ${fmtNum(losers,0)} (${(wl*100).toFixed(0)}%)` : '—');
  }

  document.addEventListener('DOMContentLoaded', refreshTrades);
  Auto.every(20000, refreshTrades);
})();

document.addEventListener('DOMContentLoaded', ()=>{
  // premier rendu
  refreshPerfPanel();

  // planification
  if (window.API && API.AutoRefresh){
    API.AutoRefresh.set('perf-day', 60_000, refreshPerfPanel);
  } else {
    setInterval(refreshPerfPanel, 60_000);
  }
});
function reservePerfSpace(){
  const dock = document.getElementById('perfDock');
  if (!dock) return;
  const h = dock.getBoundingClientRect().height || 0;
  document.documentElement.style.setProperty('--perfDockH', h + 'px');
}

document.addEventListener('DOMContentLoaded', ()=>{
  // déjà en place chez toi : refreshPerfPanel(); + auto-refresh 60s
  refreshPerfPanel();
  if (window.API && API.AutoRefresh) API.AutoRefresh.set('perf-day', 60_000, refreshPerfPanel);
  else setInterval(refreshPerfPanel, 60_000);

  // toggle + espace réservé
  const dock = document.getElementById('perfDock');
  const btnT = document.getElementById('perfToggle');
  const btnR = document.getElementById('perfResetBase');

  reservePerfSpace();
  window.addEventListener('resize', reservePerfSpace);

  if (btnT) btnT.addEventListener('click', ()=>{
    dock.classList.toggle('collapsed');
    reservePerfSpace();
  });
  if (btnR && !btnR.dataset.bound){
    btnR.dataset.bound = '1';
    btnR.addEventListener('click', async ()=>{
      try{ await fetch('/api/perf/reset_base', {method:'POST', credentials:'same-origin'}); }
      catch(_){}
      await refreshPerfPanel();
    });
  }
});
