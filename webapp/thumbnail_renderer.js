const engines=new WeakMap();
const nextFrame=()=>new Promise(resolve=>requestAnimationFrame(resolve));

export default {
  // A measurable off-screen canvas. No controls, input or competing live loop.
  template:`<div aria-hidden="true" inert style="position:fixed;left:-10000px;top:0;width:384px;height:448px;pointer-events:none" :data-thumbnail-state="state" :data-thumbnail-key="job?.key || ''">
    <canvas ref="canvas" style="width:384px;height:448px"></canvas>
  </div>`,
  props:{job:Object},
  data:()=>({state:'starting'}),
  mounted(){
    const e={disposed:false,loading:false};engines.set(this,e);
    this.state=navigator.gpu?'idle':'unavailable';
    if(navigator.gpu)this.$emit('available');
  },
  beforeUnmount(){const e=engines.get(this);if(e){e.disposed=true;e.abort?.abort();e.device?.destroy();}},
  watch:{job(){if(this.job)this.renderJob();else this.state='idle';}},
  methods:{
    async renderJob(){
      const e=engines.get(this),job=this.job;
      if(!e || e.disposed || e.loading || !job)return;
      e.loading=true;this.state='rendering';let cloth,renderer;
      try{
        if(e.lost)throw Error('Browser graphics unavailable');
        // Cached library cards only need images. Do not download or parse the
        // cloth solver, shaders and renderer unless a missing image needs work.
        const [{Cloth},{Renderer}]=await Promise.all([
          import('/webgpu/physics.js?v=22'),import('/webgpu/render.js?v=29'),
        ]);
        if(e.disposed)return;
        if(!e.device){
          const adapter=await navigator.gpu.requestAdapter({powerPreference:'low-power'});
          if(!adapter)throw Error('Browser graphics unavailable');
          e.device=await adapter.requestDevice();
          if(e.disposed){e.device.destroy();return;}
          e.device.lost.then(()=>{if(!e.disposed){e.lost=true;this.state='unavailable';}});
        }
        e.abort=new AbortController();
        const response=await fetch(job.url,{signal:e.abort.signal});
        if(!response.ok)throw Error('Could not load thumbnail scene');
        const scene=await response.json();
        if(e.disposed)return;
        cloth=await Cloth.create(e.device,scene);
        renderer=new Renderer(e.device,this.$refs.canvas,cloth,navigator.gpu.getPreferredCanvasFormat(),{transparent:true});
        renderer.pixelRatio=1;
        renderer.controls.destroy();
        this.$refs.canvas.tabIndex=-1;
        renderer.bodyView.color=[.72,.64,.57,0];
        // Six seconds of simulated cloth settling, paced to leave the page
        // responsive. requestAnimationFrame also pauses work in hidden tabs.
        for(let frame=0;frame<180;frame++){
          await nextFrame();if(e.disposed)return;
          const encoder=e.device.createCommandEncoder();
          cloth.encode(encoder,null,1/30);
          e.device.queue.submit([encoder.finish()]);
          await e.device.queue.onSubmittedWorkDone();
        }
        const positions=await cloth.readPositions();
        let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
        for(const [x,y] of positions){if(Number.isFinite(x)&&Number.isFinite(y)){minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y);}}
        if(!Number.isFinite(minX))throw Error('No settled garment geometry');
        const height=scene.body_fit?.measurements?.height?.actual_cm/100 || 1.72;
        const upper=Object.values(scene.garment_types||{}).some(Boolean);
        const low=Math.max(-.05,minY-.08),high=upper?height+.06:maxY+.12;
        const distance=Math.max((high-low)/2,(maxX-minX)/2/(384/448))/Math.tan(35*Math.PI/360)*1.12;
        Object.assign(renderer.camera,{yaw:.2,pitch:.02,distance:Math.max(1,distance),target:[(minX+maxX)/2,(low+high)/2,0],pan:[0,0]});
        const image=await renderer.capture();
        if(!e.disposed){this.state='saved';this.$emit('thumbnail',{key:job.key,url:job.url,image});}
      }catch(error){
        if(!e.disposed){this.state='failed';this.$emit('failed',{key:job.key,url:job.url,message:error.message || String(error),fatal:!e.device || e.lost});}
      }finally{
        renderer?.destroy();cloth?.destroy();e.loading=false;
        if(this.job && this.job.url!==job.url && !e.disposed)this.renderJob();
      }
    },
  },
};
