import {test} from 'node:test';
import assert from 'node:assert/strict';
import {placePanels} from '../gui/webgpu/strain.js';
test('a shirt does not remove another garment placement clearance in an outfit',()=>{
 const scene={garment:'current-design',hinges:[{}],vertices:[[0,1,0],[0,1,0]],vertex_panels:['g0__right_ftorso','g1__pant_f_l'],body_vertices:[],garment_types:{g0__:'DressShirt',g1__:null}};
 const result=placePanels(scene);assert.equal(result.positions[0][1],1);assert.equal(result.positions[1][1],1.06);
});
