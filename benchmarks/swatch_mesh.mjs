// The clamped strip of webapp/fabric_swatch.py at any cell size, for mesh-refinement studies.
//
// The application's swatch is fixed at a 10 mm grid (50 vertices, one GPU dispatch).
// This repeats swatch_scene() and apply_material() step for step, so that at
// refine = 1 it equals the committed application scenes (test_swatch_convergence
// checks that) and at refine = n it is the same strip on cells of 10/n mm.
//
//   pattern 'app'       the application's checkerboard of the two diagonals, mirror-symmetric about the strip
//   pattern 'uniform'   every cell split the same way, as the application did until the study found it twists
//   pattern 'mirrored'  every cell split along the other diagonal
//   diagonal 'along'    (the application) diagonal hinges take the along-strip rigidity; 'blend' averages both
export const STRUCTURED_GRID=2.431,FRAME=1/60,STIFFNESS_RATIO=1,LOADED_ITERATIONS=4;

// webapp/fabric_swatch.colored: greedy colouring in stored order, so solve order matches too.
function colored(items,vertexCount,ids){
  const used=Array.from({length:vertexCount},()=>new Set()),colours=[];
  for(const item of items){
    const vertices=ids(item),forbidden=new Set(vertices.flatMap(i=>[...used[i]]));
    let colour=0;while(forbidden.has(colour))colour++;
    while(colours.length<=colour)colours.push([]);
    colours[colour].push(item);
    for(const i of vertices)used[i].add(colour);
  }
  const ordered=[],batches=[];
  for(const group of colours){batches.push([ordered.length,group.length]);ordered.push(...group);}
  return [ordered,batches];
}

export function swatchScene({weight,stretchAlong=1000,stretchAcross=1000,shear=100,bendAlong=1e-5,bendAcross=1e-5,
    damping=14,mode='bend',refine=1,pattern='app',structuredGrid=STRUCTURED_GRID,clampHinge=2,gravity=9.81,diagonal='along'}){
  const columns=9*refine+1,rows=4*refine+1,step=.01/refine,width=.04,height=.12;
  const uv=[],points=[];
  for(let x=0;x<columns;x++)for(let z=0;z<rows;z++){
    const u=(x-refine)*step,v=z*width/(rows-1);
    uv.push([u,v]);points.push([u,height,v-width/2]);
  }
  const faces=[];
  for(let x=0;x<columns-1;x++)for(let z=0;z<rows-1;z++){
    const a=x*rows+z,b=(x+1)*rows+z,c=x*rows+z+1,d=(x+1)*rows+z+1;
    const other=pattern==='mirrored'||(pattern==='app'&&(x+z)%2===1);
    if(other)faces.push([a,c,d],[a,d,b]);else faces.push([a,c,b],[c,d,b]);
  }
  // Lumped mass: a third of each triangle to each corner (seweasy/meshgen/webgpu.build_scene).
  const mass=new Float64Array(points.length);
  const membranes=faces.map(ids=>{
    const [a,b,c]=ids.map(i=>uv[i]),m00=b[0]-a[0],m10=b[1]-a[1],m01=c[0]-a[0],m11=c[1]-a[1];
    const det=m00*m11-m01*m10,i00=m11/det,i01=-m01/det,i10=-m10/det,i11=m00/det,area=Math.abs(det)/2;
    for(const i of ids)mass[i]+=area*weight/1000/3;
    // Zero disables a force; a missing value was already replaced by its stated default.
    const compliance=[stretchAlong,stretchAcross,shear].map(k=>k>0?1/(area*k):-1);
    return {ids,u:[-i00-i10,i00,i10],v:[-i01-i11,i01,i11],compliance};
  });
  const pinned=(refine+1)*rows,pins=[...Array(pinned).keys()];
  const inverseMass=[...mass].map((m,i)=>i<pinned?0:1/m);

  const edges=new Map();
  for(const [a,b,c] of faces)for(const [u,v,opposite] of [[a,b,c],[b,c,a],[c,a,b]]){
    const key=Math.min(u,v)+','+Math.max(u,v);
    if(!edges.has(key))edges.set(key,[]);
    edges.get(key).push([u,v,opposite]);
  }
  const sub=(p,q)=>[p[0]-q[0],p[1]-q[1],p[2]-q[2]],norm=p=>Math.hypot(...p);
  const cross=(p,q)=>[p[1]*q[2]-p[2]*q[1],p[2]*q[0]-p[0]*q[2],p[0]*q[1]-p[1]*q[0]];
  const hinges=[];
  for(const sides of edges.values()){
    if(sides.length!==2)continue;
    const [a,b,c]=sides[0],d=sides[1][2],edge=sub(points[b],points[a]);
    const area=(norm(cross(edge,sub(points[c],points[a])))+norm(cross(sub(points[d],points[a]),edge)))/2;
    const onClampLine=Math.abs(points[a][0])<1e-12&&Math.abs(points[b][0])<1e-12;
    const factor=3*(edge[0]**2+edge[1]**2+edge[2]**2)/area/structuredGrid*(onClampLine?clampHinge:1);
    const direction=[uv[b][0]-uv[a][0],uv[b][1]-uv[a][1]];
    const fraction=direction[1]**2/(direction[0]**2+direction[1]**2);
    const rigidity=diagonal==='along'&&fraction>0?bendAlong:fraction*bendAlong+(1-fraction)*bendAcross;
    hinges.push({ids:[a,b,c,d],angle:0,compliance:rigidity>0?1/(rigidity*factor):-1});
  }

  const [orderedMembranes,membraneBatches]=colored(membranes,points.length,m=>m.ids);
  const [orderedHinges,hingeBatches]=colored(hinges,points.length,h=>h.ids);
  const tip=[...Array(rows).keys()].map(z=>(columns-1)*rows+z),spacing=width/(rows-1);
  const traction=mode==='stretch'?25:mode==='shear'?5:0,forces=points.map(()=>[0,0,0]);
  tip.forEach((vertex,index)=>{forces[vertex][mode==='stretch'?0:2]=traction*spacing*(index===0||index===rows-1?.5:1);});

  // webapp/fabric_swatch.loaded_numerics, without its ceiling: a study must converge wherever it lands.
  let worst=0;
  for(const m of orderedMembranes){
    const w=m.ids.map(i=>inverseMass[i]);
    [m.u.map(x=>x*x),m.v.map(x=>x*x),m.u.map((x,k)=>x*x+m.v[k]**2)].forEach((gradient,axis)=>{
      if(m.compliance[axis]>0)worst=Math.max(worst,FRAME**2*gradient.reduce((s,g,k)=>s+g*w[k],0)/m.compliance[axis]);
    });
  }
  const needed=Math.ceil(Math.sqrt(worst/STIFFNESS_RATIO));
  return {vertices:points,inverse_mass:inverseMass,membranes:orderedMembranes,membrane_batches:membraneBatches,
    interior_hinges:orderedHinges,interior_hinge_batches:hingeBatches,external_forces:forces,
    swatch:{pins,tip,length_m:.08,width_m:width,height_m:height},
    fabric_test:{mode,traction_n_m:traction,damping,gravity:mode==='bend'?gravity:0,
      expected_extension_percent:mode==='stretch'?traction/stretchAlong*100:null,
      numerics:{substeps:Math.max(needed,96),iterations:LOADED_ITERATIONS,needed,stiffness_ratio:worst/Math.max(needed,96)**2}}};
}
