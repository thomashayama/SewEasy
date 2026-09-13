import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cameraControls} from '../gui/webgpu/camera.js';
import {MannequinMotion} from '../gui/webgpu/motion.js';
const camera=()=>({yaw:0,pitch:0,distance:2,target:[.03,1,-.02]});
class Canvas extends EventTarget {
  clientHeight=800;focus(){}setPointerCapture(){}
  send(type,values={}){const e=new Event(type,{cancelable:true});Object.assign(e,{button:0,pointerId:1,clientX:0,clientY:0,shiftKey:false,...values});this.dispatchEvent(e);return e;}
}
test('drag, right-drag, Shift and keys keep the same mannequin center',()=>{
  const c=camera(),canvas=new Canvas(),motion=new MannequinMotion([[-1,0,-1],[1,2,1]]),controls=cameraControls(c,canvas,()=>{},motion);
  for(const button of [0,1,2]){canvas.send('pointerdown',{button});canvas.send('pointermove',{clientX:25,clientY:15,shiftKey:true});canvas.send('pointerup');}
  canvas.send('keydown',{key:'ArrowRight'});
  assert.deepEqual(c.target,[.03,1,-.02]);assert.equal(c.yaw,0);assert.ok(motion.target>.7);assert.ok(c.pitch>0);
  canvas.send('pointermove',{clientX:200});const target=motion.target;controls.destroy();canvas.send('keydown',{key:'ArrowRight'});assert.equal(motion.target,target);
});
test('pinch and scroll zoom without translating or turning; paused drag is inspection only',()=>{
  const c=camera(),canvas=new Canvas(),motion=new MannequinMotion([[-1,0,-1],[1,2,1]]),controls=cameraControls(c,canvas,()=>{},motion);
  canvas.send('pointerdown');canvas.send('pointerdown',{pointerId:2,clientX:100});canvas.send('pointermove',{pointerId:2,clientX:200,clientY:20});
  assert.ok(c.distance<2);assert.equal(motion.target,0);assert.deepEqual(c.target,[.03,1,-.02]);
  canvas.send('pointercancel',{pointerId:2});canvas.send('lostpointercapture');
  controls.viewOnly=true;canvas.send('pointerdown');canvas.send('pointermove',{clientX:100});assert.equal(motion.target,0);assert.notEqual(c.yaw,0);
  canvas.send('wheel',{deltaY:10000});assert.equal(c.distance,10);canvas.send('wheel',{deltaY:-10000});assert.equal(c.distance,.3);controls.destroy();
});
test('body motion accelerates gradually, settles and returns to the nearest front',()=>{
  const m=new MannequinMotion([[-.5,.1,-.4],[.6,1.9,.2]]),center=[...m.center];m.turn(Math.PI/2);
  let previousSpeed=0;
  for(let i=0;i<3600;i++){m.advance(1/720);assert.ok(Math.abs(m.speed)<=2.4);assert.ok(Math.abs(m.speed-previousSpeed)<=9/720+1e-12);previousSpeed=m.speed;}
  assert.ok(Math.abs(m.yaw-Math.PI/2)<1e-4);assert.deepEqual(m.center,center);
  m.yaw=2*Math.PI+.2;m.front();assert.ok(Math.abs(m.target-2*Math.PI)<1e-12);
  m.reset();assert.deepEqual([m.yaw,m.target,m.speed],[0,0,0]);
});
