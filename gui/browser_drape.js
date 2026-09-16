import {Cloth} from '/webgpu/physics.js?v=18';
import {Renderer} from '/webgpu/render.js?v=22';

// GPU objects live outside Vue's reactive graph. Each mounted stage owns one
// device and one loop; a serialized loader discards obsolete scene requests.
const engines = new WeakMap();
const linear = hex => [1,3,5].map(i => (parseInt(hex.slice(i,i+2),16)/255)**2.2);
// Six seconds of cloth motion prepares a useful drape without running the GPU
// indefinitely while editing a pattern. This is a warm-up, not a convergence test.
const WARMUP_SECONDS=6;

export default {
  template: `<div class="se-browser-drape" :data-state="state" :data-scene="loadedScene" :data-frames="frames">
    <canvas ref="canvas" data-se-local aria-label="Interactive 3D garment" :style="{visibility: ready && !preparing && !error ? 'visible' : 'hidden', cursor: 'grab'}"
      @pointerdown="wake" @pointermove="$event.buttons && wake()" @wheel="wake" @keydown="wake"></canvas>
    <div v-if="!ready || preparing || error || failure" class="se-drape-message" role="status">
      <div v-if="!(error || failure) && (preparing || scene_url)" class="se-drape-loader"></div>
      <strong>{{ error || failure || (preparing ? 'Preparing your pattern for 3D…' : progress) }}</strong>
      <span v-if="!(error || failure)">Cloth simulation runs in your browser.</span>
      <button v-if="error || failure" @click="retry">Retry preview</button>
    </div>
    <div v-if="ready && !preparing && !error && !failure" class="se-drape-controls">
      <span v-if="hasSupport && support" class="se-drape-support-note">Neckline held · fitting aid</span>
      <button data-se-local class="se-drape-icon" @click="paused = !paused" :aria-label="paused ? 'Resume' : 'Pause'" :title="paused ? 'Resume simulation' : 'Pause simulation'" :aria-pressed="paused">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path v-if="paused" d="m9 5 10 7-10 7Z"/><path v-else d="M9 5v14M15 5v14"/></svg>
      </button>
      <button data-se-local class="se-drape-icon" @click="reset" aria-label="Reset" title="Reset simulation">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 10a8 8 0 1 1 1.8 7M4 4v6h6"/></svg>
      </button>
      <button data-se-local class="se-drape-icon" @click="center" aria-label="Recenter" title="Recenter view">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4"/><circle cx="12" cy="12" r="3"/></svg>
      </button>
      <details class="se-drape-more" @keydown.esc.prevent="$event.currentTarget.open = false">
        <summary class="se-drape-icon" aria-label="More 3D controls" title="More 3D controls">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>
        </summary>
        <div class="se-drape-menu">
          <span class="se-drape-live" role="status">{{ paused ? 'Paused' : 'Live drape · ' + fps + ' fps' }}</span>
          <button @click="front">Front view</button>
          <label><input type="checkbox" :checked="show_body" @change="$emit('show-body',{value:$event.target.checked})"> Show mannequin</label>
          <button v-if="hasButtons" @click="toggleButtons">{{buttonsClosed ? 'Unbutton shirt' : 'Button shirt'}}</button>
          <label v-if="hasSupport"><input type="checkbox" v-model="support" @change="setSupport"> Hold neckline <small>(fitting aid)</small></label>
          <small>{{paused ? 'Drag to inspect the paused drape' : 'Drag left / right to turn the mannequin'}}<br>Drag up / down to change view<br>Shift-drag or right-drag to pan · Scroll to zoom<br>Touch: two fingers to pan or pinch to zoom</small>
        </div>
      </details>
    </div>
    <details v-if="ready && !preparing && !error" class="se-drape-body-note">
      <summary>{{bodyNote}}</summary>
      <div class="se-drape-fit-details">
        <p>Checked dimensions in cm. Other proportions are estimated from the template.</p>
        <table v-if="fitRows.length"><thead><tr><th>Measurement</th><th>Profile</th><th>Mannequin</th></tr></thead>
          <tbody><tr v-for="r in fitRows" :key="r.key"><td>{{r.label}}</td><td>{{r.target}}</td><td>{{r.actual}}</td></tr></tbody></table>
        <p>This approximates body shape; it does not certify garment fit.</p>
      </div>
    </details>
  </div>`,
  props: {scene_url:String, active:Boolean, docked:Boolean, preparing:Boolean, error:String,
    fabric_color:String, panel_colors:Object, panel_fabrics:Object, body_color:String, show_body:Boolean},
  data: () => ({ready:false, warmed:false, progress:'Choose a garment to preview.', failure:'', paused:false,
    fps:0, frames:0, loadedScene:'', hasSupport:false, support:false,
    bodyNote:'Default mannequin',fitRows:[],hasButtons:false,buttonsClosed:true}),
  computed: {
    state() {return this.error || this.failure ? 'error' : !this.preparing && !this.scene_url ? 'empty' : this.preparing || !this.ready ? 'preparing' :
      this.paused ? 'paused' : this.active ? 'running' : this.warmed ? 'ready' : 'warming';},
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
    active() {const e=engines.get(this);if(e?.cloth)this.frames=e.cloth.frame;if(e){e.last=null;e.stats=performance.now();e.count=0;if(e.renderer)e.renderer.dirty=true;}this.load();},
    paused() {const e=engines.get(this);if(e?.cloth)this.frames=e.cloth.frame;if(e?.renderer)e.renderer.controls.viewOnly=this.paused;if(e){e.last=null;e.stats=performance.now();e.count=0;}if(!this.paused)this.wake();},
    fabric_color() {this.appearance();},
    panel_colors: {deep:true, handler() {this.appearance();}},
    panel_fabrics: {deep:true, handler() {this.appearance();}},
    body_color() {this.appearance();}, show_body() {this.appearance();},
  },
  methods: {
    async load() {
      const e=engines.get(this);
      if(!e || e.disposed || e.loading || (this.scene_url && e.url===this.scene_url))return;
      if(!this.scene_url){this.ready=false;this.progress='Choose a garment to preview.';return;}
      const generation=e.generation, url=this.scene_url;
      e.loading=true;e.last=null; this.ready=false;this.warmed=false; this.failure=''; this.progress='Starting browser simulation…';
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
        const previousCamera=e.renderer ? {...e.renderer.camera,target:[...e.renderer.camera.target],pan:[...(e.renderer.camera.pan||[0,0])]} : null;
        e.renderer?.destroy();e.renderer=null;e.cloth?.destroy();e.cloth=null;
        cloth=await Cloth.create(e.device,scene,()=>{this.progress='Preparing cloth and mannequin in your browser…';});
        if(generation!==e.generation || e.disposed){cloth.destroy();cloth=null;return;}
        e.cloth=cloth;cloth=null;
        e.renderer=new Renderer(e.device,this.$refs.canvas,e.cloth,navigator.gpu.getPreferredCanvasFormat(),{systemTheme:true});
        const height=scene.body_fit?.measurements?.height?.actual_cm/100 || 1.72;
        e.defaultCamera={yaw:0,pitch:0,distance:height*1.9,target:[...e.cloth.motion.center],pan:[0,0]};
        Object.assign(e.renderer.camera,{...(previousCamera || e.defaultCamera),target:[...e.defaultCamera.target],pan:[...(previousCamera?.pan||[0,0])]});
        this.bodyNote=scene.body_note || 'Default mannequin';
        const labels={height:'Height',bust:'Bust',underbust:'Underbust',waist:'Waist',hips:'Hips',wrist:'Wrist (avg.)',leg_circ:'Thigh (avg.)'};
        this.fitRows=Object.entries(scene.body_fit?.measurements || {}).map(([key,r])=>({key,label:labels[key]||key,target:r.target_cm,actual:r.actual_cm}));
        e.url=url;e.warmupRemaining=WARMUP_SECONDS;this.loadedScene=scene.name;this.frames=0;this.fps=0;
        this.hasSupport=e.cloth.supportTargets.length>0;this.support=e.cloth.settings.holdNeckline;
        this.hasButtons=scene.buttons?.some(b=>b.hole)||false;this.buttonsClosed=true;
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
        const visible=this.active && this.$el.getClientRects().length>0;
        const simulate=!this.paused && (visible || !this.warmed);
        if(document.hidden || !simulate)e.last=null;
        const interval=1000/(visible?60:30);
        if(!document.hidden && this.ready && !this.preparing && !this.error && !this.failure && !e.loading &&
           ((simulate && now-(e.last||0)>=interval-.8) || e.renderer.dirty)){
          const advance=simulate && now-(e.last||0)>=interval-.8;
          const encoder=e.device.createCommandEncoder();
          if(advance){
            const elapsed=visible?(e.last==null?1/60:Math.min(1/30,(now-e.last)/1000)):1/30;
            e.cloth.encode(encoder,null,elapsed);e.last=now;e.count=(e.count||0)+1;
            e.warmupRemaining=Math.max(0,e.warmupRemaining-elapsed);this.warmed=e.warmupRemaining<1e-6;
          }
          // Draw once when warmed (or appearance changes); intermediate hidden
          // steps only need compute. The final canvas is ready before switching.
          if(visible || this.docked || e.renderer.dirty || this.warmed)e.renderer.render(encoder);
          e.device.queue.submit([encoder.finish()]);
          if(now-(e.stats||0)>500){this.frames=e.cloth.frame;this.fps=Math.round((e.count||0)*1000/(now-(e.stats||0)));e.stats=now;e.count=0;}
          await e.device.queue.onSubmittedWorkDone();
        }
      } catch(error) {if(!e.disposed)this.failure=error.message || String(error);}
      if(!e.disposed)e.frame=requestAnimationFrame(t=>this.tick(t));
    },
    appearance() {
      const e=engines.get(this);if(!e?.renderer)return;
      e.renderer.setFabricColors(this.fabric_color,this.panel_colors);
      if(this.panel_fabrics)e.renderer.setFabricPrints(this.panel_fabrics);
      e.renderer.bodyView.color=[...linear(this.body_color),0];
      e.renderer.showBody=this.show_body;e.renderer.dirty=true;
    },
    wake() {const e=engines.get(this);if(e?.cloth && !this.paused && !this.active){e.warmupRemaining=Math.max(e.warmupRemaining,1.2);this.warmed=false;}},
    reset() {const e=engines.get(this);e.cloth?.reset();e.last=null;e.warmupRemaining=WARMUP_SECONDS;this.warmed=false;this.frames=0;this.paused=false;this.buttonsClosed=true;},
    front() {this.wake();const e=engines.get(this);if(!this.paused)e.cloth.motion.front();e.renderer.camera.yaw=this.paused?e.cloth.motion.yaw:0;e.renderer.camera.pitch=0;e.renderer.dirty=true;},
    center() {const e=engines.get(this);Object.assign(e.renderer.camera,{...e.defaultCamera,target:[...e.defaultCamera.target],pan:[0,0]});e.renderer.dirty=true;},
    setSupport() {engines.get(this).cloth.settings.holdNeckline=this.support;},
    toggleButtons() {const e=engines.get(this);this.buttonsClosed=!this.buttonsClosed;e.cloth.scene.buttons.forEach((_,i)=>e.cloth.setButton(i,this.buttonsClosed));this.paused=false;this.wake();},
    retry() {const e=engines.get(this);e.url='';this.failure='';if(this.error)this.$emit('retry');else this.load();},
  },
};
