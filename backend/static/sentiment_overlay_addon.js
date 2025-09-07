
// ============================================================================
// ADDON — Sentiments (Reddit/Twitter/Combined) + Overlay BTC
// ============================================================================
(function(){
  // Fallback drawLineChart if not present
  if (typeof window.drawLineChart !== 'function') {
    window.drawLineChart = function(canvas, seriesList, {padding=12, yLabel=null, xTicks=4, yTicks=4} = {}){
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      const width = canvas.clientWidth * dpr;
      const height = canvas.clientHeight * dpr;
      if (canvas.width !== width) canvas.width = width;
      if (canvas.height !== height) canvas.height = height;
      ctx.clearRect(0,0,width,height);

      let xs=[], ys=[];
      for(const s of seriesList){ for(const p of (s.data||[])){ if(p && isFinite(p.x) && isFinite(p.y)){ xs.push(p.x); ys.push(p.y); } } }
      if(!xs.length) return;
      const xMin=Math.min(...xs), xMax=Math.max(...xs), yMin=Math.min(...ys), yMax=Math.max(...ys);
      const px=(x)=> padding + (width - padding*2) * ((x - xMin) / Math.max(1e-9, xMax - xMin));
      const py=(y)=> (height - padding) - (height - padding*2) * ((y - yMin) / Math.max(1e-9, yMax - yMin));

      ctx.lineWidth = 1*dpr; ctx.strokeStyle='rgba(255,255,255,0.12)';
      ctx.beginPath(); ctx.moveTo(padding,padding); ctx.lineTo(padding,height-padding); ctx.lineTo(width-padding,height-padding); ctx.stroke();

      let hue=210;
      for(const s of seriesList){
        ctx.beginPath();
        ctx.lineWidth=(s.width||2)*dpr;
        ctx.strokeStyle = s.color || `hsl(${hue},70%,60%)`; hue=(hue+60)%360;
        let started=false;
        for(const p of (s.data||[])){
          if(!p||!isFinite(p.x)||!isFinite(p.y)) continue;
          const x=px(p.x), y=py(p.y);
          if(!started){ ctx.moveTo(x,y); started=true; } else { ctx.lineTo(x,y); }
        }
        ctx.stroke();
      }
    };
  }

  // Simple fetch JSON helper (silent)
  async function fetchJSON(url){
    try{ const r = await fetch(url, {credentials:'same-origin'}); return await r.json(); }catch(_){ return null; }
  }

  // In-memory ring buffer for sentiment snapshots
  const SentBuf = (()=>{
    const max = 300; // keep last 300 points
    const arr = [];
    return {
      push(pt){ arr.push(pt); if(arr.length>max) arr.shift(); },
      get(){ return arr.slice(); },
      clear(){ arr.length=0; }
    };
  })();
  (async ()=>{
  try {
    const j = await fetch(`/api/sentiment/series?symbol=${sym}&window=3d&fields=tw,rd,nw,tr,cb`)
    const rows = (j && j.series) || [];
    rows.forEach(r=>{
      const vs = [];
      if (typeof r.tw === 'number') vs.push(r.tw);
      if (typeof r.rd === 'number') vs.push(r.rd);
      if (typeof r.nw === 'number') vs.push(r.nw);
      const cb = (typeof r.cb === 'number')
      ? r.cb
      : (vs.length ? (vs.reduce((a,b)=>a+b,0)/vs.length) : null);
      SentBuf.push({ t: r.t, tw: r.tw, rd: r.rd, cb });
    });
  } catch(e) {}
})();

  function nowTs(){ return Date.now(); }

  function toSeriesFromBuf(buf){
    const xsT=[], xsR=[], xsC=[];
    buf.forEach((p, i)=>{
      if (typeof p.tw === 'number') xsT.push({x:i, y:p.tw});
      if (typeof p.rd === 'number') xsR.push({x:i, y:p.rd});
      if (typeof p.cb === 'number') xsC.push({x:i, y:p.cb});
    });
    return {tw: xsT, rd: xsR, cb: xsC};
  }

  function scaleToRange(values, targetMin, targetMax){
    if(!values.length) return [];
    const ys = values.map(v=>v.y);
    let min = Math.min(...ys), max = Math.max(...ys);
    if (min === max){ min -= 1; max += 1; }
    const scale = (y)=> targetMin + (targetMax-targetMin) * ((y - min) / (max - min));
    return values.map(v=>({x:v.x, y: scale(v.y)}));
  }

  async function refreshSentiments(){
    let data = await fetchJSON('/api/sentiment_combined');
 // Expected: { ok, avg, median, count, reddit:{avg,...}, twitter:{avg,...} }
 if (!data || data.ok === false) {
   // Fallback: on prend le dernier point de /api/sentiment/series (avec cb demandé)
   const j = await fetchJSON('/api/sentiment/series?symbol=BTCUSDT&window=15m&fields=tw,rd,nw,cb');
   const rows = (j && j.series) || [];
   const last = rows[rows.length-1];
   if (!last) return;
   const tw = (typeof last.tw === 'number') ? last.tw : null;
   const rd = (typeof last.rd === 'number') ? last.rd : null;
   const cb = (typeof last.cb === 'number')
     ? last.cb
     : (tw!=null && rd!=null ? (tw+rd)/2 : (tw ?? rd));
   SentBuf.push({ t: nowTs(), tw, rd, cb });
   const buf = SentBuf.get();
   const s = toSeriesFromBuf(buf);
   const canvas = document.getElementById('chartSentiments');
   if (canvas){
     window.drawLineChart(canvas, [
       {name:'Twitter', data: s.tw, color:'hsl(205,80%,60%)', width:2},
       {name:'Reddit', data: s.rd, color:'hsl(5,80%,60%)', width:2},
       {name:'Combined', data: s.cb, color:'hsl(140,70%,55%)', width:2}
     ], {});
   }
   return; // on sort: on a déjà dessiné
 }
    const tw = (data.twitter && typeof data.twitter.avg === 'number') ? data.twitter.avg : null;
    const rd = (data.reddit && typeof data.reddit.avg === 'number') ? data.reddit.avg : null;
    const cb = (typeof data.avg === 'number') ? data.avg : (tw!=null && rd!=null ? (tw+rd)/2 : (tw!=null?tw:rd));
    SentBuf.push({t: nowTs(), tw, rd, cb});
    const buf = SentBuf.get();
    const s = toSeriesFromBuf(buf);
    const canvas = document.getElementById('chartSentiments');
    if (canvas){
      window.drawLineChart(canvas, [
        {name:'Twitter', data: s.tw, color:'hsl(205,80%,60%)', width:2},
        {name:'Reddit', data: s.rd, color:'hsl(5,80%,60%)', width:2},
        {name:'Combined', data: s.cb, color:'hsl(140,70%,55%)', width:2}
      ], {});
    }
  }

  async function refreshOverlay(){
    const buf = SentBuf.get();
    const s = toSeriesFromBuf(buf);
    if (!s.cb.length) return;

    // Price series (prefer API if available)
    let ohlc = null;
   try {
  if (window.API && typeof API.fetchOhlc === 'function') {
    // soit tu relies sur la valeur par défaut :
    ohlc = await API.fetchOhlc('BTCUSDT', '1m');
    // ou si tu veux un nombre précis de bougies :
    // ohlc = await API.fetchOhlc('BTCUSDT', '1m', 120);
  } else {
    ohlc = await fetchJSON('/api/price/ohlc?symbol=BTCUSDT&interval=1m');
  }
} catch (err) {
  console.error('Erreur fetch OHLC:', err);
}


    let priceSer = [];
    if (Array.isArray(ohlc)){
      // Expect objects with close or c
      for (let i=0;i<ohlc.length;i++){
        const o = ohlc[i];
        const y = Number(o.close ?? o.c ?? o.price ?? o.p ?? NaN);
        if (isFinite(y)) priceSer.push({x:i, y});
      }
    }

    // Align sentiment length to price length (tail)
    const N = Math.min(s.cb.length, priceSer.length);
    if (N <= 2){ return; }
    const cbTail = s.cb.slice(-N).map((p,i)=>({x:i, y:p.y}));
    const prTail = priceSer.slice(-N).map((p,i)=>({x:i, y:p.y}));

    const prMin = Math.min(...prTail.map(p=>p.y));
    const prMax = Math.max(...prTail.map(p=>p.y));
    const cbScaled = scaleToRange(cbTail, prMin, prMax);

    const canvas = document.getElementById('chartBtcSent');
    if (canvas){
      window.drawLineChart(canvas, [
        {name:'BTC', data: prTail, color:'hsl(50,90%,60%)', width:2},
        {name:'Sentiment (scaled)', data: cbScaled, color:'hsl(140,70%,55%)', width:2},
      ], {});
    }
  }

  function getRefreshSeconds(id, def){
    const el = document.getElementById(id);
    if (el && el.value) return Math.max(0, parseInt(el.value, 10) || 0);
    const v = localStorage.getItem(id);
    if (v != null) return Math.max(0, parseInt(v,10) || 0);
    return def;
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    const hasAuto = (window.API && API.AutoRefresh);
    const sentSec = getRefreshSeconds('refSent', 30);
    const ohlcSec = getRefreshSeconds('refOhlc', 60);
    if (hasAuto){
      API.AutoRefresh.set('sentiments', sentSec*1000, async ()=>{
        await refreshSentiments();
      });
      API.AutoRefresh.set('overlay', ohlcSec*1000, async ()=>{
        await refreshOverlay();
      });
    } else {
      setInterval(refreshSentiments, sentSec*1000);
      setInterval(refreshOverlay, ohlcSec*1000);
    }
    refreshSentiments().then(refreshOverlay);
  });

})();
