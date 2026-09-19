// Orthotropic surface energy A/2*(Eu*eu² + Ev*ev² + G*cos(angle)²).
// Eu/Ev/G in N/m, strain dimensionless, XPBD compliance = 1/(A*modulus).
// Independent material axes follow rest UV, not the current world orientation.
export const membraneTypes=`
struct Membrane {ids:vec4<u32>, u:vec4<f32>, v:vec4<f32>, compliance:vec4<f32>}
`;
// Shared verbatim by the reference dispatch and workgroup implementations.
export const membraneSolve=`
fn membrane_solve(index:u32,iteration:u32){
 let m=membranes[index];
 for(var axis=0u;axis<3u;axis++){
  if(m.compliance[axis]<0.0){continue;}
  let a=p[m.ids.x];let b=p[m.ids.y];let c=p[m.ids.z];
  let fu=m.u.x*a.xyz+m.u.y*b.xyz+m.u.z*c.xyz;
  let fv=m.v.x*a.xyz+m.v.y*b.xyz+m.v.z*c.xyz;
  let lu=length(fu);let lv=length(fv);if(min(lu,lv)<1e-8){continue;}
  var error=lu-1.0;var gu=fu/lu;var gv=vec3<f32>(0);
  if(axis==1u){error=lv-1.0;gu=vec3<f32>(0);gv=fv/lv;}
  if(axis==2u){error=dot(fu,fv)/(lu*lv);gu=fv/(lu*lv)-error*fu/(lu*lu);gv=fu/(lu*lv)-error*fv/(lv*lv);}
  let g0=m.u.x*gu+m.v.x*gv;let g1=m.u.y*gu+m.v.y*gv;let g2=m.u.z*gu+m.v.z*gv;
  let denom=a.w*dot(g0,g0)+b.w*dot(g1,g1)+c.w*dot(g2,g2);
  let alpha=m.compliance[axis]/(params.motion.x*params.motion.x);
  let accumulated=select(membraneMultipliers[index][axis],0.0,iteration==0u);
  let lambda=-(error+alpha*accumulated)/max(denom+alpha,1e-12);
  membraneMultipliers[index][axis]=accumulated+lambda;
  p[m.ids.x]=vec4<f32>(a.xyz+a.w*lambda*g0,a.w);
  p[m.ids.y]=vec4<f32>(b.xyz+b.w*lambda*g1,b.w);
  p[m.ids.z]=vec4<f32>(c.xyz+c.w*lambda*g2,c.w);
 }
}
`;
export const membraneShader=membraneTypes+`
struct Params {motion:vec4<f32>,material:vec4<f32>,counts:vec4<u32>,contact:vec4<f32>,limits:vec4<f32>}
struct Batch {start:u32,count:u32,iteration:u32,pad:u32}
@group(0) @binding(0) var<storage,read_write> p:array<vec4<f32>>;
@group(0) @binding(1) var<uniform> params:Params;
@group(0) @binding(2) var<storage,read> membranes:array<Membrane>;
@group(0) @binding(3) var<storage,read_write> membraneMultipliers:array<vec4<f32>>;
@group(1) @binding(0) var<uniform> batch:Batch;
`+membraneSolve+`
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x<batch.count){membrane_solve(batch.start+gid.x,batch.iteration);}
}`;
