export function selectPiece(selected, id, additive = false) {
  if (!id) return additive ? [...selected] : [];
  if (!additive) return [id];
  return selected.includes(id) ? selected.filter(p => p !== id) : [...selected, id];
}

export default {
  template: `<div class="se-pattern-canvas" @pointerdown="start" @click="background" @keydown.esc.stop.prevent="change([])">
    <img v-if="src" :src="src" alt="Sewing pattern" draggable="false">
    <svg v-if="src" :viewBox="viewbox" preserveAspectRatio="none" aria-label="Select garment sections" @keydown="keys">
      <path v-for="piece in pieces" :key="piece.id" :d="piece.path" :data-pattern-piece="piece.id"
        role="button" tabindex="0" :aria-label="piece.label" :aria-pressed="picked.includes(piece.id)"
        :class="['se-pattern-piece', {'is-selected':picked.includes(piece.id)}]" vector-effect="non-scaling-stroke"
        @click.stop="choose($event,piece.id)" @keydown.enter.stop.prevent="choose($event,piece.id)"
        @keydown.space.stop.prevent="choose($event,piece.id)"><title>{{piece.label}}</title></path>
    </svg>
  </div>`,
  props: {src:String, pieces:Array, selected:Array, viewbox:String},
  data: () => ({picked:[], origin:null}),
  watch: {selected: {immediate:true, handler(value) {this.picked=[...(value || [])];}}},
  methods: {
    start(e) {this.origin=[e.clientX,e.clientY];},
    dragged(e) {return e.type==='click' && e.detail>0 && this.origin && Math.hypot(e.clientX-this.origin[0],e.clientY-this.origin[1])>5;},
    change(value) {this.picked=value;this.$emit('selection',{panels:value});},
    choose(e,id) {if(!this.dragged(e))this.change(selectPiece(this.picked,id,e.shiftKey||e.ctrlKey||e.metaKey));},
    background(e) {if(!this.dragged(e)&&!e.shiftKey&&!e.ctrlKey&&!e.metaKey)this.change([]);},
    keys(e) {if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'){e.preventDefault();this.change(this.pieces.map(p=>p.id));}},
  },
};
