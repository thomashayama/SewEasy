// Screen-space panning moves both the eye and orbit target. It therefore
// works from the front, back and side without changing the orbit angles.
export function panCamera(camera, dx, dy, height) {
  const s=2*camera.distance*Math.tan(35*Math.PI/360)/Math.max(height,1);
  const right=[Math.cos(camera.yaw),0,-Math.sin(camera.yaw)];
  const up=[-Math.sin(camera.yaw)*Math.sin(camera.pitch),Math.cos(camera.pitch),-Math.cos(camera.yaw)*Math.sin(camera.pitch)];
  camera.target=camera.target.map((v,i)=>v+s*(-dx*right[i]+dy*up[i]));
}

export function cameraControls(camera,canvas,changed) {
  const abort=new AbortController(),opts={signal:abort.signal},pointers=new Map();
  const controls={mode:'orbit',destroy:()=>abort.abort()};
  const zoom=ratio=>{camera.distance=Math.max(.3,Math.min(10,camera.distance*ratio));};
  const pair=()=>{const [a,b]=[...pointers.values()];return {x:(a.x+b.x)/2,y:(a.y+b.y)/2,d:Math.hypot(a.x-b.x,a.y-b.y)};};
  canvas.addEventListener('contextmenu',e=>e.preventDefault(),opts);
  canvas.addEventListener('pointerdown',e=>{
    if(e.button>2)return;e.preventDefault();canvas.focus();canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,pan:e.button!==0||e.shiftKey||controls.mode==='pan'});
  },opts);
  canvas.addEventListener('pointermove',e=>{
    const previous=pointers.get(e.pointerId);if(!previous)return;
    if(pointers.size===2){
      const before=pair();pointers.set(e.pointerId,{...previous,x:e.clientX,y:e.clientY});const after=pair();
      panCamera(camera,after.x-before.x,after.y-before.y,canvas.clientHeight);
      if(before.d>1&&after.d>1)zoom(before.d/after.d);
    }else if(pointers.size===1){
      const dx=e.clientX-previous.x,dy=e.clientY-previous.y;
      if(previous.pan||e.shiftKey)panCamera(camera,dx,dy,canvas.clientHeight);
      else{camera.yaw-=dx*.008;camera.pitch=Math.max(-1.35,Math.min(1.35,camera.pitch+dy*.006));}
      pointers.set(e.pointerId,{...previous,x:e.clientX,y:e.clientY});
    }
    changed();
  },opts);
  const release=e=>pointers.delete(e.pointerId);
  canvas.addEventListener('pointerup',release,opts);canvas.addEventListener('pointercancel',release,opts);
  canvas.addEventListener('lostpointercapture',release,opts);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(e.deltaY*.001));changed();},{...opts,passive:false});
  canvas.addEventListener('keydown',e=>{
    const move={ArrowLeft:[-25,0],ArrowRight:[25,0],ArrowUp:[0,-25],ArrowDown:[0,25]}[e.key];
    if(move){e.preventDefault();panCamera(camera,...move,canvas.clientHeight);changed();}
  },opts);
  return controls;
}
