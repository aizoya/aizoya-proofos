'use strict';
(() => {
  const el=id=>document.getElementById(id);
  const expected='f4b1227712e5c7be01ff47f1f6cdf018b434923c76445b39b8006a021062686a';
  let current=null,busy=false;
  function clear(){current=null;el('recorded-outcome').hidden=true;el('recorded-json').textContent='';el('download-recorded').disabled=true;}
  el('inspect-recorded').addEventListener('click',async()=>{
    if(busy)return;busy=true;clear();el('inspect-recorded').disabled=true;
    el('recorded-feedback').textContent='Checking the packaged receipt bytes…';
    try{
      const response=await fetch('/recorded-nebius-run.json',{cache:'no-store'});
      if(!response.ok)throw Error('Recorded receipt unavailable');
      const raw=await response.text();
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw))),b=>b.toString(16).padStart(2,'0')).join('');
      if(digest!==expected)throw Error('Recorded receipt integrity mismatch');
      const data=JSON.parse(raw),assessment=data.model_analysis?.model_assessment;
      if(data.schema!=='proofos.model-review.v1'||data.release_id!=='sha256:c2b57f4b3b69dc3a7554a84932b5e23db23af652546379d7bd681e28927e101c'||data.fully_verified!==false||data.execution_evidence!=='OBSERVED_RESPONSE'||data.provider_evidence?.http_status!==200||data.provider_calls!==1||data.final_status!=='NEEDS_REVIEW'||assessment?.verdict!=='INSUFFICIENT')throw Error('Recorded receipt contract mismatch');
      const source=new URL(data.source_review.evidence.url);
      if(source.protocol!=='https:'||source.username||source.password)throw Error('Recorded source link invalid');
      el('recorded-verdict').textContent=data.final_status+' · '+assessment.verdict;
      el('recorded-explanation').textContent=assessment.explanation;
      el('recorded-tokens').textContent=JSON.stringify(data.usage);
      el('recorded-cost').textContent='$'+data.priced_usage_usd+' estimated';
      el('recorded-time').textContent=data.elapsed_ms.toFixed(2)+' ms';
      el('recorded-attribution').textContent=data.provider+' · '+data.reported_model+' · '+data.response_id+' · completed '+data.finished_at;
      el('recorded-claim').textContent=data.source_review.evidence.claim;
      el('recorded-passage').textContent=data.source_review.evidence.excerpt;
      el('recorded-source').href=source.href;
      el('recorded-json').textContent=raw;current=raw;
      el('recorded-outcome').hidden=false;el('download-recorded').disabled=false;el('recorded-outcome').focus();
      el('recorded-feedback').textContent='Original packaged receipt loaded. Recorded live run; no new model call. Byte integrity does not authenticate the provider.';
    }catch(error){clear();el('recorded-feedback').textContent=error.message+'. Recorded result unavailable.';}
    finally{busy=false;el('inspect-recorded').disabled=false;}
  });
  el('download-recorded').addEventListener('click',()=>{
    if(!current)return;
    const url=URL.createObjectURL(new Blob([current],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='proofos-recorded-live-run-2026-10-29.json';a.click();URL.revokeObjectURL(url);
  });
})();
