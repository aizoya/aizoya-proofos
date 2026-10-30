const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const {webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..'),code=fs.readFileSync(path.join(root,'public/recorded.js'),'utf8'),raw=fs.readFileSync(path.join(root,'public/recorded-nebius-run.json'),'utf8');
async function scenario({body=raw,ok=true,digestFails=false}={}){
 const elements=new Map(),requests=[],downloads=[],blobs=[];
 const get=id=>{if(!elements.has(id))elements.set(id,{hidden:true,disabled:false,textContent:'',handlers:{},addEventListener(k,f){this.handlers[k]=f},focus(){this.focused=true}});return elements.get(id)};
 const document={getElementById:get,createElement(){return {click(){downloads.push(this.download)}}}};
 const context={document,TextEncoder,Uint8Array,Blob,URL:class extends URL{static createObjectURL(b){blobs.push(b);return 'blob:test'}static revokeObjectURL(){}},crypto:digestFails?{subtle:{digest:async()=>{throw Error('Digest unavailable')}}}:webcrypto,fetch:async(url)=>{requests.push(url);assert.equal(url,'/recorded-nebius-run.json');return {ok,text:async()=>body}}};
 vm.runInNewContext(code,context);
 assert.equal(requests.length,0,'No request on initial page load');
 await get('inspect-recorded').handlers.click();
 return {get,requests,downloads,blobs};
}
(async()=>{
 let s=await scenario();assert.equal(s.get('recorded-outcome').hidden,false);assert.equal(s.get('recorded-verdict').textContent,'NEEDS_REVIEW · INSUFFICIENT');assert.match(s.get('recorded-feedback').textContent,/Recorded live run; no new model call/);
 s.get('download-recorded').handlers.click();assert.equal(s.downloads.length,1);assert.equal(await s.blobs[0].text(),raw,'Download preserves the original receipt bytes');assert.equal(s.requests.length,1);
 for(const options of [{body:raw.replace('INSUFFICIENT','SUPPORTED')},{ok:false},{digestFails:true}]){
  s=await scenario(options);assert.equal(s.get('recorded-outcome').hidden,true);assert.equal(s.get('download-recorded').disabled,true);assert.equal(s.get('recorded-json').textContent,'');s.get('download-recorded').handlers.click();assert.equal(s.downloads.length,0);
 }
 console.log('PASS: recorded result, original-byte download, no initial/provider calls, tampered receipt, HTTP failure, unavailable integrity check');
})().catch(e=>{console.error(e);process.exitCode=1});
