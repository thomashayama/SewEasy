// Small rigid attachments read the current cloth positions directly on GPU.
// The continuous sewn placket remains the solver's closed-shirt approximation.
const shader=`
struct View { mvp:mat4x4<f32>, eye:vec4<f32>, color:vec4<f32>, angle:vec4<f32>, center:vec4<f32> }
struct Button { ids:vec4<u32>, weights:vec4<f32>, style:vec4<f32> }
struct Out { @builtin(position) clip:vec4<f32>, @location(0) normal:vec3<f32>, @location(1) local:vec2<f32> }
@group(0) @binding(0) var<uniform> view:View;
@group(0) @binding(1) var<storage,read> cloth:array<vec4<f32>>;
@group(0) @binding(2) var<storage,read> buttons:array<Button>;
@vertex fn vertex(@location(0) p:vec3<f32>,@location(1) n:vec3<f32>,@builtin(instance_index) i:u32)->Out{
 let b=buttons[i];let a=cloth[b.ids.x].xyz;let c=cloth[b.ids.y].xyz;let d=cloth[b.ids.z].xyz;
 let edge=c-a;let crossn=cross(edge,d-a);let normal=crossn/max(length(crossn),1e-9)*b.style.x;
 let tangent=edge/max(length(edge),1e-9);let across=cross(normal,tangent);
 let center=a*b.weights.x+c*b.weights.y+d*b.weights.z;
 let world=center+(tangent*p.x+across*p.y+normal*p.z)*b.weights.w+normal*.0007;
 var o:Out;o.clip=view.mvp*vec4<f32>(world,1);o.normal=tangent*n.x+across*n.y+normal*n.z;o.local=p.xy;return o;
}
@fragment fn fragment(o:Out)->@location(0) vec4<f32>{
 // Four real holes in the cap; a short thread spans each pair.
 let hole=length(abs(o.local)-vec2<f32>(.23));
 if(hole<.105){discard;}
 let thread=abs(abs(o.local.y)-.23)<.035&&abs(o.local.x)<.23;
 let light=.42+.55*max(dot(normalize(o.normal),normalize(vec3<f32>(-.4,1,.8))),0.0);
 let color=select(vec3<f32>(.87,.85,.79),vec3<f32>(.33,.32,.3),thread);
 return vec4<f32>(pow(color*light,vec3<f32>(1.0/2.2)),1);
}`;

export class Buttons {
 constructor(device,cloth,view,format){
  this.count=cloth.scene.buttons?.length||0;this.buffers=[];if(!this.count)return;
  const make=(array,usage)=>{const b=device.createBuffer({size:array.byteLength,usage:usage|GPUBufferUsage.COPY_DST});device.queue.writeBuffer(b,0,array);this.buffers.push(b);return b;};
  const raw=new ArrayBuffer(this.count*48),u=new Uint32Array(raw),f=new Float32Array(raw);
  cloth.scene.buttons.forEach((b,i)=>{u.set([...b.ids,0],i*12);f.set([...b.weights,b.radius_m],i*12+4);f.set([b.normal_sign,0,0,0],i*12+8);});
  const anchors=make(new Uint8Array(raw),GPUBufferUsage.STORAGE);
  const vertices=[],segments=24;
  const vertex=(angle,r,z,nr,nz)=>[Math.cos(angle)*r,Math.sin(angle)*r,z,Math.cos(angle)*nr,Math.sin(angle)*nr,nz];
  for(let i=0;i<segments;i++){
   const a=i*2*Math.PI/segments,b=(i+1)*2*Math.PI/segments;
   vertices.push(...[0,0,.20,0,0,1],...vertex(a,.78,.20,0,1),...vertex(b,.78,.20,0,1));
   for(const [r0,z0,r1,z1,nr,nz] of [[.78,.20,1,.1,.5,.866],[1,.1,1,0,1,0]]){
    const p=vertex(a,r0,z0,nr,nz),q=vertex(b,r0,z0,nr,nz),r=vertex(a,r1,z1,nr,nz),s=vertex(b,r1,z1,nr,nz);
    vertices.push(...p,...r,...q,...q,...r,...s);
   }
  }
  this.vertexCount=vertices.length/6;this.vertices=make(new Float32Array(vertices),GPUBufferUsage.VERTEX);
  const module=device.createShaderModule({code:shader});
  this.pipeline=device.createRenderPipeline({layout:'auto',vertex:{module,entryPoint:'vertex',buffers:[{arrayStride:24,attributes:[{shaderLocation:0,offset:0,format:'float32x3'},{shaderLocation:1,offset:12,format:'float32x3'}]}]},fragment:{module,entryPoint:'fragment',targets:[{format}]},primitive:{topology:'triangle-list',cullMode:'none'},depthStencil:{format:'depth24plus',depthWriteEnabled:true,depthCompare:'less'}});
  this.bind=device.createBindGroup({layout:this.pipeline.getBindGroupLayout(0),entries:[{binding:0,resource:{buffer:view}},{binding:1,resource:{buffer:cloth.q}},{binding:2,resource:{buffer:anchors}}]});
 }
 render(pass){if(!this.count)return;pass.setPipeline(this.pipeline);pass.setBindGroup(0,this.bind);pass.setVertexBuffer(0,this.vertices);pass.draw(this.vertexCount,this.count);}
 destroy(){for(const b of this.buffers)b.destroy();}
}
