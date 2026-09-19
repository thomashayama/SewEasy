// SewEasy browser cloth experiment. Original WGSL implementation of small-step
// XPBD distance constraints; see README.md for paper references and limits.
import {strainShader, strainTopology, contactNeighbors, placePanels, waistbandTethers} from './strain.js?v=15';
import {hingeShader, interiorHingeShader, collarWeldShader} from './bending.js?v=3';
import {MannequinMotion,bodyMotionWGSL} from './motion.js?v=2';
import {buttonClosureShader,closureColors,closureRest} from './closures.js?v=2';
import {swatchShader} from './swatch_solver.js?v=1';
const common = `
struct Params { motion: vec4<f32>, material: vec4<f32>, counts: vec4<u32>, contact: vec4<f32>, limits:vec4<f32> }
@group(0) @binding(0) var<storage, read_write> q: array<vec4<f32>>;
@group(0) @binding(1) var<uniform> params: Params;
`;

const integrate = common + `
@group(0) @binding(2) var<storage, read_write> previous: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> velocity: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i = gid.x; if (i >= params.counts.x) { return; }
 let p = q[i]; previous[i] = p;
 if(p.w==0.0){velocity[i]=vec4<f32>(0);return;}
 let dt = params.motion.x;
 let ramp = clamp((params.motion.y - params.contact.w) / 0.3, 0.0, 1.0);
 let wind = params.motion.w * sin(params.motion.y * 2.5 + p.y * 4.0);
 let v = velocity[i].xyz + vec3<f32>(wind, -params.contact.x * ramp, wind * 0.4) * dt;
 q[i] = vec4<f32>(p.xyz + v * dt, p.w);
 velocity[i] = vec4<f32>(v, 0.0);
}`;

const constraints = common + `
struct Constraint { ids: vec4<u32>, rest: vec4<f32> }
struct Batch { start: u32, count: u32, pad: vec2<u32> }
@group(0) @binding(2) var<storage, read> edges: array<Constraint>;
@group(1) @binding(0) var<uniform> batch: Batch;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 if (gid.x >= batch.count) { return; }
 let c = edges[batch.start + gid.x];
 let a = c.ids.x; let b = c.ids.y;
 let pa = q[a]; let pb = q[b]; let d = pa.xyz - pb.xyz;
 if(pa.w+pb.w==0.0){return;}
 let length_now = length(d); if (length_now < 1e-9) { return; }
 var rest = length(vec2<f32>(c.rest.x * params.motion.z, c.rest.y));
 var compliance = params.material.x;
 if (c.ids.z == 1u) { compliance = params.material.y * c.rest.z; }
 if (c.ids.z == 2u) {
   rest = c.rest.w * (1.0 - clamp(params.motion.y / params.contact.w, 0.0, 1.0));
   compliance = params.material.z;
 }
 if (c.ids.z == 3u) {
   rest *= params.limits.x;
   if (length_now <= rest) { return; }
   compliance = 0.0;
 }
 let alpha = compliance / (params.motion.x * params.motion.x);
 let lambda = -(length_now - rest) / (pa.w + pb.w + alpha);
 let correction = lambda * d / length_now;
 q[a] = vec4<f32>(pa.xyz + pa.w * correction, pa.w);
 q[b] = vec4<f32>(pb.xyz - pb.w * correction, pb.w);
}`;

const bodyGeometry = `
struct Node { lo: vec4<f32>, hi: vec4<f32>, link: vec4<u32> }
@group(0) @binding(2) var<storage, read> nodes: array<Node>;
@group(0) @binding(3) var<storage, read> body: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read> faces: array<u32>;
@group(0) @binding(5) var<storage, read> normals: array<vec4<f32>>;
// Closest point in barycentric coordinates, including edges and vertices.
fn barycentric(p: vec3<f32>, a: vec3<f32>, b: vec3<f32>, c: vec3<f32>) -> vec3<f32> {
 let ab=b-a; let ac=c-a; let ap=p-a; let d1=dot(ab,ap); let d2=dot(ac,ap);
 if (d1<=0.0 && d2<=0.0) {return vec3<f32>(1,0,0);}
 let bp=p-b; let d3=dot(ab,bp); let d4=dot(ac,bp);
 if (d3>=0.0 && d4<=d3) {return vec3<f32>(0,1,0);}
 let vc=d1*d4-d3*d2;
 if (vc<=0.0 && d1>=0.0 && d3<=0.0) {let v=d1/(d1-d3);return vec3<f32>(1-v,v,0);}
 let cp=p-c; let d5=dot(ab,cp); let d6=dot(ac,cp);
 if (d6>=0.0 && d5<=d6) {return vec3<f32>(0,0,1);}
 let vb=d5*d2-d1*d6;
 if (vb<=0.0 && d2>=0.0 && d6<=0.0) {let w=d2/(d2-d6);return vec3<f32>(1-w,0,w);}
 let va=d3*d6-d5*d4;
 if (va<=0.0 && d4-d3>=0.0 && d5-d6>=0.0) {let w=(d4-d3)/((d4-d3)+(d5-d6));return vec3<f32>(0,1-w,w);}
 let inv=1.0/max(va+vb+vc,1e-20);let v=vb*inv;let w=vc*inv;return vec3<f32>(1-v-w,v,w);
}
fn body_value(p: vec3<f32>) -> vec4<f32> {
 var best=1e10;var closest=vec3<f32>(0);var normal=vec3<f32>(0,1,0);
 var node=0u;
 loop {
   if (node>=arrayLength(&nodes)) {break;}
   let n=nodes[node];let delta=max(max(n.lo.xyz-p,p-n.hi.xyz),vec3<f32>(0));
   if (dot(delta,delta)>best) {node=n.link.x;continue;}
   for (var t=0u;t<n.link.z;t++) {
     let fi=(n.link.y+t)*3u;let ia=faces[fi];let ib=faces[fi+1u];let ic=faces[fi+2u];
     let a=body[ia].xyz;let b=body[ib].xyz;let c=body[ic].xyz;
     let bary=barycentric(p,a,b,c);let candidate=a*bary.x+b*bary.y+c*bary.z;
     let distance=dot(p-candidate,p-candidate);
     if (distance<best) {
       best=distance;closest=candidate;
       normal=normalize(normals[ia].xyz*bary.x+normals[ib].xyz*bary.y+normals[ic].xyz*bary.z);
     }
   }
   node++;
 }
 let signed=select(-sqrt(best),sqrt(best),dot(p-closest,normal)>=0.0);
 return vec4<f32>(normal,signed);
}`;
const bodyCollision = common + bodyGeometry + bodyMotionWGSL + `
@group(0) @binding(7) var<uniform> motion:BodyMotion;
@group(0) @binding(6) var<storage, read_write> previous: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 let p=q[i].xyz;let hit=body_value(body_local(p));let normal=body_normal(hit.xyz);let signed=hit.w;
 let depth=params.material.w-signed;
 if (depth>0.0) {
   let push=min(depth,0.04);let corrected=p+normal*push;
   let movement=corrected-previous[i].xyz-body_movement(corrected);
   let tangent=movement-normal*dot(movement,normal);
   let friction=min(1.0,params.contact.z*push/max(length(tangent),1e-8));
   q[i]=vec4<f32>(corrected-tangent*friction,q[i].w);
 }
 if (q[i].y<0.004) {q[i].y=0.004;}
}`;

const gridType=`struct Grid { lo:vec4<f32>, step:vec4<f32>, counts:vec4<u32> }`;
const buildSdf = bodyGeometry + gridType + `
@group(0) @binding(7) var<uniform> grid:Grid;
@group(0) @binding(8) var<storage,read_write> field:array<f32>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 let i=gid.x+grid.counts.w;let size=grid.counts.xyz;if(i>=size.x*size.y*size.z){return;}
 let index=vec3<u32>(i%size.x,(i/size.x)%size.y,i/(size.x*size.y));
 field[i]=body_value(grid.lo.xyz+vec3<f32>(index)*grid.step.xyz).w;
}`;
const sdfFunctions = `
fn voxel(p:vec3<u32>)->f32{return field[p.x+grid.counts.x*(p.y+grid.counts.y*p.z)];}
fn sample_sdf(p:vec3<f32>)->f32{
 let v=clamp((p-grid.lo.xyz)/grid.step.xyz,vec3<f32>(0),vec3<f32>(grid.counts.xyz)-vec3<f32>(1.001));
 let a=vec3<u32>(floor(v));let f=fract(v);
 let c00=mix(voxel(a),voxel(a+vec3<u32>(1,0,0)),f.x);
 let c10=mix(voxel(a+vec3<u32>(0,1,0)),voxel(a+vec3<u32>(1,1,0)),f.x);
 let c01=mix(voxel(a+vec3<u32>(0,0,1)),voxel(a+vec3<u32>(1,0,1)),f.x);
 let c11=mix(voxel(a+vec3<u32>(0,1,1)),voxel(a+vec3<u32>(1,1,1)),f.x);
 return mix(mix(c00,c10,f.y),mix(c01,c11,f.y),f.z);
}
fn sdf_normal(p:vec3<f32>)->vec3<f32>{
 let h=grid.step.xyz*0.5;
 let gradient=vec3<f32>(sample_sdf(p+vec3<f32>(h.x,0,0))-sample_sdf(p-vec3<f32>(h.x,0,0)),sample_sdf(p+vec3<f32>(0,h.y,0))-sample_sdf(p-vec3<f32>(0,h.y,0)),sample_sdf(p+vec3<f32>(0,0,h.z))-sample_sdf(p-vec3<f32>(0,0,h.z)))/grid.step.xyz;
 return gradient/max(length(gradient),1e-8);
}
fn in_grid(p:vec3<f32>)->bool{let v=(p-grid.lo.xyz)/grid.step.xyz;return all(v>=vec3<f32>(1))&&all(v<vec3<f32>(grid.counts.xyz)-vec3<f32>(2));}
`;
const sdfCollision = common + gridType + bodyMotionWGSL + `
@group(0) @binding(2) var<storage,read> field:array<f32>;
@group(0) @binding(3) var<uniform> grid:Grid;
@group(0) @binding(4) var<storage,read_write> previous:array<vec4<f32>>;
@group(0) @binding(5) var<uniform> motion:BodyMotion;
` + sdfFunctions + `
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 let i=gid.x;if(i>=params.counts.x){return;}let p=q[i].xyz;
 let local=body_local(p);let v=(local-grid.lo.xyz)/grid.step.xyz;
 if(all(v>=vec3<f32>(1)) && all(v<vec3<f32>(grid.counts.xyz)-vec3<f32>(2))){
  let depth=params.material.w-sample_sdf(local);
  if(depth>0.0){
   let normal=body_normal(sdf_normal(local));let push=min(depth,0.04);let corrected=p+normal*push;
   let movement=corrected-previous[i].xyz-body_movement(corrected);let tangent=movement-normal*dot(movement,normal);
   let friction=min(1.0,params.contact.z*push/max(length(tangent),1e-8));
   q[i]=vec4<f32>(corrected-tangent*friction,q[i].w);
  }
 }
 if(q[i].y<0.004){q[i].y=0.004;}
}`;

// Resolve cloth surface samples, not just vertices: a triangle can span an
// arm while all three endpoints are outside. Coloring makes these writes safe.
const surfaceCollision=common+gridType+bodyMotionWGSL+`
struct Triangle { ids:vec4<u32>, inverse:vec4<f32> }
struct Batch { start:u32, count:u32, pad:vec2<u32> }
@group(0) @binding(2) var<storage,read> triangles:array<Triangle>;
@group(0) @binding(3) var<storage,read> field:array<f32>;
@group(0) @binding(4) var<uniform> grid:Grid;
@group(0) @binding(5) var<uniform> motion:BodyMotion;
@group(1) @binding(0) var<uniform> batch:Batch;
`+sdfFunctions+`
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x>=batch.count){return;}let t=triangles[batch.start+gid.x];
 let samples=array<vec3<f32>,4>(vec3<f32>(.5,.5,0),vec3<f32>(.5,0,.5),vec3<f32>(0,.5,.5),vec3<f32>(1.0/3.0));
 for(var j=0u;j<4u;j++){
  let w=samples[j];let a=q[t.ids.x];let b=q[t.ids.y];let c=q[t.ids.z];let p=a.xyz*w.x+b.xyz*w.y+c.xyz*w.z;
  let local=body_local(p);if(!in_grid(local)){continue;}let depth=params.material.w-sample_sdf(local);if(depth<=0.0){continue;}
  let normal=body_normal(sdf_normal(local));let denom=a.w*w.x*w.x+b.w*w.y*w.y+c.w*w.z*w.z;
  let correction=normal*min(depth,.02)/max(denom,1e-9);
  q[t.ids.x]=vec4<f32>(a.xyz+correction*(a.w*w.x),a.w);
  q[t.ids.y]=vec4<f32>(b.xyz+correction*(b.w*w.y),b.w);
  q[t.ids.z]=vec4<f32>(c.xyz+correction*(c.w*w.z),c.w);
 }
}`;

const hashCommon = common + `
@group(0) @binding(2) var<storage, read_write> heads: array<atomic<i32>>;
@group(0) @binding(3) var<storage, read_write> next: array<i32>;
fn cell(p: vec3<f32>) -> vec3<i32> {return vec3<i32>(floor(p/(params.material.w*2.0)));}
fn hash(c: vec3<i32>) -> u32 {
 let v=bitcast<vec3<u32>>(c);return ((v.x*73856093u)^(v.y*19349663u)^(v.z*83492791u))%(params.counts.w);
}
`;
const clearHash = hashCommon + `
@compute @workgroup_size(256) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 if (gid.x<params.counts.w) {atomicStore(&heads[gid.x],-1);}
}`;
const fillHash = hashCommon + `
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 next[i]=atomicExchange(&heads[hash(cell(q[i].xyz))],i32(i));
}`;
const selfCollision = hashCommon + `
@group(0) @binding(4) var<storage, read_write> corrected: array<vec4<f32>>;
@group(0) @binding(5) var<storage, read> sewn: array<u32>;
@group(0) @binding(6) var<storage, read> ranges: array<vec2<u32>>;
@group(0) @binding(7) var<storage, read> adjacent: array<u32>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 let p=q[i];let center=cell(p.xyz);let thickness=params.material.w*2.0;
 var correction=vec3<f32>(0);var count=0.0;
 for(var x=-1;x<=1;x++){for(var y=-1;y<=1;y++){for(var z=-1;z<=1;z++){
   let neighbor_cell=center+vec3<i32>(x,y,z);var j=atomicLoad(&heads[hash(neighbor_cell)]);
   loop {
     if(j<0){break;}
     let id=u32(j);j=next[id];
     if(id==i || sewn[id]==sewn[i] || any(cell(q[id].xyz)!=neighbor_cell)){continue;}
     let d=p.xyz-q[id].xyz;let l=length(d);if(l>=thickness || l<1e-7){continue;}
     var neighbor=false;let r=ranges[i];
     for(var k=0u;k<r.y;k++){if(adjacent[r.x+k]==sewn[id]){neighbor=true;break;}}
     if(neighbor){continue;}
     correction+=(d/l)*(thickness-l)*p.w/(p.w+q[id].w);count+=1.0;
   }
 }}}
 corrected[i]=vec4<f32>(p.xyz+correction/max(count,1.0),p.w);
}`;
const applySelf = common + `
@group(0) @binding(2) var<storage, read> corrected: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i<params.counts.x){q[i]=corrected[i];}
}`;
const updateVelocity = common + `
@group(0) @binding(2) var<storage, read> previous: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> velocity: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 var v=(q[i].xyz-previous[i].xyz)/params.motion.x;
 v*=exp(-params.contact.y*params.motion.x);
 v*=min(1.0,3.0/max(length(v),1e-8));
 velocity[i]=vec4<f32>(v,0.0);
}`;
const necklineSupport=common+`
@group(0) @binding(2) var<storage,read> targets:array<vec4<f32>>;
@group(0) @binding(3) var<storage,read_write> previous:array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 if(gid.x>=arrayLength(&targets)){return;}let t=targets[gid.x];let i=u32(t.x);
 q[i].y=t.y;previous[i].y=t.y;
}`;
const computeNormals = common + `
@group(0) @binding(2) var<storage, read> faces: array<u32>;
@group(0) @binding(3) var<storage, read> ranges: array<vec2<u32>>;
@group(0) @binding(4) var<storage, read> adjacent: array<u32>;
@group(0) @binding(5) var<storage, read_write> normals: array<vec4<f32>>;
@group(0) @binding(6) var<storage, read> uv:array<vec2<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 var n=vec3<f32>(0);var strain=1.0;let r=ranges[i];
 for(var j=0u;j<r.y;j++){
   let f=adjacent[r.x+j]*3u;let a=q[faces[f]].xyz;let b=q[faces[f+1u]].xyz;let c=q[faces[f+2u]].xyz;
   n+=cross(b-a,c-a);
   let v0=uv[faces[f]];let v1=uv[faces[f+1u]]-v0;let v2=uv[faces[f+2u]]-v0;
   let det=v1.x*v2.y-v2.x*v1.y;
   let f0=((b-a)*v2.y-(c-a)*v1.y)/(det*params.motion.z);let f1=((c-a)*v1.x-(b-a)*v2.x)/det;
   let xx=dot(f0,f0);let xy=dot(f0,f1);let yy=dot(f1,f1);
   strain=max(strain,sqrt(max(0.0,.5*(xx+yy+sqrt((xx-yy)*(xx-yy)+4.0*xy*xy)))));
 }
 normals[i]=vec4<f32>(n/max(length(n),1e-12),strain);
}`;

export function buffer(device, array, usage, label='') {
  const result=device.createBuffer({size:Math.max(16,(array.byteLength+3)&~3),usage:usage|GPUBufferUsage.COPY_DST,label});
  device.queue.writeBuffer(result,0,array);return result;
}
export function vec4(values, w=0) {return new Float32Array(values.flatMap((p,i)=>[...p,Array.isArray(w)||ArrayBuffer.isView(w)?w[i]:w]));}
function csr(rows) {const values=[],ranges=[];for(const row of rows){ranges.push(values.length,row.length);values.push(...row);}return [new Uint32Array(ranges),new Uint32Array(values)];}

export class Cloth {
  static async create(device, scene,progress=()=>{},settings={}) {const c=new Cloth(device,scene);Object.assign(c.settings,settings);c.progress=progress;try{await c.initialize();return c;}catch(error){c.destroy();throw error;}}
  constructor(device,scene) {
    this.device=device;this.scene=scene;this.n=scene.vertices.length;this.frame=0;this.owned=[];
    this.time=0;this.frameDt=1/60;
    this.motion=new MannequinMotion(scene.body_vertices);
    const placement=placePanels(scene);this.initialPositions=placement.positions;this.placement=placement.adjustments;this.supportTargets=placement.support;
    this.settings={substeps:12,width:1,wind:0,stretch:0.00001,bend:0.03,seam:0.0000001,thickness:0.004,gravity:9.81,damping:2,friction:0.4,sewDuration:1.6,selfCollision:true,bodyCollision:true,bodyMethod:'sdf',strainLimit:1.02,strainPasses:2,surfaceContact:true};
    this.settings.holdNeckline=this.supportTargets.length>0;
    this.buttonStates=Uint32Array.from(scene.buttons||[],b=>b.closed!==false?1:0);
  }
  make(array,usage=GPUBufferUsage.STORAGE,label=''){const b=buffer(this.device,array,usage,label);this.owned.push(b);return b;}
  async pipeline(code,resources,label,motionBinding=null){
    const module=this.device.createShaderModule({code,label});
    const info=await module.getCompilationInfo();const errors=info.messages.filter(m=>m.type==='error');
    if(errors.length)throw Error(label+': '+errors.map(m=>`${m.lineNum}: ${m.message}`).join('\n'));
    const pipeline=await this.device.createComputePipelineAsync({layout:'auto',compute:{module,entryPoint:'main'},label});
    const entries=resources.map(([binding,b])=>({binding,resource:{buffer:b}}));
    const moving=motionBinding===null?null:Array.from({length:64},(_,step)=>this.device.createBindGroup({layout:pipeline.getBindGroupLayout(0),entries:[...entries,{binding:motionBinding,resource:{buffer:this.motionBuffer,offset:step*this.motionStride,size:32}}]}));
    const bind=moving?.[0]||this.device.createBindGroup({layout:pipeline.getBindGroupLayout(0),entries});
    return {pipeline,bind,label,moving};
  }
  async initialize(){
    const d=this.device,s=this.scene;
    const placedConstraints=s.constraints.map(c=>c[2]===2?
      [...c.slice(0,6),Math.hypot(...this.initialPositions[c[0]].map((v,a)=>v-this.initialPositions[c[1]][a]))]:c);
    this.motionStride=Math.max(256,d.limits.minUniformBufferOffsetAlignment);
    this.motionRaw=new Float32Array(this.motionStride/4*64);
    this.motionBuffer=this.make(this.motionRaw,GPUBufferUsage.UNIFORM);this.writeMotion(false);
    this.q=this.make(vec4(this.initialPositions,s.inverse_mass),GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC,'Cloth positions');
    this.previous=this.make(vec4(this.initialPositions,s.inverse_mass));this.velocity=this.make(new Float32Array(this.n*4),GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC);
    this.normals=this.make(new Float32Array(this.n*4));this.scratch=this.make(new Float32Array(this.n*4));
    this.params=this.make(new Uint32Array(20),GPUBufferUsage.UNIFORM);
    this.faces=this.make(new Uint32Array(s.faces.flat()),GPUBufferUsage.STORAGE|GPUBufferUsage.INDEX);
    this.uv=this.make(new Float32Array(s.uv.flat()));
    this.body=this.make(vec4(s.body_vertices));this.bodyNormals=this.make(vec4(s.body_normals));
    this.bodyFaces=this.make(new Uint32Array(s.body_faces.flat()),GPUBufferUsage.STORAGE|GPUBufferUsage.INDEX);
    const raw=new ArrayBuffer(s.constraints.length*32),u=new Uint32Array(raw),f=new Float32Array(raw);
    placedConstraints.forEach((c,i)=>{u.set([c[0],c[1],c[2],0],i*8);f.set(c.slice(3),i*8+4);});
    this.edges=this.make(new Uint8Array(raw));
    const nodeRaw=new ArrayBuffer(s.body_bvh.length*48),nf=new Float32Array(nodeRaw),nu=new Uint32Array(nodeRaw);
    s.body_bvh.forEach((n,i)=>{nf.set(n.lo,i*12);nf.set(n.hi,i*12+4);nu.set([n.escape,n.start,n.count,0],i*12+8);});
    this.nodes=this.make(new Uint8Array(nodeRaw));
    this.hashSize=65536;this.heads=this.make(new Int32Array(this.hashSize).fill(-1));this.next=this.make(new Int32Array(this.n));
    this.sewn=this.make(new Uint32Array(s.sewn_ids));
    this.contactNeighbors=contactNeighbors(s);
    const [nr,na]=csr(this.contactNeighbors),[ir,ia]=csr(s.incident_faces);
    this.neighborRanges=this.make(nr);this.neighbors=this.make(na);this.incidentRanges=this.make(ir);this.incident=this.make(ia);
    const base=[[0,this.q],[1,this.params]];
    this.integrate=await this.pipeline(integrate,[...base,[2,this.previous],[3,this.velocity]],'Integrate');
    if(this.supportTargets.length){this.supportBuffer=this.make(new Float32Array(this.supportTargets.flat()));this.supportPass=await this.pipeline(necklineSupport,[[0,this.q],[2,this.supportBuffer],[3,this.previous]],'Optional neckline fitting support');}
    this.solve=await this.pipeline(constraints,[...base,[2,this.edges]],'Colored XPBD');
    this.buttonBatches=[];
    const buttonColors=closureColors(s.buttons),closures=buttonColors.flat();
    if(closures.length){
      const raw=new ArrayBuffer(closures.length*80),u=new Uint32Array(raw),f=new Float32Array(raw);
      closures.forEach((b,i)=>{u.set([...b.ids,b.index],i*20);u.set([...b.hole.ids,0],i*20+4);f.set([...b.weights,b.normal_sign],i*20+8);f.set([...b.hole.weights,b.clearance_m],i*20+12);f.set([b.compliance,...closureRest(b,this.initialPositions)],i*20+16);});
      this.buttonBuffer=this.make(new Uint8Array(raw));this.buttonStateBuffer=this.make(this.buttonStates);
      this.buttonSolve=await this.pipeline(common+buttonClosureShader,[...base,[2,this.buttonBuffer],[3,this.buttonStateBuffer]],'Button and buttonhole attachments');
      let offset=0;for(const color of buttonColors){this.buttonBatches.push({count:color.length,bind:d.createBindGroup({layout:this.buttonSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([offset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})});offset+=color.length;}
    }
    this.hingeBatches=[];
    this.interiorHingeBatches=[];
    if(s.interior_hinges?.length){
      const raw=new ArrayBuffer(s.interior_hinges.length*32),u=new Uint32Array(raw),f=new Float32Array(raw);
      s.interior_hinges.forEach((h,i)=>{u.set(h.ids,i*8);f.set([h.angle,h.compliance,0,0],i*8+4);});
      this.interiorHinges=this.make(new Uint8Array(raw));
      this.interiorHingeSolve=await this.pipeline(common+interiorHingeShader,[...base,[2,this.interiorHinges]],'Swatch interior bending');
      this.interiorHingeBatches=s.interior_hinge_batches.map(([start,count])=>{
        const binding=accumulate=>d.createBindGroup({layout:this.interiorHingeSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([start,count,accumulate,0]),GPUBufferUsage.UNIFORM)}}]});
        return {count,bind:binding(0),accumulatedBind:binding(1)};
      });
    }
    if(s.hinges?.length){
      const raw=new ArrayBuffer(s.hinges.length*48),u=new Uint32Array(raw),f=new Float32Array(raw);
      s.hinges.forEach((h,i)=>{u.set(h.ids.slice(0,3),i*12);u.set(h.ids.slice(3),i*12+4);f.set([h.angle,h.compliance,0,0],i*12+8);});
      this.hinges=this.make(new Uint8Array(raw));
      this.hingeSolve=await this.pipeline(common+hingeShader,[...base,[2,this.hinges]],'Signed collar bending');
      this.hingeBatches=s.hinge_batches.map(([start,count])=>({count,bind:d.createBindGroup({layout:this.hingeSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([start,count,0,0]),GPUBufferUsage.UNIFORM)}}]})}));
      const groups=new Map();
      s.sewn_ids.forEach((id,i)=>{if(!groups.has(id))groups.set(id,[]);groups.get(id).push(i);});
      // A buttoned garment must carry tension through its construction seams,
      // not relieve that tension by opening an unrelated side/shoulder seam.
      const welds=[...groups.values()].filter(ids=>ids.length>1);
      const [ranges,ids]=csr(welds);this.collarWeldCount=welds.length;
      this.collarWeld=await this.pipeline(common+collarWeldShader,[...base,[2,this.make(ranges)],[3,this.make(ids)],[4,this.previous]],'Close permanent sewing junctions');
    }
    this.batches=s.batches.map(([start,count])=>({count,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([start,count,0,0]),GPUBufferUsage.UNIFORM)}}]})}));
    const triangleColors=strainTopology(s);this.strainTriangles=triangleColors.flat();
    const tr=new ArrayBuffer(this.strainTriangles.length*32),tu=new Uint32Array(tr),tf=new Float32Array(tr);
    this.strainTriangles.forEach((t,i)=>{tu.set([...t.ids,0],i*8);tf.set(t.inverse,i*8+4);});
    this.triangles=this.make(new Uint8Array(tr));this.strainSolve=await this.pipeline(common+strainShader,[...base,[2,this.triangles]],'Principal triangle strain');
    let triangleOffset=0;this.strainBatches=triangleColors.map(color=>{const batch={count:color.length,bind:d.createBindGroup({layout:this.strainSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([triangleOffset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})};triangleOffset+=color.length;return batch;});
    // A closed waistband carries the whole lower garment. Give this small
    // region additional coupled strain/contact iterations so it cannot stretch
    // over the hips simply because the global one-iteration solve is soft.
    const waistColors=triangleColors.map(color=>color.filter(t=>t.ids.every(i=>/(^|__)wb_/.test(s.vertex_panels?.[i]||''))));
    const waist=waistColors.flat();this.waistBatches=[];
    if(waist.length){
      const raw=new ArrayBuffer(waist.length*32),u=new Uint32Array(raw),f=new Float32Array(raw);
      waist.forEach((t,i)=>{u.set([...t.ids,0],i*8);f.set(t.inverse,i*8+4);});
      this.waistSolve=await this.pipeline(common+strainShader,[...base,[2,this.make(new Uint8Array(raw))]],'Waistband strain');
      let offset=0;for(const color of waistColors){if(color.length)this.waistBatches.push({count:color.length,bind:d.createBindGroup({layout:this.waistSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([offset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})});offset+=color.length;}
    }
    this.collide=await this.pipeline(bodyCollision,[...base,[2,this.nodes],[3,this.body],[4,this.bodyFaces],[5,this.bodyNormals],[6,this.previous]],'Mannequin BVH contact',7);
    const tetherColors=waistbandTethers(s),tethers=tetherColors.flat();this.waistTetherBatches=[];
    if(tethers.length){
      const raw=new ArrayBuffer(tethers.length*32),u=new Uint32Array(raw),f=new Float32Array(raw);
      tethers.forEach((c,i)=>{u.set(c.slice(0,3),i*8);f.set(c.slice(3),i*8+4);});
      this.waistTetherSolve={...this.solve,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(0),entries:[...base,[2,this.make(new Uint8Array(raw))]].map(([binding,b])=>({binding,resource:{buffer:b}}))})};
      let offset=0;this.waistTetherBatches=tetherColors.map(color=>{const batch={count:color.length,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([offset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})};offset+=color.length;return batch;});
    }
    // Resolve stitches again after other projections; these batches are also
    // graph-colored, so their endpoint writes cannot race.
    const seamColors=[],used=Array.from({length:this.n},()=>new Set());
    for(const c of placedConstraints.filter(c=>c[2]===2)){
      let color=0;while(used[c[0]].has(color)||used[c[1]].has(color))color++;
      while(seamColors.length<=color)seamColors.push([]);seamColors[color].push(c);used[c[0]].add(color);used[c[1]].add(color);
    }
    const seams=seamColors.flat(),sr=new ArrayBuffer(seams.length*32),su=new Uint32Array(sr),sf=new Float32Array(sr);
    seams.forEach((c,i)=>{su.set([c[0],c[1],c[2],0],i*8);sf.set(c.slice(3),i*8+4);});
    this.seamEdges=this.make(new Uint8Array(sr.byteLength?sr:32));
    this.seamSolve={...this.solve,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(0),entries:[...base,[2,this.seamEdges]].map(([binding,b])=>({binding,resource:{buffer:b}}))})};
    let offset=0;this.seamBatches=seamColors.map(color=>{const batch={count:color.length,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([offset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})};offset+=color.length;return batch;});
    const waistSeams=seamColors.map(color=>color.filter(c=>c.slice(0,2).some(i=>/(^|__)wb_/.test(s.vertex_panels?.[i]||''))));
    const ws=waistSeams.flat(),wr=new ArrayBuffer(ws.length*32),wu=new Uint32Array(wr),wf=new Float32Array(wr);
    this.waistSeamBatches=[];
    if(ws.length){
      ws.forEach((c,i)=>{wu.set(c.slice(0,3),i*8);wf.set(c.slice(3),i*8+4);});
      this.waistSeamSolve={...this.solve,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(0),entries:[...base,[2,this.make(new Uint8Array(wr))]].map(([binding,b])=>({binding,resource:{buffer:b}}))})};
      let offset=0;for(const color of waistSeams){if(color.length)this.waistSeamBatches.push({count:color.length,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([offset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})});offset+=color.length;}
    }
    this.gridSize=this.settings.bodyCollision?[160,224,64]:[2,2,2];const lo=[0,1,2].map(a=>Math.min(...s.body_vertices.map(p=>p[a]))-.07),hi=[0,1,2].map(a=>Math.max(...s.body_vertices.map(p=>p[a]))+.07);
    this.gridRaw=new ArrayBuffer(48);new Float32Array(this.gridRaw).set([...lo,0,...lo.map((v,i)=>(hi[i]-v)/(this.gridSize[i]-1)),0]);
    new Uint32Array(this.gridRaw).set([...this.gridSize,0],8);this.grid=this.make(new Uint8Array(this.gridRaw),GPUBufferUsage.UNIFORM);
    const cells=this.gridSize.reduce((a,b)=>a*b);this.field=this.make(new Float32Array(cells));
    const build=await this.pipeline(buildSdf,[[2,this.nodes],[3,this.body],[4,this.bodyFaces],[5,this.bodyNormals],[7,this.grid],[8,this.field]],'Build body distance field');
    const sdfStart=performance.now();
    // Bound each submission to avoid long uninterruptible GPU work at startup.
    for(let start=0;start<cells;start+=16384){new Uint32Array(this.gridRaw)[11]=start;d.queue.writeBuffer(this.grid,0,this.gridRaw);const encoder=d.createCommandEncoder();this.dispatch(encoder,build,Math.min(16384,cells-start));d.queue.submit([encoder.finish()]);await d.queue.onSubmittedWorkDone();if(start%131072===0)this.progress(`Building body collision field on your GPU… ${Math.round(start/cells*100)}%`);}
    this.sdfSetupMs=performance.now()-sdfStart;
    this.sdfCollide=await this.pipeline(sdfCollision,[...base,[2,this.field],[3,this.grid],[4,this.previous]],'Body distance field contact',5);
    this.surfaceCollide=await this.pipeline(surfaceCollision,[...base,[2,this.triangles],[3,this.field],[4,this.grid]],'Triangle surface contact',5);
    let surfaceOffset=0;this.surfaceBatches=triangleColors.map(color=>{const batch={count:color.length,bind:d.createBindGroup({layout:this.surfaceCollide.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([surfaceOffset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})};surfaceOffset+=color.length;return batch;});
    this.clearHash=await this.pipeline(clearHash,[[1,this.params],[2,this.heads]],'Clear spatial hash');
    this.fillHash=await this.pipeline(fillHash,[...base,[2,this.heads],[3,this.next]],'Build spatial hash');
    this.self=await this.pipeline(selfCollision,[...base,[2,this.heads],[3,this.next],[4,this.scratch],[5,this.sewn],[6,this.neighborRanges],[7,this.neighbors]],'Particle self contact');
    this.applySelf=await this.pipeline(applySelf,[...base,[2,this.scratch]],'Apply self contact');
    this.velocityPass=await this.pipeline(updateVelocity,[...base,[2,this.previous],[3,this.velocity]],'Velocity');
    this.normalPass=await this.pipeline(computeNormals,[...base,[2,this.faces],[3,this.incidentRanges],[4,this.incident],[5,this.normals],[6,this.uv]],'Normals and strain display');
    if(s.garment==='fabric-swatch'&&this.n<=128&&s.interior_hinges.length<=256){
      const ranges=[...s.batches.map(([start,count])=>[start,count,0,0]),...s.interior_hinge_batches.map(([start,count])=>[start,count,1,0])];
      if(ranges.some(r=>r[1]>128))throw Error('Swatch constraint batch exceeds workgroup capacity.');
      this.fastSwatch=await this.pipeline(swatchShader,[...base,[2,this.previous],[3,this.velocity],[4,this.edges],[5,this.make(new Uint32Array(ranges.flat()))],[6,this.interiorHinges]],'Clamped swatch workgroup');
    }
    this.updateParams();
    const encoder=d.createCommandEncoder();this.dispatch(encoder,this.normalPass);d.queue.submit([encoder.finish()]);await d.queue.onSubmittedWorkDone();
    await this.checkKernels();
  }
  async checkKernels(){
    if(this.buttonSolve){
      const d=this.device,raw=new ArrayBuffer(80),u=new Uint32Array(raw),f=new Float32Array(raw);
      u.set([0,1,2,0]);u.set([3,4,5,0],4);f.set([1/3,1/3,1/3,1],8);f.set([1/3,1/3,1/3,.003],12);
      const state=this.make(new Uint32Array([1]));
      const fixture={...this.buttonSolve,bind:d.createBindGroup({layout:this.buttonSolve.pipeline.getBindGroupLayout(0),entries:
        [[0,this.q],[1,this.params],[2,this.make(new Uint8Array(raw))],[3,state]].map(([binding,buffer])=>({binding,resource:{buffer}}))})};
      const batch=d.createBindGroup({layout:this.buttonSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([0,1,0,0]),GPUBufferUsage.UNIFORM)}}]});
      const points=[[0,1,0],[.1,1,0],[0,1.1,0],[0,1,.06],[.1,1,.06],[0,1.1,.06]],mass=[1,1,1,.5,.5,.5];
      this.time=2;this.updateParams();d.queue.writeBuffer(this.q,0,vec4(points,mass));
      const encoder=d.createCommandEncoder();for(let i=0;i<30;i++)this.dispatch(encoder,fixture,1,batch);d.queue.submit([encoder.finish()]);
      const result=(await this.readPositions()).slice(0,6),mean=(p,start)=>p.slice(start,start+3).reduce((s,v)=>s+v[2],0)/3;
      this.kernelChecks={button_shank_retains_separate_layers:Math.abs(mean(result,3)-mean(result,0)-.003)<1e-6,
        button_transfers_load_to_both_panels:mean(result,0)>.03&&mean(result,3)<.05,
        button_preserves_center_of_mass:[0,1,2].every(k=>Math.abs(result.reduce((s,p,i)=>s+(p[k]-points[i][k])/mass[i],0))<1e-5)};
      d.queue.writeBuffer(state,0,new Uint32Array([0]));d.queue.writeBuffer(this.q,0,vec4(points,mass));
      const released=d.createCommandEncoder();this.dispatch(released,fixture,1,batch);d.queue.submit([released.finish()]);const open=await this.readPositions();
      this.kernelChecks.unbuttoning_removes_attachment_force=points.every((p,i)=>p.every((v,k)=>Math.abs(open[i][k]-v)<1e-7));
      this.time=0;this.updateParams();
    }
    const s=this.scene,d=this.device,testMass=s.inverse_mass.map(w=>w||1),fixture=vec4(s.vertices,testMass);
    const place=(a,b,distance)=>{
      for(let i=0;i<this.n;i++)fixture.set([10+i*.03,10,10,testMass[i]],i*4);
      fixture.set([0,0,0,testMass[a]],a*4);fixture.set([distance,0,0,testMass[b]],b*4);
      d.queue.writeBuffer(this.q,0,fixture);
    };
    const gap=(p,a,b)=>Math.hypot(...p[a].map((x,i)=>x-p[b][i]));
    const selfPass=async(a,b)=>{
      place(a,b,.003);const e=d.createCommandEncoder();
      this.dispatch(e,this.clearHash,this.hashSize/4);this.dispatch(e,this.fillHash);this.dispatch(e,this.self);this.dispatch(e,this.applySelf);
      d.queue.submit([e.finish()]);return gap(await this.readPositions(),a,b);
    };
    const a=0,b=s.sewn_ids.findIndex((id,i)=>i!==a&&!this.contactNeighbors[a].includes(id));
    const separated=await selfPass(a,b),excluded=await selfPass(a,s.neighbors[a][0]);
    const index=s.constraints.findIndex(c=>c[2]===0),c=s.constraints[index],rest=Math.hypot(c[3],c[4]);
    place(c[0],c[1],2*rest);
    const batchBuffer=this.make(new Uint32Array([index,1,0,0]),GPUBufferUsage.UNIFORM);
    const batch=d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:batchBuffer}}]});
    const e=d.createCommandEncoder();this.dispatch(e,this.solve,1,batch);d.queue.submit([e.finish()]);
    const distance=gap(await this.readPositions(),c[0],c[1]);
    const alpha=this.settings.stretch/(1/(60*this.settings.substeps))**2;
    const expected=rest+rest*alpha/(testMass[c[0]]+testMass[c[1]]+alpha);
    this.kernelChecks={...this.kernelChecks,self_contact_separates:Math.abs(separated-.008)<1e-5,adjacent_vertices_excluded:Math.abs(excluded-.003)<1e-5,xpbd_distance_matches_equation:Math.abs(distance-expected)<1e-5};
    if(this.hingeSolve){
      const raw=new ArrayBuffer(48),u=new Uint32Array(raw),f=new Float32Array(raw);
      u.set([0,1,2,0,3,4,5,0]);f.set([-2.18,0,0,0],8);d.queue.writeBuffer(this.hinges,0,raw);
      const buffer=this.make(new Uint32Array([0,1,0,0]),GPUBufferUsage.UNIFORM);
      const bind=d.createBindGroup({layout:this.hingeSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer}}]});
      const points=[[-.01,0,0],[.01,0,0],[0,.01,0],[-.01,0,0],[.01,0,0],[0,-.01,-.01]];
      const project=async(points,count)=>{
        d.queue.writeBuffer(this.q,0,vec4(points,[0,0,0,0,0,1]));
        const e=d.createCommandEncoder();for(let i=0;i<count;i++)this.dispatch(e,this.hingeSolve,1,bind);
        d.queue.submit([e.finish()]);return (await this.readPositions())[5];
      };
      const away=points.map(p=>[...p]);away[3][2]=away[4][2]=.05;
      const before=await project(away,1);
      this.kernelChecks.collar_hinge_waits_for_seam=before.every((v,i)=>Math.abs(v-points[5][i])<1e-6);
      const after=await project(points,20);
      this.kernelChecks.collar_hinge_preserves_fold_direction=Math.abs(Math.atan2(-after[2],-after[1])+2.18)<1e-4;
      const h=s.hinges[0];u.set([...h.ids.slice(0,3),0,...h.ids.slice(3),0]);f.set([h.angle,h.compliance,0,0],8);d.queue.writeBuffer(this.hinges,0,raw);
      const weld={...this.collarWeld,bind:d.createBindGroup({layout:this.collarWeld.pipeline.getBindGroupLayout(0),entries:
        [[0,this.q],[1,this.params],[2,this.make(new Uint32Array([0,3]))],[3,this.make(new Uint32Array([0,1,2]))],[4,this.previous]].map(([binding,buffer])=>({binding,resource:{buffer}}))})};
      const junction=vec4([[0,1,0],[.01,1,0],[.02,1,0]],[1,.5,1/3]);
      d.queue.writeBuffer(this.q,0,junction);d.queue.writeBuffer(this.previous,0,junction);
      this.time=2;this.updateParams();
      const close=d.createCommandEncoder();this.dispatch(close,weld,1);d.queue.submit([close.finish()]);
      const closed=(await this.readPositions()).slice(0,3);
      this.kernelChecks.collar_junction_preserves_center_of_mass=closed.every(p=>Math.abs(p[0]-.08/6)<1e-6&&Math.abs(p[1]-1)<1e-6);
      this.time=0;this.updateParams();
    }
    let seamPair=null;
    for(let i=0;i<this.n&&!seamPair;i++){
      const j=s.sewn_ids.findIndex((id,j)=>id!==s.sewn_ids[i]&&this.contactNeighbors[i].includes(id)&&!s.neighbors[i].includes(j));
      if(j>=0)seamPair=[i,j];
    }
    if(seamPair)this.kernelChecks.sewn_one_ring_excluded=Math.abs(await selfPass(...seamPair)-.003)<1e-5;
    // Exercise the actual strain shader on a sheared, stretched triangle.
    const t=this.strainTriangles[0],test=new ArrayBuffer(32),ti=new Uint32Array(test),tv=new Float32Array(test);
    ti.set([0,1,2,0]);tv.set([1,0,0,1],4);d.queue.writeBuffer(this.triangles,0,test);
    const single=this.make(new Uint32Array([0,1,0,0]),GPUBufferUsage.UNIFORM);
    const triangleBatch=d.createBindGroup({layout:this.strainSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:single}}]});
    const project=async(points)=>{
      d.queue.writeBuffer(this.q,0,vec4(points,1));const e=d.createCommandEncoder();
      for(let i=0;i<24;i++)this.dispatch(e,this.strainSolve,1,triangleBatch);
      d.queue.submit([e.finish()]);return (await this.readPositions()).slice(0,3);
    };
    const distorted=[[0,10,0],[1.6,10,0],[.4,11.3,0]],limited=await project(distorted);
    const e1=limited[1].map((v,i)=>v-limited[0][i]),e2=limited[2].map((v,i)=>v-limited[0][i]);
    const dot=(a,b)=>a.reduce((sum,v,i)=>sum+v*b[i],0),xx=dot(e1,e1),xy=dot(e1,e2),yy=dot(e2,e2);
    const sigma=Math.sqrt(.5*(xx+yy+Math.hypot(xx-yy,2*xy)));
    this.kernelChecks.principal_strain_limited=sigma<=this.settings.strainLimit+1e-5;
    this.kernelChecks.strain_preserves_center_of_mass=[0,1,2].every(axis=>Math.abs(limited.reduce((sum,p)=>sum+p[axis],0)-distorted.reduce((sum,p)=>sum+p[axis],0))<1e-5);
    const rotated=[[0,10,0],[0,10,1],[0,11,0]],restored=await project(rotated);
    this.kernelChecks.rigid_rotation_unchanged=restored.every((p,i)=>p.every((v,j)=>Math.abs(v-rotated[i][j])<1e-6));
    ti.set([...t.ids,0]);tv.set(t.inverse,4);d.queue.writeBuffer(this.triangles,0,test);
    // A sampled plane isolates friction from mannequin geometry. The point
    // moves 0.5 mm tangentially while penetrating the contact shell by 1 mm.
    const planeRaw=new ArrayBuffer(48);new Float32Array(planeRaw).set([-.02,-.02,-.02,0,.01,.01,.01,0]);new Uint32Array(planeRaw).set([5,5,5,0],8);
    const plane=this.make(Float32Array.from({length:125},(_,i)=>-.02+(Math.floor(i/5)%5)*.01));
    const planeGrid=this.make(new Uint8Array(planeRaw),GPUBufferUsage.UNIFORM);
    const planeStage={...this.sdfCollide,moving:null,bind:d.createBindGroup({layout:this.sdfCollide.pipeline.getBindGroupLayout(0),entries:[[0,this.q],[1,this.params],[2,plane],[3,planeGrid],[4,this.previous],[5,this.motionBuffer]].map(([binding,b])=>({binding,resource:{buffer:b}}))})};
    d.queue.writeBuffer(this.q,0,new Float32Array([.0005,.003,0,1]));d.queue.writeBuffer(this.previous,0,new Float32Array([0,.003,0,1]));
    const contact=d.createCommandEncoder();this.dispatch(contact,planeStage,1);d.queue.submit([contact.finish()]);const frictionPoint=(await this.readPositions())[0];
    this.kernelChecks.positional_friction_reduces_slip=Math.abs(frictionPoint[0]-.0001)<1e-6&&Math.abs(frictionPoint[1]-.004)<1e-6;
    // A rotating horizontal plane drags a resting particle tangentially.
    d.queue.writeBuffer(this.motionBuffer,0,new Float32Array([Math.cos(.04),Math.sin(.04),1,0,0,0,0,0]));
    d.queue.writeBuffer(this.q,0,new Float32Array([0,.003,.01,1]));d.queue.writeBuffer(this.previous,0,new Float32Array([0,.003,.01,1]));
    const movingContact=d.createCommandEncoder();this.dispatch(movingContact,planeStage,1);d.queue.submit([movingContact.finish()]);const carried=(await this.readPositions())[0];
    this.kernelChecks.moving_body_friction_carries_cloth=carried[0]>.00039&&carried[0]<.00041&&Math.abs(carried[1]-.004)<1e-6;
    // Turn a vertical plane through 90 degrees; its world contact normal must
    // rotate too, while its cached distance field remains untouched.
    d.queue.writeBuffer(plane,0,Float32Array.from({length:125},(_,i)=>-.02+(i%5)*.01));
    d.queue.writeBuffer(this.motionBuffer,0,new Float32Array([0,1,0,1,0,0,0,0]));
    d.queue.writeBuffer(this.q,0,new Float32Array([0,.005,-.003,1]));d.queue.writeBuffer(this.previous,0,new Float32Array([0,.005,-.003,1]));
    const turnedContact=d.createCommandEncoder();this.dispatch(turnedContact,planeStage,1);d.queue.submit([turnedContact.finish()]);const turned=(await this.readPositions())[0];
    this.kernelChecks.rotating_collider_transforms_contact_normal=Math.abs(turned[2]+.004)<1e-6&&Math.abs(turned[0])<1e-6;
    this.writeMotion(false);
    // All three vertices clear the sphere; the middle of an edge crosses it.
    const sphereRaw=new ArrayBuffer(48);new Float32Array(sphereRaw).set([-.04,-.04,-.04,0,.01,.01,.01,0]);new Uint32Array(sphereRaw).set([9,9,9,0],8);
    const sphere=this.make(Float32Array.from({length:729},(_,i)=>Math.hypot(-.04+(i%9)*.01,-.04+(Math.floor(i/9)%9)*.01,-.04+Math.floor(i/81)*.01)-.01));
    const sphereGrid=this.make(new Uint8Array(sphereRaw),GPUBufferUsage.UNIFORM);
    ti.set([0,1,2,0]);tv.set([1,0,0,1],4);d.queue.writeBuffer(this.triangles,0,test);
    const surfaceStage={...this.surfaceCollide,moving:null,bind:d.createBindGroup({layout:this.surfaceCollide.pipeline.getBindGroupLayout(0),entries:[[0,this.q],[1,this.params],[2,this.triangles],[3,sphere],[4,sphereGrid],[5,this.motionBuffer]].map(([binding,b])=>({binding,resource:{buffer:b}}))})};
    const surfaceBatch=d.createBindGroup({layout:this.surfaceCollide.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:single}}]});
    const outside=[[-.02,.003,0],[.02,.003,0],[0,.023,0]];d.queue.writeBuffer(this.q,0,vec4(outside,1));
    const surface=d.createCommandEncoder();this.dispatch(surface,surfaceStage,1,surfaceBatch);d.queue.submit([surface.finish()]);const moved=await this.readPositions();
    this.kernelChecks.surface_contact_catches_between_vertices=outside.every(p=>Math.hypot(...p)>.014)&&Math.hypot(...moved[0].map((v,i)=>(v+moved[1][i])*.5))>.013;
    ti.set([...t.ids,0]);tv.set(t.inverse,4);d.queue.writeBuffer(this.triangles,0,test);
    if(this.supportPass){
      const [id,y]=this.supportTargets[0];d.queue.writeBuffer(this.q,id*16,new Float32Array([.123,y-.02,.234,1]));
      const support=d.createCommandEncoder();this.dispatch(support,this.supportPass,this.supportTargets.length);d.queue.submit([support.finish()]);const p=(await this.readPositions())[id];
      this.kernelChecks.neckline_support_only_changes_height=Math.abs(p[1]-y)<1e-6&&Math.abs(p[0]-.123)<1e-6&&Math.abs(p[2]-.234)<1e-6;
    }
    if(this.interiorHingeSolve){
      const raw=new ArrayBuffer(32),u=new Uint32Array(raw),f=new Float32Array(raw);
      u.set([0,1,2,3]); // Flat rest angle, zero compliance for this kernel check.
      d.queue.writeBuffer(this.interiorHinges,0,raw);
      const batch=d.createBindGroup({layout:this.interiorHingeSolve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([0,1,0,0]),GPUBufferUsage.UNIFORM)}}]});
      const points=[[0,.12,0],[.01,.12,0],[0,.13,0],[0,.11,-.005]];
      d.queue.writeBuffer(this.q,0,vec4(points,[0,0,0,1]));
      const e=d.createCommandEncoder();for(let i=0;i<20;i++)this.dispatch(e,this.interiorHingeSolve,1,batch);d.queue.submit([e.finish()]);
      const p=await this.readPositions();
      this.kernelChecks.interior_bending_restores_flat_rest_angle=Math.abs(p[3][2])<1e-6;
      this.kernelChecks.interior_bending_preserves_pins=points.slice(0,3).every((v,i)=>v.every((x,a)=>Math.abs(x-p[i][a])<1e-7));
      const h=s.interior_hinges[0];u.set(h.ids);f.set([h.angle,h.compliance,0,0],4);d.queue.writeBuffer(this.interiorHinges,0,raw);
      this.reset();this.time=2;this.updateParams();
      d.queue.writeBuffer(this.velocity,0,new Float32Array(this.n*4).fill(1));
      const integrate=d.createCommandEncoder();this.dispatch(integrate,this.integrate);d.queue.submit([integrate.finish()]);
      const integrated=await this.readPositions();
      this.kernelChecks.integration_preserves_pins=s.inverse_mass.every((w,i)=>w!==0||s.vertices[i].every((v,a)=>Math.abs(v-integrated[i][a])<1e-7));
    }
    this.reset();await d.queue.onSubmittedWorkDone();
    if(this.fastSwatch){
      const optimized=this.fastSwatch;
      const step=async()=>{this.time=1;const e=d.createCommandEncoder();this.encode(e);d.queue.submit([e.finish()]);return this.readPositions();};
      const fast=await step();this.reset();this.fastSwatch=null;
      const reference=await step();this.fastSwatch=optimized;
      this.kernelChecks.swatch_workgroup_matches_reference=fast.every((p,i)=>Math.hypot(...p.map((v,a)=>v-reference[i][a]))<1e-5);
      this.reset();await d.queue.onSubmittedWorkDone();
    }
    if(!Object.values(this.kernelChecks).every(Boolean))throw Error('GPU kernel checks failed: '+JSON.stringify(this.kernelChecks));
  }
  updateParams(){
    const s=this.settings,count=this.frameSubsteps||s.substeps,raw=new ArrayBuffer(80),f=new Float32Array(raw),u=new Uint32Array(raw);
    f.set([this.frameDt/count,this.time,s.width,s.wind,s.stretch,s.bend,s.seam,s.thickness]);
    u.set([this.n,count,+s.selfCollision,this.hashSize],8);
    f.set([s.gravity,s.damping,s.friction,s.sewDuration],12);f.set([s.strainLimit,s.swatchIterations||1,0,0],16);this.device.queue.writeBuffer(this.params,0,raw);
  }
  writeMotion(advance){
    const count=this.frameSubsteps||this.settings.substeps;
    if(!Number.isInteger(count)||count<1||count>64)throw Error('Substeps must be between 1 and 64.');
    for(let step=0;step<count;step++){
      const previous=this.motion.yaw;
      if(advance)this.motion.advance(this.frameDt/count);
      this.motionRaw.set(this.motion.uniform(previous),step*this.motionStride/4);
    }
    this.device.queue.writeBuffer(this.motionBuffer,0,this.motionRaw,0,count*this.motionStride/4);
  }
  dispatch(encoder,stage,count=this.n,extra=null,timestamps=null){
    const pass=encoder.beginComputePass({label:stage.label,...(timestamps?{timestampWrites:timestamps}:{})});
    this.dispatchInPass(pass,stage,count,extra);pass.end();
  }
  dispatchInPass(pass,stage,count=this.n,extra=null){
    pass.setPipeline(stage.pipeline);pass.setBindGroup(0,stage.moving?.[this.motionStep||0]||stage.bind);if(extra)pass.setBindGroup(1,extra);
    pass.dispatchWorkgroups(Math.ceil(count/64));
  }
  encode(encoder,querySet=null,elapsed=1/60){
    // Advance body and cloth on the same clock. A 30/45 Hz display must not
    // turn the mannequin at half/three-quarter speed. Bound long stalls.
    this.frameDt=Number.isFinite(elapsed)?Math.max(1/240,Math.min(1/30,elapsed)):1/60;
    // Preserve the small solver step at lower refresh rates: larger steps let
    // fitted waistbands stretch over the hips. Bound the total work per frame.
    this.frameSubsteps=Math.min(64,Math.max(1,Math.ceil(this.settings.substeps*this.frameDt*60-1e-6)));
    this.time+=this.frameDt;
    this.frame++;this.updateParams();this.writeMotion(this.time>this.settings.sewDuration);
    // Dispatches remain ordered in one pass, avoiding thousands of separate
    // compute-pass begin/end commands per frame.
    const pass=encoder.beginComputePass({label:'cloth step',...(querySet?{timestampWrites:{querySet,beginningOfPassWriteIndex:0,endOfPassWriteIndex:1}}:{})});
    if(this.fastSwatch&&this.settings.stretch===0&&this.settings.width===1&&this.settings.wind===0&&!this.settings.bodyCollision&&!this.settings.selfCollision){
      pass.setPipeline(this.fastSwatch.pipeline);pass.setBindGroup(0,this.fastSwatch.bind);pass.dispatchWorkgroups(1);
      this.dispatchInPass(pass,this.normalPass);pass.end();return;
    }
    for(let step=0;step<this.frameSubsteps;step++){
      this.motionStep=step;
      this.dispatchInPass(pass,this.integrate);
      for(const batch of this.batches)this.dispatchInPass(pass,this.solve,batch.count,batch.bind);
      if(this.settings.bodyCollision&&this.settings.surfaceContact)for(const batch of this.surfaceBatches)this.dispatchInPass(pass,this.surfaceCollide,batch.count,batch.bind);
      for(let iteration=0;iteration<this.settings.strainPasses;iteration++)for(const batch of this.strainBatches)this.dispatchInPass(pass,this.strainSolve,batch.count,batch.bind);
      if(this.settings.selfCollision){
        this.dispatchInPass(pass,this.clearHash,this.hashSize/4);this.dispatchInPass(pass,this.fillHash);
        this.dispatchInPass(pass,this.self);this.dispatchInPass(pass,this.applySelf);
      }
      for(const batch of this.seamBatches)this.dispatchInPass(pass,this.seamSolve,batch.count,batch.bind);
      for(const batch of this.hingeBatches)this.dispatchInPass(pass,this.hingeSolve,batch.count,batch.bind);
      for(const batch of this.interiorHingeBatches||[])this.dispatchInPass(pass,this.interiorHingeSolve,batch.count,batch.bind);
      if(this.interiorHingeBatches?.length)for(let iteration=1;iteration<(this.settings.swatchIterations||1);iteration++){
        for(const batch of this.batches)this.dispatchInPass(pass,this.solve,batch.count,batch.bind);
        for(const batch of this.interiorHingeBatches)this.dispatchInPass(pass,this.interiorHingeSolve,batch.count,batch.accumulatedBind);
      }
      // Button seats can share a triangle corner with a permanent seam.
      // Couple the solves so the button cannot pull that construction seam apart.
      for(let iteration=0;iteration<(this.buttonBatches.length?3:1);iteration++){
        for(const batch of this.buttonBatches)this.dispatchInPass(pass,this.buttonSolve,batch.count,batch.bind);
        if(this.collarWeld)this.dispatchInPass(pass,this.collarWeld,this.collarWeldCount);
      }
      if(this.settings.holdNeckline&&this.supportPass)this.dispatchInPass(pass,this.supportPass,this.supportTargets.length);
      if(this.settings.bodyCollision)this.dispatchInPass(pass,this.settings.bodyMethod==='sdf'?this.sdfCollide:this.collide);
      if(this.waistBatches.length)for(let iteration=0;iteration<6;iteration++){
        for(const batch of this.waistTetherBatches)this.dispatchInPass(pass,this.waistTetherSolve,batch.count,batch.bind);
        for(const batch of this.waistBatches)this.dispatchInPass(pass,this.waistSolve,batch.count,batch.bind);
        for(const batch of this.waistSeamBatches)this.dispatchInPass(pass,this.waistSeamSolve,batch.count,batch.bind);
        if(this.settings.bodyCollision)this.dispatchInPass(pass,this.settings.bodyMethod==='sdf'?this.sdfCollide:this.collide);
      }
      if(this.buttonBatches.length&&this.collarWeld){
        this.dispatchInPass(pass,this.collarWeld,this.collarWeldCount);
        if(this.settings.bodyCollision)this.dispatchInPass(pass,this.settings.bodyMethod==='sdf'?this.sdfCollide:this.collide);
      }
      this.dispatchInPass(pass,this.velocityPass);
    }
    this.motionStep=0;
    this.dispatchInPass(pass,this.normalPass);pass.end();
  }
  reset(){
    this.time=0;this.frameDt=1/60;this.frameSubsteps=this.settings.substeps;
    if(this.buttonStateBuffer){this.buttonStates.set((this.scene.buttons||[]).map(b=>b.closed!==false?1:0));this.device.queue.writeBuffer(this.buttonStateBuffer,0,this.buttonStates);}
    this.motion.reset();this.motionStep=0;this.writeMotion(false);
    this.frame=0;this.device.queue.writeBuffer(this.q,0,vec4(this.initialPositions,this.scene.inverse_mass));
    this.device.queue.writeBuffer(this.previous,0,vec4(this.initialPositions,this.scene.inverse_mass));
    this.device.queue.writeBuffer(this.velocity,0,new Float32Array(this.n*4));this.updateParams();
    const encoder=this.device.createCommandEncoder();this.dispatch(encoder,this.normalPass);this.device.queue.submit([encoder.finish()]);
  }
  setButton(index,closed){
    if(!this.scene.buttons?.[index]?.hole)return;
    this.buttonStates[index]=closed?1:0;
    this.device.queue.writeBuffer(this.buttonStateBuffer,index*4,this.buttonStates,index,1);
  }
  async readPositions(){
    const b=this.device.createBuffer({size:this.n*32,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});
    const e=this.device.createCommandEncoder();e.copyBufferToBuffer(this.q,0,b,0,this.n*16);e.copyBufferToBuffer(this.velocity,0,b,this.n*16,this.n*16);this.device.queue.submit([e.finish()]);
    await b.mapAsync(GPUMapMode.READ);const p=new Float32Array(b.getMappedRange()).slice();b.unmap();b.destroy();
    let sum=0;for(let i=0;i<this.n;i++){const j=this.n*4+i*4;sum+=p[j]**2+p[j+1]**2+p[j+2]**2;}this.rmsVelocity=Math.sqrt(sum/this.n);
    return Array.from({length:this.n},(_,i)=>Array.from(p.slice(i*4,i*4+3)));
  }
  destroy(){for(const b of this.owned)b.destroy();}
}

