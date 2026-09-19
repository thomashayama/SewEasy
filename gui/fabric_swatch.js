import {Cloth} from '/webgpu/physics.js?v=19';
import {Renderer} from '/webgpu/render.js?v=24';
import {swatchSettings,measureSwatch} from '/webgpu/swatch.js?v=1';

const engines=new WeakMap();
const colors=['#c28a44','#74b7ec'];
export default {
  template:`<div class="se-swatch" :data-state="failure?'error':!ready?'loading':paused?'paused':settled?'settled':'running'"
      :data-time="time" :data-reference-drop-mm="samples[0]?.drop_mm" :data-fabric-drop-mm="samples[1]?.drop_mm"
      :data-pin-error-mm="pinError" :data-control="equal" :data-strain="strain" :data-kernel-checks="checks">
    <div class="se-swatch-toolbar">
      <span role="status">{{status}}</span>
      <div class="se-swatch-actions">
        <button :disabled="!ready || !!failure || settled" @click="paused=!paused" :aria-pressed="paused">{{paused?'Resume':'Pause'}}</button>
        <button :disabled="!ready || !!failure" @click="reset">Replay</button>
        <label><input type="checkbox" v-model="equal" :disabled="!ready || !!failure" @change="reset"> Equal-weight control</label>
      </div>
    </div>
    <p v-if="failure" role="alert">{{failure}}</p>
    <div class="se-swatch-stages">
      <section v-for="(name,i) in ['Reference',fabric_name]" :key="i">
        <header><span :class="i?'se-swatch-blue':'se-swatch-amber'">{{name}}</span>
          <span>{{(i&&!equal?weight_gsm:300).toLocaleString(undefined,{maximumFractionDigits:2})}} g/m²</span></header>
        <canvas :ref="i?'fabric':'reference'" :aria-label="name+' simulated swatch'"></canvas>
        <div class="se-swatch-reading"><span>Tip drop</span><strong>{{samples[i]?samples[i].drop_mm.toFixed(2):'—'}} <small>mm</small></strong></div>
      </section>
    </div>
    <div class="se-swatch-profile">
      <div class="se-swatch-profile-copy">
        <h3>Compare the bend</h3>
        <p>Both profiles share the same scale. The lines come directly from the simulated mesh.</p>
        <p v-if="samples.length" class="se-swatch-difference">{{difference.toFixed(2)}} mm <span>difference at the tip</span></p>
        <p v-if="equal">With the same weight, the profiles should coincide.</p>
        <p v-else-if="Math.abs(weight_gsm-300)<.01">This fabric has the reference weight, so the profiles should coincide.</p>
        <p v-else>{{weight_gsm<300?fabric_name:'The reference'}} is lighter. With the same stiffness, it should bend less.</p>
      </div>
      <svg viewBox="-17 -12 115 105" role="img" aria-label="Swatch side profiles on an equal millimetre scale">
        <g class="se-swatch-grid">
          <g v-for="tick in [0,20,40,60,80]" :key="tick">
            <line :x1="tick" y1="0" :x2="tick" y2="80"/><line x1="0" :y1="tick" x2="80" :y2="tick"/>
            <text :x="tick" y="88" text-anchor="middle">{{tick}}</text><text x="-4" :y="tick+1.5" text-anchor="end">{{tick}}</text>
          </g>
        </g>
        <text x="40" y="-6" text-anchor="middle" class="se-swatch-axis">Distance from clamp (mm)</text>
        <text transform="translate(-13 40) rotate(-90)" text-anchor="middle" class="se-swatch-axis">Drop (mm)</text>
        <rect x="-3" y="-2" width="3" height="5" class="se-swatch-clamp"/>
        <polyline v-for="(s,i) in samples" :key="i" :points="s.profile.map(p=>p.join(',')).join(' ')"
          fill="none" :class="i?'se-swatch-line-blue':'se-swatch-line-amber'" :stroke-dasharray="i?'2 1':null"/>
      </svg>
    </div>
    <details class="se-swatch-method"><summary>What this test does—and doesn’t—show</summary>
      <p>The imported weight changes particle mass. Geometry, gravity, stretch, damping and bending are identical.
        The fixed clamp supports a strip 80 mm long and 40 mm wide. The plot averages its width; the two axes use equal scales.</p>
      <p>Bending uses a shared assumed discrete-shell coefficient of 0.00025 N·m. Imported bend, stretch, shear,
        thickness and friction are not applied here. This tests the weight response, not how the real fabric will drape.</p>
      <p>The mesh and solver are approximate. Smaller time steps can change the measured values.</p>
      <p>Garment simulations still use their existing material settings. All simulation runs in this browser.</p>
      <label><input type="checkbox" v-model="refined" :disabled="!ready || !!failure" @change="reset"> Refine time steps to check numerical sensitivity</label>
    </details>
  </div>`,
  props:{scene_url:String,fabric_name:String,weight_gsm:Number},
  data:()=>({ready:false,failure:'',paused:false,equal:false,refined:false,settled:false,time:0,samples:[],checks:''}),
  computed:{
    difference(){return this.samples.length?Math.abs(this.samples[0].drop_mm-this.samples[1].drop_mm):0;},
    pinError(){return this.samples.length?Math.max(...this.samples.map(s=>s.pin_error_mm)):0;},
    strain(){return this.samples.length?Math.max(...this.samples.map(s=>s.max_strain)):1;},
    status(){return this.failure?'Test unavailable':!this.ready?'Preparing swatches in your browser…':
      `${this.paused?'Paused':this.settled?'Settled':'Simulating'} · ${this.time.toFixed(1)} s`;},
  },
  mounted(){engines.set(this,{disposed:false,stages:[],frame:0});this.load();},
  beforeUnmount(){const e=engines.get(this);e.disposed=true;e.abort?.abort();cancelAnimationFrame(e.frame);
    for(const s of e.stages){s.renderer?.destroy();s.cloth?.destroy();}e.device?.destroy();},
  methods:{
    async load(){
      const e=engines.get(this);
      try{
        if(!navigator.gpu)throw Error('This test needs WebGPU. Open it in a browser with WebGPU and hardware acceleration enabled.');
        const adapter=await navigator.gpu.requestAdapter();if(!adapter)throw Error('WebGPU is unavailable on this device.');
        const device=await adapter.requestDevice();if(e.disposed){device.destroy();return;}e.device=device;
        device.lost.then(()=>{if(!e.disposed)this.failure='Browser graphics stopped. Close and reopen the test to retry.';});
        device.addEventListener('uncapturederror',event=>{if(!e.disposed)this.failure=event.error.message;});
        e.abort=new AbortController();
        const responses=await Promise.all([true,false].map(reference=>fetch(this.scene_url+'?reference='+reference,{signal:e.abort.signal})));
        if(responses.some(r=>!r.ok))throw Error('Could not load this fabric. Close the test and try again.');
        const scenes=await Promise.all(responses.map(r=>r.json()));
        if(e.disposed)return;
        for(let i=0;i<2;i++){
          const scene=scenes[i],cloth=await Cloth.create(device,scene,()=>{},swatchSettings);
          if(e.disposed){cloth.destroy();return;}
          const stage={cloth,originalMass:[...scene.inverse_mass]};e.stages.push(stage);
          stage.renderer=new Renderer(device,this.$el.querySelectorAll('canvas')[i],cloth,navigator.gpu.getPreferredCanvasFormat(),{systemTheme:true});
          const r=stage.renderer;r.setFabricColors(colors[i]);r.bodyView.color=[.16,.18,.22,0];
          r.camera={yaw:-.25,pitch:.55,distance:.25,target:[.037,.105,0],pan:[0,0]};
          // Keep both views on a common, fixed camera for a fair comparison.
          r.controls.destroy();
        }
        this.checks=JSON.stringify(e.stages.map(s=>s.cloth.kernelChecks));
        this.ready=true;this.tick();
      }catch(error){if(!e.disposed && error.name!=='AbortError')this.failure=error.message||String(error);}
    },
    reset(){const e=engines.get(this);e.resetPending=true;},
    async tick(now=0){
      const e=engines.get(this);if(e.disposed)return;
      try{
        if(e.resetPending){
          e.stages[1].cloth.scene.inverse_mass=[...(this.equal?e.stages[0].originalMass:e.stages[1].originalMass)];
          for(const s of e.stages){s.cloth.settings.substeps=swatchSettings.substeps*(this.refined?2:1);s.cloth.reset();}
          this.time=0;this.samples=[];this.settled=false;this.paused=false;e.stable=0;e.resetPending=false;e.last=0;
        }
        const advance=!this.failure&&!this.paused&&!this.settled&&!document.hidden&&now-(e.last||0)>=1000/60-.8;
        if(!this.failure&&(advance||e.stages.some(s=>s.renderer.dirty))){
          const encoder=e.device.createCommandEncoder();
          for(const s of e.stages){if(advance)s.cloth.encode(encoder,null,1/60);s.renderer.render(encoder);}
          e.device.queue.submit([encoder.finish()]);await e.device.queue.onSubmittedWorkDone();if(e.disposed)return;
          if(advance){
            e.last=now;this.time=e.stages[0].cloth.time;
            if(e.stages[0].cloth.frame%15===0){
              const positions=await Promise.all(e.stages.map(s=>s.cloth.readPositions()));if(e.disposed)return;
              const samples=e.stages.map((s,i)=>measureSwatch(s.cloth.scene,positions[i]));
              const stable=this.samples.length&&samples.every((s,i)=>Math.abs(s.drop_mm-this.samples[i].drop_mm)<.015)
                &&e.stages.every(s=>s.cloth.rmsVelocity<.0002);
              e.stable=stable?(e.stable||0)+1:0;this.samples=samples;
              if(this.time>3&&e.stable>=6)this.settled=true;
              if(this.pinError>.01||this.strain>1.1)throw Error('The test exceeded its clamp or stretch tolerance. This weight needs different solver settings.');
              if(this.time>=20&&!this.settled){this.paused=true;this.failure='The swatches did not settle within 20 simulated seconds. These results are not an equilibrium measurement.';}
            }
          }
        }
      }catch(error){if(!e.disposed)this.failure=error.message||String(error);}
      if(!e.disposed)e.frame=requestAnimationFrame(t=>this.tick(t));
    },
  },
};
