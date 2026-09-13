import {buffer} from './physics.js?v=13';
import {cameraControls} from './camera.js?v=13';

function normalize(v){const l=Math.hypot(...v)||1;return v.map(x=>x/l);}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function dot(a,b){return a.reduce((s,v,i)=>s+v*b[i],0);}
function multiply(a,b){const r=new Float32Array(16);for(let c=0;c<4;c++)for(let row=0;row<4;row++)for(let k=0;k<4;k++)r[c*4+row]+=a[k*4+row]*b[c*4+k];return r;}
function cameraMatrix(eye,target,aspect){
 const z=normalize(eye.map((x,i)=>x-target[i])),x=normalize(cross([0,1,0],z)),y=cross(z,x);
 const view=[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1];
 const f=1/Math.tan(35*Math.PI/360),near=.01,far=50;
 const projection=[f/aspect,0,0,0,0,f,0,0,0,0,far/(near-far),-1,0,0,far*near/(near-far),0];
 return multiply(projection,view);
}
const shader=`
struct View { mvp: mat4x4<f32>, eye: vec4<f32>, color: vec4<f32>, angle:vec4<f32>, center:vec4<f32> }
struct Out { @builtin(position) clip: vec4<f32>, @location(0) world: vec3<f32>, @location(1) normal: vec3<f32>, @location(2) strain:f32, @location(3) color:vec3<f32> }
@group(0) @binding(0) var<uniform> view: View;
@group(0) @binding(1) var<storage, read> positions: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> normals: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> colors: array<vec4<f32>>;
fn turn(v:vec3<f32>)->vec3<f32>{let cs=view.angle.xy;return vec3<f32>(cs.x*v.x+cs.y*v.z,v.y,-cs.y*v.x+cs.x*v.z);}
@vertex fn vertex(@builtin(vertex_index) id: u32) -> Out {
 var o:Out;o.world=view.center.xyz+turn(positions[id].xyz-view.center.xyz);o.clip=view.mvp*vec4<f32>(o.world,1);o.normal=turn(normals[id].xyz);o.strain=normals[id].w;o.color=colors[id].rgb;return o;
}
@fragment fn fragment(o:Out,@builtin(front_facing) front:bool)->@location(0) vec4<f32>{
 let n=normalize(o.normal)*select(-1.0,1.0,front);let l=normalize(vec3<f32>(-0.4,1,0.8));
 let fill=max(dot(n,normalize(vec3<f32>(0.8,0.5,-1))),0.0);
 let light=0.32+0.63*max(dot(n,l),0.0)+0.18*fill;
 let v=normalize(view.eye.xyz-o.world);let rim=pow(1.0-max(dot(n,v),0.0),3.0)*0.07;
 let t=clamp((o.strain-1.0)/.2,0.0,1.0);
 let heat=select(mix(vec3<f32>(.03,.2,.5),vec3<f32>(.8,.38,.015),t*2.0),mix(vec3<f32>(.8,.38,.015),vec3<f32>(.65,.02,.015),(t-.5)*2.0),t>.5);
 let color=select(view.color.rgb*o.color,heat,view.color.a>.5);
 return vec4<f32>(pow(color*light+rim,vec3<f32>(1.0/2.2)),1);
}`;
export class Renderer {
 constructor(device,canvas,cloth,format){
  this.device=device;this.canvas=canvas;this.cloth=cloth;this.format=format;this.dirty=true;
  this.resizeObserver=new ResizeObserver(()=>this.dirty=true);this.resizeObserver.observe(canvas);
  this.context=canvas.getContext('webgpu');this.context.configure({device,format,alphaMode:'opaque'});
  this.camera={yaw:0,pitch:0,distance:2.3,target:[0,1.2,0]};this.buffers=[];this.showBody=true;
  this.clothColors=buffer(device,new Float32Array(cloth.n*4).fill(1),GPUBufferUsage.STORAGE);
  this.bodyColors=buffer(device,new Float32Array(cloth.scene.body_vertices.length*4).fill(1),GPUBufferUsage.STORAGE);
  this.buffers.push(this.clothColors,this.bodyColors);
  const makeUniform=color=>{const b=buffer(device,new Float32Array(32),GPUBufferUsage.UNIFORM);this.buffers.push(b);return {buffer:b,color};};
  this.clothView=makeUniform([0.18,0.40,0.59,0]);this.bodyView=makeUniform([0.72,0.64,0.57,0]);
  const module=device.createShaderModule({code:shader});
  this.pipeline=device.createRenderPipeline({layout:'auto',vertex:{module,entryPoint:'vertex'},fragment:{module,entryPoint:'fragment',targets:[{format}]},primitive:{topology:'triangle-list',cullMode:'none'},depthStencil:{format:'depth24plus',depthWriteEnabled:true,depthCompare:'less'}});
  const bind=(uniform,q,n,color)=>device.createBindGroup({layout:this.pipeline.getBindGroupLayout(0),entries:[{binding:0,resource:{buffer:uniform}},{binding:1,resource:{buffer:q}},{binding:2,resource:{buffer:n}},{binding:3,resource:{buffer:color}}]});
  this.clothBind=bind(this.clothView.buffer,cloth.q,cloth.normals,this.clothColors);this.bodyBind=bind(this.bodyView.buffer,cloth.body,cloth.bodyNormals,this.bodyColors);
  canvas.tabIndex=0;
  this.controls=cameraControls(this.camera,canvas,()=>this.dirty=true,cloth.motion);
 }
 render(encoder,querySet=null){
  this.dirty=false;
  const c=this.canvas,pixel=Math.min(devicePixelRatio,2),w=Math.max(1,Math.round(c.clientWidth*pixel)),h=Math.max(1,Math.round(c.clientHeight*pixel));
  if(c.width!==w||c.height!==h||!this.depth){c.width=w;c.height=h;this.depth?.destroy();this.depth=this.device.createTexture({size:[w,h],format:'depth24plus',usage:GPUTextureUsage.RENDER_ATTACHMENT});}
  const v=this.camera,r=v.distance,eye=[v.target[0]+r*Math.sin(v.yaw)*Math.cos(v.pitch),v.target[1]+r*Math.sin(v.pitch),v.target[2]+r*Math.cos(v.yaw)*Math.cos(v.pitch)];
  const mvp=cameraMatrix(eye,v.target,w/h);
  for(const view of [this.clothView,this.bodyView]){const a=new Float32Array(32);a.set(mvp);a.set([...eye,1],16);a.set(view.color,20);a.set(view===this.bodyView?this.cloth.motion.uniform():[1,0,1,0,0,0,0,0],24);this.device.queue.writeBuffer(view.buffer,0,a);}
  const pass=encoder.beginRenderPass({colorAttachments:[{view:this.context.getCurrentTexture().createView(),clearValue:{r:.91,g:.94,b:.96,a:1},loadOp:'clear',storeOp:'store'}],depthStencilAttachment:{view:this.depth.createView(),depthClearValue:1,depthLoadOp:'clear',depthStoreOp:'store'},...(querySet?{timestampWrites:{querySet,beginningOfPassWriteIndex:2,endOfPassWriteIndex:3}}:{})});
  pass.setPipeline(this.pipeline);
  if(this.showBody){pass.setBindGroup(0,this.bodyBind);pass.setIndexBuffer(this.cloth.bodyFaces,'uint32');pass.drawIndexed(this.cloth.scene.body_faces.length*3);}
  pass.setBindGroup(0,this.clothBind);pass.setIndexBuffer(this.cloth.faces,'uint32');pass.drawIndexed(this.cloth.scene.faces.length*3);pass.end();
 }
 setFabricColors(base,overrides={}){
  const values=new Float32Array(this.cloth.n*4),cache=new Map();
  for(let i=0;i<this.cloth.n;i++){
   const hex=overrides[this.cloth.scene.vertex_panels?.[i]]||base;
   if(!cache.has(hex))cache.set(hex,[...[1,3,5].map(j=>(parseInt(hex.slice(j,j+2),16)/255)**2.2),1]);
   values.set(cache.get(hex),i*4);
  }
  this.device.queue.writeBuffer(this.clothColors,0,values);this.clothView.color=[1,1,1,this.clothView.color[3]];this.dirty=true;
 }
 destroy(){this.controls.destroy();this.resizeObserver.disconnect();this.depth?.destroy();for(const b of this.buffers)b.destroy();}
}
