// Signed dihedral bending across a seam. Seam endpoints remain separate
// particles; their averages define the hinge and share its gradient equally.
export const hingeShader = `
struct Hinge { a:vec4<u32>, b:vec4<u32>, rest:vec4<f32> }
struct Batch { start:u32, count:u32, pad:vec2<u32> }
@group(0) @binding(2) var<storage,read> hinges:array<Hinge>;
@group(1) @binding(0) var<uniform> batch:Batch;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x>=batch.count){return;}
 let h=hinges[batch.start+gid.x];
 let a=q[h.a.x];let b=q[h.a.y];let c=q[h.a.z];
 let d=q[h.b.x];let e=q[h.b.y];let f=q[h.b.z];
 // Do not bend about an artificial midpoint while these panels are apart.
 if(max(distance(a.xyz,d.xyz),distance(b.xyz,e.xyz))>.015){return;}
 let p0=(a.xyz+d.xyz)*.5;let p1=(b.xyz+e.xyz)*.5;
 let edge=p1-p0;let length2=dot(edge,edge);if(length2<1e-10){return;}
 let len=sqrt(length2);let axis=edge/len;
 let n0=cross(edge,c.xyz-p0);let n1=cross(f.xyz-p0,edge);
 let area0=dot(n0,n0);let area1=dot(n1,n1);
 if(min(area0,area1)<1e-14){return;}
 let u=n0/sqrt(area0);let v=n1/sqrt(area1);
 let angle=atan2(dot(cross(u,v),axis),clamp(dot(u,v),-1.0,1.0));
 let delta=angle-h.rest.x;let error=atan2(sin(delta),cos(delta));
 let g2=-len*n0/area0;let g3=-len*n1/area1;
 let t2=dot(c.xyz-p0,edge)/length2;let t3=dot(f.xyz-p0,edge)/length2;
 let g0=-(1.0-t2)*g2-(1.0-t3)*g3;let g1=-t2*g2-t3*g3;
 let denom=.25*(a.w+d.w)*dot(g0,g0)+.25*(b.w+e.w)*dot(g1,g1)+c.w*dot(g2,g2)+f.w*dot(g3,g3);
 let alpha=h.rest.y/(params.motion.x*params.motion.x);
 let lambda=-error/max(denom+alpha,1e-12);
 q[h.a.x]=vec4<f32>(a.xyz+.5*a.w*lambda*g0,a.w);
 q[h.a.y]=vec4<f32>(b.xyz+.5*b.w*lambda*g1,b.w);
 q[h.a.z]=vec4<f32>(c.xyz+c.w*lambda*g2,c.w);
 q[h.b.x]=vec4<f32>(d.xyz+.5*d.w*lambda*g0,d.w);
 q[h.b.y]=vec4<f32>(e.xyz+.5*e.w*lambda*g1,e.w);
 q[h.b.z]=vec4<f32>(f.xyz+f.w*lambda*g3,f.w);
}`;

// Multi-panel junctions must finish sewing as one point, rather than a chain
// of pair constraints that leaves the last pair open. Preserve center of mass
// and share motion history so contact friction cannot pull the copies apart.
export const collarWeldShader = `
@group(0) @binding(2) var<storage,read> ranges:array<vec2<u32>>;
@group(0) @binding(3) var<storage,read> ids:array<u32>;
@group(0) @binding(4) var<storage,read_write> previous:array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x>=arrayLength(&ranges)||params.motion.y<params.contact.w){return;}
 let range=ranges[gid.x];var total=0.0;var position=vec3<f32>(0);var history=vec3<f32>(0);
 for(var j=0u;j<range.y;j++){
  let i=ids[range.x+j];let mass=1.0/max(q[i].w,1e-12);
  total+=mass;position+=mass*q[i].xyz;history+=mass*previous[i].xyz;
 }
 for(var j=0u;j<range.y;j++){
  let i=ids[range.x+j];q[i]=vec4<f32>(position/total,q[i].w);
  previous[i]=vec4<f32>(history/total,previous[i].w);
 }
}`;
