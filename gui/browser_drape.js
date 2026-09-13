import {Cloth} from '/webgpu/physics.js?v=10';
import {Renderer} from '/webgpu/render.js?v=10';

// GPU objects live outside Vue's reactive graph. Each mounted stage owns one
// device and one loop; a serialized loader discards obsolete scene requests.
const engines = new WeakMap();
const linear = hex => [1,3,5].map(i => (parseInt(hex.slice(i,i+2),16)/255)**2.2);

export default {
  template: `<div class="se-browser-drape" :data-state="state" :data-scene="loadedScene" :data-frames="frames">
    <canvas ref="canvas" aria-label="Interactive 3D garment" :style="{visibility: ready && !preparing && !error ? 'visible' : 'hidden'}"></canvas>
    <div v-if="!ready || preparing || error || failure" class="se-drape-message" role="status">
      <div v-if="!(error || failure) && (preparing || scene_url)" class="se-drape-loader"></div>
      <strong>{{ error || failure || (preparing ? 'Preparing your pattern for 3D…' : progress) }}</strong>
      <span v-if="!(error || failure)">Cloth simulation runs in your browser.</span>
      <button v-if="error || failure" @click="retry">Retry preview</button>
    </div>
    <div v-if="ready && !preparing && !error && !failure" class="se-drape-controls">
      <span class="se-drape-live" role="status">{{ paused ? 'Paused' : 'Live drape · ' + fps + ' fps' }}</span>
      <button @click="paused = !paused">{{ paused ? 'Resume' : 'Pause' }}</button>
      <button @click="reset">Reset</button>
      <button @click="front">Front</button>
      <label v-if="hasSupport"><input type="checkbox" v-model="support" @change="setSupport"> Hold neckline <small>(fitting aid)</small></label>
      <small>Drag to orbit · Scroll to zoom</small>
    </div>
    <small v-if="ready && !error" class="se-drape-body-note">Standard mannequin · not matched to your measurements</small>
  </div>`,
  props: {scene_url:String, active:Boolean, preparing:Boolean, error:String,
    fabric_color:String, panel_colors:Object, body_color:String, show_body:Boolean},
  data: () => ({ready:false, progress:'Choose a garment to preview.', failure:'', paused:false,
    fps:0, frames:0, loadedScene:'', hasSupport:false, support:false}),
  computed: {
    state() {return this.error || this.failure ? 'error' : !this.preparing && !this.scene_url ? 'empty' : this.preparing || !this.ready ? 'preparing' :
      !this.active || this.paused ? 'paused' : 'running';},
  },
  mounted() {
    engines.set(this, {generation:0, disposed:false, loading:false, frame:0});
    this.load();
    this.tick();
  },
  beforeUnmount() {
    const e=engines.get(this); e.disposed=true; e.generation++; e.abort?.abort();
    cancelAnimationFrame(e.frame); e.renderer?.destroy(); e.cloth?.destroy(); e.device?.destroy();
  },
  watch: {
    scene_url() {const e=engines.get(this); if(e){e.generation++; e.abort?.abort(); this.load();}},
    active() {const e=engines.get(this);if(e?.cloth)this.frames=e.cloth.frame;if(e){e.stats=performance.now();e.count=0;}if(this.active)this.load();},
    paused() {const e=engines.get(this);if(e?.cloth)this.frames=e.cloth.frame;if(e){e.stats=performance.now();e.count=0;}},
    fabric_color() {this.appearance();},
    panel_colors: {deep:true, handler() {this.appearance();}},
    body_color() {this.appearance();}, show_body() {this.appearance();},
  },
  methods: {
    async load() {
      const e=engines.get(this);
      if(!e || e.disposed || e.loading || !this.active || (this.scene_url && e.url===this.scene_url))return;
      if(!this.scene_url){this.ready=false;this.progress='Choose a garment to preview.';return;}
      const generation=e.generation, url=this.scene_url;
      e.loading=true; this.ready=false; this.failure=''; this.progress='Starting browser simulation…';
      let cloth;
      try {
        if(!navigator.gpu)throw Error('WebGPU is unavailable. Open this page in a WebGPU-capable browser over HTTPS or localhost.');
        if(!e.device){
          const adapter=await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
          if(!adapter)throw Error('No WebGPU adapter is available. Enable browser hardware acceleration and reload.');
          const device=await adapter.requestDevice();
          if(e.disposed){device.destroy();return;}
          e.device=device;
          device.lost.then(()=>{if(!e.disposed && e.device===device){this.failure='Browser graphics stopped. Retry the preview.';e.device=null;e.url='';}});
          e.device.addEventListener('uncapturederror',event=>{this.failure=event.error.message;});
        }
        if(generation!==e.generation || e.disposed)return;
        e.abort=new AbortController();
        const response=await fetch(url,{signal:e.abort.signal});
        if(!response.ok)throw Error('Could not load the 3D pattern. Retry the preview.');
        const scene=await response.json();
        if(generation!==e.generation || e.disposed)return;
        // Wait for any previous submission before releasing its buffers.
        await e.device.queue.onSubmittedWorkDone();
        if(generation!==e.generation || e.disposed)return;
        e.renderer?.destroy();e.renderer=null;e.cloth?.destroy();e.cloth=null;
        cloth=await Cloth.create(e.device,scene,()=>{this.progress='Preparing cloth and mannequin in your browser…';});
        if(generation!==e.generation || e.disposed){cloth.destroy();cloth=null;return;}
        e.cloth=cloth;cloth=null;
        e.renderer=new Renderer(e.device,this.$refs.canvas,e.cloth,navigator.gpu.getPreferredCanvasFormat());
        e.url=url;this.loadedScene=scene.name;this.frames=0;this.fps=0;
        this.hasSupport=e.cloth.supportTargets.length>0;this.support=e.cloth.settings.holdNeckline;
        this.appearance();this.paused=false;this.ready=true;
        this.$emit('ready',{scene:scene.name});
      } catch(error) {
        cloth?.destroy();
        if(generation===e.generation && !e.disposed && error.name!=='AbortError'){
          this.failure=error.message || String(error); this.$emit('error',{message:this.failure});
        }
      } finally {
        e.loading=false;
        if(generation!==e.generation && !e.disposed)this.load();
      }
    },
    async tick(now=0) {
      const e=engines.get(this);if(!e || e.disposed)return;
      try {
        const visible=this.active && !document.hidden && this.$el.getClientRects().length>0;
        if(visible && this.ready && !this.preparing && !this.error && !this.failure && !e.loading &&
           ((!this.paused && now-(e.last||0)>=1000/60-.8) || e.renderer.dirty)){
          const advance=!this.paused && now-(e.last||0)>=1000/60-.8;
          const encoder=e.device.createCommandEncoder();
          if(advance){e.cloth.encode(encoder);e.last=now;e.count=(e.count||0)+1;}
          e.renderer.render(encoder);e.device.queue.submit([encoder.finish()]);
          if(now-(e.stats||0)>500){this.frames=e.cloth.frame;this.fps=Math.round((e.count||0)*1000/(now-(e.stats||0)));e.stats=now;e.count=0;}
          await e.device.queue.onSubmittedWorkDone();
        }
      } catch(error) {if(!e.disposed)this.failure=error.message || String(error);}
      if(!e.disposed)e.frame=requestAnimationFrame(t=>this.tick(t));
    },
    appearance() {
      const e=engines.get(this);if(!e?.renderer)return;
      e.renderer.setFabricColors(this.fabric_color,this.panel_colors);
      e.renderer.bodyView.color=[...linear(this.body_color),0];
      e.renderer.showBody=this.show_body;e.renderer.dirty=true;
    },
    reset() {const e=engines.get(this);e.cloth?.reset();this.frames=0;this.paused=false;},
    front() {const e=engines.get(this);e.renderer.camera.yaw=0;e.renderer.camera.pitch=0;e.renderer.dirty=true;},
    setSupport() {engines.get(this).cloth.settings.holdNeckline=this.support;},
    retry() {const e=engines.get(this);e.url='';this.failure='';if(this.error)this.$emit('retry');else this.load();},
  },
};
