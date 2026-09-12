// SewEasy browser cloth experiment. Original WGSL implementation of small-step
// XPBD distance constraints; see README.md for paper references and limits.
const common = `
struct Params { motion: vec4<f32>, material: vec4<f32>, counts: vec4<u32>, contact: vec4<f32> }
@group(0) @binding(0) var<storage, read_write> q: array<vec4<f32>>;
@group(0) @binding(1) var<uniform> params: Params;
`;

const integrate = common + `
@group(0) @binding(2) var<storage, read_write> previous: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read_write> velocity: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i = gid.x; if (i >= params.counts.x) { return; }
 let p = q[i]; previous[i] = p;
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
 let length_now = length(d); if (length_now < 1e-9) { return; }
 var rest = length(vec2<f32>(c.rest.x * params.motion.z, c.rest.y));
 var compliance = params.material.x;
 if (c.ids.z == 1u) { compliance = params.material.y * c.rest.z; }
 if (c.ids.z == 2u) {
   rest = c.rest.w * (1.0 - clamp(params.motion.y / params.contact.w, 0.0, 1.0));
   compliance = params.material.z;
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
const bodyCollision = common + bodyGeometry + `
@group(0) @binding(6) var<storage, read_write> previous: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 let p=q[i].xyz;let hit=body_value(p);let normal=hit.xyz;let signed=hit.w;
 let depth=params.material.w-signed;
 if (depth>0.0) {
   let push=min(depth,0.04);let corrected=p+normal*push;
   let movement=corrected-previous[i].xyz;
   let tangent=movement-normal*dot(movement,normal);
   let friction=min(1.0,params.contact.z*push/max(length(tangent),1e-8));
   previous[i]=vec4<f32>(previous[i].xyz+tangent*friction,previous[i].w);
   q[i]=vec4<f32>(corrected,q[i].w);
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
const sdfCollision = common + gridType + `
@group(0) @binding(2) var<storage,read> field:array<f32>;
@group(0) @binding(3) var<uniform> grid:Grid;
@group(0) @binding(4) var<storage,read_write> previous:array<vec4<f32>>;
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
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid:vec3<u32>){
 let i=gid.x;if(i>=params.counts.x){return;}let p=q[i].xyz;
 let v=(p-grid.lo.xyz)/grid.step.xyz;
 if(all(v>=vec3<f32>(1)) && all(v<vec3<f32>(grid.counts.xyz)-vec3<f32>(2))){
  let depth=params.material.w-sample_sdf(p);
  if(depth>0.0){
   let h=grid.step.xyz*0.5;
   let gradient=vec3<f32>(sample_sdf(p+vec3<f32>(h.x,0,0))-sample_sdf(p-vec3<f32>(h.x,0,0)),sample_sdf(p+vec3<f32>(0,h.y,0))-sample_sdf(p-vec3<f32>(0,h.y,0)),sample_sdf(p+vec3<f32>(0,0,h.z))-sample_sdf(p-vec3<f32>(0,0,h.z)))/grid.step.xyz;
   let normal=gradient/max(length(gradient),1e-8);let push=min(depth,0.04);let corrected=p+normal*push;
   let movement=corrected-previous[i].xyz;let tangent=movement-normal*dot(movement,normal);
   let friction=min(1.0,params.contact.z*push/max(length(tangent),1e-8));
   previous[i]=vec4<f32>(previous[i].xyz+tangent*friction,previous[i].w);q[i]=vec4<f32>(corrected,q[i].w);
  }
 }
 if(q[i].y<0.004){q[i].y=0.004;}
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
     for(var k=0u;k<r.y;k++){if(adjacent[r.x+k]==id){neighbor=true;break;}}
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
const computeNormals = common + `
@group(0) @binding(2) var<storage, read> faces: array<u32>;
@group(0) @binding(3) var<storage, read> ranges: array<vec2<u32>>;
@group(0) @binding(4) var<storage, read> adjacent: array<u32>;
@group(0) @binding(5) var<storage, read_write> normals: array<vec4<f32>>;
@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
 let i=gid.x;if(i>=params.counts.x){return;}
 var n=vec3<f32>(0);let r=ranges[i];
 for(var j=0u;j<r.y;j++){
   let f=adjacent[r.x+j]*3u;let a=q[faces[f]].xyz;let b=q[faces[f+1u]].xyz;let c=q[faces[f+2u]].xyz;
   n+=cross(b-a,c-a);
 }
 normals[i]=vec4<f32>(n/max(length(n),1e-12),0.0);
}`;

export function buffer(device, array, usage, label='') {
  const result=device.createBuffer({size:Math.max(16,(array.byteLength+3)&~3),usage:usage|GPUBufferUsage.COPY_DST,label});
  device.queue.writeBuffer(result,0,array);return result;
}
export function vec4(values, w=0) {return new Float32Array(values.flatMap((p,i)=>[...p,Array.isArray(w)||ArrayBuffer.isView(w)?w[i]:w]));}
function csr(rows) {const values=[],ranges=[];for(const row of rows){ranges.push(values.length,row.length);values.push(...row);}return [new Uint32Array(ranges),new Uint32Array(values)];}

export class Cloth {
  static async create(device, scene,progress=()=>{}) {const c=new Cloth(device,scene);c.progress=progress;await c.initialize();return c;}
  constructor(device,scene) {
    this.device=device;this.scene=scene;this.n=scene.vertices.length;this.frame=0;this.owned=[];
    this.initialPositions=scene.vertices.map(p=>[p[0],p[1]+0.06,p[2]]);
    this.settings={substeps:12,width:1,wind:0,stretch:0.0001,bend:0.03,seam:0.0000001,thickness:0.004,gravity:9.81,damping:2,friction:0.4,sewDuration:0.8,selfCollision:true,bodyCollision:true,bodyMethod:'sdf'};
  }
  make(array,usage=GPUBufferUsage.STORAGE,label=''){const b=buffer(this.device,array,usage,label);this.owned.push(b);return b;}
  async pipeline(code,resources,label){
    const module=this.device.createShaderModule({code,label});
    const info=await module.getCompilationInfo();const errors=info.messages.filter(m=>m.type==='error');
    if(errors.length)throw Error(label+': '+errors.map(m=>`${m.lineNum}: ${m.message}`).join('\n'));
    const pipeline=await this.device.createComputePipelineAsync({layout:'auto',compute:{module,entryPoint:'main'},label});
    const bind=this.device.createBindGroup({layout:pipeline.getBindGroupLayout(0),entries:resources.map(([binding,b])=>({binding,resource:{buffer:b}}))});
    return {pipeline,bind,label};
  }
  async initialize(){
    const d=this.device,s=this.scene;
    this.q=this.make(vec4(this.initialPositions,s.inverse_mass),GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC,'Cloth positions');
    this.previous=this.make(vec4(this.initialPositions,s.inverse_mass));this.velocity=this.make(new Float32Array(this.n*4),GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC);
    this.normals=this.make(new Float32Array(this.n*4));this.scratch=this.make(new Float32Array(this.n*4));
    this.params=this.make(new Uint32Array(16),GPUBufferUsage.UNIFORM);
    this.faces=this.make(new Uint32Array(s.faces.flat()),GPUBufferUsage.STORAGE|GPUBufferUsage.INDEX);
    this.body=this.make(vec4(s.body_vertices));this.bodyNormals=this.make(vec4(s.body_normals));
    this.bodyFaces=this.make(new Uint32Array(s.body_faces.flat()),GPUBufferUsage.STORAGE|GPUBufferUsage.INDEX);
    const raw=new ArrayBuffer(s.constraints.length*32),u=new Uint32Array(raw),f=new Float32Array(raw);
    s.constraints.forEach((c,i)=>{u.set([c[0],c[1],c[2],0],i*8);f.set(c.slice(3),i*8+4);});
    this.edges=this.make(new Uint8Array(raw));
    const nodeRaw=new ArrayBuffer(s.body_bvh.length*48),nf=new Float32Array(nodeRaw),nu=new Uint32Array(nodeRaw);
    s.body_bvh.forEach((n,i)=>{nf.set(n.lo,i*12);nf.set(n.hi,i*12+4);nu.set([n.escape,n.start,n.count,0],i*12+8);});
    this.nodes=this.make(new Uint8Array(nodeRaw));
    this.hashSize=65536;this.heads=this.make(new Int32Array(this.hashSize).fill(-1));this.next=this.make(new Int32Array(this.n));
    this.sewn=this.make(new Uint32Array(s.sewn_ids));
    const [nr,na]=csr(s.neighbors),[ir,ia]=csr(s.incident_faces);
    this.neighborRanges=this.make(nr);this.neighbors=this.make(na);this.incidentRanges=this.make(ir);this.incident=this.make(ia);
    const base=[[0,this.q],[1,this.params]];
    this.integrate=await this.pipeline(integrate,[...base,[2,this.previous],[3,this.velocity]],'Integrate');
    this.solve=await this.pipeline(constraints,[...base,[2,this.edges]],'Colored XPBD');
    this.batches=s.batches.map(([start,count])=>({count,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([start,count,0,0]),GPUBufferUsage.UNIFORM)}}]})}));
    this.collide=await this.pipeline(bodyCollision,[...base,[2,this.nodes],[3,this.body],[4,this.bodyFaces],[5,this.bodyNormals],[6,this.previous]],'Mannequin BVH contact');
    // Resolve stitches again after other projections; these batches are also
    // graph-colored, so their endpoint writes cannot race.
    const seamColors=[],used=Array.from({length:this.n},()=>new Set());
    for(const c of s.constraints.filter(c=>c[2]===2)){
      let color=0;while(used[c[0]].has(color)||used[c[1]].has(color))color++;
      while(seamColors.length<=color)seamColors.push([]);seamColors[color].push(c);used[c[0]].add(color);used[c[1]].add(color);
    }
    const seams=seamColors.flat(),sr=new ArrayBuffer(seams.length*32),su=new Uint32Array(sr),sf=new Float32Array(sr);
    seams.forEach((c,i)=>{su.set([c[0],c[1],c[2],0],i*8);sf.set(c.slice(3),i*8+4);});
    this.seamEdges=this.make(new Uint8Array(sr));
    this.seamSolve={...this.solve,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(0),entries:[...base,[2,this.seamEdges]].map(([binding,b])=>({binding,resource:{buffer:b}}))})};
    let offset=0;this.seamBatches=seamColors.map(color=>{const batch={count:color.length,bind:d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:this.make(new Uint32Array([offset,color.length,0,0]),GPUBufferUsage.UNIFORM)}}]})};offset+=color.length;return batch;});
    this.gridSize=[160,224,64];const lo=[0,1,2].map(a=>Math.min(...s.body_vertices.map(p=>p[a]))-.07),hi=[0,1,2].map(a=>Math.max(...s.body_vertices.map(p=>p[a]))+.07);
    this.gridRaw=new ArrayBuffer(48);new Float32Array(this.gridRaw).set([...lo,0,...lo.map((v,i)=>(hi[i]-v)/(this.gridSize[i]-1)),0]);
    new Uint32Array(this.gridRaw).set([...this.gridSize,0],8);this.grid=this.make(new Uint8Array(this.gridRaw),GPUBufferUsage.UNIFORM);
    const cells=this.gridSize.reduce((a,b)=>a*b);this.field=this.make(new Float32Array(cells));
    const build=await this.pipeline(buildSdf,[[2,this.nodes],[3,this.body],[4,this.bodyFaces],[5,this.bodyNormals],[7,this.grid],[8,this.field]],'Build body distance field');
    const sdfStart=performance.now();
    // Bound each submission to avoid long uninterruptible GPU work at startup.
    for(let start=0;start<cells;start+=16384){new Uint32Array(this.gridRaw)[11]=start;d.queue.writeBuffer(this.grid,0,this.gridRaw);const encoder=d.createCommandEncoder();this.dispatch(encoder,build,Math.min(16384,cells-start));d.queue.submit([encoder.finish()]);await d.queue.onSubmittedWorkDone();if(start%131072===0)this.progress(`Building body collision field on your GPU… ${Math.round(start/cells*100)}%`);}
    this.sdfSetupMs=performance.now()-sdfStart;
    this.sdfCollide=await this.pipeline(sdfCollision,[...base,[2,this.field],[3,this.grid],[4,this.previous]],'Body distance field contact');
    this.clearHash=await this.pipeline(clearHash,[[1,this.params],[2,this.heads]],'Clear spatial hash');
    this.fillHash=await this.pipeline(fillHash,[...base,[2,this.heads],[3,this.next]],'Build spatial hash');
    this.self=await this.pipeline(selfCollision,[...base,[2,this.heads],[3,this.next],[4,this.scratch],[5,this.sewn],[6,this.neighborRanges],[7,this.neighbors]],'Particle self contact');
    this.applySelf=await this.pipeline(applySelf,[...base,[2,this.scratch]],'Apply self contact');
    this.velocityPass=await this.pipeline(updateVelocity,[...base,[2,this.previous],[3,this.velocity]],'Velocity');
    this.normalPass=await this.pipeline(computeNormals,[...base,[2,this.faces],[3,this.incidentRanges],[4,this.incident],[5,this.normals]],'Normals');
    this.updateParams();
    const encoder=d.createCommandEncoder();this.dispatch(encoder,this.normalPass);d.queue.submit([encoder.finish()]);await d.queue.onSubmittedWorkDone();
    await this.checkKernels();
  }
  async checkKernels(){
    const s=this.scene,d=this.device,fixture=vec4(s.vertices,s.inverse_mass);
    const place=(a,b,distance)=>{
      for(let i=0;i<this.n;i++)fixture.set([10+i*.03,10,10,s.inverse_mass[i]],i*4);
      fixture.set([0,0,0,s.inverse_mass[a]],a*4);fixture.set([distance,0,0,s.inverse_mass[b]],b*4);
      d.queue.writeBuffer(this.q,0,fixture);
    };
    const gap=(p,a,b)=>Math.hypot(...p[a].map((x,i)=>x-p[b][i]));
    const selfPass=async(a,b)=>{
      place(a,b,.003);const e=d.createCommandEncoder();
      this.dispatch(e,this.clearHash,this.hashSize/4);this.dispatch(e,this.fillHash);this.dispatch(e,this.self);this.dispatch(e,this.applySelf);
      d.queue.submit([e.finish()]);return gap(await this.readPositions(),a,b);
    };
    const a=0,b=s.sewn_ids.findIndex((id,i)=>i!==a&&id!==s.sewn_ids[a]&&!s.neighbors[a].includes(i));
    const separated=await selfPass(a,b),excluded=await selfPass(a,s.neighbors[a][0]);
    const index=s.constraints.findIndex(c=>c[2]===0),c=s.constraints[index],rest=Math.hypot(c[3],c[4]);
    place(c[0],c[1],2*rest);
    const batchBuffer=this.make(new Uint32Array([index,1,0,0]),GPUBufferUsage.UNIFORM);
    const batch=d.createBindGroup({layout:this.solve.pipeline.getBindGroupLayout(1),entries:[{binding:0,resource:{buffer:batchBuffer}}]});
    const e=d.createCommandEncoder();this.dispatch(e,this.solve,1,batch);d.queue.submit([e.finish()]);
    const distance=gap(await this.readPositions(),c[0],c[1]);
    const alpha=this.settings.stretch/(1/(60*this.settings.substeps))**2;
    const expected=rest+rest*alpha/(s.inverse_mass[c[0]]+s.inverse_mass[c[1]]+alpha);
    this.kernelChecks={self_contact_separates:Math.abs(separated-.008)<1e-5,adjacent_vertices_excluded:Math.abs(excluded-.003)<1e-5,xpbd_distance_matches_equation:Math.abs(distance-expected)<1e-5};
    this.reset();await d.queue.onSubmittedWorkDone();
    if(!Object.values(this.kernelChecks).every(Boolean))throw Error('GPU kernel checks failed: '+JSON.stringify(this.kernelChecks));
  }
  updateParams(){
    const s=this.settings,raw=new ArrayBuffer(64),f=new Float32Array(raw),u=new Uint32Array(raw);
    f.set([1/(60*s.substeps),this.frame/60,s.width,s.wind,s.stretch,s.bend,s.seam,s.thickness]);
    u.set([this.n,s.substeps,+s.selfCollision,this.hashSize],8);
    f.set([s.gravity,s.damping,s.friction,s.sewDuration],12);this.device.queue.writeBuffer(this.params,0,raw);
  }
  dispatch(encoder,stage,count=this.n,extra=null,timestamps=null){
    const pass=encoder.beginComputePass({label:stage.label,...(timestamps?{timestampWrites:timestamps}:{})});
    pass.setPipeline(stage.pipeline);pass.setBindGroup(0,stage.bind);if(extra)pass.setBindGroup(1,extra);
    pass.dispatchWorkgroups(Math.ceil(count/64));pass.end();
  }
  encode(encoder,querySet=null){
    this.frame++;this.updateParams();
    for(let step=0;step<this.settings.substeps;step++){
      this.dispatch(encoder,this.integrate,this.n,null,querySet&&step===0?{querySet,beginningOfPassWriteIndex:0}:null);
      for(const batch of this.batches)this.dispatch(encoder,this.solve,batch.count,batch.bind);
      if(this.settings.selfCollision){
        this.dispatch(encoder,this.clearHash,this.hashSize/4);this.dispatch(encoder,this.fillHash);
        this.dispatch(encoder,this.self);this.dispatch(encoder,this.applySelf);
      }
      for(const batch of this.seamBatches)this.dispatch(encoder,this.seamSolve,batch.count,batch.bind);
      if(this.settings.bodyCollision)this.dispatch(encoder,this.settings.bodyMethod==='sdf'?this.sdfCollide:this.collide);
      this.dispatch(encoder,this.velocityPass);
    }
    this.dispatch(encoder,this.normalPass,this.n,null,querySet?{querySet,endOfPassWriteIndex:1}:null);
  }
  reset(){
    this.frame=0;this.device.queue.writeBuffer(this.q,0,vec4(this.initialPositions,this.scene.inverse_mass));
    this.device.queue.writeBuffer(this.previous,0,vec4(this.initialPositions,this.scene.inverse_mass));
    this.device.queue.writeBuffer(this.velocity,0,new Float32Array(this.n*4));this.updateParams();
    const encoder=this.device.createCommandEncoder();this.dispatch(encoder,this.normalPass);this.device.queue.submit([encoder.finish()]);
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
