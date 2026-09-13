import {Cloth} from './physics.js';
import {Renderer} from './render.js';
const status=document.querySelector('#status'),canvas=document.querySelector('canvas');
for(const b of document.querySelectorAll('button'))b.disabled=true;
try {
 const file=new URL(location.href).searchParams.get('scene')||'dress-shirt_1.5cm.json';
 const scene=await (await fetch(file)).json();
 const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
 const device=await adapter.requestDevice();
 device.addEventListener('uncapturederror',e=>{status.textContent=e.error.message;});
 const cloth=await Cloth.create(device,scene,s=>{status.textContent=s;});
 const renderer=new Renderer(device,canvas,cloth,navigator.gpu.getPreferredCanvasFormat());
 const height=scene.body_fit?.measurements?.height?.actual_cm/100||1.72;
 Object.assign(renderer.camera,{yaw:0,pitch:.1,distance:height*.5,target:[0,height*.83,0]});
 let positions,ms=0,colors=false;
 const draw=()=>{const e=device.createCommandEncoder();renderer.render(e);device.queue.submit([e.finish()]);};
 const frame=()=>{if(renderer.dirty)draw();requestAnimationFrame(frame);};frame();
 const inspect=async()=>{
  positions=await cloth.readPositions();
  const panels={};
  for(const name of new Set(scene.vertex_panels))if(/collar|stand/.test(name)){
   const ids=scene.vertex_panels.flatMap((n,i)=>n===name?[i]:[]);
   panels[name]={vertices:ids.length,lo:[0,1,2].map(a=>Math.min(...ids.map(i=>positions[i][a]))),hi:[0,1,2].map(a=>Math.max(...ids.map(i=>positions[i][a])))};
  }
  const seams=scene.constraints.filter(c=>c[2]===2),gap=c=>Math.hypot(...positions[c[0]].map((v,j)=>v-positions[c[1]][j]));
  status.textContent=JSON.stringify({frame:cloth.frame,msPerFrame:ms,creases:scene.crease_constraints,seamMax:Math.max(...seams.map(gap)),kernelChecks:cloth.kernelChecks,panels},null,2);
 };
 const run=async(n)=>{
  for(const b of document.querySelectorAll('button'))b.disabled=true;
  const start=performance.now();
  for(let i=0;i<n;i++){const e=device.createCommandEncoder();cloth.encode(e);renderer.render(e);device.queue.submit([e.finish()]);await device.queue.onSubmittedWorkDone();if(i%60===0)status.textContent=`Running ${i}/${n} frames…`;}
  ms=(performance.now()-start)/n;await inspect();
  for(const b of document.querySelectorAll('button'))b.disabled=false;
 };
 document.querySelector('#reset').onclick=async()=>{cloth.reset();draw();await inspect();};
 for(const [id,n] of [['step',60],['settle',300],['long',1800]])document.querySelector('#'+id).onclick=()=>run(n);
 for(const [id,yaw] of [['front',0],['back',Math.PI],['side',Math.PI/2]])document.querySelector('#'+id).onclick=()=>{renderer.camera.yaw=yaw;renderer.dirty=true;};
 document.querySelector('#body').onclick=()=>{renderer.showBody=!renderer.showBody;renderer.dirty=true;};
 document.querySelector('#colors').onclick=()=>{colors=!colors;const mapping={};for(const name of new Set(scene.vertex_panels))mapping[name]=/collar/.test(name)?'#f0ad65':/stand/.test(name)?'#93c9a3':'#b7cde5';renderer.setFabricColors('#b7cde5',colors?mapping:{});renderer.dirty=true;};
 document.querySelector('#save').onclick=async()=>{await inspect();const response=await fetch('/__results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({report:{scene:scene.name,frames:cloth.frame,msPerFrame:ms,kernelChecks:cloth.kernelChecks,placement:cloth.placement},positions})});status.textContent+='\n'+await response.text();};
 draw();await inspect();
 for(const b of document.querySelectorAll('button'))b.disabled=false;
}catch(error){status.textContent=error.stack;}
