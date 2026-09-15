import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cameraControls,panCamera,framingScale} from '../gui/webgpu/camera.js';
import {cameraMatrix} from '../gui/webgpu/render.js';
import {MannequinMotion} from '../gui/webgpu/motion.js';
const camera=()=>({yaw:0,pitch:0,distance:2,target:[.03,1,-.02],pan:[0,0]});
class Canvas extends EventTarget {
  clientHeight=800;focus(){}setPointerCapture(){}
  send(type,values={}){const e=new Event(type,{cancelable:true});Object.assign(e,{button:0,pointerId:1,clientX:0,clientY:0,shiftKey:false,...values});this.dispatchEvent(e);return e;}
}
test('drag turns the mannequin; right-drag, Shift-drag and Shift-keys pan with a fixed pivot',()=>{
  const c=camera(),canvas=new Canvas(),motion=new MannequinMotion([[-1,0,-1],[1,2,1]]),controls=cameraControls(c,canvas,()=>{},motion);
  canvas.send('pointerdown');canvas.send('pointermove',{clientX:25,clientY:15});canvas.send('pointerup');
  assert.equal(motion.target,.2);assert.deepEqual(c.pan,[0,0]);
  for(const gesture of [{button:1},{button:2},{shiftKey:true}]){
    const before=[...c.pan];canvas.send('pointerdown',gesture);canvas.send('pointermove',{clientX:25,clientY:15});canvas.send('pointerup');
    assert.ok(c.pan[0]>before[0]);assert.ok(c.pan[1]<before[1]);assert.equal(motion.target,.2);
  }
  const before=c.pan[0];canvas.send('keydown',{key:'ArrowRight',shiftKey:true});assert.ok(c.pan[0]>before);assert.equal(motion.target,.2);
  canvas.send('keydown',{key:'ArrowRight'});
  assert.deepEqual(c.target,[.03,1,-.02]);assert.deepEqual(motion.center,[0,1,0]);assert.equal(c.yaw,0);assert.equal(motion.target,.4);assert.ok(c.pitch>0);
  canvas.send('pointermove',{clientX:200});const target=motion.target;controls.destroy();canvas.send('keydown',{key:'ArrowRight'});assert.equal(motion.target,target);
});
test('two fingers pan and pinch without turning; paused drag is inspection only',()=>{
  const c=camera(),canvas=new Canvas(),motion=new MannequinMotion([[-1,0,-1],[1,2,1]]),controls=cameraControls(c,canvas,()=>{},motion);
  canvas.send('pointerdown');canvas.send('pointerdown',{pointerId:2,clientX:100});canvas.send('pointermove',{pointerId:2,clientX:200,clientY:20});
  assert.ok(c.distance<2);assert.ok(c.pan[0]>0);assert.ok(c.pan[1]<0);assert.equal(motion.target,0);assert.deepEqual(c.target,[.03,1,-.02]);
  canvas.send('pointercancel',{pointerId:2});canvas.send('lostpointercapture');
  controls.viewOnly=true;canvas.send('pointerdown');canvas.send('pointermove',{clientX:100});assert.equal(motion.target,0);assert.notEqual(c.yaw,0);
  canvas.send('wheel',{deltaY:10000});assert.equal(c.distance,10);canvas.send('wheel',{deltaY:-10000});assert.equal(c.distance,.3);controls.destroy();
});
test('body motion accelerates gradually, settles and returns to the nearest front',()=>{
  const m=new MannequinMotion([[-.5,.1,-.4],[.6,1.9,.2]]),center=[...m.center];m.turn(Math.PI/2);
  let previousSpeed=0;
  for(let i=0;i<3600;i++){m.advance(1/720);assert.ok(Math.abs(m.speed)<=6);assert.ok(Math.abs(m.speed-previousSpeed)<=120/720+1e-12);previousSpeed=m.speed;}
  assert.ok(Math.abs(m.yaw-Math.PI/2)<1e-4);assert.deepEqual(m.center,center);
  m.yaw=2*Math.PI+.2;m.front();assert.ok(Math.abs(m.target-2*Math.PI)<1e-12);
  m.reset();assert.deepEqual([m.yaw,m.target,m.speed],[0,0,0]);
});

test('a quarter turn responds within 0.4 seconds at both 30 and 60 Hz',()=>{
  const results=[];
  for(const hz of [30,60]){
    const m=new MannequinMotion([[-1,0,-1],[1,2,1]]);m.turn(Math.PI/2);
    for(let frame=0;frame<hz*.4;frame++)for(let step=0;step<12;step++)m.advance(1/(hz*12));
    assert.ok(Math.abs(m.yaw-Math.PI/2)<.02,`${hz} Hz quarter turn lags by ${Math.PI/2-m.yaw}`);
    assert.ok(Math.abs(m.speed)<.7);results.push(m.yaw);
  }
  assert.ok(Math.abs(results[0]-results[1])<.005);
});

test('panning follows the pointer on screen at different zooms and viewing angles',()=>{
  for(const [width,height] of [[1200,800],[272,480]])for(const distance of [1,4])for(const yaw of [0,1.3]){
    const c=camera();c.distance=distance;c.yaw=yaw;c.pitch=.3;
    const eye=c.target.map((v,i)=>v+distance*framingScale(width,height)*[Math.sin(yaw)*Math.cos(c.pitch),Math.sin(c.pitch),Math.cos(yaw)*Math.cos(c.pitch)][i]);
    const screen=()=>{
      const m=cameraMatrix(eye,c.target,width/height,c.pan),p=[...c.target,1];
      const clip=[0,1,2,3].map(row=>p.reduce((s,v,i)=>s+m[i*4+row]*v,0));
      return [clip[0]/clip[3]*width/2,-clip[1]/clip[3]*height/2];
    };
    const before=screen();panCamera(c,60,40,height,width);const after=screen();
    assert.ok(Math.abs(after[0]-before[0]-60)<.001);assert.ok(Math.abs(after[1]-before[1]-40)<.001);
    assert.deepEqual(c.target,[.03,1,-.02]);
  }
});
