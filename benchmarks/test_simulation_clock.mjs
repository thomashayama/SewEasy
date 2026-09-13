import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Cloth} from '../gui/webgpu/physics.js';
import {MannequinMotion} from '../gui/webgpu/motion.js';

// Exercise the production frame encoder without allocating a browser GPU.
// The live harness separately validates the dispatched kernels and geometry.
function clock() {
  const cloth=Object.create(Cloth.prototype),writes=[],steps=[];
  Object.assign(cloth,{time:2,frame:0,n:1,frameDt:1/60,
    settings:{substeps:12,sewDuration:1.6,strainPasses:0},
    motion:new MannequinMotion([[-1,0,-1],[1,2,1]]),motionStride:256,motionRaw:new Float32Array(64*64),
    motionBuffer:{},params:{},device:{queue:{writeBuffer(buffer,_offset,data){if(buffer===cloth.params)writes.push(new Float32Array(data).slice());}}},
    batches:[],seamBatches:[],hingeBatches:[],waistBatches:[],integrate:{},
    dispatchInPass(_pass,stage){if(stage===this.integrate)steps.push(this.motionStep);}});
  let passes=0,ends=0;
  const encoder={beginComputePass(){passes++;return {end(){ends++;}};}};
  return {cloth,writes,steps,encoder,passes:()=>passes,ends:()=>ends};
}

test('30 and 60 Hz advance the same simulated time using small cloth steps',()=>{
  const yaws=[];
  for(const hz of [30,60]){
    const c=clock();c.cloth.motion.turn(Math.PI/2);
    for(let i=0;i<hz*.4;i++)c.cloth.encode(c.encoder,null,1/hz);
    assert.ok(Math.abs(c.cloth.time-2.4)<1e-12);
    assert.equal(c.steps.length,288);
    assert.ok(c.writes.every(p=>Math.abs(p[0]-1/720)<1e-9));
    assert.equal(c.passes(),hz*.4);assert.equal(c.ends(),c.passes());
    yaws.push(c.cloth.motion.yaw);
  }
  assert.ok(Math.abs(yaws[0]-yaws[1])<1e-12);assert.ok(Math.abs(yaws[0]-Math.PI/2)<.02);
});

test('long stalls have bounded work and substeps receive successive collider poses',()=>{
  const c=clock();c.cloth.motion.turn(1);c.cloth.encode(c.encoder,null,10);
  assert.ok(Math.abs(c.cloth.time-2-1/30)<1e-12);assert.equal(c.steps.length,24);
  const raw=c.cloth.motionRaw,stride=c.cloth.motionStride/4;
  for(let i=1;i<24;i++){
    assert.equal(raw[i*stride+2],raw[(i-1)*stride]);
    assert.equal(raw[i*stride+3],raw[(i-1)*stride+1]);
    assert.ok(raw[i*stride+1]>raw[(i-1)*stride+1]);
  }
  assert.ok(Math.abs(raw[23*stride+1]-Math.sin(c.cloth.motion.yaw))<1e-7);
});
