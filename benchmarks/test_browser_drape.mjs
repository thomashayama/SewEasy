// Exercise the actual Vue controller with a fake GPU, without a browser driver.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {test} from 'node:test';

const source=readFileSync(new URL('../gui/browser_drape.js',import.meta.url),'utf8')
  .replace(/^import .*;$/gm,'').replace('export default {','globalThis.component = {');

function setup({gpu,fetch}={}) {
  const emitted=[],destroyed=[],elapsed=[],renderers=[];
  const device={queue:{onSubmittedWorkDone:async()=>{},submit(){}},createCommandEncoder:()=>({finish(){}}),lost:new Promise(()=>{}),
    addEventListener(){},destroy(){destroyed.push('device');}};
  const context=vm.createContext({navigator:gpu===false?{}:{gpu:{
    requestAdapter:async()=>({requestDevice:async()=>device}),getPreferredCanvasFormat:()=> 'bgra8unorm'}},
    fetch,performance:{now:()=>1000},AbortController,document:{hidden:false},
    requestAnimationFrame:()=>1,cancelAnimationFrame(){},
    Cloth:{create:async(_device,scene)=>({scene,frame:0,motion:{center:[0,.86,0]},supportTargets:[],settings:{holdNeckline:false},
      encode(_encoder,_queries,dt){elapsed.push(dt);this.frame++;},destroy(){destroyed.push(scene.name);}})},
    Renderer:class {constructor(){this.bodyView={};this.controls={};this.camera={target:[0,1,0],pan:[0,0]};renderers.push(this);}render(){this.dirty=false;}setFabricColors(){}destroy(){}}
  });
  vm.runInContext(source,context);
  const component=context.component;
  const instance={...component.data(),scene_url:'/geo/test/scene-0.json',active:true,preparing:false,error:'',
    fabric_color:'#ffffff',body_color:'#ffffff',panel_colors:{},show_body:true,
    $refs:{canvas:{}},$el:{getClientRects:()=>[{}]},$emit:(...event)=>emitted.push(event)};
  for(const [key,fn] of Object.entries(component.methods))instance[key]=fn.bind(instance);
  return {instance,component,emitted,destroyed,elapsed,renderers,context};
}

async function until(predicate) {
  for(let n=0;n<100;n++){if(predicate())return;await new Promise(setImmediate);}
  assert.fail('Controller did not finish');
}

test('unsupported browser shows an error without requesting scene or server simulation',async()=>{
  let requests=0;
  const s=setup({gpu:false,fetch:()=>requests++});s.component.mounted.call(s.instance);
  await until(()=>s.instance.failure);
  assert.match(s.instance.failure,/WebGPU is unavailable/);assert.equal(requests,0);
  s.component.beforeUnmount.call(s.instance);
});

test('a response for an obsolete design is discarded',async()=>{
  let finishFirst;const requests=[];
  const s=setup({fetch:async url=>{requests.push(url);if(requests.length===1)return await new Promise(r=>finishFirst=r);
    return {ok:true,json:async()=>({name:'latest'})};}});
  s.component.mounted.call(s.instance);await until(()=>finishFirst);
  s.instance.scene_url='/geo/test/scene-1.json';s.component.watch.scene_url.call(s.instance);
  finishFirst({ok:true,json:async()=>({name:'obsolete'})});
  await until(()=>s.instance.ready);
  assert.equal(s.instance.loadedScene,'latest');assert.equal(requests.length,2);
  assert.deepEqual(s.emitted.map(event=>event[1].scene),['latest']);
  s.component.beforeUnmount.call(s.instance);
  assert.deepEqual(s.destroyed,['latest','device']);
});

test('unmount during loading never creates a renderer or publishes ready',async()=>{
  let finish;
  const s=setup({fetch:()=>new Promise(r=>finish=r)});
  s.component.mounted.call(s.instance);await until(()=>finish);
  s.component.beforeUnmount.call(s.instance);
  finish({ok:true,json:async()=>({name:'closed'})});
  await new Promise(setImmediate);
  assert.equal(s.instance.ready,false);assert.equal(s.emitted.length,0);
  assert.deepEqual(s.destroyed,['device']);
});

test('simulation uses elapsed time and discards time spent paused or hidden',async()=>{
  const s=setup({fetch:async()=>({ok:true,json:async()=>({name:'clock'})})});
  s.component.mounted.call(s.instance);await until(()=>s.instance.ready);
  await s.instance.tick(1000);await s.instance.tick(1033);
  assert.deepEqual(s.elapsed,[1/60,.033]);assert.equal(s.instance.failure,'');
  s.instance.paused=true;s.component.watch.paused.call(s.instance);await s.instance.tick(2000);
  assert.equal(s.elapsed.length,2);assert.equal(s.renderers[0].controls.viewOnly,true);
  s.instance.paused=false;s.component.watch.paused.call(s.instance);await s.instance.tick(3000);
  assert.equal(s.elapsed.at(-1),1/60);
  s.context.document.hidden=true;await s.instance.tick(4000);
  s.context.document.hidden=false;await s.instance.tick(5000);
  assert.equal(s.elapsed.at(-1),1/60);assert.equal(s.elapsed.length,4);
  s.component.beforeUnmount.call(s.instance);
});

test('scene replacement preserves framing and recenter clears pan without changing the body pivot',async()=>{
  const s=setup({fetch:async()=>({ok:true,json:async()=>({name:'pan'})})});
  s.component.mounted.call(s.instance);await until(()=>s.instance.ready);
  const first=s.renderers[0];first.camera.pan=[.25,-.1];first.camera.distance=1;
  s.instance.scene_url='/geo/test/scene-1.json';s.component.watch.scene_url.call(s.instance);await until(()=>s.instance.ready);
  const next=s.renderers[1];assert.deepEqual([...next.camera.pan],[.25,-.1]);assert.equal(next.camera.distance,1);
  assert.notEqual(next.camera.pan,first.camera.pan);assert.deepEqual([...next.camera.target],[0,.86,0]);
  s.instance.center();assert.deepEqual([...next.camera.pan],[0,0]);assert.deepEqual([...next.camera.target],[0,.86,0]);
  s.component.beforeUnmount.call(s.instance);
});

test('2D view warms the cloth, draws its final state and reveals the same scene without reloading',async()=>{
  let requests=0;
  const s=setup({fetch:async()=>{requests++;return {ok:true,json:async()=>({name:'background'})};}});
  s.instance.active=false;s.component.mounted.call(s.instance);await until(()=>s.instance.ready);
  let now=1000;
  while(!s.instance.warmed && now<12000){await s.instance.tick(now);now+=34;}
  assert.equal(s.instance.warmed,true);assert.equal(s.elapsed.length,180);
  assert.ok(s.elapsed.every(dt=>dt===1/30));assert.equal(s.renderers[0].dirty,false);
  await s.instance.tick(now+1000);assert.equal(s.elapsed.length,180);
  s.instance.active=true;s.component.watch.active.call(s.instance);await s.instance.tick(now+2000);
  assert.equal(requests,1);assert.equal(s.renderers.length,1);assert.equal(s.instance.loadedScene,'background');
  assert.equal(s.elapsed.length,181);assert.equal(s.elapsed.at(-1),1/60);
  s.component.beforeUnmount.call(s.instance);
});

test('background warm-up respects Pause and a hidden browser tab',async()=>{
  const s=setup({fetch:async()=>({ok:true,json:async()=>({name:'background-pause'})})});
  s.instance.active=false;s.component.mounted.call(s.instance);await until(()=>s.instance.ready);
  s.instance.paused=true;s.component.watch.paused.call(s.instance);await s.instance.tick(1000);
  assert.equal(s.elapsed.length,0);
  s.instance.paused=false;s.component.watch.paused.call(s.instance);
  s.context.document.hidden=true;await s.instance.tick(2000);assert.equal(s.elapsed.length,0);
  s.context.document.hidden=false;await s.instance.tick(3000);assert.deepEqual(s.elapsed,[1/30]);
  s.component.beforeUnmount.call(s.instance);
});

test('a material or design revision warms again while still in 2D',async()=>{
  let revision=0;
  const s=setup({fetch:async()=>({ok:true,json:async()=>({name:'revision-'+revision++})})});
  s.instance.active=false;s.component.mounted.call(s.instance);await until(()=>s.instance.ready);
  s.instance.warmed=true;
  s.instance.scene_url='/geo/test/scene-1.json';s.component.watch.scene_url.call(s.instance);
  await until(()=>s.instance.ready);assert.equal(s.instance.warmed,false);assert.equal(s.instance.loadedScene,'revision-1');
  await s.instance.tick(1000);assert.deepEqual(s.elapsed,[1/30]);
  s.component.beforeUnmount.call(s.instance);
});

test('interacting with the dock wakes physics, settles again and respects explicit Pause',async()=>{
  let requests=0;
  const s=setup({fetch:async()=>{requests++;return {ok:true,json:async()=>({name:'dock'})};}});
  s.instance.active=false;s.instance.docked=true;
  s.component.mounted.call(s.instance);await until(()=>s.instance.ready);
  let now=1000;
  while(!s.instance.warmed){await s.instance.tick(now);now+=34;}
  const before=s.elapsed.length;
  s.instance.wake();assert.equal(s.instance.warmed,false);
  while(!s.instance.warmed){await s.instance.tick(now);now+=34;}
  assert.equal(s.elapsed.length,before+36);
  await s.instance.tick(now+1000);assert.equal(s.elapsed.length,before+36);
  s.instance.paused=true;s.component.watch.paused.call(s.instance);s.instance.wake();
  await s.instance.tick(now+2000);assert.equal(s.elapsed.length,before+36);
  assert.equal(requests,1);assert.equal(s.renderers.length,1);
  s.component.beforeUnmount.call(s.instance);
});
