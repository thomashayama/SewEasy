// The diagnostic mesh fits in one GPU workgroup. Keep intermediate positions
// in workgroup memory instead of issuing thousands of tiny compute dispatches.
// Same colored distance/dihedral XPBD equations as Cloth's reference path.
import {membraneTypes,membraneSolve} from './membrane.js?v=1';
export const swatchShader=membraneTypes+`
struct Params { motion:vec4<f32>, material:vec4<f32>, counts:vec4<u32>, contact:vec4<f32>, limits:vec4<f32> }
struct Edge { ids:vec4<u32>, rest:vec4<f32> }
struct Hinge { ids:vec4<u32>, rest:vec4<f32> }
@group(0) @binding(0) var<storage,read_write> q:array<vec4<f32>>;
@group(0) @binding(1) var<uniform> params:Params;
@group(0) @binding(2) var<storage,read_write> previous:array<vec4<f32>>;
@group(0) @binding(3) var<storage,read_write> velocity:array<vec4<f32>>;
@group(0) @binding(4) var<storage,read> edges:array<Edge>;
@group(0) @binding(5) var<storage,read> batches:array<vec4<u32>>;
@group(0) @binding(6) var<storage,read> hinges:array<Hinge>;
@group(0) @binding(7) var<storage,read> membranes:array<Membrane>;
@group(0) @binding(8) var<storage,read> appliedForces:array<vec4<f32>>;
var<workgroup> p:array<vec4<f32>,128>;
var<workgroup> old:array<vec3<f32>,128>;
var<workgroup> v:array<vec3<f32>,128>;
var<workgroup> multipliers:array<f32,256>;
var<workgroup> membraneMultipliers:array<vec4<f32>,256>;
`+membraneSolve+`
fn edge_solve(index:u32){
 let e=edges[index];let a=p[e.ids.x];let b=p[e.ids.y];let delta=a.xyz-b.xyz;
 let len=length(delta);if(len<1e-9||a.w+b.w==0.0){return;}
 let rest=length(e.rest.xy);let correction=-(len-rest)*delta/(len*(a.w+b.w));
 p[e.ids.x]=vec4<f32>(a.xyz+a.w*correction,a.w);
 p[e.ids.y]=vec4<f32>(b.xyz-b.w*correction,b.w);
}
fn bend_solve(index:u32,iteration:u32){
 let h=hinges[index];if(h.rest.y<0.0){return;}let a=p[h.ids.x];let b=p[h.ids.y];let c=p[h.ids.z];let d=p[h.ids.w];
 let edge=b.xyz-a.xyz;let length2=dot(edge,edge);if(length2<1e-12){return;}
 let len=sqrt(length2);let n0=cross(edge,c.xyz-a.xyz);let n1=cross(d.xyz-a.xyz,edge);
 let area0=dot(n0,n0);let area1=dot(n1,n1);if(min(area0,area1)<1e-18){return;}
 let u=n0/sqrt(area0);let normal=n1/sqrt(area1);
 let delta=atan2(dot(cross(u,normal),edge/len),clamp(dot(u,normal),-1.0,1.0))-h.rest.x;
 let error=atan2(sin(delta),cos(delta));
 let g2=-len*n0/area0;let g3=-len*n1/area1;
 let t2=dot(c.xyz-a.xyz,edge)/length2;let t3=dot(d.xyz-a.xyz,edge)/length2;
 let g0=-(1.0-t2)*g2-(1.0-t3)*g3;let g1=-t2*g2-t3*g3;
 let denom=a.w*dot(g0,g0)+b.w*dot(g1,g1)+c.w*dot(g2,g2)+d.w*dot(g3,g3);
 let alpha=h.rest.y/(params.motion.x*params.motion.x);
 let accumulated=select(multipliers[index],0.0,iteration==0u);
 let lambda=-(error+alpha*accumulated)/max(denom+alpha,1e-12);
 multipliers[index]=accumulated+lambda;
 p[h.ids.x]=vec4<f32>(a.xyz+a.w*lambda*g0,a.w);
 p[h.ids.y]=vec4<f32>(b.xyz+b.w*lambda*g1,b.w);
 p[h.ids.z]=vec4<f32>(c.xyz+c.w*lambda*g2,c.w);
 p[h.ids.w]=vec4<f32>(d.xyz+d.w*lambda*g3,d.w);
}
@compute @workgroup_size(128) fn main(@builtin(local_invocation_index) i:u32){
 if(i<params.counts.x){p[i]=q[i];v[i]=velocity[i].xyz;}
 workgroupBarrier();
 let dt=params.motion.x;let ramp=clamp((params.motion.y-params.contact.w)/.3,0.0,1.0);
 for(var step=0u;step<params.counts.y;step++){
  if(i<params.counts.x){
   old[i]=p[i].xyz;
   if(p[i].w==0.0){v[i]=vec3<f32>(0);}else{
    v[i]+=(vec3<f32>(0,-params.contact.x,0)+appliedForces[i].xyz*p[i].w)*ramp*dt;
    p[i]=vec4<f32>(p[i].xyz+v[i]*dt,p[i].w);
   }
  }
  workgroupBarrier();
  for(var iteration=0u;iteration<u32(params.limits.y);iteration++){
   for(var b=0u;b<arrayLength(&batches);b++){
    let batch=batches[b];
    if(i<batch.y){if(batch.z==0u){edge_solve(batch.x+i);}else if(batch.z==2u){membrane_solve(batch.x+i,iteration);}else{bend_solve(batch.x+i,iteration);}}
    workgroupBarrier();
   }
  }
  if(i<params.counts.x){v[i]=(p[i].xyz-old[i])/dt*exp(-params.contact.y*dt);v[i]*=min(1.0,3.0/max(length(v[i]),1e-8));}
  workgroupBarrier();
 }
 if(i<params.counts.x){q[i]=p[i];previous[i]=vec4<f32>(old[i],p[i].w);velocity[i]=vec4<f32>(v[i],0);}
}`;
