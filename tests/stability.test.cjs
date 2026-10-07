const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const ROOT = path.resolve(__dirname, '..');
const SCOPE = 'https://example.test/Perfil_Tienda_DM/';
const PREFIX = `perfil-tienda:${encodeURIComponent(SCOPE)}:`;
const fastTimeout = (fn, delay) => setTimeout(fn, delay >= 8000 ? 5 : delay);
const json = (value, headers={}) => new Response(JSON.stringify(value), {headers:{'Content-Type':'application/json', ...headers}});
function pair() {
  return {
    dashboard:{schemaVersion:2, generatedAt:'2026-10-07T00:00:00Z', directory:[{cc:'38101',store:'Tienda de prueba',opened:null}], months:[{id:1,label:'Enero',short:'Ene'}], graphs:[],metricHeaders:[],profile:{},business:{},mix:{},partners:{}},
    audit:{schemaVersion:2,generatedAt:'2026-10-07T00:00:00Z',issueCount:0,warningCount:0,warnings:[]}
  };
}

function worker() {
  const listeners = {}, storage = new Map();
  const keyFor = request => typeof request === 'string' ? request : request.url;
  const environment = {network:null, calls:0, cacheFails:false,claimed:false,skipped:false};
  const caches = {
    async open(name) {
      if (!storage.has(name)) storage.set(name,new Map());
      const entries = storage.get(name);
      return {
        async match(request) { return entries.get(keyFor(request))?.clone(); },
        async put(request,response) { if (environment.cacheFails) throw new Error('QuotaExceeded'); entries.set(keyFor(request),response.clone()); },
        async addAll(requests) { for (const request of requests) entries.set(keyFor(request),new Response('asset')); }
      };
    },
    async keys() { return [...storage.keys()]; },
    async delete(name) { return storage.delete(name); }
  };
  const context = vm.createContext({URL,Request,Response,AbortController,setTimeout:fastTimeout,clearTimeout,caches,
    fetch:async (...args) => { environment.calls++; return environment.network(...args); },
    self:{registration:{scope:SCOPE},location:{origin:'https://example.test'},
      addEventListener:(name,handler)=>{listeners[name]=handler;},
      skipWaiting:async()=>{environment.skipped=true;},clients:{claim:async()=>{environment.claimed=true;}}}
  });
  vm.runInContext(fs.readFileSync(path.join(ROOT,'sw.js'),'utf8'),context);
  environment.setPair = value => { environment.network = async url => json(String(url).endsWith('dashboard.json') ? value.dashboard : value.audit); };
  environment.dispatch = async (url,options) => {
    let response;
    listeners.fetch({request:new Request(new URL(url,SCOPE),options),respondWith:value=>{response=value;}});
    return response;
  };
  environment.lifecycle = async name => { let pending; listeners[name]({waitUntil:value=>{pending=value;}}); await pending; };
  return Object.assign(environment,{storage,caches});
}

test('concurrent data requests share one verified dashboard/audit snapshot',async()=>{
  const w=worker(), expected=pair(); w.setPair(expected);
  const responses=await Promise.all([w.dispatch('data/dashboard.json'),w.dispatch('data/audit.json')]);
  assert.equal(w.calls,2);
  assert.deepEqual(await responses[0].json(),expected.dashboard);
  assert.deepEqual(await responses[1].json(),expected.audit);
  assert.equal(w.storage.get(`${PREFIX}data-v1`).size,1);
});

test('HTTP errors, invalid JSON, failed audit and mixed builds cannot overwrite a valid snapshot',async()=>{
  const w=worker(), expected=pair(); w.setPair(expected); await w.dispatch('data/dashboard.json');
  const bad=pair(); bad.audit.generatedAt='different';
  const failed=pair(); failed.audit.issueCount=1;
  const incomplete=pair(); delete incomplete.dashboard.graphs;
  const faults=[async()=>new Response('Server error',{status:500}),async()=>new Response('not JSON'),
    async url=>json(String(url).endsWith('dashboard.json')?bad.dashboard:bad.audit),
    async url=>json(String(url).endsWith('dashboard.json')?failed.dashboard:failed.audit),
    async url=>json(String(url).endsWith('dashboard.json')?incomplete.dashboard:incomplete.audit),async()=>json(null)];
  for (const network of faults) {
    w.network=network;
    const response=await w.dispatch('data/dashboard.json');
    assert.equal(response.status,200); assert.equal(response.headers.get('X-Perfil-Offline'),'1');
    assert.deepEqual(await response.json(),expected.dashboard);
  }
});

test('missing verified cache produces an explicit 503 response',async()=>{
  const w=worker(); w.network=async()=>{throw new Error('Offline');};
  assert.equal((await w.dispatch('data/dashboard.json')).status,503);
});

test('installation saves verified data for offline use after the first visit',async()=>{
  const w=worker(); w.setPair(pair()); await w.lifecycle('install');
  w.network=async()=>{throw new Error('Offline');};
  const response=await w.dispatch('data/dashboard.json');
  assert.equal(response.status,200); assert.equal(response.headers.get('X-Perfil-Offline'),'1');
});

test('corrupt cached JSON cannot be presented as verified data',async()=>{
  const w=worker(); const cache=await w.caches.open(`${PREFIX}data-v1`);
  await cache.put(`${SCOPE}data/.verified-snapshot`,new Response('corrupt'));
  w.network=async()=>{throw new Error('Offline');};
  assert.equal((await w.dispatch('data/dashboard.json')).status,503);
});

test('a stalled data request is aborted and falls back to the verified snapshot',async()=>{
  const w=worker(); w.setPair(pair()); await w.dispatch('data/dashboard.json');
  w.network=(_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true}));
  assert.equal((await w.dispatch('data/audit.json')).headers.get('X-Perfil-Offline'),'1');
});

test('cache quota failures do not reject valid network data',async()=>{
  const w=worker(); w.setPair(pair()); w.cacheFails=true;
  const response=await w.dispatch('data/dashboard.json');
  assert.equal(response.status,200); assert.equal(response.headers.get('X-Perfil-Offline'),'0');
});

test('activation preserves other applications caches and this applications verified data',async()=>{
  const w=worker();
  for (const name of ['another-app',`${PREFIX}core-v11`,`${PREFIX}data-v1`,'perfil-tienda:another-scope:core-v11']) await w.caches.open(name);
  await w.lifecycle('install'); await w.lifecycle('activate');
  assert.equal(w.storage.has(`${PREFIX}core-v11`),false);
  for (const name of ['another-app',`${PREFIX}data-v1`,'perfil-tienda:another-scope:core-v11']) assert.equal(w.storage.has(name),true);
  assert.equal(w.claimed,true); assert.equal(w.skipped,true);
});

test('POST, external origins and resources outside scope are not intercepted',async()=>{
  const w=worker(); w.setPair(pair());
  for (const [url,options] of [['data/dashboard.json',{method:'POST'}],['https://other.test/data/dashboard.json'],['https://example.test/another/app.js']]) assert.equal(await w.dispatch(url,options),undefined);
  assert.equal(w.calls,0);
});

test('assets refresh from the network and retain last good contents after server failure',async()=>{
  const w=worker(); w.network=async()=>new Response('new script');
  assert.equal(await (await w.dispatch('app.js')).text(),'new script');
  w.network=async()=>new Response('Server error',{status:500});
  assert.equal(await (await w.dispatch('app.js')).text(),'new script');
});

function app(network) {
  const nodes=new Map(), errors=[], registrations=[];
  const element=id=>{
    if (!nodes.has(id)) {
      const classes=new Set(), listeners={};
      nodes.set(id,{innerHTML:'',textContent:'',value:'',dataset:{},listeners,
        classList:{add:name=>classes.add(name),remove:name=>classes.delete(name),toggle:(name,value)=>value?classes.add(name):classes.delete(name)},
        addEventListener:(name,handler)=>{(listeners[name]??=[]).push(handler);},setAttribute:()=>{},querySelectorAll:()=>[],querySelector:()=>element(`${id}:span`)});
    }
    return nodes.get(id);
  };
  const environment={network, calls:0};
  const context=vm.createContext({URL,Request,Response,AbortController,setTimeout:fastTimeout,clearTimeout,
    fetch:(...args)=>{environment.calls++;return environment.network(...args);},
    console:{error:error=>errors.push(error)},location:{protocol:'https:'},
    navigator:{serviceWorker:{register:async url=>{registrations.push(url);}}},
    document:{getElementById:element,querySelectorAll:()=>[],querySelector:()=>null}
  });
  vm.runInContext(fs.readFileSync(path.join(ROOT,'app.js'),'utf8'),context);
  environment.element=element; environment.errors=errors; environment.registrations=registrations;
  return environment;
}
async function waitFor(predicate) {
  for (let i=0;i<100;i++) { if (predicate()) return; await new Promise(resolve=>setTimeout(resolve,1)); }
  assert.fail('Application did not reach expected state');
}
const pairNetwork=(value,offline=false)=>async url=>json(url.endsWith('dashboard.json')?value.dashboard:value.audit,{'X-Perfil-Offline':offline?'1':'0'});

test('application renders a valid contract and marks cached fallback visibly',async()=>{
  const a=app(pairNetwork(pair(),true));
  await waitFor(()=>a.element('sourceStatus:span').textContent.includes('respaldo'));
  assert.match(a.element('profileHero').innerHTML,/38101/); assert.equal(a.errors.length,0);
});

test('application rejects mixed builds and registers recovery worker even after a failed load',async()=>{
  const value=pair(); value.audit.generatedAt='different'; const a=app(pairNetwork(value));
  await waitFor(()=>a.errors.length);
  assert.match(a.element('profileHero').innerHTML,/Reintentar carga/);
  assert.match(a.element('profileHero').innerHTML,/no forman una versión válida/);
  assert.deepEqual(a.registrations,['sw.js']);
});

test('retry recovers from an HTTP failure and repeated clicks do not duplicate loads',async()=>{
  const a=app(async()=>new Response('unavailable',{status:503})); await waitFor(()=>a.errors.length);
  a.network=pairNetwork(pair());
  const retry=a.element('retryLoad').listeners.click[0]; retry(); retry();
  await waitFor(()=>a.element('sourceStatus:span').textContent.includes('meses validados'));
  assert.equal(a.calls,4); assert.match(a.element('profileHero').innerHTML,/38101/);
});

test('application aborts stalled requests and provides a retry action',async()=>{
  const a=app((_url,{signal})=>new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>{const error=new Error('aborted');error.name='AbortError';reject(error);},{once:true})));
  await waitFor(()=>a.errors.length);
  assert.match(a.element('profileHero').innerHTML,/tardó demasiado/);
  assert.match(a.element('profileHero').innerHTML,/Reintentar carga/);
});
