import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ConnectionRecovery,isServerControl} from '../webapp/connection.js';

function fixture({initialConnected=false,...options}={}) {
  const timers=new Map(), frames=[], acknowledgements=[];
  let timerId=0,ready=false,online=true;
  const socket={connected:initialConnected, attempts:0, handlers:{},
    io:{reconnectionDelay(){},reconnectionDelayMax(){},timeout(){}},
    on(event,fn){this.handlers[event]=fn;},off(event){delete this.handlers[event];},
    connect(){this.attempts++;},disconnect(){this.connected=false;this.handlers.disconnect?.();},
    arrive(){this.connected=true;this.handlers.connect();},
  };
  const recovery=new ConnectionRecovery({socket,
    handshake:done=>acknowledgements.push(done),ready:value=>{ready=value;},
    render:frame=>frames.push(frame),online:()=>online,
    later:fn=>{timers.set(++timerId,fn);return timerId;},cancel:id=>timers.delete(id),
    ...options,
  });
  return {recovery,socket,acknowledgements,frames,get ready(){return ready;},
    offline(){online=false;recovery.lost();},online(){online=true;recovery.resume();},
    elapsed(){for(const [id,fn] of [...timers]){timers.delete(id);fn();}},
    connected(){socket.arrive();acknowledgements.at(-1)(true);},
  };
}

test('a brief drop reconnects without a notice or reload',()=>{
  const f=fixture(); f.connected();
  f.socket.disconnect(); assert.equal(f.ready,false);
  f.connected(); f.elapsed();
  assert.equal(f.ready,true);
  assert.equal(f.recovery.state,'connected');
  assert.ok(f.frames.every(frame=>!frame.visible));
});
test('a longer drop is visible, then clears only after the handshake',()=>{
  const f=fixture(); f.connected(); f.socket.disconnect(); f.elapsed();
  assert.deepEqual(f.frames.at(-1),{state:'connecting',visible:true});
  f.socket.arrive(); assert.equal(f.ready,false);
  f.acknowledgements.at(-1)(true);
  assert.deepEqual(f.frames.at(-1),{state:'connected',visible:false});
});
test('offline-to-online resumes automatically and stale acknowledgements cannot unlock editing',()=>{
  const f=fixture(); f.socket.arrive(); const stale=f.acknowledgements.at(-1);
  f.socket.disconnect(); f.offline(); f.elapsed();
  assert.equal(f.recovery.state,'offline'); stale(true); assert.equal(f.ready,false);
  f.online(); assert.equal(f.socket.attempts,1);
  f.connected(); assert.equal(f.ready,true);
});
test('timeouts retry without reloading and a rejected session requires explicit reload',()=>{
  const f=fixture(); f.connected();
  f.socket.handlers.connect_error({message:'timeout'});f.elapsed();
  assert.equal(f.recovery.state,'connecting');
  f.socket.arrive();f.acknowledgements.at(-1)(false);
  assert.equal(f.recovery.state,'expired'); assert.equal(f.ready,false);
  f.online(); assert.equal(f.socket.attempts,0);
  assert.equal(f.frames.at(-1).visible,true);
});
test('missing handshake acknowledgements restart the socket rather than leave a stuck retry button',()=>{
  const f=fixture();f.socket.arrive();f.acknowledgements.at(-1)(null);
  assert.equal(f.socket.attempts,1);assert.equal(f.ready,false);
  f.connected();assert.equal(f.ready,true);
});
test('already connected and in-flight initial handshakes are not sent twice',()=>{
  for(const initialReady of [true,false]) {
    let complete;
    const f=fixture({initialConnected:true,initialReady,initialHandshake:done=>{complete=done;}});
    if(!initialReady) complete();
    assert.equal(f.recovery.state,'connected');assert.equal(f.acknowledgements.length,0);
  }
});
test('an initial handshake that stalls gets a fresh connection attempt',()=>{
  let complete;
  const f=fixture({initialConnected:true,initialHandshake:done=>{complete=done;}});
  complete(false);
  assert.equal(f.ready,false);assert.equal(f.socket.attempts,1);
  f.connected();assert.equal(f.ready,true);
});
test('an expired message history stops retrying until the user reloads',()=>{
  const f=fixture(); f.connected(); f.socket.handlers.try_reconnect();
  assert.equal(f.recovery.state,'expired');assert.equal(f.ready,false);
  f.recovery.resume();assert.equal(f.socket.attempts,0);
});
test('offline actions pause, while local 3D controls are exempt',()=>{
  const control={closest:selector=>selector.includes('button,a')?{}:null};
  const local={closest:selector=>selector.includes('[data-se-local]')?{}:null};
  const background={closest:()=>null};
  assert.equal(isServerControl(control),true);
  assert.equal(isServerControl(local),false);
  assert.equal(isServerControl(background),false);
});
