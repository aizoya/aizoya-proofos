'use strict';
const byId = id => document.getElementById(id);
let releaseId = null, receipt = null;
const fields = ['claim', 'url', 'quote', 'excerpt'];
function clearResult() {
  receipt = null;
  byId('outcome').hidden = true; byId('empty').hidden = false;
  byId('review-json').textContent = '';
  byId('feedback').textContent = 'Input changed. Review it again for a current receipt.';
}
fields.forEach(id => byId(id).addEventListener('input', clearResult));
byId('example').addEventListener('click', () => {
  clearResult();
  const passage = 'Submissions are due Friday, October 30 at 10:00 AM PT.';
  byId('claim').value = 'The hackathon submission deadline is October 30, 2026 at 10 AM Pacific.';
  byId('url').value = 'https://nebiusglobalaihackathon.devpost.com/updates/46207-final-stretch-here-s-your-submission-checklist';
  byId('quote').value = passage;
  byId('excerpt').value = passage;
  byId('feedback').textContent = 'Published text snapshot loaded. Open the original to check its current content.';
  byId('claim').focus();
});
byId('source-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!releaseId || byId('review').disabled) return;
  receipt = null; byId('outcome').hidden = true; byId('review-json').textContent = '';
  byId('review').disabled = true; byId('feedback').textContent = 'Checking the supplied passage…';
  const input = Object.fromEntries(fields.map(id => [id, byId(id).value]));
  fields.forEach(id => { byId(id).disabled = true; }); byId('example').disabled = true;
  try {
    const response = await fetch('/api/review', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(input)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Review failed');
    if (data.release_id !== releaseId) throw new Error('Release changed; reload before continuing');
    // Never render untrusted source or model text as HTML.
    receipt = data;
    byId('conclusion').textContent = data.conclusion;
    byId('next').textContent = data.recommended_next_action;
    byId('checks').replaceChildren(...data.checks.map(check => {const li=document.createElement('li');li.textContent=check.outcome+' · '+check.name;return li;}));
    byId('original').href = data.evidence.url;
    byId('timing').textContent = typeof data.server_processing_ms === 'number' && Number.isFinite(data.server_processing_ms) ? data.server_processing_ms.toFixed(2) + ' ms' : 'Not available';
    byId('review-json').textContent = JSON.stringify(data, null, 2);
    byId('empty').hidden = true; byId('outcome').hidden = false; byId('outcome').focus();
    byId('feedback').textContent = 'Review ready. Factual truth and live inference remain unchecked.';
  } catch (error) {
    receipt = null; byId('feedback').textContent = error.message + '. No automatic retry.';
  } finally { fields.forEach(id => { byId(id).disabled = false; }); byId('example').disabled = false; byId('review').disabled = !releaseId; }
});
byId('download-review').addEventListener('click', () => {
  if (!receipt) return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='proofos-source-review-'+receipt.task_id+'.json';a.click();URL.revokeObjectURL(url);
});
fetch('/api/review').then(async response => {
  if (!response.ok) throw new Error('Service unavailable');
  const status=await response.json();
  if (!status.ready || !status.release_id) throw new Error('Approved origin is not configured');
  releaseId=status.release_id;byId('review').disabled=false;
  byId('build-info').textContent='Release: '+status.release_id+' · Engine source: '+status.source_candidate_id+' · Live model: not run.';
  byId('feedback').textContent='Ready. Paste public source text or start with the published example.';
}).catch(error => {byId('feedback').textContent=error.message+'. Review unavailable; no automatic retry.';});
