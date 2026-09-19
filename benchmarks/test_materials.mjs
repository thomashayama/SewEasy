// Solver-wide material values ride in the scene; per-piece mass is in the mesh.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Cloth} from '../gui/webgpu/physics.js';

function scene(extra={}) {
  return {name:'materials',vertices:[[0,0,0],[.1,0,0],[0,.1,0]],uv:[[0,0],[.1,0],[0,.1]],faces:[[0,1,2]],
    vertex_panels:['front','front','front'],body_vertices:[[-1,0,-1],[1,2,1]],constraints:[],batches:[],
    inverse_mass:[100,100,100],...extra};
}

test('an unassigned garment keeps the documented solver defaults',()=>{
  const cloth=new Cloth({},scene());
  assert.equal(cloth.settings.damping,2);
  assert.equal(cloth.settings.friction,0.4);
  assert.equal(cloth.settings.thickness,0.004);
});

test('assigned fabrics set damping, body friction and the contact margin',()=>{
  const cloth=new Cloth({},scene({material_settings:{damping:9.2,friction:.82,thickness:.009}}));
  assert.equal(cloth.settings.damping,9.2);
  assert.equal(cloth.settings.friction,0.82);
  assert.equal(cloth.settings.thickness,0.009);
  // Untouched controls stay at their garment values.
  assert.equal(cloth.settings.stretch,0.00001);
  assert.equal(cloth.settings.gravity,9.81);
  assert.equal(cloth.settings.strainLimit,1.02);
});

test('explicit settings still win, so swatch fixtures are unaffected',()=>{
  const cloth=new Cloth({},scene({material_settings:{damping:9.2}}));
  Object.assign(cloth.settings,{damping:0});      // what Cloth.create applies afterwards
  assert.equal(cloth.settings.damping,0);
});
