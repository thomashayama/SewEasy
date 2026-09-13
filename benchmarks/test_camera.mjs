import {test} from 'node:test';
import assert from 'node:assert/strict';
import {panCamera,cameraControls} from '../gui/webgpu/camera.js';

const camera=()=>({yaw:0,pitch:0,distance:2,target:[0,1,0]});
class Canvas extends EventTarget {
  clientHeight=800;focus(){}setPointerCapture(){}
  send(type,values={}){const e=new Event(type,{cancelable:true});Object.assign(e,{button:0,pointerId:1,clientX:0,clientY:0,shiftKey:false,...values});this.dispatchEvent(e);return e;}
}

test('pan follows the screen axes when rotated and zoomed',()=>{
  const c=camera();panCamera(c,100,0,800);assert.ok(c.target[0]<0);assert.equal(c.target[1],1);
  const side=camera();side.yaw=Math.PI/2;panCamera(side,100,0,800);
  assert.ok(Math.abs(side.target[0])<1e-12);assert.ok(side.target[2]>0);
  const zoomed=camera();zoomed.distance=4;panCamera(zoomed,100,0,800);
  assert.ok(Math.abs(zoomed.target[0]-2*c.target[0])<1e-12);
});
test('right-drag and Pan mode translate without orbiting; release stops motion',()=>{
  const c=camera(),canvas=new Canvas(),controls=cameraControls(c,canvas,()=>{});
  canvas.send('pointerdown',{button:2});canvas.send('pointermove',{clientX:100});
  assert.ok(c.target[0]<0);assert.equal(c.yaw,0);
  canvas.send('lostpointercapture');const x=c.target[0];canvas.send('pointermove',{clientX:200});assert.equal(c.target[0],x);
  controls.mode='pan';canvas.send('pointerdown');canvas.send('pointermove',{clientY:100});assert.ok(c.target[1]>1);
  controls.destroy();const y=c.target[1];canvas.send('pointermove',{clientY:200});assert.equal(c.target[1],y);
});
test('ordinary drag orbits, Shift-drag pans, and two fingers pan and zoom',()=>{
  const c=camera(),canvas=new Canvas(),controls=cameraControls(c,canvas,()=>{});
  canvas.send('pointerdown');canvas.send('pointermove',{clientX:100});assert.notEqual(c.yaw,0);
  const yaw=c.yaw;canvas.send('pointermove',{clientX:150,shiftKey:true});assert.equal(c.yaw,yaw);
  canvas.send('pointerup');canvas.send('pointerdown',{pointerId:1,clientX:0});
  canvas.send('pointerdown',{pointerId:2,clientX:100});canvas.send('pointermove',{pointerId:2,clientX:200,clientY:20});
  assert.ok(c.distance<2);assert.ok(c.target[1]>1);
  controls.destroy();
});
