import test from 'node:test';
import assert from 'node:assert/strict';
import {selectPiece} from '../gui/pattern_canvas.js';
import FabricPanel, {sharedValue} from '../gui/fabric_panel.js';

test('ordinary click replaces selection; modifier clicks toggle independently',()=>{
  let selected=selectPiece(['front'],'back');
  assert.deepEqual(selected,['back']);
  selected=selectPiece(selected,'front',true);
  assert.deepEqual(selected,['back','front']);
  assert.deepEqual(selectPiece(selected,'back',true),['front']);
  assert.deepEqual(selected,['back','front']);
});
test('background clears selection unless a modifier is held',()=>{
  assert.deepEqual(selectPiece(['front'],null),[]);
  assert.deepEqual(selectPiece(['front'],null,true),['front']);
});
test('mixed settings are detected independently, including zero and empty selection',()=>{
  const pieces=[{bg:'#ffffff',kind:'stripe',scale:1},{bg:'#ffffff',kind:'plain',scale:2}];
  assert.equal(sharedValue(pieces,'bg'),'#ffffff');
  assert.equal(sharedValue(pieces,'kind'),null);
  assert.equal(sharedValue(pieces,'scale'),null);
  assert.equal(sharedValue([],'bg'),null);
});
test('delayed edits retain their original sections and preserve edits to different fields',async()=>{
  const emitted=[],panel={...FabricPanel.data(),selection:[{id:'front'}],$emit:(event,payload)=>emitted.push(payload)};
  for(const [name,fn] of Object.entries(FabricPanel.methods))panel[name]=fn.bind(panel);
  panel.queue('bg','#112233');
  panel.queue('scale',2);
  panel.selection=[{id:'back'}];
  await new Promise(resolve=>setTimeout(resolve,350));
  assert.deepEqual(emitted,[{panels:['front'],field:'bg',value:'#112233'},{panels:['front'],field:'scale',value:2}]);
});
test('an explicit reset follows pending input instead of being overwritten by it',()=>{
  const emitted=[],panel={...FabricPanel.data(),selection:[{id:'front'}],$emit:(event,payload)=>emitted.push(payload)};
  for(const [name,fn] of Object.entries(FabricPanel.methods))panel[name]=fn.bind(panel);
  panel.queue('bg','#112233');panel.edit('reset');
  assert.deepEqual(emitted.map(p=>p.field),['bg','reset']);
  assert.deepEqual(panel.pending,{});
});
