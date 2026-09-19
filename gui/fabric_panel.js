export function sharedValue(selection, field) {
  if (!selection.length) return null;
  const first=selection[0][field];
  return selection.every(p=>p[field]===first) ? first : null;
}

export default {
  template: `<aside v-if="open || docked" class="se-fabric-panel" :class="{'is-empty':!selection.length}" aria-label="Fabric settings" :aria-busy="busy">
    <header><h2>{{selectionTitle}}</h2><button v-if="selection.length" class="se-fabric-icon" aria-label="Close fabric settings" @click="$emit('close')">×</button></header>
    <div class="se-fabric-scroll">
      <div v-if="!selection.length" class="se-fabric-empty">
        <svg viewBox="0 0 44 44" aria-hidden="true"><path d="M8 6h19v7h9v25H8Z"/><path d="m17 18 14 8-7 2-3 7Z"/></svg>
        <h3>Select a pattern piece</h3>
        <p>Choose a fabric, then make it your own with color and print.</p>
        <p>Drag a box to select a group.<br>Hold Shift or Ctrl to add pieces.</p>
        <button :disabled="!available" class="se-select-all" @click="$emit('select-all')">Select all pieces</button>
      </div>
      <fieldset v-if="selection.length" :disabled="busy">
        <label class="se-fabric-field se-fabric-material">Fabric type
          <select aria-label="Fabric type" :value="shared('material')??''" @change="edit('material',$event.target.value)">
            <option v-if="shared('material')===null" value="" disabled>Mixed fabrics</option>
            <option value="default">Garment default</option>
            <option v-if="assignedName" :value="shared('material')">{{assignedName}}</option>
            <optgroup v-for="group in libraryGroups" :key="group.name" :label="group.name">
              <option v-for="fabric in group.items" :key="fabric.id" :value="fabric.id">{{fabric.label}}</option>
            </optgroup>
            <optgroup label="Drape presets">
              <option v-for="fabric in materials" :key="fabric.id" :value="fabric.id">{{fabric.label}}</option>
            </optgroup>
            <option value="custom">Custom</option>
          </select>
        </label>
        <button type="button" class="se-fabric-browse" @click="$emit('browse')">Browse fabrics…</button>
        <p v-if="outdated" class="se-fabric-outdated" role="note">This fabric changed in your library after it was applied here.
          <button v-if="shared('material')" @click="edit('material',shared('material'))">Apply current fabric</button>
        </p>
        <div class="se-color-swatches" aria-label="Fabric colors">
          <button v-for="swatch in swatches" :key="swatch.color" :style="{'--swatch':swatch.color}" :aria-label="swatch.name+' fabric'"
            :aria-pressed="shared('bg')===swatch.color" :title="swatch.name" @click="edit('bg',swatch.color)"></button>
        </div>
        <label class="se-fabric-field">Pattern
          <select aria-label="Fabric pattern" :value="shared('kind')??''" @change="edit('kind',$event.target.value)">
            <option v-if="shared('kind')===null" value="" disabled>Mixed patterns</option>
            <option value="plain">Solid</option><option value="pinstripe">Pinstripe</option><option value="stripe">Stripe</option>
            <option value="polka_dot">Polka dot</option><option value="gingham">Gingham</option><option value="windowpane">Windowpane</option>
          </select>
        </label>
        <details class="se-fabric-drape"><summary>Drape</summary>
          <p>{{materialDescription}}</p>
          <label class="se-fabric-field se-fabric-stiffness">Bending stiffness
            <input type="number" aria-label="Bending stiffness" min="0.5" max="30" step="0.5" :placeholder="shared('stiffness')===null?'Mixed':''" :value="shared('stiffness')??''" @input="number('stiffness',$event)" @blur="restoreInvalid('stiffness',$event)">
            <small>Higher values hold their shape more. Presets approximate drape.</small>
          </label>
        </details>
        <details class="se-fabric-custom"><summary>Custom colors &amp; spacing</summary>
        <label v-for="field in colorFields" :key="field.key" class="se-fabric-field">{{field.label}}
          <span class="se-fabric-color" :class="{'is-mixed':shared(field.key)===null}">
            <input type="color" :aria-label="field.label+' swatch'" :value="shared(field.key)||'#b7cde5'" @input="color(field.key,$event)">
            <input type="text" :aria-label="field.label" :value="shared(field.key)||''" :placeholder="shared(field.key)===null?'Mixed':'#000000'" spellcheck="false" maxlength="7" pattern="#[0-9a-fA-F]{6}" @input="color(field.key,$event)" @blur="restoreInvalid(field.key,$event)">
          </span>
        </label>
        <label v-if="shared('kind')!=='plain'" class="se-fabric-field">Pattern spacing <span class="se-fabric-unit">cm</span>
          <input type="number" aria-label="Pattern spacing" min="0.2" max="4" step="0.1" :placeholder="shared('scale')===null?'Mixed':''" :value="shared('scale')??''" @input="number('scale',$event)" @blur="restoreInvalid('scale',$event)">
        </label>
        </details>
        <details class="se-fabric-selection"><summary>Selected pieces ({{selection.length}})</summary>
          <ul class="se-fabric-pieces"><li v-for="p in selection" :key="p.id">{{p.label}}</li></ul>
          <div class="se-fabric-selection-actions"><button :disabled="!available" @click="$emit('select-all')">Select all</button><button @click="$emit('clear')">Clear selection</button></div>
          <button class="se-fabric-reset" @click="edit('reset')">Reset fabric settings</button>
        </details>
      </fieldset>
    </div>
    <footer v-if="selection.length" role="status">{{busy?'Applying fabric…':'Applied to all selected pieces'}}</footer>
  </aside>`,
  props: {selection:Array, open:Boolean, docked:Boolean, available:Number, busy:Boolean, materials:Array, library:Array},
  data: () => ({pending:{}, swatches:[{name:'Oxford blue',color:'#b7cde5'},{name:'White',color:'#f8fafc'},
    {name:'Silver',color:'#bfc6cf'},{name:'Rose',color:'#deb5c0'},{name:'Navy',color:'#263f5d'}]}),
  beforeUnmount() {Object.values(this.pending).forEach(p=>clearTimeout(p.timer));},
  computed: {
    selectionTitle() {
      if(!this.selection.length)return 'Fabric';
      const noun=['cuff','sleeve','collar'].find(word=>this.selection.every(p=>p.label.toLowerCase().includes(word)))||'piece';
      return this.selection.length+' '+noun+(this.selection.length===1?'':'s')+' selected';
    },
    colorFields() {return this.shared('kind')==='plain' ? [{key:'bg',label:'Fabric color'}] : [{key:'bg',label:'Base color'},{key:'fg',label:'Print color'}];},
    materialDescription() {
      const id=this.shared('material');
      if(id===null)return 'Choose a fabric for all selected sections.';
      if(id==='default')return 'Original stiffness, including structured collars and cuffs.';
      if(id==='custom')return 'Your own stiffness setting.';
      const saved=(this.library||[]).find(fabric=>fabric.id===id);
      if(saved)return 'Saved fabric: its weight and bending drive this piece. Edit the fabric in your account.';
      if(this.assignedName)return 'Saved with this garment. It is not in your fabric library.';
      return this.materials.find(fabric=>fabric.id===id)?.description||'';
    },
    outdated() {return this.selection.some(p=>p.material_outdated);},
    libraryGroups() {
      const groups=[];
      for(const fabric of this.library||[]){
        const name=fabric.group||'Fabrics';
        let group=groups.find(g=>g.name===name);
        if(!group)groups.push(group={name,items:[]});
        group.items.push(fabric);
      }
      return groups;
    },
    assignedName() {
      // A fabric can travel with a shared garment, or be deleted after assignment.
      const id=this.shared('material');
      if(!id||id==='default'||id==='custom')return '';
      if((this.library||[]).some(f=>f.id===id)||this.materials.some(f=>f.id===id))return '';
      return this.selection[0]?.material_name||'Saved fabric';
    },
  },
  methods: {
    shared(field) {return sharedValue(this.selection,field);},
    edit(field,value) {
      for(const p of Object.values(this.pending)){clearTimeout(p.timer);this.$emit('edit',p.payload);}
      this.pending={};this.$emit('edit',{panels:this.selection.map(p=>p.id),field,value});
    },
    cancel(field) {const key=JSON.stringify([this.selection.map(p=>p.id),field]);clearTimeout(this.pending[key]?.timer);delete this.pending[key];return key;},
    queue(field,value) {
      const key=this.cancel(field);
      // Capture the edited selection; a later click must not redirect the edit.
      const payload={panels:this.selection.map(p=>p.id),field,value};
      this.pending[key]={payload,timer:setTimeout(()=>{delete this.pending[key];this.$emit('edit',payload);},300)};
    },
    color(field,e) {this.cancel(field);if(/^#[0-9a-fA-F]{6}$/.test(e.target.value))this.queue(field,e.target.value);},
    number(field,e) {this.cancel(field);if(e.target.value!==''&&e.target.checkValidity())this.queue(field,Number(e.target.value));},
    restoreInvalid(field,e) {if(e.target.value===''||!e.target.checkValidity())e.target.value=this.shared(field)??'';},
  },
};
