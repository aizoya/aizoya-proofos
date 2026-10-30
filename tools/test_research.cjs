const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../public/research.js'),'utf8');
const receipt={schema:'proofos.retrieval.v1',release_id:'test-release',task_id:'test-only',fully_verified:false,inference_calls:0,plan:{request_sha256:'test-hash'},state:'COMPLETE',final_status:'NEEDS_REVIEW',reported_credits:1,transport_kind:'TEST_DOUBLE',claim:'test claim',elapsed_ms:4,retrieved_at:'test-time',sources:[{title:'Test source',url:'https://nebiusglobalaihackathon.devpost.com/test',excerpt:'<script>untrusted</script>'}]};
async function scenario({body=receipt,ready=true,postOK=true}={}){
 const elements=new Map(),requests=[],downloads=[];
 function element(){return {disabled:false,hidden:true,textContent:'',value:'',children:[],handlers:{},addEventListener(k,f){this.handlers[k]=f},replaceChildren(...x){this.children=x},append(...x){this.children.push(...x)},dispatchEvent(){this.cleared=true},focus(){this.focused=true},click(){downloads.push(this.download)}}}
 const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
 const document={getElementById:get,createElement:element};
 const context={document,Event:class{},Blob,URL:class extends URL{static createObjectURL(){return 'blob:test'}static revokeObjectURL(){}},fetch:async(url,options)=>{requests.push({url,options});assert.equal(url,'/api/research');return options?{ok:postOK,json:async()=>body}:{ok:true,json:async()=>({ready,release_id:'test-release',plan:{request_sha256:'test-hash'},fully_verified:false})}}};
 vm.runInNewContext(code,context);await new Promise(setImmediate);
 assert.equal(requests.length,1);assert.equal(requests[0].options,undefined,'Initial availability check is GET only');
 await get('search-prepared').handlers.click();
 return {get,requests,downloads};
}
(async()=>{
 let s=await scenario();assert.equal(s.get('research-outcome').hidden,false);assert.match(s.get('research-metrics').textContent,/TEST DOUBLE/);
 const card=s.get('research-sources').children[0];assert.equal(card.children[1].textContent,'<script>untrusted</script>');
 card.children[3].handlers.click();assert.equal(s.get('excerpt').value,'<script>untrusted</script>');assert.equal(s.get('quote').value,'');assert.equal(s.get('quote').focused,true);
 s.get('download-research').handlers.click();assert.equal(s.downloads.length,1);
 await s.get('search-prepared').handlers.click();assert.equal(s.requests.length,2,'No second attempt');
 s=await scenario({ready:false});assert.equal(s.requests.length,1);assert.equal(s.get('search-prepared').disabled,true);
 for(const body of [{...receipt,release_id:'wrong'}, {...receipt,fully_verified:true}, {...receipt,sources:[{...receipt.sources[0],url:'javascript:alert(1)'}]}, {...receipt,sources:[]}, {...receipt,reported_credits:2}]){
  s=await scenario({body});assert.equal(s.get('research-outcome').hidden,true);assert.equal(s.get('download-research').disabled,true);
 }
 s=await scenario({body:{...receipt,state:'UNCERTAIN',final_status:'BLOCKED',sources:[]}});assert.equal(s.get('research-outcome').hidden,true);assert.equal(s.get('download-research').disabled,false);assert.match(s.get('research-feedback').textContent,/reconcile/);
 s=await scenario({postOK:false});assert.equal(s.get('download-research').disabled,true);
 console.log('PASS: availability GET only, source cards, text-only rendering, source selection, receipt download, no second attempt, locked approval, wrong identity, fully-verified rejection, unsafe URL, empty results, unexpected credits, blocked receipt and HTTP error');
})().catch(error=>{console.error(error);process.exitCode=1});
