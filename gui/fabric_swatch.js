import {Cloth} from '/webgpu/physics.js?v=21';
import {Renderer} from '/webgpu/render.js?v=25';
import {settingsForSwatch,swatchSteps,measureSwatch} from '/webgpu/swatch.js?v=4';

const engines=new WeakMap();
const colors=['#c28a44','#74b7ec'];
export default {
  template:`<div class="se-swatch" :data-state="failure?'error':!ready?'loading':paused?'paused':settled?'settled':'running'"
      :data-time="time" :data-reference-drop-mm="samples[0]?.drop_mm" :data-fabric-drop-mm="samples[1]?.drop_mm"
      :data-pin-error-mm="pinError" :data-control="equal" :data-strain="strain" :data-kernel-checks="checks"
      :data-mode="mode" :data-measurements="JSON.stringify(samples)" :data-properties="JSON.stringify(material)" :data-wall-seconds="wallSeconds">
    <div class="se-swatch-toolbar">
      <span role="status">{{status}}</span>
      <div class="se-swatch-actions">
        <label>Test <select v-model="mode" :disabled="!ready" @change="reload">
          <option value="bend">Bend under gravity</option><option value="stretch">Stretch · 25 N/m</option><option value="shear">Shear · 5 N/m</option>
        </select></label>
        <button :disabled="!ready || !!failure || settled" @click="paused=!paused" :aria-pressed="paused">{{paused?'Resume':'Pause'}}</button>
        <button :disabled="!ready || !!failure" @click="reset">Replay</button>
        <label><input type="checkbox" v-model="equal" :disabled="!ready || !!failure" @change="reload"> Same-grain control</label>
      </div>
    </div>
    <p v-if="failure" role="alert">{{failure}}</p>
    <p class="se-swatch-assumptions" role="note" v-for="warning in material?.normalization?.warnings||[]" :key="warning.property">{{warning.message}}</p>
    <div class="se-swatch-stages">
      <section v-for="(name,i) in ['Warp · along the grain',equal?'Warp · control':'Weft · across the grain']" :key="i">
        <header><span :class="i?'se-swatch-blue':'se-swatch-amber'">{{name}}</span>
          <span>{{weight_gsm.toLocaleString(undefined,{maximumFractionDigits:2})}} g/m²</span></header>
        <canvas :ref="i?'fabric':'reference'" :aria-label="name+' simulated swatch'"></canvas>
        <div class="se-swatch-reading"><span>{{mode==='bend'?'Tip drop':mode==='stretch'?'Extension':'Sideways displacement'}}</span>
          <strong>{{samples[i]?reading(samples[i]).toFixed(2):'—'}} <small>{{mode==='stretch'?'%':'mm'}}</small></strong></div>
      </section>
    </div>
    <div class="se-swatch-profile">
      <div class="se-swatch-profile-copy">
        <h3>{{mode==='bend'?'A fabric has a direction':mode==='stretch'?'Pull along each grain':'Test in-plane distortion'}}</h3>
        <p>{{mode==='bend'?'An 80 × 40 mm strip bends under its own weight. Both profiles share an equal millimetre scale.':mode==='stretch'?'A distributed 25 N/m force pulls the free edge along the strip. Gravity is off to isolate its tensile response.':'A distributed 5 N/m force pulls the free edge sideways. The result includes shear and directional stretch; gravity is off.'}}</p>
        <p v-if="samples.length" class="se-swatch-difference">{{difference.toFixed(2)}} {{mode==='stretch'?'percentage points':'mm'}} <span>difference between directions</span></p>
        <p v-if="equal">Both use warp properties. Their results should coincide.</p>
        <p v-else>Weight is identical. Differences come from the fabric’s directional properties.</p>
        <p v-if="mode==='stretch' && material?.expected_extension_percent!=null">Linear strip prediction, warp: {{material.expected_extension_percent.toFixed(2)}}% extension. The clamped mesh approximates this response.</p>
        <p v-if="mode==='bend' && material?.expected_drop_mm!=null">Exact clamped strip (heavy elastica), warp: {{material.expected_drop_mm.toFixed(1)}} mm drop. The 10 mm mesh follows it within 1% up to a 72 mm drop, and within 2.5% for limper fabrics.</p>
        <p v-if="material?.numerics && material.numerics.validated">Solver step sized for this fabric: {{material.numerics.substeps}} substeps per frame. {{mode==='stretch'?'Within this range the reading is within 0.2% of the exact strip.':'Within this range the step adds under 0.2%.'}}</p>
        <p v-if="mode==='shear'" role="note">No exact answer exists for this test. Against the same strip on a mesh-converged grid, the 10 mm mesh reads this movement 9–13% low, most for cloth that stretches easily. Compare fabrics with it; do not read a shear stiffness from it.</p>
        <p v-if="material?.numerics && !material.numerics.validated" class="se-swatch-warning" role="note">This fabric is stiffer for its weight than the solver’s validated range (stiffness ratio {{material.numerics.stiffness_ratio.toFixed(1)}}, validated to 1). Its reading may be wrong by more than 1%.</p>
      </div>
      <svg v-if="mode==='bend'" viewBox="-17 -12 115 105" role="img" aria-label="Swatch side profiles on an equal millimetre scale">
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
      <div v-else class="se-swatch-load-note"><strong>{{mode==='stretch'?'25':'5'}} N/m</strong><p>{{mode==='stretch'?'Longitudinal':'Transverse'}} edge load · {{mode==='stretch'?'1.0':'0.2'}} N total</p><p>Material coefficients are independent of mesh area. All readings come from the simulated vertices.</p></div>
    </div>
    <p class="se-swatch-assumptions" v-if="material">{{assumptionText}}</p>
    <details class="se-swatch-method"><summary>Applied properties &amp; test limitations</summary>
      <table v-if="material"><thead><tr><th>Property</th><th>Value</th><th>Source</th></tr></thead><tbody>
        <tr v-for="(p,key) in material.applied" :key="key"><td>{{labels[key]}}</td><td>{{format(p.value)}} {{p.unit}}</td><td>{{p.origin}}</td></tr>
      </tbody></table>
      <p>Directional stretch and shear use a linear surface-energy model. Bending uses interior dihedral angles; damping attenuates velocity exponentially. Zero values disable that property; blank values use the assumptions listed above.</p>
      <p v-if="Object.keys(activeFits).length">Bending was estimated from raw short-loop compression tests using an ideal clamped elastica, with a separate force offset per cycle. This is an uncalibrated fit, not a direct conversion of vendor bending numbers.</p>
      <p v-for="(fit,key) in activeFits" :key="key">{{labels[key]}} fit range: {{format(fit.range[0])}}–{{format(fit.range[1])}} N·m across {{fit.cycles.length}} cycles.</p>
      <p>Thickness and friction require contact and are not exercised by these tests. Nonlinear loading curves, hysteresis, and bend/twist coupling are preserved or left unknown, not reproduced by this approximation.</p>
      <p>The mesh and solver are approximate. Smaller time steps can change the readings. This prototype has not been calibrated against a physical swatch.</p>
      <p>Garment simulations still use their existing material settings. All simulation runs in this browser.</p>
      <label><input type="checkbox" v-model="refined" :disabled="!ready || !!failure" @change="reset"> Refine solver to check numerical sensitivity</label>
    </details>
  </div>`,
  props:{scene_url:String,fabric_name:String,weight_gsm:Number},
  data:()=>({ready:false,failure:'',paused:false,equal:false,refined:false,settled:false,time:0,wallSeconds:0,samples:[],checks:'',mode:'bend',material:null,
    labels:{stretch_warp:'Warp stretch',stretch_weft:'Weft stretch',shear:'Shear',bend_warp:'Warp bending',bend_weft:'Weft bending',damping:'Damping'}}),
  computed:{
    activeFits(){return Object.fromEntries(Object.entries(this.material?.normalization?.bending_fits||{}).filter(([key])=>this.material.applied[key]?.origin==='estimated'));},
    difference(){return this.samples.length?Math.abs(this.reading(this.samples[0])-this.reading(this.samples[1])):0;},
    assumptionText(){const p=this.material.applied,assumed=Object.keys(p).filter(k=>p[k].origin==='assumed').map(k=>`${this.labels[k].toLowerCase()} ${this.format(p[k].value)} ${p[k].unit}`),estimated=Object.keys(p).filter(k=>p[k].origin==='estimated').map(k=>this.labels[k].toLowerCase());return (assumed.length?'Assumed: '+assumed.join(', ')+'. ':'')+(estimated.length?'Estimated: '+estimated.join(', ')+'. Estimates are not calibrated measurements.':'');},
    pinError(){return this.samples.length?Math.max(...this.samples.map(s=>s.pin_error_mm)):0;},
    strain(){return this.samples.length?Math.max(...this.samples.map(s=>s.max_strain)):1;},
    status(){return this.failure?'Test unavailable':!this.ready?'Preparing swatches in your browser…':
      `${this.paused?'Paused':this.settled?'Settled':'Simulating'} · ${this.time.toFixed(1)} s`;},
  },
  mounted(){engines.set(this,{disposed:false,stages:[],frame:0});this.load();},
  beforeUnmount(){const e=engines.get(this);e.disposed=true;e.abort?.abort();cancelAnimationFrame(e.frame);
    for(const s of e.stages){s.renderer?.destroy();s.cloth?.destroy();}e.device?.destroy();},
  methods:{
    reading(s){return this.mode==='bend'?s.drop_mm:this.mode==='stretch'?s.extension_percent:s.shear_mm;},
    format(v){return Math.abs(v)>0 && Math.abs(v)<.01?v.toExponential(3):Number(v.toPrecision(5)).toString();},
    reload(){engines.get(this).reloadPending=true;},
    async load(){
      const e=engines.get(this);
      try{
        if(!navigator.gpu)throw Error('This test needs WebGPU. Open it in a browser with WebGPU and hardware acceleration enabled.');
        const adapter=await navigator.gpu.requestAdapter();if(!adapter)throw Error('WebGPU is unavailable on this device.');
        const device=await adapter.requestDevice();if(e.disposed){device.destroy();return;}e.device=device;
        device.lost.then(()=>{if(!e.disposed)this.failure='Browser graphics stopped. Close and reopen the test to retry.';});
        device.addEventListener('uncapturederror',event=>{if(!e.disposed)this.failure=event.error.message;});
        await this.build();if(!e.disposed)this.tick();
      }catch(error){if(!e.disposed && error.name!=='AbortError')this.failure=error.message||String(error);}
    },
    async build(){
        const e=engines.get(this),device=e.device;
        this.ready=false;this.failure='';this.samples=[];this.time=0;this.settled=false;this.paused=false;e.stable=0;e.last=0;e.lastRead=0;e.remainder=0;e.reloadPending=false;
        for(const s of e.stages){s.renderer?.destroy();s.cloth?.destroy();}e.stages=[];
        e.abort=new AbortController();
        const responses=await Promise.all(['warp',this.equal?'warp':'weft'].map(direction=>fetch(this.scene_url+'?direction='+direction+'&mode='+this.mode,{signal:e.abort.signal})));
        for(const r of responses)if(!r.ok){const body=await r.json().catch(()=>({}));throw Error(body.detail||'Could not load this fabric. Close the test and try again.');}
        const scenes=await Promise.all(responses.map(r=>r.json()));
        if(e.disposed)return;
        for(let i=0;i<2;i++){
          const scene=scenes[i],cloth=await Cloth.create(device,scene,()=>{},settingsForSwatch(scene,this.refined));
          if(e.disposed){cloth.destroy();return;}
          const stage={cloth};e.stages.push(stage);
          stage.renderer=new Renderer(device,this.$el.querySelectorAll('canvas')[i],cloth,navigator.gpu.getPreferredCanvasFormat(),{systemTheme:true});
          const r=stage.renderer;r.setFabricColors(colors[i]);r.bodyView.color=[.16,.18,.22,0];
          r.camera={yaw:-.9,pitch:.45,distance:.20,target:[.03,.09,0],pan:[0,0]};
          // Keep both views on a common, fixed camera for a fair comparison.
          r.controls.destroy();
        }
        this.checks=JSON.stringify(e.stages.map(s=>s.cloth.kernelChecks));
        this.material=scenes[0].fabric_test;this.ready=true;e.started=performance.now();
    },
    reset(){const e=engines.get(this);e.resetPending=true;},
    async tick(now=0){
      const e=engines.get(this);if(e.disposed)return;
      try{
        if(e.reloadPending)await this.build();
        if(e.disposed)return;
        if(e.resetPending){
          for(const s of e.stages){Object.assign(s.cloth.settings,settingsForSwatch(s.cloth.scene,this.refined));s.cloth.reset();}
          this.time=0;this.samples=[];this.settled=false;this.paused=false;e.stable=0;e.resetPending=false;e.last=0;e.lastRead=0;e.remainder=0;e.started=performance.now();
        }
        const advance=!this.failure&&!this.paused&&!this.settled&&!document.hidden&&now-(e.last||0)>=1000/60-.8;
        if(!this.failure&&(advance||e.stages.some(s=>s.renderer.dirty))){
          const budget=advance?swatchSteps(this.mode,e.last,now,e.remainder):{steps:0,remainder:e.remainder};
          e.remainder=budget.remainder;
          for(let step=0;step<Math.max(1,budget.steps);step++){
            const encoder=e.device.createCommandEncoder();
            for(const s of e.stages){if(step<budget.steps)s.cloth.encode(encoder,null,1/60);if(step===Math.max(1,budget.steps)-1)s.renderer.render(encoder);}
            // Submit before updating uniforms for the next fixed increment.
            e.device.queue.submit([encoder.finish()]);
          }
          await e.device.queue.onSubmittedWorkDone();if(e.disposed)return;
          if(advance){
            e.last=now;this.time=e.stages[0].cloth.time;this.wallSeconds=(performance.now()-e.started)/1000;
            if(e.stages[0].cloth.frame-e.lastRead>=15){
              e.lastRead=e.stages[0].cloth.frame;
              const positions=await Promise.all(e.stages.map(s=>s.cloth.readPositions()));if(e.disposed)return;
              const samples=e.stages.map((s,i)=>measureSwatch(s.cloth.scene,positions[i]));
              const stable=this.samples.length&&samples.every((s,i)=>Math.abs(this.reading(s)-this.reading(this.samples[i]))<.015)
                &&e.stages.every(s=>s.cloth.rmsVelocity<.0002);
              e.stable=stable?(e.stable||0)+1:0;this.samples=samples;
              if(this.time>3&&e.stable>=6)this.settled=true;
              if(this.pinError>.01||this.strain>4)throw Error('The test exceeded its clamp or deformation tolerance. These properties need a different load or solver configuration.');
              if(this.time>=20&&!this.settled){this.paused=true;this.failure='Still moving after 20 simulated seconds; this is not an equilibrium reading. Low or zero damping can keep the fabric oscillating.';}
            }
          }
        }
      }catch(error){if(!e.disposed)this.failure=error.message||String(error);}
      if(!e.disposed)e.frame=requestAnimationFrame(t=>this.tick(t));
    },
  },
};
