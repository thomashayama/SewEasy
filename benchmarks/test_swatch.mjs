import assert from 'node:assert/strict';
import {test} from 'node:test';
import {measureSwatch} from '../gui/webgpu/swatch.js';
import {placePanels} from '../gui/webgpu/strain.js';

const scene={garment:'fabric-swatch',vertices:[[0,.12,0],[.08,.12,0],[.08,.12,.04]],
  constraints:[[0,1,0,.08,0]],swatch:{height_m:.12,pins:[0],tip:[1,2],sections:[[0],[1,2]]}};
test('swatch measurements convert metres to mm and average the whole free edge',()=>{
  const result=measureSwatch(scene,[[0,.12,0],[.075,.11,0],[.075,.10,.04]]);
  assert.ok(Math.abs(result.drop_mm-15)<1e-12);
  assert.equal(result.pin_error_mm,0);
  assert.deepEqual(result.profile[0],[0,0]);
  assert.ok(Math.abs(result.profile[1][0]-75)<1e-12);
  assert.ok(Math.abs(result.profile[1][1]-15)<1e-12);
});
test('a detached clamp or nonfinite simulation cannot silently become a good result',()=>{
  const result=measureSwatch(scene,[[0,.119,0],[.08,.12,0],[.08,.12,.04]]);
  assert.ok(Math.abs(result.pin_error_mm-1)<1e-12);
  assert.throws(()=>measureSwatch(scene,[[0,.12,0],[NaN,.12,0],[.08,.12,.04]]),/unstable/);
});
test('fixture placement preserves the actual clamp position instead of lifting it like a garment',()=>{
  const placed=placePanels(scene);
  assert.deepEqual(placed.positions,scene.vertices);
  assert.notEqual(placed.positions,scene.vertices);
  assert.deepEqual(placed.support,[]);
});
