const API='https://api.github.com/repos/hyb1992/homeplan/releases/latest';
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
export function installUpdateNotice(){
  const panel=document.createElement('div');panel.className='update-notice';panel.id='update-notice';
  panel.innerHTML='<span id="update-state" role="status">버전 확인 중…</span><button class="button small" id="update-check" type="button">새 버전 확인</button><a class="button small soft" id="update-download" target="_blank" rel="noopener noreferrer" hidden>새 버전 다운로드</a>';
  document.querySelector('main').prepend(panel);
  const status=panel.querySelector('#update-state'),button=panel.querySelector('#update-check'),link=panel.querySelector('#update-download');
  let checking=false;
  async function check(manual=false){
    if(checking)return;checking=true;button.disabled=true;
    try{
      let metadata;
      if(globalThis.HOMEPLAN_BROWSER){
        const build=await(await fetch(new URL('./build.json',import.meta.url),{cache:'no-store',signal:AbortSignal.timeout(6000)})).json();
        const response=await fetch(API,{signal:AbortSignal.timeout(6000),headers:{Accept:'application/vnd.github+json'}});
        if(!response.ok)throw new Error('unavailable');
        metadata={current_version:build.version,current_build:build.build,release:await response.json()};
      }else{
        const response=await fetch('/api/updates'+(manual?'?force=true':''),{signal:AbortSignal.timeout(6000)});
        if(!response.ok)throw new Error('unavailable');metadata=await response.json();
      }
      if(!metadata.release)throw new Error('unavailable');
      const result=releaseStatus(metadata.release,metadata.current_version,metadata.current_build);
      status.textContent=result.available?`새 버전 v${result.version} · 직접 다운로드할 수 있어요`:`v${metadata.current_version} · 최신 버전입니다`;
      link.hidden=!result.available;
      if(result.available){link.href=result.url;link.title='배포 ZIP만 다운로드합니다. 현재 앱과 저장 데이터는 변경하지 않습니다.';}
    }catch{
      status.textContent='업데이트 확인을 건너뛰었어요. 기존 앱은 그대로 사용할 수 있습니다.';
    }finally{checking=false;button.disabled=false;}
  }
  button.onclick=()=>check(true);
  check();
}
