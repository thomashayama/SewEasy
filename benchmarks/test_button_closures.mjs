import {test} from 'node:test';
import assert from 'node:assert/strict';
import {closureColors,closureRest} from '../gui/webgpu/closures.js';

test('closures that share material vertices cannot race in the same GPU batch',()=>{
 const buttons=[
  {ids:[0,1,2],hole:{ids:[3,4,5]}},
  {ids:[1,6,7],hole:{ids:[8,9,10]}},
  {ids:[11,12,13],hole:{ids:[14,15,16]}},
 ];
 const colors=closureColors(buttons);assert.equal(colors.length,2);
 assert.deepEqual(colors.flat().map(b=>b.index).sort(),[0,1,2]);
 for(const color of colors){const ids=color.flatMap(b=>[...b.ids,...b.hole.ids]);assert.equal(new Set(ids).size,ids.length);}
});

test('a decorative attachment is not silently used as a physical closure',()=>{
 assert.deepEqual(closureColors([{ids:[0,1,2]}]),[]);
 assert.throws(()=>closureColors([{ids:[0,1,2],hole:{ids:[2,3,4]}}]),/distinct material triangles/);
});

test('button assembly starts at the authored panel separation, including the shank',()=>{
 const positions=[[0,1,0],[1,1,0],[0,2,0],[0,1,.3],[1,1,.3],[0,2,.3]];
 const b={ids:[0,1,2],weights:[.2,.3,.5],hole:{ids:[3,4,5],weights:[.2,.3,.5]},normal_sign:1,clearance_m:.003};
 const rest=closureRest(b,positions);assert.ok(Math.abs(rest[2]-.297)<1e-12);assert.deepEqual(rest.slice(0,2),[0,0]);
});
