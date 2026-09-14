import test from 'node:test';
import assert from 'node:assert/strict';
import PatternCanvas, {selectPiece, selectEnclosed, selectionBox} from '../gui/pattern_canvas.js';
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
test('box selection works in every drag direction and excludes partially enclosed pieces',()=>{
  const pieces=[{id:'front',left:20,right:80,top:30,bottom:100},
    {id:'collar',left:35,right:70,top:10,bottom:20},
    {id:'sleeve',left:90,right:140,top:30,bottom:90}];
  for(const [start,end] of [[{x:10,y:5},{x:100,y:110}],[{x:100,y:110},{x:10,y:5}],
    [{x:100,y:5},{x:10,y:110}],[{x:10,y:110},{x:100,y:5}]]){
    assert.deepEqual(selectEnclosed(['sleeve'],pieces,selectionBox(start,end)),['front','collar']);
  }
});
test('additive boxes preserve existing sections and never toggle enclosed ones off',()=>{
  const bounds=[{id:'front',left:10,right:40,top:20,bottom:70}];
  const box={left:0,right:50,top:0,bottom:80},selected=['front','back'];
  assert.deepEqual(selectEnclosed(selected,bounds,box,true),selected);
  assert.deepEqual(selectEnclosed(['back'],bounds,box,true),['back','front']);
  assert.deepEqual(selectEnclosed(selected,[],box,true),selected);
  assert.deepEqual(selectEnclosed(selected,[],box),[]);
});
test('box bounds remain correct after the workspace is panned or scaled',()=>{
  const bounds=[{id:'front',left:-20,right:20,top:50,bottom:100}];
  assert.deepEqual(selectEnclosed([],bounds,selectionBox({x:-20,y:50},{x:20,y:100})),['front']);
  assert.deepEqual(selectEnclosed([],bounds,selectionBox({x:-19,y:50},{x:20,y:100})),[]);
});
test('the synthetic click after a box drag cannot erase the selection; keyboard picking still works',()=>{
  const emitted=[],canvas={...PatternCanvas.data(),picked:['front','back'],suppressClick:true,
    $emit:(_,payload)=>emitted.push(payload)};
  for(const [name,fn] of Object.entries(PatternCanvas.methods))canvas[name]=fn.bind(canvas);
  canvas.background({type:'click',detail:1,button:0});
  canvas.choose({type:'click',detail:1},'sleeve');
  assert.deepEqual(emitted,[]);
  canvas.choose({type:'keydown',shiftKey:true},'sleeve');
  assert.deepEqual(emitted,[{panels:['front','back','sleeve']}]);
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
