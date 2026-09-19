// Numerical settings only. Physical material properties arrive with the scene.
export const swatchSettings={substeps:48,swatchIterations:32,stretch:0,sewDuration:.001,damping:14,
  selfCollision:false,bodyCollision:false,surfaceContact:false,strainPasses:0};

export function settingsForSwatch(scene,refined=false){
  const test=scene.fabric_test;
  const bending=test.mode==='bend';
  return {...swatchSettings,substeps:bending?(refined?24:12):(refined?64:48),
    swatchIterations:bending?(refined?8:4):32,damping:test.damping,gravity:test.gravity};
}

export function swatchSteps(mode,previous,now,remainder=0){
  // Fixed integration increments avoid equilibrium jitter from varying dt.
  // A 30 Hz display consumes two increments; long stalls have bounded work.
  if(mode!=='bend')return {steps:1,remainder:0};
  const elapsed=previous?Math.max(0,Math.min(1/30,(now-previous)/1000)):1/60;
  const accumulated=remainder+elapsed,steps=Math.min(2,Math.floor(accumulated*60+1e-7));
  return {steps,remainder:Math.max(0,accumulated-steps/60)};
}

export function measureSwatch(scene,positions){
  if(positions.some(p=>p.some(v=>!Number.isFinite(v))))throw Error('The swatch became unstable with these properties.');
  const spec=scene.swatch;
  const average=ids=>[0,1,2].map(axis=>ids.reduce((s,i)=>s+positions[i][axis],0)/ids.length);
  const tip=average(spec.tip);
  return {
    drop_mm:(spec.height_m-tip[1])*1000,
    extension_percent:(tip[0]/(spec.length_m||.08)-1)*100,
    shear_mm:tip[2]*1000,
    pin_error_mm:Math.max(...spec.pins.map(i=>Math.hypot(...positions[i].map((v,a)=>v-scene.vertices[i][a]))))*1000,
    profile:spec.sections.map(ids=>{const p=average(ids);return [p[0]*1000,(spec.height_m-p[1])*1000];}),
    max_strain:Math.max(...scene.constraints.filter(c=>c[2]===0).map(c=>
      Math.hypot(...positions[c[0]].map((v,a)=>v-positions[c[1]][a]))/Math.hypot(c[3],c[4]))),
  };
}
