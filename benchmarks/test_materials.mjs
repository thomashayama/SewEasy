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

test('kernel self-checks keep the reference contact values to assert against',()=>{
  // Their expected numbers assume friction .4 and a 4 mm margin; a fabric with
  // its own friction must not make a correct kernel look broken.
  const cloth=new Cloth({},scene({material_settings:{damping:9.2,friction:.2,thickness:.009}}));
  assert.deepEqual(cloth.referenceContact,{damping:2,friction:0.4,thickness:0.004});
  assert.equal(cloth.settings.friction,0.2);
});

test('explicit settings still win, so swatch fixtures are unaffected',()=>{
  const cloth=new Cloth({},scene({material_settings:{damping:9.2}}));
  Object.assign(cloth.settings,{damping:0});      // what Cloth.create applies afterwards
  assert.equal(cloth.settings.damping,0);
});

// Imported base-colour maps: which layer and physical size each vertex samples.
import {fabricRecords,FABRIC_STRIDE} from '../gui/webgpu/render.js';

const specs={sleeve:{kind:'texture',texture:'twill',fg:'#ffffff',bg:'#336699',scale:1},
  cuff:{kind:'stripe',fg:'#ffffff',bg:'#000000',scale:2},collar:{kind:'texture',texture:'lost',fg:'#ffffff',bg:'#112233',scale:1}};
const textures={twill:{front:{image:'F',size_mm:[40,20]},back:{image:'B',size_mm:[12,8]}},
  plain:{front:{image:'P',size_mm:[30,30]},back:{image:'P',size_mm:[30,30]}},lost:{front:{image:'X',size_mm:[5,5]},back:{image:'X',size_mm:[5,5]}}};
const near=(actual,expected)=>expected.forEach((value,i)=>assert.ok(Math.abs(actual[i]-value)<1e-6,`${i}: ${actual[i]} != ${value}`));

test('a textured piece samples its own front and back layers at their physical sizes',()=>{
  const data=fabricRecords(['sleeve','cuff'],specs,textures,new Map([['F',0],['B',1],['P',2]]));
  assert.equal(data.length,2*FABRIC_STRIDE);
  near(data.slice(0,4),[6,.01,0,1]);                        // texture kind, front layer 0, back layer 1
  near(data.slice(12,16),[.04,.02,.012,.008]);              // metres: front 40×20 mm, back 12×8 mm
  near(data.slice(FABRIC_STRIDE,FABRIC_STRIDE+4),[2,.02,0,0]);   // a procedural print is untouched
});

test('one map serves both faces, and a map that never loaded falls back to the plain colour',()=>{
  const both=fabricRecords(['sleeve'],{sleeve:{...specs.sleeve,texture:'plain'}},textures,new Map([['P',2]]));
  near(both.slice(0,4),[6,.01,2,2]);near(both.slice(12,16),[.03,.03,.03,.03]);
  const onlyFront=fabricRecords(['sleeve'],specs,textures,new Map([['F',0]]));
  near(onlyFront.slice(0,4),[6,.01,0,0]);near(onlyFront.slice(12,16),[.04,.02,.04,.02]);   // the back reuses the front
  const missing=fabricRecords(['collar','hem'],specs,textures,new Map([['F',0]]));
  assert.equal(missing[0],0);                               // plain, not a texture with no layer
  near(missing.slice(8,11),[0x11,0x22,0x33].map(v=>(v/255)**2.2));
  assert.ok(missing.slice(FABRIC_STRIDE).every(v=>v===0));  // a piece with no spec at all
});
