const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), vm=require('node:vm'), crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const source=['identity.js','settings-page.js','driver.js'].map(f=>fs.readFileSync(path.join(root,'atom65.reaplugin',f),'utf8')).join('\n');
const flush=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const profile=(title='Espresso',extra={})=>({title,notes:'',author:'',version:'2',beverage_type:'espresso',steps:[{name:'Preinfusion',temperature:93,flow:3}],target_weight:36,target_volume:0,target_volume_count_start:0,tank_temperature:0,...extra});
const workflow=(p=profile(),weight=18)=>({id:'workflow-'+Math.random(),profile:p,context:{targetDoseWeight:weight,targetYield:36}});
const xor=b=>b.reduce((s,n)=>s^n,0);
function status(s={}){const d={result:0,flags:1,sequence:0,dose:18,slot:1,mode:0,minimum:5,maximum:1000,...s};const b=[166,1,d.result,d.flags,d.sequence&255,d.sequence>>8,Math.round(d.dose*10)&255,Math.round(d.dose*10)>>8,d.slot,d.mode,Math.round(d.minimum*10)&255,Math.round(d.minimum*10)>>8,Math.round(d.maximum*10)&255,Math.round(d.maximum*10)>>8];return Buffer.from([...b,xor(b)]).toString('base64');}
function fixture(options={}){
  let now=0,tid=0,factory,plugin,store=options.store??null;
  const timers=new Map(),writes=[],publications=[],storage=[],bindings=[],logs=[];
  const context=vm.createContext({btoa:s=>Buffer.from(s,'binary').toString('base64'),setTimeout:(fn,delay)=>{timers.set(++tid,{fn,at:now+delay});return tid;},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,context);
  const host={log:m=>logs.push(m),storage(command){storage.push(command);queueMicrotask(()=>{if(command.type==='read'){if(!options.delayRead)plugin.onEvent({name:'storageRead',payload:{key:command.key,value:store}});}else{store=JSON.parse(JSON.stringify(command.data));if(!options.noStorageAck)plugin.onEvent({name:'storageWrite',payload:command.data});}});},devices:{bindDriver:async(id,f)=>{bindings.push(id);factory=f;}}};
  plugin=context.createPlugin(host);
  async function tick(ms){const end=now+ms;await flush();for(let tries=0;tries<1000;tries++){const entries=[...timers].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at);if(!entries.length)break;const [key,t]=entries[0];now=t.at;timers.delete(key);t.fn();await flush();}now=end;await flush();}
  async function connect(id='28:84:85:8d:23:d4',overrides={}){
    let subscriber,terminal;const physical={dose:18,slot:1,mode:0,flags:1,...overrides};const h=factory.create({id:'plugin:atom65.reaplugin:atom65:'+id,name:'GrindByWeight'});let disconnected=0;
    const deviceId='plugin:atom65.reaplugin:atom65:'+id;
    const session={publish:async s=>{publications.push({deviceId,...s});},reportDisconnected:async()=>{disconnected++;},gatt:{onDisconnect:fn=>{terminal=fn;},discoverServices:async()=>['5e5d6500-3f45-4b8c-9a65-28b4858d23d4'],subscribe:async(s,c,fn)=>{subscriber=fn;return {unsubscribe:async()=>{}};},read:async()=>status(physical),async writeWithResponse(service,char,encoded){const b=[...Buffer.from(encoded,'base64')];writes.push({deviceId,service,char,bytes:b,dose:(b[5]|b[6]<<8)/10});if(options.writeBlock)await options.writeBlock();if(options.writeFails)throw new Error('write failure');if(options.noAck)return;const sequence=b[3]|b[4]<<8,result=physical.mode!==0?4:physical.flags!==1?2:1;if(result===1){physical.dose=(b[5]|b[6]<<8)/10;physical.slot=2;}await subscriber(status({...physical,result,sequence}));}}};
    if(options.overrideGatt)Object.assign(session.gatt,options.overrideGatt);
    await h.connect(session);await flush();
    return {h,deviceId,physical,notify:async s=>subscriber(status({...physical,...s})),raw:async s=>subscriber(s),drop:()=>terminal(),get disconnected(){return disconnected;}};
  }
  async function api(endpoint,body,deviceId){const r=await plugin.handleHttpRequest({endpoint,method:endpoint==='status'?'GET':'POST',body,query:deviceId?{deviceId}:{}});return {status:r.status,body:JSON.parse(r.body)};}
  function select(w){plugin.onEvent({name:'workflowUpdated',payload:w});}
  function key(p){return context.atomProfile({profile:p}).key;}
  async function rule(device,w,mode='workflow',weight=18,enabled=true){select(w);await flush();return api('configure',{profileKey:key(w.profile),mode,weight,enabled},device.deviceId);}
  return {context,plugin,host,writes,publications,storage,bindings,logs,timers,tick,connect,api,select,key,rule,get store(){return store;},async load(values={}){await plugin.onLoad(values);await flush();}};
}
test('identity matches SHA-256 including Unicode and long content',()=>{const f=fixture();for(const value of ['', 'abc', 'שלום ☕ 😀', 'x'.repeat(10000)])assert.equal(f.context.atomSha256(value),crypto.createHash('sha256').update(value).digest('hex'));});
test('same title different execution gets a different rule; key order and notes do not',()=>{const f=fixture(),a=profile();assert.equal(f.key(a),f.key({...a,notes:'new',author:'other',version:'3'}));assert.equal(f.key(a),f.key(Object.fromEntries(Object.entries(a).reverse())));assert.notEqual(f.key(a),f.key(profile('Espresso',{steps:[{temperature:95}]})));assert.notEqual(f.key(a),f.key(profile('Renamed')));});
test('unconfigured profiles and first connection send nothing',async()=>{const f=fixture();await f.load();f.select(workflow());await f.connect();await f.tick(300);assert.equal(f.writes.length,0);assert.deepEqual(f.bindings,['atom65']);f.plugin.onUnload();});
test('opted profile follows workflow dose and confirms CUSTOM; unrelated edits deduplicate',async()=>{const f=fixture();await f.load();const d=await f.connect(),w=workflow();assert.equal((await f.rule(d,w)).status,200);await f.tick(150);assert.equal(f.writes.length,1);assert.equal(f.writes[0].dose,18);assert.equal(xor(f.writes[0].bytes),0);assert.match((await f.api('status',null,d.deviceId)).body.message,/Synced/);f.select({...w,id:'new',context:{...w.context,targetYield:42}});await f.tick(150);assert.equal(f.writes.length,1);f.select({...w,context:{targetDoseWeight:19.2}});await f.tick(150);assert.equal(f.writes[1].dose,19.2);f.plugin.onUnload();});
test('fixed mode ignores dose edits, missing workflow dose and yield',async()=>{const f=fixture();await f.load();const d=await f.connect(),w=workflow(profile(),null);await f.rule(d,w,'fixed',20.5);await f.tick(150);assert.equal(f.writes[0].dose,20.5);f.select({...w,context:{targetDoseWeight:17,targetYield:55}});await f.tick(150);assert.equal(f.writes.length,1);f.plugin.onUnload();});
test('choosing an excluded profile cancels an unsent weight change',async()=>{const f=fixture();await f.load();const d=await f.connect();await f.rule(d,workflow());f.select(workflow(profile('Filter'),30));await f.tick(500);assert.equal(f.writes.length,0);f.plugin.onUnload();});
test('changing a configured profile to leave cancels the queued write',async()=>{const f=fixture();await f.load();const d=await f.connect(),w=workflow();await f.rule(d,w);await f.rule(d,w,'leave');await f.tick(150);assert.equal(f.writes.length,0);assert.equal((await f.api('status',null,d.deviceId)).body.rules.length,0);f.plugin.onUnload();});
test('rapid A B C changes coalesce to the latest enabled dose',async()=>{const f=fixture();await f.load();const d=await f.connect(),a=workflow(profile('A'),17),b=workflow(profile('B'),19),c=workflow(profile('C'),21);for(const w of [a,b,c])await f.rule(d,w);f.select(a);f.select(b);f.select(c);await f.tick(150);assert.equal(f.writes.length,1);assert.equal(f.writes[0].dose,21);f.plugin.onUnload();});
test('missing, string, nonfinite, zero, huge, and sub-decigram doses never use yield as fallback',async()=>{for(const weight of [undefined,null,'18',NaN,Infinity,0,-1,4.9,41,18.05]){const f=fixture();await f.load();const d=await f.connect(),w=workflow();await f.rule(d,w);f.select({...w,context:{targetDoseWeight:weight,targetYield:36}});await f.tick(150);assert.equal(f.writes.length,0,String(weight));assert.match((await f.api('status',null,d.deviceId)).body.message,/Dose must/);f.plugin.onUnload();}});
test('fixed doses validate before persisting',async()=>{const f=fixture();await f.load();const d=await f.connect(),w=workflow();for(const weight of [null,'18',4,40.1,18.01])assert.equal((await f.rule(d,w,'fixed',weight)).status,400);assert.equal(f.storage.filter(x=>x.type==='write').length,0);f.plugin.onUnload();});
test('master switch and per-device pause suppress syncing',async()=>{for(const master of [true,false]){const f=fixture();await f.load({SyncEnabled:master});const d=await f.connect();await f.rule(d,workflow(),'workflow',18,!master);await f.tick(150);assert.equal(f.writes.length,0);f.plugin.onUnload();}});
test('choices survive reload and current opted profile syncs on reconnect',async()=>{const f=fixture();await f.load();const d=await f.connect(),w=workflow();await f.rule(d,w,'fixed',22);f.plugin.onUnload();const next=fixture({store:f.store});await next.load();next.select(w);await next.connect();await next.tick(150);assert.equal(next.writes[0].dose,22);next.plugin.onUnload();});
test('reconnect with an excluded profile leaves grinder unchanged',async()=>{const f=fixture();await f.load();const d=await f.connect();await f.rule(d,workflow());f.plugin.onUnload();const next=fixture({store:f.store});await next.load();next.select(workflow(profile('Other')));await next.connect();await next.tick(150);assert.equal(next.writes.length,0);next.plugin.onUnload();});
test('workflow events before storage has loaded cannot overwrite or send',async()=>{const f=fixture({delayRead:true});await f.load();const d=await f.connect();f.select(workflow());assert.equal((await f.rule(d,workflow())).status,503);await f.tick(150);assert.equal(f.writes.length,0);f.plugin.onUnload();});
test('invalid persisted choices fail closed',async()=>{const f=fixture({store:{schema:9,devices:{}}});await f.load();const d=await f.connect();f.select(workflow());await f.tick(150);assert.equal(f.writes.length,0);assert.ok((await f.api('status',null,d.deviceId)).body.storageError);f.plugin.onUnload();});
test('settings are acknowledged before syncing and storage timeout stays paused',async()=>{const f=fixture({noStorageAck:true});await f.load();const d=await f.connect();const pending=f.rule(d,workflow());await flush();await f.tick(2600);assert.equal((await pending).status,502);assert.equal(f.writes.length,0);assert.ok((await f.api('status',null,d.deviceId)).body.storageError);f.plugin.onUnload();});
test('profile change during settings save is detected',async()=>{const f=fixture();await f.load();const d=await f.connect(),a=workflow();f.select(workflow(profile('Other')));assert.equal((await f.api('configure',{profileKey:f.key(a.profile),mode:'workflow',enabled:true},d.deviceId)).status,409);assert.equal(f.writes.length,0);f.plugin.onUnload();});
test('busy, OTA, editing and time mode do not queue a dose for later',async()=>{for(const state of [{flags:2},{flags:4},{flags:8},{mode:1}]){const f=fixture();await f.load();const d=await f.connect('device',state);await f.rule(d,workflow());await f.tick(150);assert.equal(f.writes.length,0);await d.notify({flags:1,mode:0});await f.tick(150);assert.equal(f.writes.length,0);f.plugin.onUnload();}});
test('firmware busy rejection is not shown as applied or automatically retried',async()=>{const f=fixture();await f.load();const d=await f.connect();await f.rule(d,workflow());d.physical.flags=2;await f.tick(150);assert.equal(f.writes.length,1);assert.match((await f.api('status',null,d.deviceId)).body.message,/busy/);await f.tick(1000);assert.equal(f.writes.length,1);f.plugin.onUnload();});
test('timeout is uncertain and never automatically retried',async()=>{const f=fixture({noAck:true});await f.load();const d=await f.connect();await f.rule(d,workflow());await f.tick(2700);assert.equal(f.writes.length,1);assert.match((await f.api('status',null,d.deviceId)).body.message,/timed out/);f.plugin.onUnload();});
test('Sync now explicitly resends after a busy rejection',async()=>{const f=fixture();await f.load();const d=await f.connect();await f.rule(d,workflow());d.physical.flags=2;await f.tick(150);d.physical.flags=1;await d.notify({});assert.equal((await f.api('sync',{},d.deviceId)).status,202);await f.tick(150);assert.equal(f.writes.length,2);assert.match((await f.api('status',null,d.deviceId)).body.message,/Synced/);f.plugin.onUnload();});
test('two grinders have independent choices and unloading cancels all four bindings',async()=>{const f=fixture();await f.load();const ds=await Promise.all(['a','b','c','d'].map(id=>f.connect(id)));await f.rule(ds[0],workflow(),'fixed',17);await f.rule(ds[1],workflow(),'fixed',21);await f.tick(150);assert.deepEqual(f.writes.map(x=>x.dose),[17,21]);await f.rule(ds[2],workflow());f.plugin.onUnload();await f.tick(150);assert.equal(f.writes.length,2);});
test('disconnect cancels queued work; late callbacks cannot publish or write',async()=>{const f=fixture();await f.load();const d=await f.connect();await f.rule(d,workflow());const count=f.publications.length;d.drop();await f.tick(150);await d.notify({dose:30});assert.equal(f.writes.length,0);assert.equal(f.publications.length,count);f.plugin.onUnload();});
test('protocol checksum and stream silence disconnect only their own session',async()=>{const f=fixture();await f.load();const d=await f.connect('a'),other=await f.connect('b');const bad=Buffer.from(status(),'base64');bad[6]^=1;await assert.rejects(d.raw(bad.toString('base64')));assert.equal(d.disconnected,1);assert.equal((await f.api('status',null,other.deviceId)).body.connected,true);await f.tick(4100);assert.equal(other.disconnected,1);f.plugin.onUnload();});
test('renamed or edited recipe defaults to leave even with the same workflow id',async()=>{const f=fixture();await f.load();const d=await f.connect(),w=workflow();await f.rule(d,w);f.select({...w,profile:profile('Espresso',{steps:[{temperature:94}]})});await f.tick(150);assert.equal(f.writes.length,0);f.plugin.onUnload();});
test('invalid global settings fail during plugin load',async()=>{for(const values of [{SyncEnabled:'yes'},{MaximumDose:0},{MaximumDose:'40'},{MaximumDose:Infinity}])await assert.rejects(fixture().load(values));});
test('native manifest does not misrepresent dose as burr position or motor capability',()=>{const m=JSON.parse(fs.readFileSync(path.join(root,'atom65.reaplugin/manifest.json')));assert.deepEqual(m.drivers[0].capabilities,[]);assert.ok(m.permissions.includes('events.workflow'));assert.ok(m.drivers[0].ble.match.serviceUuids[0].startsWith('5e5d6500'));});
test('settings UI parses and renders user-controlled labels through textContent',()=>{const f=fixture();const html=f.context.atomSettingsPage();new vm.Script(html.match(/<script>([\s\S]*)<\/script>/)[1]);assert.ok(html.includes("li.textContent=r.title"));assert.ok(!html.includes('innerHTML'));assert.ok(html.includes('Leave grinder unchanged'));});

test('skin can read and save another profile without selecting or syncing it',async()=>{
  const f=fixture();await f.load();const d=await f.connect(),active=workflow(profile('Active')),other=profile('Other');f.select(active);
  const read=await f.api('profile-settings',{profile:other},d.deviceId);
  assert.equal(read.status,200);assert.equal(read.body.profile.key,f.key(other));assert.equal(read.body.rule.mode,'leave');
  assert.equal(f.storage.filter(x=>x.type==='write').length,0);
  const saved=await f.api('profile-settings',{profile:other,choice:{profileKey:read.body.profile.key,mode:'fixed',weight:20.5}},d.deviceId);
  assert.equal(saved.status,200);assert.equal(saved.body.rule.weight,20.5);assert.equal((await f.api('status',null,d.deviceId)).body.profile.title,'Active');
  await f.tick(150);assert.equal(f.writes.length,0);
  f.select(workflow(other,17));await f.tick(150);assert.equal(f.writes.length,1);assert.equal(f.writes[0].dose,20.5);
  f.select(active);await f.tick(150);assert.equal(f.writes.length,1);
  f.plugin.onUnload();
});
test('library rules remain per device, survive reload, and can be disabled',async()=>{
  const f=fixture();await f.load();const d=await f.connect('a'),other=await f.connect('b'),p=profile();
  const choice={profileKey:f.key(p),mode:'fixed',weight:21};
  await f.api('profile-settings',{profile:p,choice},d.deviceId);
  assert.equal((await f.api('profile-settings',{profile:p},other.deviceId)).body.rule.mode,'leave');
  const next=fixture({store:f.store});f.plugin.onUnload();await next.load();const reconnected=await next.connect('a');
  assert.equal((await next.api('profile-settings',{profile:p},reconnected.deviceId)).body.rule.weight,21);
  next.select(workflow(p));
  await next.api('profile-settings',{profile:p,choice:{profileKey:next.key(p),mode:'leave'}},reconnected.deviceId);
  await next.tick(150);assert.equal(next.writes.length,0);next.plugin.onUnload();
});
test('library edits cannot resume a paused grinder or conflate same-title recipes',async()=>{
  const f=fixture();await f.load();const d=await f.connect(),a=profile(),b=profile('Espresso',{steps:[{temperature:94}]});
  await f.rule(d,workflow(a),'workflow',18,false);
  const r=await f.api('profile-settings',{profile:b,choice:{profileKey:f.key(b),mode:'fixed',weight:19}},d.deviceId);
  assert.equal(r.status,200);assert.equal(r.body.deviceEnabled,false);
  assert.equal((await f.api('profile-settings',{profile:a},d.deviceId)).body.rule.mode,'workflow');
  f.select(workflow(b));await f.tick(150);assert.equal(f.writes.length,0);f.plugin.onUnload();
});
test('library API rejects invalid profiles, mismatched keys and unexpected fields',async()=>{
  const f=fixture();await f.load();const d=await f.connect(),p=profile();
  for(const body of [{profile:{title:'Empty'}},{profile:p,unexpected:true},{profile:p,choice:{profileKey:f.key(p),mode:'fixed',weight:18,enabled:true}},{profile:p,choice:{profileKey:f.key(p),mode:'fixed',weight:18.05}}])assert.equal((await f.api('profile-settings',body,d.deviceId)).status,400);
  assert.equal((await f.api('profile-settings',{profile:p,choice:{profileKey:f.key(profile('Different')),mode:'workflow'}},d.deviceId)).status,409);
  assert.equal(f.storage.filter(x=>x.type==='write').length,0);assert.equal(f.writes.length,0);f.plugin.onUnload();
});
