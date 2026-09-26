import {Cloth} from './physics.js?v=21';
import {Renderer} from './render.js?v=27';

export async function captureThumbnail(scene,canvas,onProgress=()=>{}){
  const adapter=await navigator.gpu.requestAdapter({powerPreference:'low-power'});
  if(!adapter)throw Error('WebGPU is unavailable on this device. The 2D pattern is ready.');
  const device=await adapter.requestDevice();let cloth,renderer,lost=false;
  device.lost.then(()=>{lost=true;});
  try{
    cloth=await Cloth.create(device,scene);
    renderer=new Renderer(device,canvas,cloth,navigator.gpu.getPreferredCanvasFormat(),{transparent:true});
    renderer.pixelRatio=1;renderer.outputSize=[384,448];renderer.controls.destroy();renderer.bodyView.color=[.72,.64,.57,0];
    for(let frame=0;frame<180;frame++){
      await new Promise(resolve=>requestAnimationFrame(resolve));
      if(lost)throw Error('Graphics connection lost. Retry when the browser is ready.');
      const encoder=device.createCommandEncoder();cloth.encode(encoder,null,1/30);
      if(frame%6===0)renderer.render(encoder);
      device.queue.submit([encoder.finish()]);
      await device.queue.onSubmittedWorkDone();onProgress(frame+1);
    }
    const positions=await cloth.readPositions();let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    for(const [x,y] of positions){if(Number.isFinite(x)&&Number.isFinite(y)){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}}
    if(!Number.isFinite(minX))throw Error('No settled garment geometry. Check the pattern.');
    const height=scene.body_fit?.measurements?.height?.actual_cm/100 || 1.72,upper=Object.values(scene.garment_types||{}).some(Boolean);
    const low=Math.max(-.05,minY-.08),high=upper?height+.06:maxY+.12;
    const distance=Math.max((high-low)/2,(maxX-minX)/2/(384/448))/Math.tan(35*Math.PI/360)*1.12;
    Object.assign(renderer.camera,{yaw:.2,pitch:.02,distance:Math.max(1,distance),target:[(minX+maxX)/2,(low+high)/2,0],pan:[0,0]});
    return await renderer.capture();
  }finally{renderer?.destroy();cloth?.destroy();device.destroy();}
}
