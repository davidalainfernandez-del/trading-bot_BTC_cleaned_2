(function () {
  // Namespace commun
  if (!window.API) window.API = {};
  const NS = window.API;

  

  // ==========================
  // Utilitaires génériques
  // ==========================
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

  // ==========================
  // Endpoints Flask réels
  // ==========================
  NS.fetchSentimentSnapshot = function () { return getJSON('/api/sentiment'); };
  NS.fetchSentimentTimeline = function () { return getJSON('/api/sentiment_price'); };
  NS.fetchCorrelation      = function () { return getJSON('/api/sentiment_correlation'); };
  NS.fetchSocialSentiments = function () { return getJSON('/tweets-sentiment'); };

  // ==========================
  // Rendu DOM (best-effort)
  // ==========================
  function renderSnapshot(data) {
    // Cibles possibles (prends la première qui existe)
    const target = $('#sentiment-snapshot') || $('[data-sentiment-snapshot]');
    if (!target) return;

    // Rendu simple sous forme de tableau clé/valeur
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

  function renderCorrelation(obj) {
    const el = $('#correlationValue') || $('[data-correlation]');
    if (!el) return;
    const val = (obj && typeof obj === 'object') ? obj.correlation : obj;
    el.textContent = fmtNum(val, 3);
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

  // --- Timeline -> graphique ---
  // Essaie Chart.js si présent et si un <canvas> est dispo. Sinon fallbacks.
  let chartInstance = null;
  function renderTimeline(series) {
    const data = Array.isArray(series) ? series : [];
    // Détecte la cible
    const canvas = $('#sentimentChart') || $('#lstmCanvas') || document.querySelector('canvas[data-sentiment-chart]');
    const tableTarget = $('#timelineTable') || $('[data-timeline-table]');

    if (canvas && window.Chart) {
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
          interaction: { mode: 'index', intersect: false },
          stacked: false,
          scales: {
            y1: { type: 'linear', position: 'left' },
            y2: { type: 'linear', position: 'right', grid: { drawOnChartArea: false } }
          }
        }
      };

      if (chartInstance) { chartInstance.destroy(); }
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
        th.style.borderBottom = '2px solid #ccc';
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
          td.style.borderBottom = '1px solid #eee';
        });
        tr.append(tdT, tdS, tdP);
        tbody.append(tr);
      });

      table.append(thead, tbody);
      tableTarget.append(table);
    }
  }

  // ==========================
  // Cycle de vie
  // ==========================
  async function refreshAll() {
    // Snapshot
    try {
      const snap = await NS.fetchSentimentSnapshot();
      renderSnapshot(snap);
      window.dispatchEvent(new CustomEvent('sentiment:snapshot', { detail: snap }));
    } catch (e) { console.error('Snapshot error:', e); }

    // Timeline
    try {
      const series = await NS.fetchSentimentTimeline();
      renderTimeline(series);
      window.dispatchEvent(new CustomEvent('sentiment:timeline', { detail: series }));
    } catch (e) { console.error('Timeline error:', e); }

    // Correlation
    try {
      const corr = await NS.fetchCorrelation();
      renderCorrelation(corr);
      window.dispatchEvent(new CustomEvent('sentiment:correlation', { detail: corr }));
    } catch (e) { console.error('Correlation error:', e); }

    // Social
    try {
      const social = await NS.fetchSocialSentiments();
      renderSocial(social);
      window.dispatchEvent(new CustomEvent('sentiment:social', { detail: social }));
    } catch (e) { console.error('Social error:', e); }
  }

  // Expose une API simple
  NS.refreshAll = refreshAll;
  NS.start = function start(intervalMs = 30000) {
    refreshAll();
    if (start._timer) clearInterval(start._timer);
    start._timer = setInterval(refreshAll, intervalMs);
    return () => clearInterval(start._timer);
  };

  // Auto-init si le DOM est prêt
  document.addEventListener('DOMContentLoaded', () => {
    // Démarre automatiquement si on trouve au moins une cible reconnue
    const hasTargets = $('#sentiment-snapshot') || $('[data-sentiment-snapshot]') ||
                       $('#correlationValue') || $('[data-correlation]') ||
                       $('#socialList') || $('[data-social-list]') ||
                       $('#sentimentChart') || $('#lstmCanvas') || document.querySelector('canvas[data-sentiment-chart]') ||
                       $('#timelineTable') || $('[data-timeline-table]');
    if (hasTargets) NS.start(30000); // 30s par défaut
  });
})();
