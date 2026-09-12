import {Cloth} from './physics.js?v=9';
import {Renderer} from './render.js?v=9';

const $=id=>document.getElementById(id);
let device,adapter,cloth,renderer,manifest,running=false,loading=true,measuring=null,lastResult=null,lastPositions=null;
let queries,queryResolve,queryRead,lastFrameTime=0,lastUpdateTime=0,accumulator=0,displaySamples=[];
const errors=[];
const percentile=(a,p)=>{const b=[...a].sort((x,y)=>x-y),x=(b.length-1)*p,i=Math.floor(x);return b[i]+(b[Math.min(i+1,b.length-1)]-b[i])*(x-i);};
function status(text){$('status').textContent=text;}
function failure(error){const message=error?.message||String(error);running=false;measuring=null;errors.push(message);status(message);$('run').textContent='Run simulation';console.error(message);}
function controls(disabled){for(const id of ['garment','run','reset','width','widen','wind','measure','substeps','stretch','bend','body-contact','self-contact','continue','strain-limit','hold-neckline','duration'])$(id).disabled=disabled;}
function settings(){
 if(!cloth)return;const s=cloth.settings;
 s.width=+$('width').value/100;s.wind=+$('wind').value;s.substeps=+$('substeps').value;
 s.stretch=Math.max(0,+$('stretch').value);s.bend=Math.max(0,+$('bend').value);
 s.strainLimit=1+Math.max(1,Math.min(30,+$('strain-limit').value||8))/100;
 s.selfCollision=$('self-contact').checked;s.bodyCollision=$('body-contact').checked;
 s.holdNeckline=$('hold-neckline').checked&&cloth.supportTargets.length>0;
 $('width-value').textContent=$('width').value+'%';$('wind-value').textContent=s.wind?'On':'Off';
}
async function load(){
 loading=true;running=false;controls(true);$('run').textContent='Run simulation';$('download').disabled=true;$('report').disabled=true;$('results').close();
 status('Loading original panels and mannequin…');
 try{
  await device.queue.onSubmittedWorkDone();renderer?.destroy();cloth?.destroy();renderer=null;cloth=null;
  const start=performance.now(),response=await fetch($('garment').value);if(!response.ok)throw Error('Could not load garment');
  const scene=await response.json();status('Preparing WebGPU pipelines…');
  cloth=await Cloth.create(device,scene,status);renderer=new Renderer(device,$('canvas'),cloth,navigator.gpu.getPreferredCanvasFormat());
  $('support-option').hidden=!cloth.supportTargets.length;$('hold-neckline').checked=cloth.settings.holdNeckline;
  renderer.clothView.color[3]=+$('show-strain').checked;
  settings();$('mesh-info').textContent=cloth.n.toLocaleString();$('elapsed').textContent='0.0 s';$('fps').textContent='—';$('gpu-ms').textContent='—';
  cloth.setupMs=performance.now()-start;lastResult=null;lastPositions=null;$('results').hidden=true;
  status(`${scene.panels} panels · ${scene.seams} seams. Ready to sew and drape.`);controls(false);
 }catch(e){failure(e);}finally{loading=false;}
}
function reset(){running=false;cloth.reset();renderer.dirty=true;$('run').textContent='Run simulation';$('elapsed').textContent='0.0 s';$('fps').textContent='—';$('gpu-ms').textContent='—';status('Original panels restored.');lastResult=null;lastPositions=null;$('results').close();$('report').disabled=true;$('download').disabled=true;}
function summarize(positions,initial){
 const s=cloth.scene,stretch=[],seams=[],triangleStretch=[];let maxMove=0,finite=true;
 for(let i=0;i<positions.length;i++){
  finite&&=positions[i].every(Number.isFinite);maxMove=Math.max(maxMove,Math.hypot(...positions[i].map((x,j)=>x-initial[i][j])));
 }
 for(const c of s.constraints){
  const a=positions[c[0]],b=positions[c[1]],length=Math.hypot(...a.map((v,i)=>v-b[i]));
  if(c[2]===0)stretch.push(length/Math.hypot(c[3]*cloth.settings.width,c[4]));
  if(c[2]===2)seams.push(length*1000);
 }
 for(const t of cloth.strainTriangles){
  const [a,b,c]=t.ids.map(i=>positions[i]),m=t.inverse,w=cloth.settings.width;
  const f0=a.map((v,i)=>((b[i]-v)*m[0]+(c[i]-v)*m[2])/w),f1=a.map((v,i)=>(b[i]-v)*m[1]+(c[i]-v)*m[3]);
  const dot=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0),xx=dot(f0,f0),xy=dot(f0,f1),yy=dot(f1,f1);
  triangleStretch.push(Math.sqrt(.5*(xx+yy+Math.hypot(xx-yy,2*xy))));
 }
 return {finite,rms_velocity_m_s:cloth.rmsVelocity,displacement_max_m:maxMove,edge_stretch_p95:percentile(stretch,.95),edge_stretch_max:Math.max(...stretch),triangle_stretch_p95:percentile(triangleStretch,.95),triangle_stretch_max:Math.max(...triangleStretch),triangles_above_target:triangleStretch.filter(x=>x>cloth.settings.strainLimit+.02).length,seam_gap_p95_mm:percentile(seams,.95),seam_gap_max_mm:Math.max(...seams),bounds_m:[0,1,2].map(a=>[Math.min(...positions.map(p=>p[a])),Math.max(...positions.map(p=>p[a]))])};
}
async function finish(){
 const m=measuring;running=false;measuring=null;status('Reading final geometry for validation…');
 lastPositions=await cloth.readPositions();
 const wall=(m.ended-m.started)/1000;
 lastResult={engine:'Browser WebGPU small-step XPBD',implementation:'principal-strain-v1',scene:cloth.scene.name,start_frame:m.startFrame,frames:m.frames,simulated_seconds:m.frames/60,wall_s:wall,updates_per_second:m.frames/wall,
  browser_frame_ms_median:percentile(m.frameMs,.5),browser_frame_ms_p95:percentile(m.frameMs,.95),
  gpu_physics_ms_median:m.gpu.length?percentile(m.gpu,.5):null,gpu_physics_ms_p95:m.gpu.length?percentile(m.gpu,.95):null,
  gpu_render_ms_median:m.render.length&&percentile(m.render,.5)>0?percentile(m.render,.5):null,setup_ms:cloth.setupMs,sdf_setup_ms:cloth.sdfSetupMs,sdf_grid:cloth.gridSize,kernel_checks:cloth.kernelChecks,
  vertices:cloth.n,triangles:cloth.scene.faces.length,constraints:cloth.scene.constraints.length,colors:cloth.scene.batches.length,
  strain_colors:cloth.strainBatches.length,surface_contact_samples_per_triangle:4,
  settings:{...cloth.settings},placement:cloth.placement,adapter:adapter.info?{vendor:adapter.info.vendor,architecture:adapter.info.architecture,device:adapter.info.device,description:adapter.info.description}:null,
  user_agent:navigator.userAgent,initialization:m.startFrame?'Continue browser-generated drape at fixed topology':`Original unsewn panels with recorded placement adjustments; sew for ${cloth.settings.sewDuration} s before gravity; no precomputed drape`,quality:summarize(lastPositions,m.initial),
  fitting_support:{enabled:cloth.settings.holdNeckline,vertices:cloth.settings.holdNeckline?cloth.supportTargets.length:0,type:'Neckline height only; horizontal motion remains free. Supported previews do not establish unsupported fit.'},
  timestamp_query:!!queries,errors:[...errors],frame_ms:m.frameMs,gpu_physics_ms:m.gpu,gpu_render_ms:m.render,
  limitations:['Distance-based stretch, iterative principal-strain target and approximate bending; uncalibrated fabric',
   'Discrete body contact with browser-generated distance field; no continuous collision detection',
   'Particle self-contact only: does not guarantee triangle/edge separation',
   'Pattern width changes rest distances at fixed topology, no pattern redraft'],
  backend:'Static assets only during simulation; optional CPU-only result archive on Save'};
 $('results').hidden=false;$('result-summary').textContent=`${lastResult.updates_per_second.toFixed(1)} browser updates/s. ${queries?lastResult.gpu_physics_ms_median.toFixed(2)+' ms median GPU physics.':'GPU timestamps unavailable.'} Geometry moved ${(lastResult.quality.displacement_max_m*100).toFixed(1)} cm; p95 seam gap ${lastResult.quality.seam_gap_p95_mm.toFixed(2)} mm.`;
 $('result-json').textContent=JSON.stringify({...lastResult,frame_ms:undefined,gpu_physics_ms:undefined,gpu_render_ms:undefined},null,2);
 $('fps').textContent=lastResult.updates_per_second.toFixed(1);$('gpu-ms').textContent=queries?lastResult.gpu_physics_ms_median.toFixed(2)+' ms':'Unavailable';
 controls(false);$('report').disabled=false;$('download').disabled=false;$('run').textContent='Run simulation';status(`Measurement finished. p95 stretch ${((lastResult.quality.triangle_stretch_p95-1)*100).toFixed(1)}%.${lastResult.quality.triangle_stretch_max>1.5?' High local distortion: inspect fit.':''}`);
}
async function animate(now){
 if(!loading&&cloth&&renderer&&(running||renderer.dirty)){
  try{
   accumulator=running?Math.min(accumulator+(now-lastFrameTime)/1000,0.1):0;
   const simulated=running&&(measuring||accumulator>=1/60),readTime=simulated&&queries&&(measuring||cloth.frame%30===0);
   if(simulated&&!measuring)accumulator-=1/60;
   if(!simulated&&!renderer.dirty){lastFrameTime=now;requestAnimationFrame(animate);return;}
   const tick=performance.now();const encoder=device.createCommandEncoder();
   if(simulated)cloth.encode(encoder,readTime?queries:null);
   renderer.render(encoder,readTime?queries:null);
   if(readTime){encoder.resolveQuerySet(queries,0,4,queryResolve,0);encoder.copyBufferToBuffer(queryResolve,0,queryRead,0,32);}
   device.queue.submit([encoder.finish()]);await device.queue.onSubmittedWorkDone();
   let gpu=null,render=null;
   if(readTime){await queryRead.mapAsync(GPUMapMode.READ);const t=new BigUint64Array(queryRead.getMappedRange());gpu=Number(t[1]-t[0])/1e6;render=Number(t[3]-t[2])/1e6;queryRead.unmap();$('gpu-ms').textContent=gpu.toFixed(2)+' ms';}
   if(simulated){
    $('elapsed').textContent=(cloth.frame/60).toFixed(1)+' s';
    if(lastUpdateTime){displaySamples.push(now-lastUpdateTime);if(displaySamples.length>30)displaySamples.shift();$('fps').textContent=(1000/(displaySamples.reduce((a,b)=>a+b)/displaySamples.length)).toFixed(1);}lastUpdateTime=now;
    if(measuring){
     measuring.frames++;measuring.frameMs.push(performance.now()-tick);if(gpu!==null){measuring.gpu.push(gpu);measuring.render.push(render);}
     status(`Measuring ${measuring.frames} / ${measuring.target} frames. All physics runs in this browser.`);
     if(measuring.frames===measuring.target){measuring.ended=performance.now();await finish();}
    }
   }
  }catch(e){failure(e);controls(false);}
 }
 lastFrameTime=now;requestAnimationFrame(animate);
}
$('garment').onchange=load;
$('run').onclick=()=>{running=!running;lastUpdateTime=0;displaySamples=[];$('run').textContent=running?'Pause':'Run simulation';status(running?'Sewing and draping on your device at real time.':'Simulation paused.');};
$('reset').onclick=reset;
for(const id of ['width','wind','substeps','stretch','bend','body-contact','self-contact','strain-limit','hold-neckline'])$(id).oninput=settings;
$('widen').onclick=()=>{$('width').value=Math.min(110,+$('width').value+2);settings();status('Rest-panel width increased by 2%. Run or continue the measurement to settle.');};
for(const [id,yaw] of [['front',0],['side',Math.PI/2],['back',Math.PI]])$(id).onclick=()=>{if(renderer){renderer.camera.yaw=yaw;renderer.camera.pitch=0;renderer.dirty=true;}};
for(const [id,distance,target] of [['focus-garment',2.3,[0,1.2,0]],['full-body',3.6,[0,.95,0]]])$(id).onclick=()=>{if(renderer){Object.assign(renderer.camera,{distance,target});renderer.dirty=true;}};
$('show-strain').oninput=()=>{$('strain-legend').hidden=!$('show-strain').checked;if(renderer){renderer.clothView.color[3]=+$('show-strain').checked;renderer.dirty=true;}};
$('measure').onclick=async()=>{try{running=false;controls(true);if(!$('continue').checked)cloth.reset();settings();$('download').disabled=true;$('report').disabled=true;displaySamples=[];lastUpdateTime=0;const initial=await cloth.readPositions();measuring={frames:0,target:+$('duration').value,startFrame:cloth.frame,initial,started:performance.now(),frameMs:[],gpu:[],render:[]};running=true;}catch(e){failure(e);controls(false);}};
$('duration').onchange=()=>$('measure').textContent=`Measure ${$('duration').value} frames`;
$('report').onclick=()=>$('results').showModal();$('close-report').onclick=()=>$('results').close();
$('download').onclick=async()=>{
 if(!lastResult)return;const data={report:lastResult,positions:lastPositions};
 // This optional endpoint merely writes JSON. Neither physics nor rendering
 // ever calls the backend. Standard static hosts use the download fallback.
 try{
  const response=await fetch('/__results',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(!response.ok)throw Error('Static host');const saved=await response.json();status(`Saved ${saved.path}`);
 }catch{
  const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));a.href=url;a.download=`seweasy-webgpu-${cloth.scene.name}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Result and geometry downloaded.');
 }
};
try{
 if(!navigator.gpu)throw Error('WebGPU is unavailable. Open this page in a current Chrome or Edge browser with hardware acceleration, on HTTPS or localhost.');
 adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});if(!adapter)throw Error('No WebGPU adapter is available.');
 const timestamp=adapter.features.has('timestamp-query');device=await adapter.requestDevice({requiredFeatures:timestamp?['timestamp-query']:[]});
 device.addEventListener('uncapturederror',e=>failure(e.error));device.lost.then(info=>failure('WebGPU device lost: '+info.message));
 const info=adapter.info;$('device').textContent=`WebGPU active${info?.description?' · '+info.description:info?.vendor?' · '+info.vendor:''}`;
 if(timestamp){queries=device.createQuerySet({type:'timestamp',count:4});queryResolve=device.createBuffer({size:32,usage:GPUBufferUsage.QUERY_RESOLVE|GPUBufferUsage.COPY_SRC});queryRead=device.createBuffer({size:32,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});}
 manifest=await(await fetch('manifest.json')).json();for(const entry of manifest)$('garment').add(new Option(entry.label,entry.path));
 await load();requestAnimationFrame(animate);
}catch(e){failure(e);$('device').textContent='WebGPU unavailable';}
