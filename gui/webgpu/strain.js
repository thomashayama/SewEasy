import {placeTrouserLegs} from './trousers.js?v=1';

// Maximum principal stretch of F = Ds * inverse(Dm). Unlike edge lengths,
// this also detects shearing and distortion of thin triangles.
export const strainShader = `
struct Triangle { ids:vec4<u32>, inverse:vec4<f32> }
struct Batch { start:u32, count:u32, pad:vec2<u32> }
@group(0) @binding(2) var<storage,read> triangles:array<Triangle>;
@group(1) @binding(0) var<uniform> batch:Batch;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x>=batch.count){return;}
 let t=triangles[batch.start+gid.x];let a=t.ids.x;let b=t.ids.y;let c=t.ids.z;
 let col0=t.inverse.xz/params.motion.z;let col1=t.inverse.yw;
 // Re-evaluate the principal direction after each projection, including
 // the second direction when both singular values exceed the target.
 for(var iteration=0;iteration<2;iteration++){
  let pa=q[a];let pb=q[b];let pc=q[c];let e1=pb.xyz-pa.xyz;let e2=pc.xyz-pa.xyz;
  let f0=e1*col0.x+e2*col0.y;let f1=e1*col1.x+e2*col1.y;
  let xx=dot(f0,f0);let xy=dot(f0,f1);let yy=dot(f1,f1);
  let eigenvalue=0.5*(xx+yy+sqrt((xx-yy)*(xx-yy)+4.0*xy*xy));
  let sigma=sqrt(max(eigenvalue,0.0));if(sigma<=params.limits.x){break;}
  var v=select(vec2<f32>(0,1),vec2<f32>(1,0),xx>=yy);
  if(abs(xy)>1e-6){v=normalize(vec2<f32>(xy,eigenvalue-xx));}
  let direction=(f0*v.x+f1*v.y)/max(sigma,1e-8);
  let coeff=col0*v.x+col1*v.y;let g0=-coeff.x-coeff.y;
  let denominator=pa.w*g0*g0+pb.w*coeff.x*coeff.x+pc.w*coeff.y*coeff.y;
  let lambda=(sigma-params.limits.x)/max(denominator,1e-12);
  q[a]=vec4<f32>(pa.xyz-direction*(lambda*pa.w*g0),pa.w);
  q[b]=vec4<f32>(pb.xyz-direction*(lambda*pb.w*coeff.x),pb.w);
  q[c]=vec4<f32>(pc.xyz-direction*(lambda*pc.w*coeff.y),pc.w);
 }
}`;

export function strainTopology(scene) {
 const colors=[],used=Array.from({length:scene.vertices.length},()=>new Set());
 for(const ids of scene.faces){
  const [a,b,c]=ids.map(i=>scene.uv[i]);
  const x=b[0]-a[0],y=b[1]-a[1],z=c[0]-a[0],w=c[1]-a[1],det=x*w-y*z;
  if(!Number.isFinite(det)||Math.abs(det)<1e-12)throw Error('Degenerate rest triangle');
  let color=0;while(ids.some(i=>used[i].has(color)))color++;
  while(colors.length<=color)colors.push([]);
  colors[color].push({ids,inverse:[w/det,-z/det,-y/det,x/det]});
  for(const i of ids)used[i].add(color);
 }
 for(const color of colors){const ids=color.flatMap(t=>t.ids);if(new Set(ids).size!==ids.length)throw Error('Triangle color contains shared vertices');}
 return colors;
}

// Exclude every copy of the sewn one-ring, including vertices on the other
// panel. Otherwise particles next to a stitch fight their own cloth surface.
export function contactNeighbors(scene) {
 const rings=new Map();
 for(let i=0;i<scene.vertices.length;i++){
  const id=scene.sewn_ids[i];if(!rings.has(id))rings.set(id,new Set([id]));
  for(const j of scene.neighbors[i])rings.get(id).add(scene.sewn_ids[j]);
 }
 return scene.sewn_ids.map(id=>[...rings.get(id)]);
}

// Propagate tension across a waistband faster than a chain of tiny mesh edges.
// These are maximum-distance material constraints, not pins: folding and rigid
// motion remain free, and every correction is shared by both cloth particles.
export function waistbandTethers(scene) {
 const panels=new Map(),pairs=new Map();
 (scene.vertex_panels||[]).forEach((name,i)=>{
  if(!/(^|__)wb_/.test(name))return;
  if(!panels.has(name))panels.set(name,[]);panels.get(name).push(i);
 });
 for(const ids of panels.values())for(const a of ids)for(const span of [.06,.10]){
  const [x,y]=scene.uv[a];let best=-1,error=Infinity;
  for(const b of ids){
   const dx=scene.uv[b][0]-x,dy=scene.uv[b][1]-y;
   if(dx<span*.65||dx>span*1.35||Math.abs(dy)>.02)continue;
   const score=(dx-span)**2+dy*dy;
   if(score<error){best=b;error=score;}
  }
  if(best>=0)pairs.set(`${a}:${best}`,[a,best,3,scene.uv[best][0]-x,scene.uv[best][1]-y,0,0]);
 }
 const colors=[],used=Array.from({length:scene.vertices.length},()=>new Set());
 for(const c of pairs.values()){
  let color=0;while(used[c[0]].has(color)||used[c[1]].has(color))color++;
  while(colors.length<=color)colors.push([]);colors[color].push(c);
  used[c[0]].add(color);used[c[1]].add(color);
 }
 return colors;
}

export function placePanels(scene) {
 if(scene.garment==='fabric-swatch')return {positions:scene.vertices.map(p=>[...p]),adjustments:[],support:[]};
 // A collared shirt already has a drafted neck height. Raising it can sew
 // the stand around the jaw on larger profiles and trap the whole shirt.
 const lift=scene.garment==='element-top'||scene.hinges?.length?0:.06;
 const positions=scene.vertices.map((p,i)=>{
  const name=scene.vertex_panels?.[i]||'',prefix=name.includes('__')?name.split('__')[0]+'__':'';
  const type=scene.garment_types?.[prefix];
  const height=Object.hasOwn(scene.garment_types||{},prefix)?(['DressShirt','ElementTubeTop'].includes(type)?0:.06):lift;
  return [p[0],p[1]+height,p[2]];
 }),adjustments=[{part:'panels',translation_m:[0,lift,0]}];
 // The upstream flat sleeve placements can close a cuff above the wrist.
 // Align each sleeve/cuff assembly with the mannequin at its cuff X position
 // before sewing. This is a rigid translation, not a pin or a stored drape.
 const names=scene.vertex_panels||[],prefixes=new Set(names.map(name=>name.includes('__')?name.split('__')[0]+'__':''));
 for(const prefix of prefixes)for(const side of ['left','right']){
  const ids=names.flatMap((name,i)=>name.startsWith(`${prefix}sl_${side}_cuff_`)?[i]:[]);
  if(!ids.length)continue;
  const center=[0,1,2].map(axis=>ids.reduce((sum,i)=>sum+positions[i][axis],0)/ids.length);
  const body=scene.body_vertices.filter(p=>Math.abs(p[0]-center[0])<.01&&p[1]>.5);
  if(body.length<8)continue;
  const target=[1,2].map(axis=>(Math.min(...body.map(p=>p[axis]))+Math.max(...body.map(p=>p[axis])))*.5);
  const delta=[0,target[0]-center[1],target[1]-center[2]];
  for(let i=0;i<names.length;i++)if(names[i].startsWith(`${prefix}${side}_sleeve_`)||names[i].startsWith(`${prefix}sl_${side}_cuff_`))positions[i]=positions[i].map((v,j)=>v+delta[j]);
  adjustments.push({prefix,side,translation_m:delta});
 }
 adjustments.push(...placeTrouserLegs(scene,positions));
 const support=[];
 for(const prefix of prefixes)if((scene.garment==='element-top'||scene.garment_types?.[prefix]==='ElementTubeTop')&&scene.vertex_panels){
  const ring=new Map();
  for(const name of ['front','back']){
   const ids=scene.vertex_panels.flatMap((p,i)=>p===prefix+name?[i]:[]),top=Math.max(...ids.map(i=>positions[i][1]));
   for(const i of ids)if(top-positions[i][1]<.001)ring.set(scene.sewn_ids[i],positions[i][1]);
  }
  for(let i=0;i<positions.length;i++)if(ring.has(scene.sewn_ids[i]))support.push([i,ring.get(scene.sewn_ids[i]),0,0]);
 }
 return {positions,adjustments,support};
}
