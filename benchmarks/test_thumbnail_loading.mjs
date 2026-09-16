import {test} from 'node:test';
import assert from 'node:assert/strict';
// This module must be importable without resolving browser-only /webgpu
// modules. Those dependencies belong exclusively to a real missing-image job.
import component from '../webapp/thumbnail_renderer.js';

test('an image-only library never starts a GPU or fetches a simulation',async t=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  let requests=0;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{gpu:{
    requestAdapter(){requests++;throw Error('No thumbnail job needs an adapter');},
  }}});
  t.after(()=>{if(previous)Object.defineProperty(globalThis,'navigator',previous);else delete globalThis.navigator;});
  const events=[];
  const view={...component.data(),job:null,$emit:name=>events.push(name),...component.methods};
  component.mounted.call(view);
  assert.equal(view.state,'idle');
  assert.deepEqual(events,['available']);
  await view.renderJob();
  component.watch.job.call(view);
  assert.equal(requests,0);
  component.beforeUnmount.call(view);
});
