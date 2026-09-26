// Pan the framing separately from the mannequin's fixed rotation pivot.
// Tall, narrow views (a phone held upright) pull back so outstretched arms fit;
// the 384x448 thumbnails stay at 1.
export function framingScale(width=Infinity,height=1) {
  return Math.max(1,.85*height/Math.max(1,width));
}
export function panCamera(camera,dx,dy,height,width=Infinity) {
  const scale=2*camera.distance*framingScale(width,height)*Math.tan(35*Math.PI/360)/Math.max(1,height);
  camera.pan??=[0,0];camera.pan[0]+=dx*scale;camera.pan[1]-=dy*scale;
}
export function cameraControls(camera,canvas,changed,motion=null) {
  const abort=new AbortController(),opts={signal:abort.signal},pointers=new Map();
  const controls={destroy:()=>abort.abort()};
  const pan=(dx,dy)=>panCamera(camera,dx,dy,canvas.clientHeight,canvas.clientWidth);
  const zoom=ratio=>{camera.distance=Math.max(.3,Math.min(10,camera.distance*ratio));};
  const rotate=(dx,dy)=>{
    if(motion&&!controls.viewOnly)motion.turn(dx*.008);else camera.yaw-=dx*.008;
    camera.pitch=Math.max(-1.35,Math.min(1.35,camera.pitch+dy*.006));
  };
  const separation=()=>{const [a,b]=[...pointers.values()];return Math.hypot(a.x-b.x,a.y-b.y);};
  const midpoint=()=>{const [a,b]=[...pointers.values()];return [(a.x+b.x)/2,(a.y+b.y)/2];};
  canvas.addEventListener('contextmenu',e=>e.preventDefault(),opts);
  canvas.addEventListener('pointerdown',e=>{
    if(e.button>2)return;e.preventDefault();canvas.focus();canvas.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,pan:e.button!==0||e.shiftKey});
  },opts);
  canvas.addEventListener('pointermove',e=>{
    const previous=pointers.get(e.pointerId);if(!previous)return;
    const before=pointers.size===2?separation():0,center=pointers.size===2?midpoint():null;
    pointers.set(e.pointerId,{...previous,x:e.clientX,y:e.clientY});
    if(pointers.size===2){
      const next=midpoint();pan(next[0]-center[0],next[1]-center[1]);
      const after=separation();if(before>1&&after>1)zoom(before/after);
    }
    else if(pointers.size===1)(previous.pan||e.shiftKey?pan:rotate)(e.clientX-previous.x,e.clientY-previous.y);
    changed();
  },opts);
  const release=e=>pointers.delete(e.pointerId);
  canvas.addEventListener('pointerup',release,opts);canvas.addEventListener('pointercancel',release,opts);
  canvas.addEventListener('lostpointercapture',release,opts);
  canvas.addEventListener('wheel',e=>{e.preventDefault();zoom(Math.exp(e.deltaY*.001));changed();},{...opts,passive:false});
  canvas.addEventListener('keydown',e=>{
    const move={ArrowLeft:[-25,0],ArrowRight:[25,0],ArrowUp:[0,-25],ArrowDown:[0,25]}[e.key];
    if(move){e.preventDefault();(e.shiftKey?pan:rotate)(...move);changed();}
  },opts);
  return controls;
}
