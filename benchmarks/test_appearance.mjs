import {test} from 'node:test';
import assert from 'node:assert/strict';
import {watchSystemBackground,lightBackground,darkBackground} from '../gui/webgpu/appearance.js';

test('live previews follow the initial OS appearance and later changes, then detach on close',()=>{
 const listeners=new Set(),colors=[];
 const media={matches:true,addEventListener(type,fn){assert.equal(type,'change');listeners.add(fn);},
  removeEventListener(type,fn){assert.equal(type,'change');listeners.delete(fn);}};
 const stop=watchSystemBackground(color=>colors.push(color),media);
 assert.deepEqual(colors,[darkBackground]);
 media.matches=false;for(const fn of listeners)fn();
 assert.deepEqual(colors,[darkBackground,lightBackground]);
 media.matches=true;for(const fn of listeners)fn();
 assert.equal(colors.at(-1),darkBackground);
 stop();assert.equal(listeners.size,0);
});
