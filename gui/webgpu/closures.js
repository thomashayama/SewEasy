// Discrete, two-sided material attachments. No body anchors or front-edge welds.
export const buttonClosureShader = `
struct Closure { a:vec4<u32>, b:vec4<u32>, wa:vec4<f32>, wb:vec4<f32>, material:vec4<f32> }
struct Batch { start:u32, count:u32, pad:vec2<u32> }
@group(0) @binding(2) var<storage,read> closures:array<Closure>;
@group(0) @binding(3) var<storage,read> closed:array<u32>;
@group(1) @binding(0) var<uniform> batch:Batch;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x>=batch.count){return;}
 let c=closures[batch.start+gid.x];if(closed[c.a.w]==0u){return;}
 let a=q[c.a.x];let b=q[c.a.y];let d=q[c.a.z];
 let e=q[c.b.x];let f=q[c.b.y];let g=q[c.b.z];
 let p=a.xyz*c.wa.x+b.xyz*c.wa.y+d.xyz*c.wa.z;
 let h=e.xyz*c.wb.x+f.xyz*c.wb.y+g.xyz*c.wb.z;
 let n=cross(b.xyz-a.xyz,d.xyz-a.xyz);let normal=n/max(length(n),1e-9)*c.wa.w;
 // The button is sewn to A. Its short shank passes through the hole in B.
 // Tangential alignment and finite normal clearance retain the overlap;
 // equal/opposite, inverse-mass-weighted corrections transmit the load.
 let ramp=clamp(params.motion.y/params.contact.w,0.0,1.0);
 // Match the permanent seam assembly schedule. Closing cuff buttons early
 // pulls a flat sleeve beside the arm before its tube has formed around it.
 let error=h-p-normal*c.wb.w-c.material.yzw*(1.0-ramp);
 let denominator=dot(vec3<f32>(a.w,b.w,d.w),c.wa.xyz*c.wa.xyz)+dot(vec3<f32>(e.w,f.w,g.w),c.wb.xyz*c.wb.xyz);
 let alpha=c.material.x/(params.motion.x*params.motion.x);
 let delta=error/max(denominator+alpha,1e-12);
 let maxWeight=max(max(max(a.w*c.wa.x,b.w*c.wa.y),d.w*c.wa.z),max(max(e.w*c.wb.x,f.w*c.wb.y),g.w*c.wb.z));
 // Rebuttoning a wide-open shirt assembles progressively, not in a teleport.
 let correction=delta*min(1.0,.01/max(length(delta)*maxWeight,1e-12));
 q[c.a.x]=vec4<f32>(a.xyz+correction*a.w*c.wa.x,a.w);
 q[c.a.y]=vec4<f32>(b.xyz+correction*b.w*c.wa.y,b.w);
 q[c.a.z]=vec4<f32>(d.xyz+correction*d.w*c.wa.z,d.w);
 q[c.b.x]=vec4<f32>(e.xyz-correction*e.w*c.wb.x,e.w);
 q[c.b.y]=vec4<f32>(f.xyz-correction*f.w*c.wb.y,f.w);
 q[c.b.z]=vec4<f32>(g.xyz-correction*g.w*c.wb.z,g.w);
}`;

export function closureColors(buttons=[]) {
 const colors=[],used=new Map();
 buttons.forEach((button,index)=>{
  if(!button.hole)return;
  const ids=[...button.ids,...button.hole.ids];
  if(new Set(ids).size!==6)throw Error('Button closures require two distinct material triangles');
  let color=0;while(ids.some(i=>used.get(i)?.has(color)))color++;
  while(colors.length<=color)colors.push([]);
  colors[color].push({...button,index});
  for(const i of ids){if(!used.has(i))used.set(i,new Set());used.get(i).add(color);}
 });
 return colors;
}

export function closureRest(button,positions){
 const seat=s=>[0,1,2].map(k=>s.ids.reduce((sum,id,j)=>sum+positions[id][k]*s.weights[j],0));
 const p=seat(button),h=seat(button.hole),[a,b,c]=button.ids.map(i=>positions[i]);
 const u=b.map((v,i)=>v-a[i]),v=c.map((x,i)=>x-a[i]);
 const n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]],length=Math.hypot(...n)||1;
 return h.map((x,i)=>x-p[i]-n[i]/length*button.normal_sign*button.clearance_m);
}
