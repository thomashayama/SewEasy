// Fixed pivot: one finger turns the mannequin and changes viewing elevation;
// two fingers only zoom. No button or modifier can translate the target.
export function cameraControls(camera,canvas,changed,motion=null) {
  const abort=new AbortController(),opts={signal:abort.signal},pointers=new Map();
  const controls={destroy:()=>abort.abort()};
  const zoom=ratio=>{camera.distance=Math.max(.3,Math.min(10,camera.distance*ratio));};
  const rotate=(dx,dy)=>{
    if(motion&&!controls.viewOnly)motion.turn(dx*.008);else camera.yaw-=dx*.008;
    camera.pitch=Math.max(-1.35,Math.min(1.35,camera.pitch+dy*.006));
  };
  const separation=()=>{const [a,b]=[...pointers.values()];return Math.hypot(a.x-b.x,a.y-b.y);};
  canvas.addEventListener('contextmenu',e=>e.preventDefault(),opts);
  canvas.addEventListener('pointerdown',e=>{
    if(e.button>2)return;e.preventDefault();canvas.focus();canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
  },opts);
  canvas.addEventListener('pointermove',e=>{
    const previous=pointers.get(e.pointerId);if(!previous)return;
    const before=pointers.size===2?separation():0;
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
    if(pointers.size===2){const after=separation();if(before>1&&after>1)zoom(before/after);}
    else if(pointers.size===1)rotate(e.clientX-previous.x,e.clientY-previous.y);
    changed();
  },opts);
  const release=e=>pointers.delete(e.pointerId);
  canvas.addEventListener('pointerup',release,opts);canvas.addEventListener('pointercancel',release,opts);
  canvas.addEventListener('lostpointercapture',release,opts);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(e.deltaY*.001));changed();},{...opts,passive:false});
  canvas.addEventListener('keydown',e=>{
    const move={ArrowLeft:[-25,0],ArrowRight:[25,0],ArrowUp:[0,-25],ArrowDown:[0,25]}[e.key];
    if(move){e.preventDefault();rotate(...move);changed();}
  },opts);
  return controls;
}
