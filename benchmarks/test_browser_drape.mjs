// Exercise the actual Vue controller with a fake GPU, without a browser driver.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {test} from 'node:test';

const source=readFileSync(new URL('../gui/browser_drape.js',import.meta.url),'utf8')
  .replace(/^import .*;$/gm,'').replace('export default {','globalThis.component = {');

function setup({gpu,fetch}={}) {
  const emitted=[],destroyed=[];
  const device={queue:{onSubmittedWorkDone:async()=>{}},lost:new Promise(()=>{}),
    addEventListener(){},destroy(){destroyed.push('device');}};
  const context=vm.createContext({navigator:gpu===false?{}:{gpu:{
    requestAdapter:async()=>({requestDevice:async()=>device}),getPreferredCanvasFormat:()=> 'bgra8unorm'}},
    fetch,performance:{now:()=>1000},AbortController,document:{hidden:false},
    requestAnimationFrame:()=>1,cancelAnimationFrame(){},
    Cloth:{create:async(_device,scene)=>({scene,frame:0,supportTargets:[],settings:{holdNeckline:false},
      destroy(){destroyed.push(scene.name);}})},
    Renderer:class {constructor(){this.bodyView={};this.controls={};this.camera={target:[0,1,0]};}setFabricColors(){}destroy(){}}
  });
  vm.runInContext(source,context);
  const component=context.component;
  const instance={...component.data(),scene_url:'/geo/test/scene-0.json',active:true,preparing:false,error:'',
    fabric_color:'#ffffff',body_color:'#ffffff',panel_colors:{},show_body:true,
    $refs:{canvas:{}},$el:{getClientRects:()=>[{}]},$emit:(...event)=>emitted.push(event)};
  for(const [key,fn] of Object.entries(component.methods))instance[key]=fn.bind(instance);
  return {instance,component,emitted,destroyed};
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
