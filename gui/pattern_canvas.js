export function selectPiece(selected, id, additive = false) {
  if (!id) return additive ? [...selected] : [];
  if (!additive) return [id];
  return selected.includes(id) ? selected.filter(p => p !== id) : [...selected, id];
}

export function selectionBox(start, end) {
  return {left:Math.min(start.x,end.x), top:Math.min(start.y,end.y),
    right:Math.max(start.x,end.x), bottom:Math.max(start.y,end.y)};
}

export function selectEnclosed(selected, bounds, box, additive = false) {
  const enclosed=bounds.filter(p=>p.left>=box.left && p.right<=box.right &&
    p.top>=box.top && p.bottom<=box.bottom).map(p=>p.id);
  return additive ? [...new Set([...selected,...enclosed])] : enclosed;
}

export function rulerTicks(origin, scale, length) {
  if (!(scale > 0) || !(length > 0)) return [];
  const major = 10 ** Math.floor(Math.log10(55 / scale));
  const step = [1, 2, 5, 10].map(n => n * major).find(n => n * scale >= 45);
  const minor = step / 5, start = Math.ceil(-origin / scale / minor), end = Math.floor((length - origin) / scale / minor);
  return Array.from({length:Math.max(0, end-start+1)}, (_, i) => {
    const n=start+i, value=Number((n*minor).toFixed(3));
    return {position:origin+value*scale, label:n%5===0 ? String(value) : null};
  });
}

// Keep DOM nodes, pointer capture and listeners outside Vue's reactive state.
const workspaces=new WeakMap();

export default {
  template: `<div class="se-pattern-canvas">
    <img v-if="src" :src="src" alt="Sewing pattern" draggable="false" @load="autoFit">
    <svg v-if="src" ref="svg" :viewBox="viewbox" preserveAspectRatio="none" aria-label="Select garment sections">
      <path v-for="piece in pieces" :key="piece.id" :d="piece.path" :data-pattern-piece="piece.id"
        role="button" tabindex="0" :aria-label="piece.label" :aria-pressed="picked.includes(piece.id)"
        :class="['se-pattern-piece', {'is-selected':picked.includes(piece.id)}]" vector-effect="non-scaling-stroke"
        @click.stop="choose($event,piece.id)" @keydown.enter.stop.prevent="choose($event,piece.id)"
        @keydown.space.stop.prevent="choose($event,piece.id)"><title>{{piece.label}}</title></path>
      <text v-for="piece in pieces" :key="'label-'+piece.id" :x="piece.x" :y="piece.y"
        class="se-piece-label" :style="{fontSize:labelSize+'px'}" text-anchor="middle" aria-hidden="true">
        <tspan v-for="(line,i) in caption(piece.label)" :key="i" :x="piece.x" :dy="i ? labelSize*1.15 : 0">{{line}}</tspan>
      </text>
      <rect v-if="marquee" class="se-pattern-marquee" :x="marquee.x" :y="marquee.y"
        :width="marquee.width" :height="marquee.height" vector-effect="non-scaling-stroke" aria-hidden="true"/>
    </svg>
    <Teleport v-if="rulerTarget && src" :to="rulerTarget">
      <svg class="se-pattern-rulers" :viewBox="'0 0 '+rulers.width+' '+rulers.height" aria-hidden="true">
        <rect x="0" y="0" :width="rulers.width" height="28"/><rect x="0" y="0" width="28" :height="rulers.height"/>
        <g v-for="(tick,i) in rulers.x" :key="'x'+i" v-show="tick.position>30">
          <line :x1="tick.position" :x2="tick.position" :y1="tick.label===null?23:19" y2="28"/>
          <text v-if="tick.label!==null" :x="tick.position" y="13" text-anchor="middle">{{tick.label}}</text>
        </g>
        <g v-for="(tick,i) in rulers.y" :key="'y'+i" v-show="tick.position>35">
          <line :y1="tick.position" :y2="tick.position" :x1="tick.label===null?23:19" x2="28"/>
          <text v-if="tick.label!==null" x="13" :y="tick.position" text-anchor="middle" dominant-baseline="middle">{{tick.label}}</text>
        </g>
        <text x="6" y="14">cm</text>
      </svg>
    </Teleport>
  </div>`,
  props: {src:String, pieces:Array, selected:Array, viewbox:String},
  data: () => ({picked:[], origin:null, marquee:null, suppressClick:false, rulerTarget:null,
    rulers:{width:1,height:1,x:[],y:[]},labelSize:2.6}),
  mounted() {
    const ws=this.$el.closest('.se-workspace'), abort=new AbortController();
    if(!ws)return;
    const resize=new ResizeObserver(()=>{this.autoFit();this.updateRulers();});
    workspaces.set(this,{ws,abort,resize,gesture:null,fitting:true});
    resize.observe(ws);
    const opts={signal:abort.signal};
    this.rulerTarget=ws.parentElement;
    ws.addEventListener('scroll',this.updateRulers,{...opts,passive:true});
    for(const [event,handler] of Object.entries({pointerdown:this.start,click:this.background,
      keydown:this.keys,contextmenu:e=>e.preventDefault()}))ws.addEventListener(event,handler,opts);
    for(const [event,handler] of Object.entries({pointermove:this.move,pointerup:this.finish,
      pointercancel:this.cancel,lostpointercapture:this.cancel}))document.addEventListener(event,handler,opts);
    window.addEventListener('blur',this.cancel,opts);
  },
  beforeUnmount() {this.cancel();workspaces.get(this)?.abort.abort();workspaces.get(this)?.resize.disconnect();workspaces.delete(this);},
  watch: {
    selected: {immediate:true, handler(value) {this.cancel();this.picked=[...(value || [])];}},
    pieces() {this.cancel();},
    src() {this.cancel();},
  },
  methods: {
    caption(label) {
      const words=label.split(' · ').pop().split(' ');
      return words.length<3 ? [words.join(' ')] : [words.slice(0,-1).join(' '),words.at(-1)];
    },
    updateRulers() {
      const state=workspaces.get(this);
      if(!state||!this.src)return;
      const r=this.$el.getBoundingClientRect(), ws=state.ws, viewport=ws.getBoundingClientRect();
      const [x,y,width,height]=this.viewbox.split(' ').map(Number), scale=r.width/width;
      if(!(scale>0))return;
      this.labelSize=Math.min(4,Math.max(2.6,8.5/scale));
      const originX=r.left-viewport.left-x*scale, originY=r.top-viewport.top-y*r.height/height;
      this.rulers={width:ws.clientWidth,height:ws.clientHeight,
        x:rulerTicks(originX,scale,ws.clientWidth),y:rulerTicks(originY,r.height/height,ws.clientHeight)};
      ws.style.setProperty('--grid-step',scale+'px');
      ws.style.setProperty('--grid-major',scale*10+'px');
      ws.style.setProperty('--grid-position',originX+'px '+originY+'px');
    },
    autoFit() {if(workspaces.get(this)?.fitting)this.$nextTick(()=>this.fit());},
    fit() {
      const state=workspaces.get(this), paper=this.$el.closest('.se-pattern-paper');
      if(!state||!paper||!this.src)return;
      const r=this.$el.getBoundingClientRect();
      if(r.width<1||r.height<1||state.ws.clientWidth<1)return;
      paper.style.margin=state.ws.clientHeight/2+'px '+state.ws.clientWidth/2+'px';
      this.zoom(Math.min((state.ws.clientWidth-64)/r.width,(state.ws.clientHeight-160)/r.height));
      state.fitting=true;
      const next=this.$el.getBoundingClientRect(), viewport=state.ws.getBoundingClientRect();
      state.ws.scrollLeft+=next.left+next.width/2-viewport.left-(state.ws.clientWidth+28)/2;
      state.ws.scrollTop+=next.top+next.height/2-viewport.top-(state.ws.clientHeight+40)/2;
      this.updateRulers();
    },
    zoom(factor) {
      const state=workspaces.get(this), paper=this.$el.closest('.se-pattern-paper');
      if(!state||!paper)return;
      this.cancel();state.fitting=false;
      const width=paper.offsetWidth, next=Math.max(80,Math.min(10000,width*factor)), ratio=next/width;
      const before=paper.getBoundingClientRect(), viewport=state.ws.getBoundingClientRect();
      const x=viewport.left+state.ws.clientWidth/2-before.left, y=viewport.top+state.ws.clientHeight/2-before.top;
      paper.style.width=next+'px';
      const after=paper.getBoundingClientRect();
      state.ws.scrollLeft+=after.left+x*ratio-viewport.left-state.ws.clientWidth/2;
      state.ws.scrollTop+=after.top+y*ratio-viewport.top-state.ws.clientHeight/2;
      this.updateRulers();
    },
    start(e) {
      const state=workspaces.get(this);
      if(!state||state.gesture||e.button>2)return;
      this.origin=[e.clientX,e.clientY];this.suppressClick=false;
      // Touch continues to use native scrolling and tap selection.
      if(e.pointerType==='touch'||!this.$refs.svg)return;
      const piece=e.target.closest('[data-pattern-piece]'), additive=e.shiftKey||e.ctrlKey||e.metaKey;
      // Native SVG focus can scroll the entire image to its top on a click.
      // Keep the clicked piece focused without moving the cutting table.
      if(piece){e.preventDefault();piece.focus?.({preventScroll:true});}
      if(e.button===0&&piece&&additive)return;
      const mode=e.button!==0||piece ? 'pan' : 'box';
      if(e.button!==0)e.preventDefault();
      const bounds=mode==='box' ? [...this.$refs.svg.querySelectorAll('[data-pattern-piece]')].map(p=>{
        const r=p.getBoundingClientRect();return {id:p.dataset.patternPiece,left:r.left,right:r.right,top:r.top,bottom:r.bottom};
      }) : [];
      state.gesture={id:e.pointerId,mode,additive,bounds,base:[...this.picked],
        start:{x:e.clientX,y:e.clientY},scroll:[state.ws.scrollLeft,state.ws.scrollTop],dragging:false};
      if(!piece)state.ws.focus({preventScroll:true});
    },
    move(e) {
      const state=workspaces.get(this),g=state?.gesture;
      if(!g||e.pointerId!==g.id)return;
      const end={x:e.clientX,y:e.clientY};
      if(!g.dragging&&Math.hypot(end.x-g.start.x,end.y-g.start.y)<=5)return;
      e.preventDefault();
      if(!g.dragging){g.dragging=true;state.ws.setPointerCapture(g.id);}
      if(g.mode==='pan'){
        state.fitting=false;
        state.ws.classList.add('se-dragging');
        state.ws.scrollLeft=g.scroll[0]-(end.x-g.start.x);
        state.ws.scrollTop=g.scroll[1]-(end.y-g.start.y);
      }else{
        const box=selectionBox(g.start,end),matrix=this.$refs.svg.getScreenCTM();
        if(!matrix)return;
        const inverse=matrix.inverse();
        const a=new DOMPoint(box.left,box.top).matrixTransform(inverse),b=new DOMPoint(box.right,box.bottom).matrixTransform(inverse);
        this.marquee={x:a.x,y:a.y,width:b.x-a.x,height:b.y-a.y};
        this.picked=selectEnclosed(g.base,g.bounds,box,g.additive);
      }
    },
    finish(e) {
      const state=workspaces.get(this),g=state?.gesture;
      if(!g||e.pointerId!==g.id)return;
      // Include the release position even if the last move was coalesced.
      this.move(e);
      const selection=[...this.picked];
      this.endGesture();
      if(g.dragging&&g.mode==='box')this.change(selection);
    },
    endGesture() {
      const state=workspaces.get(this),g=state?.gesture;
      if(!g)return;
      state.gesture=null;this.marquee=null;this.suppressClick=g.dragging;
      state.ws.classList.remove('se-dragging');
      if(state.ws.hasPointerCapture(g.id))state.ws.releasePointerCapture(g.id);
    },
    cancel(e) {
      const g=workspaces.get(this)?.gesture;
      if(!g||(e?.pointerId!==undefined&&e.pointerId!==g.id))return;
      this.picked=[...g.base];this.endGesture();
    },
    dragged(e) {return e.type==='click' && e.detail>0 && (this.suppressClick || this.origin && Math.hypot(e.clientX-this.origin[0],e.clientY-this.origin[1])>5);},
    change(value) {this.picked=value;this.$emit('selection',{panels:value});},
    choose(e,id) {if(!this.dragged(e))this.change(selectPiece(this.picked,id,e.shiftKey||e.ctrlKey||e.metaKey));},
    background(e) {if(e.button===0&&!this.dragged(e)&&!e.shiftKey&&!e.ctrlKey&&!e.metaKey)this.change([]);},
    keys(e) {
      if(e.key==='Escape'){
        e.preventDefault();e.stopPropagation();
        if(workspaces.get(this)?.gesture)this.cancel();else this.change([]);
      }else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'){
        e.preventDefault();this.cancel();this.change(this.pieces.map(p=>p.id));
      }
    },
  },
};
