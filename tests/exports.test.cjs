const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ROOT=path.resolve(__dirname,'..');
const context=vm.createContext({Intl,console,setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync(path.join(ROOT,'exports.js'),'utf8'),context);
const api=context.PerfilExports;
const data=JSON.parse(fs.readFileSync(path.join(ROOT,'data/exports.json')));
const dashboard=JSON.parse(fs.readFileSync(path.join(ROOT,'data/dashboard.json')));
const audit=JSON.parse(fs.readFileSync(path.join(ROOT,'data/audit.json')));
const current={data:dashboard,audit,scope:'store',selection:dashboard.directory[0].cc,productivity:'IPLH'};
test('one group per pillar and YTD rules preserve null months',()=>{
  const r=api.report(data,current,['Partner','Cliente','Negocio']);
  assert.deepEqual(Array.from(r.groups,g=>g.metrics.length),[4,6,11]);
  const rotation=r.groups[0].metrics[0];
  assert.equal(rotation.actual,[...rotation.series].reverse().find(p=>typeof p[0]==='number')[0]);
  const sales=r.groups[2].metrics.find(m=>m.id==='sales');
  assert.equal(sales.actual,sales.series.reduce((t,p)=>t+(p[0]??0),0));
  assert.equal(r.groups[2].metrics.find(m=>m.id==='ticket').budget,null);
});
test('month selection and productivity follow the visible choices',()=>{
  const r=api.report(data,{...current,productivity:'TPLH'},['Partner'],'9');
  assert.equal(r.groups[0].metrics.find(m=>m.id==='tplh').status,'Sin dato');
  assert.equal(r.groups[0].metrics.some(m=>m.id==='productividad'),false);
  assert.equal(r.groups[0].metrics[0].actual,null);
});
test('different construction, invalid period and missing scope are blocked',()=>{
  assert.throws(()=>api.report({...data,generatedAt:'old'},current,['Partner']));
  assert.throws(()=>api.report(data,current,['Partner'],'20'));
  assert.throws(()=>api.report(data,{...current,selection:'99999'},['Partner']));
});
test('negative gap is favorable for Labor but not for sales; missing is neutral',()=>{
  const r=api.report(data,current,['Partner','Negocio']);
  for(const g of r.groups.flatMap(g=>g.metrics)){
    if(g.delta===null)assert.ok(['Sin dato','Sin comparación'].includes(g.status));
    else assert.equal(g.status,(g.direction==='lower'?g.delta<=0:g.delta>=0)?'Favorable':'Atención');
  }
});
test('Excel is a valid ZIP with native charts, formulas, caches and literal text',async()=>{
  const Zip=require('../assets/vendor/jszip-3.10.1.min.js');
  const r=api.report(data,current,['Partner','Cliente','Negocio']);
  r.label='=HYPERLINK("https://example.test") <literal>';
  const bytes=await api.excel(r,Zip),zip=await Zip.loadAsync(bytes);
  const sheet=await zip.file('xl/worksheets/sheet1.xml').async('string');
  assert.match(sheet,/inlineStr/);assert.match(sheet,/HYPERLINK\(&quot;/);assert.match(sheet,/<f>IF\(COUNT/);
  assert.equal(Object.keys(zip.files).filter(s=>/xl\/charts\/chart\d+\.xml$/.test(s)).length,6);
  assert.match(await zip.file('xl/charts/chart1.xml').async('string'),/dispBlanksAs val="gap"/);
});
test('a zero reference remains a reference in the report and native chart',async()=>{
  const changed=JSON.parse(JSON.stringify(data));
  changed.reports.store[current.selection].series.rotacion.forEach(p=>{p[1]=0;p[4]=1;});
  const r=api.report(changed,current,['Partner']);assert.equal(r.groups[0].metrics[0].reference,0);assert.equal(r.groups[0].metrics[0].hasReference,true);
  const Zip=require('../assets/vendor/jszip-3.10.1.min.js'),zip=await Zip.loadAsync(await api.excel(r,Zip));
  const chart=await zip.file('xl/charts/chart1.xml').async('string');assert.equal((chart.match(/<c:ser>/g)||[]).length,2);
});
test('Export button snapshots the current scope and downloads Excel without external calls',async()=>{
  const nodes=new Map(),files=[],urls=[],listeners=new Map();
  function element(id){if(!nodes.has(id))nodes.set(id,{id,value:'',disabled:false,dataset:{},textContent:'',children:[],addEventListener:(name,handler)=>listeners.set(id+':'+name,handler),append(item){this.children.push(item);if(this.id==='exportPeriod'&&this.children.length===1)this.value=String(item.value);},replaceChildren(){this.children=[];},showModal(){this.open=true;},close(){this.open=false;},remove(){},click(){files.push(this.download);}});return nodes.get(id);}
  const Zip=require('../assets/vendor/jszip-3.10.1.min.js');
  const env=vm.createContext({Intl,console,Blob,AbortController,JSZip:Zip,setTimeout:(f,d)=>d===60000?0:setTimeout(f,d),clearTimeout,URL:{createObjectURL:blob=>{urls.push(blob);return 'blob:test';},revokeObjectURL(){}},fetch:async url=>{assert.equal(url,'data/exports.json');return {ok:true,json:async()=>data};},document:{getElementById:element,createElement:tag=>element(tag+Math.random()),body:{append(){}},head:{append(){throw new Error('External script was requested');}}}});
  vm.runInContext(fs.readFileSync(path.join(ROOT,'exports.js'),'utf8'),env);
  let selection={...current,pillar:'Cliente'};env.PerfilExports.connect(()=>selection);
  assert.equal(element('openExport').disabled,false);listeners.get('openExport:click')();assert.equal(element('exportPillar').value,'Cliente');assert.equal(element('exportDialog').open,true);
  selection={...selection,scope:'dm',selection:Object.keys(data.reports.dm)[0]};
  await listeners.get('downloadExcel:click')();assert.equal(files.length,1);assert.match(files[0],/38101_Angel_Cliente/);assert.equal(element('downloadExcel').disabled,false);
  const zip=await Zip.loadAsync(await urls[0].arrayBuffer()),sheet=await zip.file('xl/worksheets/sheet1.xml').async('string');assert.match(sheet,/38101 · Angel/);
});
