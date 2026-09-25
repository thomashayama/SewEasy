import {buffer} from './physics.js?v=21';
import {cameraControls,framingScale} from './camera.js?v=15';
import {Buttons} from './buttons.js?v=3';
import {lightBackground,watchSystemBackground} from './appearance.js?v=1';
import {STRAND_M,coveredHead,hairMesh} from './hair.js?v=1';

function normalize(v){const l=Math.hypot(...v)||1;return v.map(x=>x/l);}
function cross(a,b){return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}
function dot(a,b){return a.reduce((s,v,i)=>s+v*b[i],0);}
const toLinear=hex=>[1,3,5].map(j=>(parseInt(hex.slice(j,j+2),16)/255)**2.2);
function multiply(a,b){const r=new Float32Array(16);for(let c=0;c<4;c++)for(let row=0;row<4;row++)for(let k=0;k<4;k++)r[c*4+row]+=a[k*4+row]*b[c*4+k];return r;}
export function cameraMatrix(eye,target,aspect,pan=[0,0]){
 const z=normalize(eye.map((x,i)=>x-target[i])),x=normalize(cross([0,1,0],z)),y=cross(z,x);
 const view=[x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1];
 const f=1/Math.tan(35*Math.PI/360),near=.01,far=50;
 const projection=[f/aspect,0,0,0,0,f,0,0,0,0,far/(near-far),-1,0,0,far*near/(near-far),0];
 // Lens shift changes framing without moving the orbit or physics pivot.
 const distance=Math.hypot(...eye.map((v,i)=>v-target[i]));
 projection[8]=-pan[0]*f/aspect/distance;projection[9]=-pan[1]*f/distance;
 return multiply(projection,view);
}
const shader=`
struct View { mvp: mat4x4<f32>, eye: vec4<f32>, color: vec4<f32>, angle:vec4<f32>, center:vec4<f32> }
struct Out { @builtin(position) clip: vec4<f32>, @location(0) world: vec3<f32>, @location(1) normal: vec3<f32>, @location(2) strain:f32, @location(3) color:vec3<f32>, @location(4) uv:vec2<f32>, @location(5) motif:vec2<f32>, @location(6) fg:vec3<f32>, @location(7) bg:vec3<f32>, @location(8) @interpolate(flat) panel:u32, @location(9) @interpolate(flat) layers:vec2<f32>, @location(10) @interpolate(flat) mapsize:vec4<f32> }
struct Hole { seat:vec4<f32>, shape:vec4<f32> }
@group(0) @binding(0) var<uniform> view: View;
@group(0) @binding(1) var<storage, read> positions: array<vec4<f32>>;
@group(0) @binding(2) var<storage, read> normals: array<vec4<f32>>;
@group(0) @binding(3) var<storage, read> colors: array<vec4<f32>>;
@group(0) @binding(4) var<storage, read> uv: array<vec2<f32>>;
@group(0) @binding(5) var<storage, read> fabrics: array<vec4<f32>>;
@group(0) @binding(6) var<storage, read> panels: array<u32>;
@group(0) @binding(7) var<storage, read> holes: array<Hole>;
@group(0) @binding(8) var maps: texture_2d_array<f32>;
@group(0) @binding(9) var mapSampler: sampler;
fn turn(v:vec3<f32>)->vec3<f32>{let cs=view.angle.xy;return vec3<f32>(cs.x*v.x+cs.y*v.z,v.y,-cs.y*v.x+cs.x*v.z);}
@vertex fn vertex(@builtin(vertex_index) id: u32) -> Out {
 var o:Out;o.world=view.center.xyz+turn(positions[id].xyz-view.center.xyz);o.clip=view.mvp*vec4<f32>(o.world,1);o.normal=turn(normals[id].xyz);o.strain=normals[id].w;o.color=colors[id].rgb;
 let fi=min(id,arrayLength(&fabrics)/4u-1u)*4u;o.motif=fabrics[fi].xy;o.layers=fabrics[fi].zw;o.fg=fabrics[fi+1u].rgb;o.bg=fabrics[fi+2u].rgb;o.mapsize=fabrics[fi+3u];o.uv=uv[min(id,arrayLength(&uv)-1u)];o.panel=panels[min(id,arrayLength(&panels)-1u)];return o;
}
@fragment fn fragment(o:Out,@builtin(front_facing) front:bool)->@location(0) vec4<f32>{
 // An imported base-colour map repeats at its physical size in rest-pattern
 // metres; the wrong side of the cloth may carry its own map. Image rows run
 // down the cloth while rest v runs up it. Sampled before any discard.
 let mapSize=max(select(o.mapsize.zw,o.mapsize.xy,front),vec2<f32>(.0001));
 let texel=textureSample(maps,mapSampler,vec2<f32>(o.uv.x,-o.uv.y)/mapSize,i32(select(o.layers.y,o.layers.x,front)+.5)).rgb;
 var stitching=0.0;
 for(var i=0u;i<arrayLength(&holes);i++){
  let h=holes[i];if(o.panel==0u||o.panel!=u32(h.shape.z)){continue;}
  let d=o.uv-h.seat.xy;let along=abs(dot(d,h.seat.zw));let across=dot(d,vec2<f32>(-h.seat.w,h.seat.z));
  let distance=length(vec2<f32>(max(along-h.shape.x,0.0),across));
  if(distance<h.shape.y){discard;}
  stitching=max(stitching,1.0-smoothstep(h.shape.y,h.shape.y+.0008,distance));
 }
 let n=normalize(o.normal)*select(-1.0,1.0,front);let l=normalize(vec3<f32>(-0.4,1,0.8));
 let fill=max(dot(n,normalize(vec3<f32>(0.8,0.5,-1))),0.0);
 let light=0.32+0.63*max(dot(n,l),0.0)+0.18*fill;
 let v=normalize(view.eye.xyz-o.world);let rim=pow(1.0-max(dot(n,v),0.0),3.0)*0.07;
 let t=clamp((o.strain-1.0)/.2,0.0,1.0);
 let heat=select(mix(vec3<f32>(.03,.2,.5),vec3<f32>(.8,.38,.015),t*2.0),mix(vec3<f32>(.8,.38,.015),vec3<f32>(.65,.02,.015),(t-.5)*2.0),t>.5);
 let p=o.uv/max(o.motif.y,.001);let aa=max(fwidth(p),vec2<f32>(.002));let f=fract(p);
 var ink=0.0;let kind=u32(o.motif.x+.5);
 if(kind==1u){ink=1.0-smoothstep(.083-aa.x,.083+aa.x,f.x);}
 if(kind==2u){ink=1.0-smoothstep(.5-aa.x,.5+aa.x,f.x);}
 if(kind==3u){let shift=vec2<f32>(f32(u32(abs(floor(p.y)))%2u)*.5,0);let d=length(fract(p+shift+.5)-.5);ink=1.0-smoothstep(.28-length(aa),.28+length(aa),d);}
 if(kind==4u){ink=(1.0-smoothstep(.5-aa.x,.5+aa.x,f.x)+1.0-smoothstep(.5-aa.y,.5+aa.y,f.y))*.5;}
 if(kind==5u){let lines=vec2<f32>(1)-smoothstep(vec2<f32>(.045)-aa,vec2<f32>(.045)+aa,f);ink=max(lines.x,lines.y);}
 // Hair: each strand across the flow gets its own shade, fading to the mean
 // once strands are finer than a pixel, so a full-length view does not shimmer.
 // Computed for every fragment: derivatives must stay in uniform control flow.
 let s=o.uv.x/max(o.motif.y,.0002);let shade=fract(sin(floor(s)*12.9898)*43758.5453);
 let along=.93+.07*sin(o.uv.y*90.0+shade*6.2832);
 let detail=1.0-smoothstep(.35,.9,fwidth(s));
 let isHair=kind==7u;
 let strands=select(1.0,mix(1.0,mix(.72,1.2,shade)*along,detail),isHair);
 let sheen=select(0.0,pow(max(dot(n,normalize(l+v)),0.0),28.0)*.16,isHair);
 let printed=select(select(view.color.rgb*o.color*strands,mix(o.bg,o.fg,ink),kind>0u&&kind<6u),texel,kind==6u);
 let color=select(printed*(1.0-.45*stitching),heat,view.color.a>.5);
 return vec4<f32>(pow(color*light+rim+sheen,vec3<f32>(1.0/2.2)),1);
}`;
export const FABRIC_STRIDE=16,FABRIC_KINDS=['plain','pinstripe','stripe','polka_dot','gingham','windowpane','texture'];
// Per vertex: [kind, print spacing m, front layer, back layer], fg, bg, [front w,h, back w,h] in metres.
export function fabricRecords(vertexPanels,specs,textures={},layers=new Map()){
 const data=new Float32Array(vertexPanels.length*FABRIC_STRIDE),linear=hex=>[1,3,5].map(j=>(parseInt(hex.slice(j,j+2),16)/255)**2.2);
 const metres=map=>(map?.size_mm||[10,10]).map(v=>Math.max(.0001,Number(v)*.001));
 for(let i=0;i<vertexPanels.length;i++){
  const spec=specs?.[vertexPanels[i]];if(!spec)continue;
  const maps=spec.kind==='texture'?textures?.[spec.texture]:null,front=layers.get(maps?.front?.image),back=layers.get(maps?.back?.image);
  // A map that has not loaded, or never will, leaves the piece its plain colour.
  const kind=spec.kind==='texture'?(front===undefined?0:6):Math.max(0,FABRIC_KINDS.indexOf(spec.kind));
  data.set([kind,Math.max(.01,Number(spec.scale)||1)*.01,front??0,back??front??0,...linear(spec.fg),0,...linear(spec.bg),0,
   ...metres(maps?.front),...metres(back===undefined?maps?.front:maps?.back)],i*FABRIC_STRIDE);
 }
 return data;
}
export class Renderer {
 constructor(device,canvas,cloth,format,{systemTheme=false,transparent=false}={}){
  this.device=device;this.canvas=canvas;this.cloth=cloth;this.format=format;this.dirty=true;
  // Thumbnails keep their alpha so the page can supply a theme-aware backdrop.
  this.background=transparent?{r:0,g:0,b:0,a:0}:lightBackground;
  if(systemTheme)this.stopTheme=watchSystemBackground(color=>{this.background=color;this.dirty=true;});
  this.resizeObserver=new ResizeObserver(()=>this.dirty=true);this.resizeObserver.observe(canvas);
  this.context=canvas.getContext('webgpu');this.context.configure({device,format,alphaMode:transparent?'premultiplied':'opaque',usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.COPY_SRC});
  this.camera={yaw:0,pitch:0,distance:2.3,target:[0,1.2,0],pan:[0,0]};this.buffers=[];this.showBody=true;
  this.clothColors=buffer(device,new Float32Array(cloth.n*4).fill(1),GPUBufferUsage.STORAGE);
  this.bodyColors=buffer(device,new Float32Array(cloth.scene.body_vertices.length*4).fill(1),GPUBufferUsage.STORAGE);
  this.buffers.push(this.clothColors,this.bodyColors);
  this.fabricData=buffer(device,new Float32Array(cloth.n*FABRIC_STRIDE),GPUBufferUsage.STORAGE);
  this.emptyFabric=buffer(device,new Float32Array(FABRIC_STRIDE),GPUBufferUsage.STORAGE);
  this.emptyUV=buffer(device,new Float32Array(4),GPUBufferUsage.STORAGE);
  this.buffers.push(this.fabricData,this.emptyFabric,this.emptyUV);
  const panelNames=[...new Set(cloth.scene.vertex_panels)],panelIds=new Map(panelNames.map((p,i)=>[p,i+1]));
  this.panelIds=buffer(device,Uint32Array.from(cloth.scene.vertex_panels,p=>panelIds.get(p)),GPUBufferUsage.STORAGE);
  this.emptyPanels=buffer(device,new Uint32Array(1),GPUBufferUsage.STORAGE);
  const holeData=(cloth.scene.buttons||[]).filter(b=>b.hole?.uv_center).flatMap(b=>[...b.hole.uv_center,...b.hole.uv_direction,b.radius_m*.95,.00065,panelIds.get(b.hole.panel),0]);
  this.holes=buffer(device,new Float32Array(holeData.length?holeData:new Array(8).fill(0)),GPUBufferUsage.STORAGE);
  this.buffers.push(this.panelIds,this.emptyPanels,this.holes);
  const makeUniform=color=>{const b=buffer(device,new Float32Array(32),GPUBufferUsage.UNIFORM);this.buffers.push(b);return {buffer:b,color};};
  this.clothView=makeUniform([0.18,0.40,0.59,0]);this.bodyView=makeUniform([0.72,0.64,0.57,0]);
  // Hair turns with the mannequin, so it shares the body's motion; no hair until asked for.
  this.hairView=makeUniform([.04,.02,.015,0]);this.hair=null;this.hairKey='none';
  this.buttons=new Buttons(device,cloth,this.clothView.buffer,format);
  const module=device.createShaderModule({code:shader});
  this.pipeline=device.createRenderPipeline({layout:'auto',vertex:{module,entryPoint:'vertex'},fragment:{module,entryPoint:'fragment',targets:[{format}]},primitive:{topology:'triangle-list',cullMode:'none'},depthStencil:{format:'depth24plus',depthWriteEnabled:true,depthCompare:'less'}});
  this.mapSampler=device.createSampler({addressModeU:'repeat',addressModeV:'repeat',magFilter:'linear',minFilter:'linear',mipmapFilter:'linear',maxAnisotropy:4});
  this.maps=this.mapTexture(1,1,1);this.mapLayers=new Map();this.textures={};
  this.rebind();
  canvas.tabIndex=0;
  this.controls=cameraControls(this.camera,canvas,()=>this.dirty=true,cloth.motion);
  this.setFabricPrints();
  if(cloth.scene.panel_colors)this.setFabricColors('#b7cde5',cloth.scene.panel_colors);
  // Pieces keep their plain colour until their maps arrive; capture() waits.
  this.texturesReady=this.loadTextures().catch(()=>{});
 }
 mapTexture(size,layers,levels){return this.device.createTexture({size:[size,size,layers],format:'rgba8unorm-srgb',mipLevelCount:levels,usage:GPUTextureUsage.TEXTURE_BINDING|GPUTextureUsage.COPY_DST|GPUTextureUsage.RENDER_ATTACHMENT});}
 rebind(){
  const cloth=this.cloth,maps=this.maps.createView({dimension:'2d-array'});
  const bind=(uniform,q,n,color,uv,fabric,panels)=>this.device.createBindGroup({layout:this.pipeline.getBindGroupLayout(0),entries:[{binding:0,resource:{buffer:uniform}},{binding:1,resource:{buffer:q}},{binding:2,resource:{buffer:n}},{binding:3,resource:{buffer:color}},{binding:4,resource:{buffer:uv}},{binding:5,resource:{buffer:fabric}},{binding:6,resource:{buffer:panels}},{binding:7,resource:{buffer:this.holes}},{binding:8,resource:maps},{binding:9,resource:this.mapSampler}]});
  this.clothBind=bind(this.clothView.buffer,cloth.q,cloth.normals,this.clothColors,cloth.uv,this.fabricData,this.panelIds);this.bodyBind=bind(this.bodyView.buffer,cloth.body,cloth.bodyNormals,this.bodyColors,this.emptyUV,this.emptyFabric,this.emptyPanels);
  if(this.hair){const b=this.hair.buffers;this.hairBind=bind(this.hairView.buffer,b.positions,b.normals,b.colors,b.uv,b.fabric,b.panels);}
 }
 // Style 'none', 'short' or 'bun' (hair.js) in a '#rrggbb' colour. Shaped from
 // this scene's fitted head; hidden while a hood covers it.
 setHair(style='none',color=null){
  const key=coveredHead(this.cloth.scene)?'none':style;
  if(key!==this.hairKey){
   this.dropHair();this.hairKey=key;
   const mesh=hairMesh(this.cloth.scene,key);
   if(mesh){
    const d=this.device,S=GPUBufferUsage.STORAGE,fabric=new Float32Array(mesh.count*FABRIC_STRIDE);
    for(let i=0;i<mesh.count;i++){fabric[i*FABRIC_STRIDE]=7;fabric[i*FABRIC_STRIDE+1]=STRAND_M;}
    const buffers={positions:buffer(d,mesh.positions,S),normals:buffer(d,mesh.normals,S),colors:buffer(d,new Float32Array(mesh.count*4).fill(1),S),
     uv:buffer(d,mesh.uv,S),fabric:buffer(d,fabric,S),panels:buffer(d,new Uint32Array(mesh.count),S),faces:buffer(d,mesh.faces,GPUBufferUsage.INDEX)};
    this.hair={buffers,count:mesh.faces.length};
   }
   this.rebind();
  }
  if(color)this.hairView.color=[...toLinear(color),0];
  this.dirty=true;
 }
 dropHair(){if(this.hair)for(const b of Object.values(this.hair.buffers))b.destroy();this.hair=null;this.hairBind=null;}
 async loadTextures(textures=this.cloth.scene.fabric_textures){
  const images=[...new Set(Object.values(textures||{}).flatMap(m=>[m?.front?.image,m?.back?.image]).filter(Boolean))];
  if(!images.length)return;
  // One square layer per map; the physical size, not the pixel aspect, sets its scale.
  // Every mip level is resampled from the source, so fine weaves do not shimmer.
  const size=512,levels=Math.log2(size)+1,texture=this.mapTexture(size,images.length,levels),layers=new Map();
  for(const [layer,url] of images.entries()){
   try{
    const blob=await (await fetch(url)).blob();
    for(let level=0;level<levels;level++){
     const s=size>>level,bitmap=await createImageBitmap(blob,{resizeWidth:s,resizeHeight:s,resizeQuality:'high'});
     this.device.queue.copyExternalImageToTexture({source:bitmap},{texture,mipLevel:level,origin:[0,0,layer]},[s,s]);bitmap.close();
    }
    layers.set(url,layer);
   }catch{/* An unreadable map leaves its pieces their plain colour. */}
  }
  if(this.destroyed){texture.destroy();return;}
  this.maps.destroy();this.maps=texture;this.mapLayers=layers;this.textures=textures;this.rebind();this.setFabricPrints(this.printSpecs);
 }
 render(encoder,querySet=null){
  this.dirty=false;
  const c=this.canvas,pixel=this.pixelRatio ?? Math.min(devicePixelRatio,2),w=this.outputSize?.[0] ?? Math.max(1,Math.round(c.clientWidth*pixel)),h=this.outputSize?.[1] ?? Math.max(1,Math.round(c.clientHeight*pixel));
  if(c.width!==w||c.height!==h||!this.depth){c.width=w;c.height=h;this.depth?.destroy();this.depth=this.device.createTexture({size:[w,h],format:'depth24plus',usage:GPUTextureUsage.RENDER_ATTACHMENT});}
  // Preserve the whole mannequin in the narrow inspector dock; expanding the
  // same canvas keeps the user's camera distance and pan unchanged.
  const v=this.camera,r=v.distance*framingScale(w,h),eye=[v.target[0]+r*Math.sin(v.yaw)*Math.cos(v.pitch),v.target[1]+r*Math.sin(v.pitch),v.target[2]+r*Math.cos(v.yaw)*Math.cos(v.pitch)];
  const mvp=cameraMatrix(eye,v.target,w/h,v.pan);
  for(const view of [this.clothView,this.bodyView,this.hairView]){const a=new Float32Array(32);a.set(mvp);a.set([...eye,1],16);a.set(view.color,20);a.set(view===this.clothView?[1,0,1,0,0,0,0,0]:this.cloth.motion.uniform(),24);this.device.queue.writeBuffer(view.buffer,0,a);}
  const pass=encoder.beginRenderPass({colorAttachments:[{view:this.context.getCurrentTexture().createView(),clearValue:this.background,loadOp:'clear',storeOp:'store'}],depthStencilAttachment:{view:this.depth.createView(),depthClearValue:1,depthLoadOp:'clear',depthStoreOp:'store'},...(querySet?{timestampWrites:{querySet,beginningOfPassWriteIndex:2,endOfPassWriteIndex:3}}:{})});
  pass.setPipeline(this.pipeline);
  if(this.showBody){pass.setBindGroup(0,this.bodyBind);pass.setIndexBuffer(this.cloth.bodyFaces,'uint32');pass.drawIndexed(this.cloth.scene.body_faces.length*3);}
  if(this.showBody&&this.hair){pass.setBindGroup(0,this.hairBind);pass.setIndexBuffer(this.hair.buffers.faces,'uint32');pass.drawIndexed(this.hair.count);}
  pass.setBindGroup(0,this.clothBind);pass.setIndexBuffer(this.cloth.faces,'uint32');pass.drawIndexed(this.cloth.scene.faces.length*3);this.buttons.render(pass);pass.end();
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
 setFabricPrints(specs=this.cloth.scene.panel_fabrics){
  this.printSpecs=specs;
  this.device.queue.writeBuffer(this.fabricData,0,fabricRecords(this.cloth.scene.vertex_panels,specs,this.textures,this.mapLayers));this.dirty=true;
 }
 async capture(){
  await this.texturesReady;
  // Copy the rendered texture before presentation clears a WebGPU canvas.
  // Reading back the framebuffer avoids blank images from toDataURL races.
  const encoder=this.device.createCommandEncoder();this.render(encoder);
  const w=this.canvas.width,h=this.canvas.height,stride=Math.ceil(w*4/256)*256;
  const readback=this.device.createBuffer({size:stride*h,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});
  try{
   encoder.copyTextureToBuffer({texture:this.context.getCurrentTexture()},{buffer:readback,bytesPerRow:stride},[w,h]);
   this.device.queue.submit([encoder.finish()]);await readback.mapAsync(GPUMapMode.READ);
   const raw=new Uint8Array(readback.getMappedRange()),pixels=new Uint8ClampedArray(w*h*4),bgra=this.format.startsWith('bgra');
   for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const src=y*stride+x*4,dst=(y*w+x)*4;
    pixels[dst]=raw[src+(bgra?2:0)];pixels[dst+1]=raw[src+1];pixels[dst+2]=raw[src+(bgra?0:2)];pixels[dst+3]=raw[src+3];
   }
   const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;
   canvas.getContext('2d').putImageData(new ImageData(pixels,w,h),0,0);
   return canvas.toDataURL('image/webp',.88);
  }finally{readback.unmap();readback.destroy();}
 }
 destroy(){this.destroyed=true;this.dropHair();this.maps.destroy();this.stopTheme?.();this.controls.destroy();this.resizeObserver.disconnect();this.depth?.destroy();this.buttons.destroy();for(const b of this.buffers)b.destroy();}
}
