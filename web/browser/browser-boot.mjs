const realFetch=globalThis.fetch.bind(globalThis);
const status=document.querySelector('#content');
const notice=document.createElement('div');
notice.className='notice';
notice.textContent='웹 버전 · 이 브라우저에만 저장됩니다. 다른 기기로 옮길 때 입력값을 내보내세요. 브라우저 데이터를 삭제하면 저장본도 지워집니다.';
document.querySelector('main').prepend(notice);
document.querySelector('.local-status').textContent='이 브라우저에 저장';
globalThis.HOMEPLAN_BROWSER=true;
const worker=new Worker(new URL('./browser-worker.js',import.meta.url));
const pending=new Map();let sequence=0;
const request=payload=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});worker.postMessage({id,...payload});});
worker.onmessage=({data})=>{
  if(data.progress){status.textContent=data.progress;return;}
  const item=pending.get(data.id);if(!item)return;pending.delete(data.id);
  data.error?item.reject(new Error(data.error)):item.resolve(data.result);
};
worker.onerror=event=>{for(const {reject} of pending.values())reject(new Error(event.message));pending.clear();};
const locked=fn=>navigator.locks.request('homeplan-browser-database',fn);
try{
  if(!navigator.locks||!globalThis.indexedDB)throw new Error('이 브라우저에서는 저장 기능을 사용할 수 없습니다. 최신 Edge 또는 Chrome으로 열어주세요.');
  await locked(()=>request({init:true}));
  globalThis.fetch=async(input,options={})=>{
    const url=new URL(typeof input==='string'?input:input.url,location.href);
    if(url.origin!==location.origin||!url.pathname.startsWith('/api/'))return realFetch(input,options);
    const result=await locked(()=>request({path:url.pathname+url.search,method:options.method||'GET',body:options.body||''}));
    return new Response(result.body,{status:result.status,headers:result.headers});
  };
  await import('./app.js');
  navigator.storage?.persist?.().catch(()=>{});
  let current=(await realFetch(new URL('./build.json',import.meta.url),{cache:'no-store'})).json();current=await current;
  setInterval(async()=>{
    try{
      const latest=await(await realFetch(new URL('./build.json',import.meta.url),{cache:'no-store'})).json();
      if(latest.engine!==current.engine){notice.textContent='새 버전이 배포되었습니다. 변경사항을 저장한 뒤 새로고침하면 업데이트됩니다.';}
    }catch{}
  },300000);
}catch(error){
  status.replaceChildren();
  const title=document.createElement('h2');title.textContent='웹 앱을 준비하지 못했습니다.';
  const message=document.createElement('p');message.textContent=error.message;
  const retry=document.createElement('button');retry.className='button primary';retry.textContent='다시 시도';retry.onclick=()=>location.reload();
  status.append(title,message,retry);
}
