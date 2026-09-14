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

// Keep DOM nodes, pointer capture and listeners outside Vue's reactive state.
const workspaces=new WeakMap();

export default {
  template: `<div class="se-pattern-canvas">
    <img v-if="src" :src="src" alt="Sewing pattern" draggable="false">
    <svg v-if="src" ref="svg" :viewBox="viewbox" preserveAspectRatio="none" aria-label="Select garment sections">
      <path v-for="piece in pieces" :key="piece.id" :d="piece.path" :data-pattern-piece="piece.id"
        role="button" tabindex="0" :aria-label="piece.label" :aria-pressed="picked.includes(piece.id)"
        :class="['se-pattern-piece', {'is-selected':picked.includes(piece.id)}]" vector-effect="non-scaling-stroke"
        @click.stop="choose($event,piece.id)" @keydown.enter.stop.prevent="choose($event,piece.id)"
        @keydown.space.stop.prevent="choose($event,piece.id)"><title>{{piece.label}}</title></path>
      <rect v-if="marquee" class="se-pattern-marquee" :x="marquee.x" :y="marquee.y"
        :width="marquee.width" :height="marquee.height" vector-effect="non-scaling-stroke" aria-hidden="true"/>
    </svg>
  </div>`,
  props: {src:String, pieces:Array, selected:Array, viewbox:String},
  data: () => ({picked:[], origin:null, marquee:null, suppressClick:false}),
  mounted() {
    const ws=this.$el.closest('.se-workspace'), abort=new AbortController();
    if(!ws)return;
    workspaces.set(this,{ws,abort,gesture:null});
    const opts={signal:abort.signal};
    for(const [event,handler] of Object.entries({pointerdown:this.start,click:this.background,
      keydown:this.keys,contextmenu:e=>e.preventDefault()}))ws.addEventListener(event,handler,opts);
    for(const [event,handler] of Object.entries({pointermove:this.move,pointerup:this.finish,
      pointercancel:this.cancel,lostpointercapture:this.cancel}))document.addEventListener(event,handler,opts);
    window.addEventListener('blur',this.cancel,opts);
  },
  beforeUnmount() {this.cancel();workspaces.get(this)?.abort.abort();workspaces.delete(this);},
  watch: {
    selected: {immediate:true, handler(value) {this.cancel();this.picked=[...(value || [])];}},
    pieces() {this.cancel();},
    src() {this.cancel();},
  },
  methods: {
    start(e) {
      const state=workspaces.get(this);
      if(!state||state.gesture||e.button>2)return;
      this.origin=[e.clientX,e.clientY];this.suppressClick=false;
      // Touch continues to use native scrolling and tap selection.
      if(e.pointerType==='touch'||!this.$refs.svg)return;
      const piece=e.target.closest('[data-pattern-piece]'), additive=e.shiftKey||e.ctrlKey||e.metaKey;
      if(e.button===0&&piece&&additive)return;
      const mode=e.button!==0||piece ? 'pan' : 'box';
      if(e.button!==0)e.preventDefault();
      const bounds=mode==='box' ? [...this.$refs.svg.querySelectorAll('[data-pattern-piece]')].map(p=>{
        const r=p.getBoundingClientRect();return {id:p.dataset.patternPiece,left:r.left,right:r.right,top:r.top,bottom:r.bottom};
      }) : [];
      state.gesture={id:e.pointerId,mode,additive,bounds,base:[...this.picked],
        start:{x:e.clientX,y:e.clientY},scroll:[state.ws.scrollLeft,state.ws.scrollTop],dragging:false};
      state.ws.focus({preventScroll:true});
    },
    move(e) {
      const state=workspaces.get(this),g=state?.gesture;
      if(!g||e.pointerId!==g.id)return;
      const end={x:e.clientX,y:e.clientY};
      if(!g.dragging&&Math.hypot(end.x-g.start.x,end.y-g.start.y)<=5)return;
      e.preventDefault();
      if(!g.dragging){g.dragging=true;state.ws.setPointerCapture(g.id);}
      if(g.mode==='pan'){
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
