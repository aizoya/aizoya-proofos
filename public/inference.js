'use strict';
// No inference request occurs on page load, example load, input edit or download.
(() => {
  const el=id=>document.getElementById(id),keys=['claim','url','quote','excerpt'];
  let status=null,current=null,busy=false,consumed=false;
  const matches=()=>status && keys.every(k=>el(k).value===status.required_input[k]);
  function sync(){el('run-model').disabled=busy||consumed||!status?.ready||!matches();}
  function clear(){current=null;el('model-outcome').hidden=true;el('model-json').textContent='';sync();}
  keys.forEach(k=>el(k).addEventListener('input',clear));
  el('example').addEventListener('click',clear);
  el('run-model').addEventListener('click',async()=>{
    if(busy||consumed||el('review').disabled||!status?.ready||!matches())return;
    const payload=Object.fromEntries(keys.map(k=>[k,el(k).value]));
    busy=true;consumed=true;clear();
    keys.forEach(k=>el(k).disabled=true);el('example').disabled=true;el('review').disabled=true;
    el('feedback').textContent='NVIDIA sample requested through the owner-local guard. No automatic retry.';
    try{
      const response=await fetch('/api/inference',{method:'POST',headers:{'Content-Type':'application/json','X-ProofOS-Inference':'owner-local'},body:JSON.stringify(payload)});
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Inference unavailable');
      if(data.release_id!==status.release_id||data.fully_verified!==false)throw Error('Receipt binding unavailable');
      current=data;
      const assessment=data.model_analysis?.model_assessment;
      el('model-verdict').textContent=data.final_status+' · '+(assessment?.verdict||'No accepted model assessment');
      el('model-explanation').textContent=assessment?.explanation||data.recommended_next_action;
      el('model-next').textContent=data.recommended_next_action;
      el('model-attribution').textContent=data.provider+' · requested '+data.requested_model+' · reported '+(data.reported_model||'unavailable');
      el('model-evidence-label').textContent=data.execution_evidence==='TEST_DOUBLE'?'TEST DOUBLE — no live inference evidence':data.execution_evidence==='OBSERVED_RESPONSE'?'Provider response observed — factual truth still needs review':'Execution unconfirmed — do not retry';
      el('model-usage').textContent=data.usage?JSON.stringify(data.usage):'Usage unavailable';
      el('model-cost').textContent=data.priced_usage_usd!==null&&data.priced_usage_usd!==undefined?'$'+data.priced_usage_usd+' estimated from reported tokens':'Cost unknown';
      el('model-time').textContent=typeof data.elapsed_ms==='number'?data.elapsed_ms.toFixed(2)+' ms guard elapsed':'Timing unavailable';
      el('model-json').textContent=JSON.stringify(data,null,2);el('model-outcome').hidden=false;el('model-outcome').focus();
      el('feedback').textContent='Model receipt ready. Source authenticity and business outcome remain unchecked.';
    }catch(error){current=null;el('feedback').textContent=error.message+'. Reconcile this attempt; do not retry.';}
    finally{busy=false;keys.forEach(k=>el(k).disabled=false);el('example').disabled=false;el('review').disabled=!releaseId;sync();}
  });
  el('download-model').addEventListener('click',()=>{
    if(!current)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='proofos-model-review-'+current.task_id+'.json';a.click();URL.revokeObjectURL(url);
  });
  fetch('/api/inference').then(async r=>{
    if(!r.ok)throw Error('Owner-local backend required; Vercel inference is not enabled.');
    const data=await r.json();
    if(!data.required_input||!data.release_id)throw Error('Inference status unavailable.');
    status=data;el('model-availability').textContent=data.reason||'Only the unchanged published deadline sample is eligible for the one-attempt guard.';sync();
  }).catch(e=>{el('model-availability').textContent=e.message;sync();});
})();
