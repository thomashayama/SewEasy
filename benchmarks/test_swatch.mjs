import assert from 'node:assert/strict';
import {test} from 'node:test';
import {measureSwatch,settingsForSwatch,swatchSteps} from '../gui/webgpu/swatch.js';
import {placePanels} from '../gui/webgpu/strain.js';

const scene={garment:'fabric-swatch',vertices:[[0,.12,0],[.08,.12,0],[.08,.12,.04]],
  constraints:[[0,1,0,.08,0]],swatch:{height_m:.12,pins:[0],tip:[1,2],sections:[[0],[1,2]]}};
test('bending follows display time while loaded measurements keep fixed small steps',()=>{
  for(const hz of [30,45,60]){
    let total=0,remainder=0;
    for(let i=1;i<=hz;i++){const b=swatchSteps('bend',1000+(i-1)*1000/hz,1000+i*1000/hz,remainder);total+=b.steps;remainder=b.remainder;}
    assert.equal(total,60);assert.ok(remainder<1e-10);
  }
  assert.equal(swatchSteps('bend',1,10001).steps,2);
  assert.equal(swatchSteps('stretch',1,10001).steps,1);
});
test('fixture accuracy settings preserve material values, including zero damping',()=>{
  for(const mode of ['bend','stretch','shear']){
    const fixture={fabric_test:{mode,damping:0,gravity:mode==='bend'?9.81:0}};
    const settings=settingsForSwatch(fixture),refined=settingsForSwatch(fixture,true);
    assert.equal(settings.damping,0);assert.equal(settings.gravity,fixture.fabric_test.gravity);
    assert.equal(settings.bodyCollision,false);assert.equal(settings.strainPasses,0);
    assert.ok(refined.substeps>settings.substeps&&refined.substeps<=64);
    assert.ok(refined.swatchIterations>=settings.swatchIterations);
  }
});
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
