/* Python 엔진과 SQLite는 이 worker 안에서만 실행된다. 금융 입력은 네트워크로 전송하지 않는다. */
const CDN='https://cdn.jsdelivr.net/pyodide/v0.29.3/full/';
let runtime;
const sync=populate=>new Promise((resolve,reject)=>runtime.FS.syncfs(populate,error=>error?reject(error):resolve()));
async function initialize(){
  postMessage({progress:'첫 실행에 계산 환경을 내려받습니다. 금융 입력은 이 브라우저에서만 처리합니다.'});
  importScripts(CDN+'pyodide.js');
  runtime=await loadPyodide({indexURL:CDN});
  await runtime.loadPackage(['fastapi','httpx','pydantic','pyyaml','sqlite3']);
  const engine=new URL('./engine.zip',self.location.href);engine.search=self.location.search;
  const response=await fetch(engine);
  if(!response.ok)throw new Error('계산 엔진 다운로드에 실패했습니다.');
  runtime.FS.mkdirTree('/homeplan/data');
  runtime.FS.mount(runtime.FS.filesystems.IDBFS,{},'/homeplan/data');
  await sync(true);
  runtime.unpackArchive(await response.arrayBuffer(),'zip',{extractDir:'/homeplan/src'});
  await runtime.runPythonAsync(`
import sys, json, functools, inspect
from pathlib import Path
sys.path.insert(0, '/homeplan/src')
Path('/homeplan/fresh-start.flag').touch()
import fastapi.routing, fastapi.dependencies.utils, starlette.concurrency, starlette.routing
async def _without_threads(func, *args, **kwargs):
    return func(*args, **kwargs)
for _module in (fastapi.routing, fastapi.dependencies.utils, starlette.concurrency, starlette.routing):
    _module.run_in_threadpool = _without_threads
import httpx
from homeplan.server import create_app
_app = create_app(Path('/homeplan/data/homeplan.local.sqlite'), seed_root=Path('/homeplan'))
_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=_app), base_url='http://testserver')
async def _request(payload):
    value = json.loads(payload)
    if value['path'] == '/api/backups' and value['method'] == 'POST':
        body = json.loads(value['body'] or '{}')
        if body.get('directory') and body['directory'] != '/homeplan/data/backups':
            return json.dumps({'status': 422, 'headers': {}, 'body': json.dumps({'detail': '웹 버전의 백업은 브라우저 안에 저장됩니다. 외부 보관은 입력값 내보내기를 사용하세요.'})})
    response = await _client.request(value['method'], value['path'], content=value['body'], headers={'Content-Type':'application/json'})
    return json.dumps({'status': response.status_code, 'headers': dict(response.headers), 'body': response.text})
`);
  await sync(false);
}
let chain=Promise.resolve();
self.onmessage=({data})=>{
  chain=chain.then(async()=>{
    try{
      if(data.init){await initialize();postMessage({id:data.id,result:true});return;}
      await sync(true);
      runtime.globals.set('_payload',JSON.stringify(data));
      const result=JSON.parse(await runtime.runPythonAsync('await _request(_payload)'));
      await sync(false);
      postMessage({id:data.id,result});
    }catch(error){postMessage({id:data.id,error:String(error)});}
  });
};
