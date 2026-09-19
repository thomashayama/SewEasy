// Shared controls for both swatches. These are diagnostic assumptions, not
// measured material properties or the settings used for garment draping.
export const swatchSettings={substeps:24,swatchIterations:8,stretch:0,sewDuration:.001,damping:14,
  selfCollision:false,bodyCollision:false,surfaceContact:false,strainPasses:0};

export function measureSwatch(scene,positions){
  if(positions.some(p=>p.some(v=>!Number.isFinite(v))))throw Error('The swatch became unstable. Try another fabric weight.');
  const spec=scene.swatch;
  const average=ids=>[0,1,2].map(axis=>ids.reduce((s,i)=>s+positions[i][axis],0)/ids.length);
  const tip=average(spec.tip);
  return {
    drop_mm:(spec.height_m-tip[1])*1000,
    pin_error_mm:Math.max(...spec.pins.map(i=>Math.hypot(...positions[i].map((v,a)=>v-scene.vertices[i][a]))))*1000,
    profile:spec.sections.map(ids=>{const p=average(ids);return [p[0]*1000,(spec.height_m-p[1])*1000];}),
    max_strain:Math.max(...scene.constraints.filter(c=>c[2]===0).map(c=>
      Math.hypot(...positions[c[0]].map((v,a)=>v-positions[c[1]][a]))/Math.hypot(c[3],c[4]))),
  };
}
