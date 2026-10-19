const realFetch=globalThis.fetch.bind(globalThis);
const status=document.querySelector('#content');
const notice=document.createElement('div');
notice.className='notice';
notice.textContent='웹 버전 · 이 브라우저에만 저장됩니다. 다른 기기로 옮길 때 입력값을 내보내세요. 브라우저 데이터를 삭제하면 저장본도 지워집니다.';
document.querySelector('main').prepend(notice);
document.querySelector('.local-status').textContent='이 브라우저에 저장';
globalThis.HOMEPLAN_BROWSER=true;
window.homeplanStartup?.wait(180000);
const worker=new Worker(new URL('./browser-worker.js?v=370a8c05cffa45b2',import.meta.url));
const pending=new Map();let sequence=0;
const request=payload=>new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('처리 시간이 초과되었습니다. 연결을 확인하고 다시 열어주세요.'));},payload.init?180000:120000);pending.set(id,{resolve,reject,timer});worker.postMessage({id,...payload});});
worker.onmessage=({data})=>{
  if(data.progress){if(pending.size)status.textContent=data.progress;return;}
  const item=pending.get(data.id);if(!item)return;pending.delete(data.id);clearTimeout(item.timer);
  data.error?item.reject(new Error(data.error)):item.resolve(data.result);
};
worker.onerror=event=>{for(const {reject,timer} of pending.values()){clearTimeout(timer);reject(new Error(event.message));}pending.clear();};
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
  await import('./app.js?v=370a8c05cffa45b2');
  navigator.storage?.persist?.().catch(()=>{});
  let current;try{current=await(await realFetch(new URL('./build.json',import.meta.url),{cache:'no-store',signal:AbortSignal.timeout(4000)})).json();}catch{}
  setInterval(async()=>{
    try{
      const latest=await(await realFetch(new URL('./build.json',import.meta.url),{cache:'no-store',signal:AbortSignal.timeout(4000)})).json();
      if(current&&latest.engine!==current.engine){notice.textContent='새 버전이 배포되었습니다. 변경사항을 저장한 뒤 새로고침하면 업데이트됩니다.';}current=latest;
    }catch{}
  },300000);
}catch(error){
  if(window.homeplanStartup){window.homeplanStartup.fail(error.message);}else{
  status.replaceChildren();
  const title=document.createElement('h2');title.textContent='웹 앱을 준비하지 못했습니다.';
  const message=document.createElement('p');message.textContent=error.message;
  const retry=document.createElement('button');retry.className='button primary';retry.textContent='다시 시도';retry.onclick=()=>location.reload();
  status.append(title,message,retry);
  }
}
