// The loaded swatch tests against their exact answer, on the application's own scenes.
// A converged strip extends by exactly traction / stiffness (see swatch_reference.mjs),
// so these expose small-strain solver error that kernel parity checks cannot.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {simulate,fixtures} from './swatch_reference.mjs';
import {swatchScene} from './swatch_mesh.mjs';
import {material,gridFactor,reading} from './swatch_refinement.mjs';

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
  // More iterations at the same step are the wrong cure: the sized step does ten times better at little over half the cost.
  const iterated=simulate(scene,{substeps:48,iterations:128,seconds:2.5}),sized=simulate(scene,{seconds:2.5});
  const {substeps,iterations}=scene.fabric_test.numerics;
  assert.ok(substeps*iterations<48*128*.6);
  assert.ok(Math.abs(sized.extension/expected-1)<Math.abs(iterated.extension/expected-1)/10,
    `${sized.extension.toFixed(4)}% against ${iterated.extension.toFixed(4)}%`);
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

test('the bend test reproduces the heavy elastica, the exact clamped strip under its own weight',()=>{
  // Before the grid was calibrated these read up to 14% short: the mesh bent as if twice as stiff.
  for(const [name,scene] of named('bend')){
    const expected=scene.fabric_test.expected_drop_mm,got=simulate(scene,{seconds:5}).drop;
    // The limper the strip, the tighter it curls at the clamp, and a 10 mm cell follows that less well.
    const tolerance=expected>72?.025:.01;
    assert.ok(Math.abs(got/expected-1)<tolerance,`${name}: ${got.toFixed(2)} mm vs ${expected.toFixed(2)} mm`);
  }
});

test('bending is insensitive to the step, so the interactive setting is kept',()=>{
  const scene=scenes['cupro / warp / bend'];
  const interactive=simulate(scene,{seconds:4}),fine=simulate(scene,{substeps:96,iterations:8,precision:64,seconds:4});
  assert.ok(Math.abs(interactive.drop/fine.drop-1)<RELATIVE,`${interactive.drop.toFixed(3)} vs ${fine.drop.toFixed(3)} mm`);
});

// Mesh resolution (benchmarks/swatch_refinement.mjs). The refined strips come from swatch_mesh.mjs,
// which is only worth refining if at the application's cell size it is the application's scene.
test('the refinable strip equals the scenes the application builds at 10 mm',()=>{
  const close=(a,b)=>Math.abs(a-b)<=1e-9*Math.max(1,Math.abs(a),Math.abs(b));
  for(const [name,scene] of Object.entries(scenes)){
    const [sample,direction,mode]=name.split(' / '),mine=swatchScene({...material(sample,direction),mode});
    assert.deepEqual(mine.membrane_batches,scene.membrane_batches,name);
    assert.deepEqual(mine.interior_hinge_batches,scene.interior_hinge_batches,name);
    assert.deepEqual(mine.swatch.tip,scene.swatch.tip);
    assert.ok(scene.vertices.every((q,i)=>q.every((x,k)=>close(x,mine.vertices[i][k]))),name);
    assert.ok(scene.inverse_mass.every((w,i)=>close(w,mine.inverse_mass[i])),name);
    assert.ok(scene.external_forces.every((f,i)=>f.every((x,k)=>close(x,mine.external_forces[i][k]))),name);
    scene.membranes.forEach((m,i)=>{
      assert.deepEqual(m.ids,mine.membranes[i].ids);
      for(const key of ['u','v','compliance'])assert.ok(m[key].every((x,k)=>close(x,mine.membranes[i][key][k])),`${name} membrane ${i}.${key}`);
    });
    scene.interior_hinges.forEach((h,i)=>{
      assert.deepEqual(h.ids,mine.interior_hinges[i].ids);
      assert.ok(close(h.compliance,mine.interior_hinges[i].compliance),`${name} hinge ${i}`);
    });
    if(mode!=='bend')assert.equal(mine.fabric_test.numerics.substeps,scene.fabric_test.numerics.substeps,name);
  }
});

test('a symmetric strip hangs level; splitting every cell the same way made it twist',()=>{
  for(const [name,scene] of named('bend'))
    assert.ok(Math.abs(simulate(scene,{seconds:5}).tilt)<.1,`${name}: one corner hangs lower`);
  const uniform=swatchScene({...material('polyester dobby','warp'),mode:'bend',pattern:'uniform',diagonal:'blend',structuredGrid:2.476});
  assert.ok(Math.abs(simulate(uniform,{seconds:5}).tilt)>3);                       // 5.8 mm across a 40 mm edge
});

test('the bend test answers to the rigidity along the strip, not the one across it',()=>{
  // Diagonal hinges that blended both directions moved this by 10% either way.
  const factors=[.25,1,4].map(across=>gridFactor(1,{across}));
  for(const factor of factors)assert.ok(Math.abs(factor/2.431-1)<.02,`grid factor ${factor.toFixed(4)}`);
  const blended=[.25,4].map(across=>gridFactor(1,{across,diagonal:'blend'}));
  assert.ok(blended[1]/blended[0]>1.2);
});

test('the 10 mm grid reads shear low by the documented amount',()=>{
  // No exact answer exists for this test, so the reference is the same strip on 5 mm cells:
  // 8.5% more movement for cupro, on the way to a mesh-converged 11.7% (docs/FabricSwatch.md).
  const coarse=reading('cupro','warp','shear',1).value,fine=reading('cupro','warp','shear',2).value;
  assert.ok(coarse/fine-1<-.07&&coarse/fine-1>-.10,`${coarse.toFixed(3)} mm at 10 mm, ${fine.toFixed(3)} mm at 5 mm`);
});
