import assert from 'node:assert/strict';
import {test} from 'node:test';
import {placePanels} from '../gui/webgpu/strain.js';

test('a collared shirt stays at its drafted neck height without a fitting pin',()=>{
 const scene={garment:'current-design',vertices:[[0,1.45,.12],[.1,1.48,.12]],
  vertex_panels:['right_stand_front','left_collar_front'],hinges:[{}]};
 const result=placePanels(scene);
 assert.deepEqual(result.positions,scene.vertices);
 assert.deepEqual(result.support,[]);
});

test('uncollared shirt placement retains its existing clearance',()=>{
 const result=placePanels({garment:'t-shirt',vertices:[[0,1.4,.3]],vertex_panels:['front']});
 assert.ok(Math.abs(result.positions[0][1]-1.46)<1e-10);
});
