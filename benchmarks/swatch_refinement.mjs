// Mesh-resolution sensitivity of the shear and bend swatch tests (RIV-91).
//
// Stretch needs no study: a converged strip extends by exactly traction / stiffness
// on any mesh. Shear and bending carry the grid's own error, and the application's
// grid is fixed at 10 mm, so the same strip is solved here on 10, 5 and 2.5 mm cells
// (benchmarks/swatch_mesh.mjs) in float64 with the step sized as the application
// sizes it. Shear has no exact answer, so Richardson extrapolation of the three
// readings estimates the mesh-converged value the 10 mm reading is judged against.
// Bending has one, the heavy elastica, and every cell size is judged against that.
//
//   node benchmarks/swatch_refinement.mjs                 shear and bend readings, about 40 minutes
//   node benchmarks/swatch_refinement.mjs --mode=shear    shear only
//   node benchmarks/swatch_refinement.mjs --mode=factor   the bending grid factor each cell size and split needs
//   node benchmarks/swatch_refinement.mjs --levels=1,2    a quick look
import {simulate,fixtures} from './swatch_reference.mjs';
import {swatchScene} from './swatch_mesh.mjs';

// benchmarks/export_swatch_fixtures.SAMPLES: weight, stretch warp/weft, bending warp/weft (null: the stated default).
export const SAMPLES={
  'polyester dobby':[79.2,6571.345,3560.165,1.989e-5,1.357e-5],
  'cotton voile':[92,1674.790,338.036,null,2.231e-6],
  'cupro':[105.6,587.5116,1035.2515,1.0022226e-5,1.6023748e-5],
};

export function material(sample,direction){
  const [weight,warp,weft,bendWarp,bendWeft]=SAMPLES[sample],along=direction==='warp';
  return {weight,stretchAlong:along?warp:weft,stretchAcross:along?weft:warp,
    bendAlong:(along?bendWarp:bendWeft)??1e-5,bendAcross:(along?bendWeft:bendWarp)??1e-5};
}

// Three readings a constant factor of two apart give the observed order and the h -> 0 limit.
export function richardson(coarse,medium,fine){
  const ratio=(coarse-medium)/(medium-fine);
  if(!(ratio>1))return {order:null,limit:fine};                 // not yet in the asymptotic range
  return {order:Math.log2(ratio),limit:fine+(fine-medium)/(ratio-1)};
}

// The grid factor each cell size needs to bend like the rigidity it is given: a small-deflection
// cantilever, where beam theory is exact, solved on the uncorrected hinges.
// The hinge stiffness ratio grows as 1/h^4, so the step shrinks with the square of the cell.
export function gridFactor(refine,{pattern='app',diagonal='along',across=1}={}){
  const gravity=.05,weight=105.6,rigidity=1e-5,theory=weight/1000*gravity*.08**4/(8*rigidity)*1000;
  const scene=swatchScene({weight,stretchAlong:587.5116,stretchAcross:1035.2515,bendAlong:rigidity,bendAcross:rigidity*across,
    mode:'bend',refine,pattern,diagonal,structuredGrid:1,gravity,damping:6});
  return theory/simulate(scene,{precision:64,seconds:12,substeps:24*refine*refine,iterations:refine>1?4:8,settle:1e-9}).drop;
}

export function reading(sample,direction,mode,refine,pattern='app',options={},scene={}){
  scene=swatchScene({...material(sample,direction),mode,refine,pattern,...scene});
  // Bending is insensitive to the step at 10 mm; finer cells stiffen the membrane, so the step follows them.
  const step=mode==='bend'?{substeps:12*refine*refine,iterations:4}:{};
  const result=simulate(scene,{precision:64,seconds:mode==='bend'?5:2.5,...step,...options});
  return {value:mode==='bend'?result.drop:result.shear,rested:result.rested,
    substeps:options.substeps??step.substeps??scene.fabric_test.numerics.substeps,vertices:scene.vertices.length};
}

if(process.argv[1]?.endsWith('swatch_refinement.mjs')){
  const args=Object.fromEntries(process.argv.slice(2).map(a=>a.replace(/^--/,'').split('=')));
  const levels=(args.levels||'1,2,3,4').split(',').map(Number),modes=(args.mode||'shear,bend').split(',');
  const patterns=(args.patterns||'app,uniform,mirrored').split(','),elastica=fixtures();
  if(modes.includes('factor')){
    // What STRUCTURED_GRID would have to be, and how far the across-strip rigidity moves it.
    for(const [pattern,diagonal] of [['app','along'],['app','blend'],['uniform','blend']])for(const refine of levels.filter(n=>n<4)){
      const row={mode:'factor',pattern,diagonal,cell_mm:+(10/refine).toFixed(1)};
      for(const across of refine===1?[.25,1,4]:[1])row['across/along '+across]=+gridFactor(refine,{pattern,diagonal,across}).toFixed(4);
      console.log(JSON.stringify(row));
    }
  }
  for(const mode of modes.filter(m=>m!=='factor'))for(const sample of Object.keys(SAMPLES))for(const direction of ['warp','weft']){
    // The mirrored and checkerboard splits show whether the 10 mm reading depends on which way cells are cut.
    for(const pattern of sample==='cupro'&&direction==='warp'?patterns:['app']){
      const started=performance.now(),row={mode,fixture:`${sample} / ${direction}`,pattern,mm:{}};
      for(const refine of levels.filter(n=>mode!=='bend'||n!==3)){
        const got=reading(sample,direction,mode,refine,pattern,{},pattern==='app'?{}:{diagonal:'blend',structuredGrid:2.476});
        row.mm[(10/refine).toFixed(1)]=+got.value.toFixed(4);
        if(!got.rested)row.unrested=(row.unrested||[]).concat(refine);
      }
      const [coarse,medium,fine]=[1,2,4].map(n=>row.mm[(10/n).toFixed(1)]);
      if(mode==='bend'){
        const exact=elastica[`${sample} / ${direction} / bend`].fabric_test.expected_drop_mm;
        row.elastica_mm=+exact.toFixed(3);
        row.against_elastica=Object.fromEntries(Object.entries(row.mm).map(([cell,mm])=>[cell,+((mm/exact-1)*100).toFixed(2)+'%']));
      }else if(fine!==undefined){
        const {order,limit}=richardson(coarse,medium,fine);
        Object.assign(row,{order:order&&+order.toFixed(2),converged_mm:+limit.toFixed(4),
          error_at_10mm:+((coarse/limit-1)*100).toFixed(2)+'%',error_at_5mm:+((medium/limit-1)*100).toFixed(2)+'%'});
      }
      row.wall_s=+((performance.now()-started)/1000).toFixed(0);
      console.log(JSON.stringify(row));
    }
  }
}
