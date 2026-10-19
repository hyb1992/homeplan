const PREFIX='https://github.com/hyb1992/homeplan/releases/download/';
export function releaseStatus(release,currentVersion,currentBuild='development'){
  const base={available:false,version:currentVersion,url:null};
  if(!release||release.draft||release.prerelease)return base;
  const parse=value=>String(value).match(/^v?(\d+)\.(\d+)\.(\d+)(?:$|[-+])/);
  const remote=parse(release.tag_name),local=parse(currentVersion);
  if(!remote||!local)return base;
  const asset=release.assets?.find(item=>item.name==='HomePlan-Windows-x64.zip');
  if(!asset?.browser_download_url?.startsWith(PREFIX))return base;
  const url=new URL(asset.browser_download_url);
  if(url.protocol!=='https:'||url.host!=='github.com'||url.username||url.password)return base;
  let difference=0;for(let i=1;i<=3;i++){difference=Number(remote[i])-Number(local[i]);if(difference)break;}
  const newerBuild=difference===0&&/^[a-f0-9]{40}$/.test(currentBuild)&&/^[a-f0-9]{40}$/.test(release.target_commitish||'')&&currentBuild!==release.target_commitish;
  return {available:difference>0||newerBuild,version:remote.slice(1,4).join('.'),url:asset.browser_download_url};
}
export function newerWebBuild(current,latest){
  if(!current||latest.build===current.build)return false;
  const parse=value=>String(value).match(/^(\d+)\.(\d+)\.(\d+)$/);
  const a=parse(latest.version),b=parse(current.version);if(!a||!b)return false;
  for(let i=1;i<=3;i++){const difference=Number(a[i])-Number(b[i]);if(difference)return difference>0;}
  return Number.isFinite(Date.parse(latest.built_at))&&Date.parse(latest.built_at)>Date.parse(current.built_at);
}
export function installUpdateNotice({canReload=()=>true,beforeReload=()=>{}}={}){
  const panel=document.createElement('div');panel.className='update-notice';panel.id='update-notice';
  panel.innerHTML='<span id="update-state" role="status">버전 확인 중…</span><button class="button small" id="update-check" type="button">새 버전 확인</button><button class="button small soft" id="update-apply" type="button" hidden>업데이트 적용</button>';
  document.querySelector('main').prepend(panel);
  const status=panel.querySelector('#update-state'),button=panel.querySelector('#update-check'),apply=panel.querySelector('#update-apply');
  let checking=false,timer,ready=null,restarting=false;
  const schedule=delay=>{clearTimeout(timer);timer=setTimeout(()=>check(),delay);};
  const reload=()=>{if(!canReload())return false;beforeReload();location.reload();return true;};
  async function applyReady(){
    if(!ready||restarting)return;
    if(!canReload()){status.textContent='업데이트 준비 완료 · 편집 내용을 저장하거나 창을 닫으면 적용합니다.';schedule(5000);return;}
    if(globalThis.HOMEPLAN_BROWSER){reload();return;}
    restarting=true;apply.disabled=true;beforeReload();
    try{
      const response=await fetch('/api/updates/apply',{method:'POST',signal:AbortSignal.timeout(10000)});
      if(!response.ok||!(await response.json()).restarting)throw new Error('not ready');
      status.textContent='새 버전을 적용하고 있습니다. 저장 데이터는 그대로 유지됩니다.';
      for(let attempt=0;attempt<90;attempt++){
        await new Promise(resolve=>setTimeout(resolve,500));
        try{
          const health=await(await fetch('/api/health',{cache:'no-store',signal:AbortSignal.timeout(1000)})).json();
          if(health.version===ready.version){if(!reload()){status.textContent='새 버전이 적용되었습니다. 편집을 마친 뒤 화면을 갱신합니다.';schedule(5000);}return;}
        }catch{}
      }
      throw new Error('restart timeout');
    }catch{status.textContent='업데이트 적용을 미뤘어요. 기존 입력은 유지됩니다. 다음 실행 때 다시 적용합니다.';schedule(300000);}
    finally{restarting=false;apply.disabled=false;}
  }
  async function check(manual=false){
    if(checking||restarting)return;checking=true;button.disabled=true;schedule(900000);
    try{
      if(globalThis.HOMEPLAN_BROWSER){
        const response=await fetch(new URL('./build.json',import.meta.url),{cache:'no-store',signal:AbortSignal.timeout(6000)});
        if(!response.ok)throw new Error('unavailable');
        const latest=await response.json(),current=globalThis.HOMEPLAN_BUILD;
        if(newerWebBuild(current,latest)){ready={version:latest.version};apply.hidden=false;status.textContent=`새 버전 v${latest.version} · 자동 적용 준비 완료`;await applyReady();}
        else{status.textContent=`v${latest.version} · 최신 버전입니다`;apply.hidden=true;}
        return;
      }
      const response=await fetch('/api/updates'+(manual?'?force=true':''),{signal:AbortSignal.timeout(6000)});
      if(!response.ok)throw new Error('unavailable');const metadata=await response.json();
      if(!metadata.release&&metadata.preparation!=='ready')throw new Error('unavailable');
      const result=metadata.preparation==='ready'&&metadata.ready_version?{available:true,version:metadata.ready_version}:releaseStatus(metadata.release,metadata.current_version,metadata.current_build);
      if(metadata.preparation==='source'){
        status.textContent=`v${metadata.current_version} · 이 컴퓨터의 최신 소스로 실행 중`;apply.hidden=true;return;
      }
      if(metadata.preparation==='ready'){
        ready=result;apply.hidden=false;status.textContent=`새 버전 v${result.version} · 자동 적용 준비 완료`;await applyReady();
      }else if(metadata.preparation==='downloading'){
        status.textContent=`새 버전 v${result.version} · 백그라운드에서 업데이트 준비 중…`;schedule(2000);
      }else if(metadata.preparation==='skipped')throw new Error('unavailable');
      else{status.textContent=`v${metadata.current_version} · 최신 버전입니다`;apply.hidden=true;}
    }catch{status.textContent='업데이트 확인을 건너뛰었어요. 기존 앱은 그대로 사용할 수 있습니다.';}
    finally{checking=false;button.disabled=false;}
  }
  apply.onclick=applyReady;button.onclick=()=>check(true);check();
}
