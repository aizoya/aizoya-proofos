'use strict';
(() => {
  const el = id => document.getElementById(id);
  let current = null, context = null, attempted = false;
  const allowedHost = 'nebiusglobalaihackathon.devpost.com';
  const clear = () => {
    current = null; el('research-outcome').hidden = true;
    el('research-sources').replaceChildren(); el('download-research').disabled = true;
  };
  const safeURL = value => {
    const u = new URL(value);
    if (u.protocol !== 'https:' || u.host !== allowedHost || u.username || u.password) throw Error('Unexpected source link');
    return u.href;
  };
  el('search-prepared').addEventListener('click', async () => {
    if (!context?.ready || attempted) return;
    attempted = true; clear(); el('search-prepared').disabled = true;
    el('research-feedback').textContent = 'Searching organizer sources through Tavily. One attempt; no automatic retry…';
    try {
      const response = await fetch('/api/research', {method:'POST', headers:{'Content-Type':'application/json', 'X-ProofOS-Research':'prepared-search-v1'}, body:JSON.stringify({request_sha256:context.plan.request_sha256})});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || 'Search failed');
      if (data.release_id !== context.release_id || data.schema !== 'proofos.retrieval.v1' || data.fully_verified !== false || data.inference_calls !== 0 || data.plan?.request_sha256 !== context.plan.request_sha256) throw Error('Retrieval receipt identity mismatch');
      current = data; el('download-research').disabled = false;
      if (data.state !== 'COMPLETE' || data.final_status !== 'NEEDS_REVIEW') {
        if (data.final_status !== 'BLOCKED' || !['IN_FLIGHT','UNCERTAIN'].includes(data.state)) throw Error('Invalid failure receipt');
        el('research-feedback').textContent = 'Search blocked or uncertain. This attempt cannot be repeated. Download its receipt and reconcile usage.';
        return;
      }
      if (!Array.isArray(data.sources) || data.sources.length < 1 || data.sources.length > 3 || data.reported_credits !== 1 || !['TAVILY_HTTPS','TEST_DOUBLE'].includes(data.transport_kind)) throw Error('Invalid retrieval evidence');
      const cards = data.sources.map(source => {
        if (typeof source.title !== 'string' || typeof source.excerpt !== 'string' || !source.excerpt.trim() || source.excerpt.length > 12000) throw Error('Source excerpt unavailable');
        const url = safeURL(source.url), card = document.createElement('article');
        const title = document.createElement('h3'), link = document.createElement('a'), passage = document.createElement('p'), use = document.createElement('button');
        title.textContent = source.title; passage.textContent = source.excerpt;
        link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Inspect original source ↗';
        use.type = 'button'; use.className = 'secondary'; use.textContent = 'Use this source for a passage check';
        use.addEventListener('click', () => {
          ['claim','url','quote','excerpt'].forEach(id => el(id).dispatchEvent(new Event('input')));
          el('claim').value = data.claim; el('url').value = url; el('excerpt').value = source.excerpt; el('quote').value = '';
          el('feedback').textContent = 'Tavily excerpt loaded. Choose an exact quotation to check. No new model analysis has run.';
          el('quote').focus();
        });
        card.append(title, passage, link, use); return card;
      });
      el('research-sources').replaceChildren(...cards);
      el('research-metrics').textContent = `${data.transport_kind === 'TEST_DOUBLE' ? 'TEST DOUBLE · not live Tavily' : 'Observed Tavily response'} · ${data.sources.length} sources · ${data.reported_credits} reported API credit · ${data.elapsed_ms} ms · retrieved ${data.retrieved_at}`;
      el('research-feedback').textContent = 'Sources retrieved; factual support still needs review. Select a source, inspect its original page, and choose a quotation.';
      el('research-outcome').hidden = false; el('research-outcome').focus();
    } catch (error) {
      clear(); el('research-feedback').textContent = error.message + '. Do not retry; reconcile the retained attempt.';
    }
  });
  el('download-research').addEventListener('click', () => {
    if (!current) return;
    const blob = new Blob([JSON.stringify(current, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob), a = document.createElement('a');
    a.href = url; a.download = 'proofos-retrieval-'+current.task_id+'.json'; a.click(); URL.revokeObjectURL(url);
  });
  fetch('/api/research').then(async response => {
    if (!response.ok) throw Error('Retrieval is not enabled on this server');
    const data = await response.json();
    if (data.fully_verified !== false || typeof data.plan?.request_sha256 !== 'string') throw Error('Retrieval identity unavailable');
    context = data;
    el('search-prepared').disabled = data.ready !== true;
    el('research-feedback').textContent = data.ready ? 'Ready for one approved owner-local Tavily search. Expected usage: one API credit. No model request.' : (data.reason || 'A fresh owner approval is required');
  }).catch(() => {
    el('search-prepared').disabled = true;
    el('research-feedback').textContent = 'Tavily is implemented but live retrieval is locked. The owner-local service needs a fresh reviewed one-credit approval. No search has run here.';
  });
})();
