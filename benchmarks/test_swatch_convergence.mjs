// The loaded swatch tests against their exact answer, on the application's own scenes.
// A converged strip extends by exactly traction / stiffness (see swatch_reference.mjs),
// so these expose small-strain solver error that kernel parity checks cannot.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {simulate,fixtures} from './swatch_reference.mjs';

const scenes=fixtures(),named=mode=>Object.entries(scenes).filter(([name])=>name.endsWith('/ '+mode));
// Relative error exposes a stiff fabric's 0.38% strain; the absolute bound, in
// percentage points of extension, keeps a soft fabric's 7% strain honest too.
const RELATIVE=.005,ABSOLUTE=.02;

test('every stretch fixture settles on traction / stiffness with the sized step',()=>{
  for(const [name,scene] of named('stretch')){
    const expected=scene.fabric_test.expected_extension_percent,got=simulate(scene,{seconds:2.5});
    assert.ok(scene.fabric_test.numerics.validated,name);
    assert.ok(Math.abs(got.extension/expected-1)<RELATIVE,`${name}: ${got.extension.toFixed(4)}% vs ${expected.toFixed(4)}%`);
    assert.ok(Math.abs(got.extension-expected)<ABSOLUTE,name);
    assert.ok(Math.abs(got.shear)<.02,`${name}: a pure pull drifted ${got.shear.toFixed(4)} mm sideways`);
  }
});

test('the old fixed step fails the same tolerance, which is what this guards',()=>{
  const scene=scenes['polyester dobby / warp / stretch'],expected=scene.fabric_test.expected_extension_percent;
  const before=simulate(scene,{substeps:48,iterations:32,seconds:2.5});
  assert.ok(before.extension/expected-1>.3,`48 x 32 read ${before.extension.toFixed(4)}%`);     // the documented +38%
  // More iterations at the same step are the wrong cure; smaller steps at equal cost are the right one.
  const iterated=simulate(scene,{substeps:48,iterations:128,seconds:2.5}),stepped=simulate(scene,{substeps:384,iterations:4,seconds:2.5});
  assert.ok(Math.abs(stepped.extension/expected-1)<Math.abs(iterated.extension/expected-1)/2);
});

test('float32 state is not the limit: it matches float64 at the sized step',()=>{
  const scene=scenes['polyester dobby / warp / stretch'];
  const single=simulate(scene,{seconds:2.5}),double=simulate(scene,{seconds:2.5,precision:64});
  assert.ok(Math.abs(single.extension/double.extension-1)<.002,`${single.extension} vs ${double.extension}`);
});

test('shear readings with the sized step match a far finer solve',()=>{
  // The stiff polyester, where the old step over-read by 23%, and the soft cupro.
  for(const [name,scene] of named('shear').filter(([name])=>/^(polyester dobby|cupro) \/ warp/.test(name))){
    const sized=simulate(scene,{seconds:2.5}),fine=simulate(scene,{substeps:1024,iterations:8,precision:64,seconds:2.5});
    assert.ok(Math.abs(sized.shear/fine.shear-1)<RELATIVE,`${name}: ${sized.shear.toFixed(4)} vs ${fine.shear.toFixed(4)} mm`);
  }
});

test('bending is insensitive to the step, so the interactive setting is kept',()=>{
  const scene=scenes['cupro / warp / bend'];
  const interactive=simulate(scene,{seconds:4}),fine=simulate(scene,{substeps:96,iterations:8,precision:64,seconds:4});
  assert.ok(Math.abs(interactive.drop/fine.drop-1)<RELATIVE,`${interactive.drop.toFixed(3)} vs ${fine.drop.toFixed(3)} mm`);
});
