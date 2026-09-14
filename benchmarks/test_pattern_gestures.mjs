import test from 'node:test';
import assert from 'node:assert/strict';
import PatternCanvas from '../gui/pattern_canvas.js';

function canvasHarness(t) {
  const originals={window:globalThis.window,document:globalThis.document,DOMPoint:globalThis.DOMPoint};
  globalThis.window=new EventTarget();globalThis.document=new EventTarget();
  globalThis.DOMPoint=class {constructor(x,y){this.x=x;this.y=y;}matrixTransform(){return this;}};
  const ws=new EventTarget(),captured=new Set(),classes=new Set(),emitted=[];
  Object.assign(ws,{scrollLeft:40,scrollTop:20,focus(){},
    classList:{add:c=>classes.add(c),remove:c=>classes.delete(c)},
    setPointerCapture:id=>captured.add(id),hasPointerCapture:id=>captured.has(id),releasePointerCapture:id=>captured.delete(id)});
  const pieces=[{id:'front',left:10,right:40,top:20,bottom:60},{id:'sleeve',left:60,right:90,top:20,bottom:60}];
  const svg={getScreenCTM:()=>({inverse:()=>({})}),querySelectorAll:()=>pieces.map(p=>({
    dataset:{patternPiece:p.id},getBoundingClientRect:()=>p}))};
  const canvas={...PatternCanvas.data(),picked:['back'],pieces,$refs:{svg},$el:{closest:()=>ws},
    $emit:(_,payload)=>emitted.push(payload)};
  for(const [name,fn] of Object.entries(PatternCanvas.methods))canvas[name]=fn.bind(canvas);
  PatternCanvas.mounted.call(canvas);
  t.after(()=>{PatternCanvas.beforeUnmount.call(canvas);Object.assign(globalThis,originals);});
  const pointer=(x,y,extra={})=>({pointerId:1,pointerType:'mouse',button:0,clientX:x,clientY:y,
    target:{closest:()=>null},preventDefault(){},...extra});
  return {canvas,ws,pointer,emitted,captured,classes};
}

test('box preview stays local until release and additive selection keeps existing pieces',t=>{
  const {canvas,pointer,emitted,captured}=canvasHarness(t);
  canvas.start(pointer(0,0,{ctrlKey:true}));canvas.move(pointer(50,70));
  assert.deepEqual(canvas.picked,['back','front']);assert.ok(canvas.marquee);assert.equal(emitted.length,0);
  canvas.finish(pointer(100,70));
  assert.deepEqual(emitted,[{panels:['back','front','sleeve']}]);
  assert.equal(canvas.marquee,null);assert.equal(captured.size,0);assert.equal(canvas.suppressClick,true);
});

test('Escape, cancelled pointers and lost window focus restore selection without publishing a preview',t=>{
  const {canvas,pointer,emitted,captured}=canvasHarness(t);
  for(const cancel of [()=>canvas.keys({key:'Escape',preventDefault(){},stopPropagation(){}}),
    ()=>canvas.cancel({pointerId:1}),()=>globalThis.window.dispatchEvent(new Event('blur'))]){
    canvas.start(pointer(0,0));canvas.move(pointer(50,70));assert.deepEqual(canvas.picked,['front']);
    cancel();assert.deepEqual(canvas.picked,['back']);assert.equal(canvas.marquee,null);assert.equal(captured.size,0);
  }
  assert.deepEqual(emitted,[]);
});

test('right/middle drags pan from blank space while piece drags preserve existing selection',t=>{
  const {canvas,ws,pointer,emitted,classes}=canvasHarness(t);
  for(const extra of [{button:2},{button:1},{target:{closest:()=>({})}}]){
    ws.scrollLeft=40;ws.scrollTop=20;
    canvas.start(pointer(100,100,extra));canvas.move(pointer(70,80,extra));
    assert.equal(ws.scrollLeft,70);assert.equal(ws.scrollTop,40);assert.ok(classes.has('se-dragging'));
    canvas.finish(pointer(70,80,extra));
    assert.equal(classes.size,0);assert.deepEqual(canvas.picked,['back']);
  }
  assert.deepEqual(emitted,[]);
});

test('a different pointer cannot finish the gesture; taps do not create a selection box',t=>{
  const {canvas,pointer,emitted}=canvasHarness(t);
  canvas.start(pointer(0,0));canvas.move(pointer(50,70));
  canvas.finish(pointer(50,70,{pointerId:2}));assert.ok(canvas.marquee);assert.deepEqual(emitted,[]);
  canvas.cancel();
  canvas.start(pointer(0,0,{pointerType:'touch'}));canvas.move(pointer(100,70,{pointerType:'touch'}));
  assert.equal(canvas.marquee,null);assert.deepEqual(canvas.picked,['back']);
});
