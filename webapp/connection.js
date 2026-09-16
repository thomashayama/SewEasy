// NiceGUI 2.x reconnect adapter. Keep normal update/replay handlers, but replace
// the timeout reload loop and reconnect popup with explicit recovery states.
export class ConnectionRecovery {
  constructor({socket, handshake, render, ready, initialReady=false, initialHandshake,
    online=()=>true, later=(fn,ms)=>setTimeout(fn,ms), cancel=id=>clearTimeout(id)}) {
    Object.assign(this,{socket,handshake,render,ready,online,later,cancel});
    this.state='connecting'; this.notice=false; this.timer=null; this.generation=0;
    this.handlers={connect:()=>this.connect(), disconnect:()=>this.lost(),
      connect_error:()=>this.lost(), try_reconnect:()=>this.expired()};
    for(const [event,handler] of Object.entries(this.handlers)) {
      socket.off(event); // Replace only NiceGUI's connection handlers.
      socket.on(event,handler);
    }
    socket.io.reconnectionDelay(500);
    socket.io.reconnectionDelayMax(5000);
    socket.io.timeout(10000);
    this.lost();
    if(socket.connected) {
      // NiceGUI may already have sent the first handshake before DOMContentLoaded.
      // Sending it twice would count this socket as two live page connections.
      if(initialReady) this.connected();
      else if(initialHandshake) {
        const generation=this.generation;
        initialHandshake((ok=true)=>{
          if(generation!==this.generation || !socket.connected) return;
          if(ok) this.connected();
          else {this.socket.disconnect();this.socket.connect();}
        });
      } else this.connect();
    }
  }
  paint() {this.render({state:this.state,visible:this.notice});}
  lost() {
    if(this.state==='expired') return;
    this.generation++;
    this.ready(false);
    this.state=this.online()?'connecting':'offline';
    if(!this.timer && !this.notice) this.timer=this.later(()=>{
      this.timer=null; this.notice=true; this.paint();
    },3000);
    this.paint();
  }
  connect() {
    if(this.state==='expired') return;
    const generation=++this.generation;
    this.handshake(ok=>{
      if(generation!==this.generation || !this.socket.connected) return;
      if(ok===null) {this.lost();this.socket.disconnect();this.socket.connect();return;}
      if(!ok) {this.expired();return;}
      this.connected();
    });
  }
  connected() {
    this.cancel(this.timer); this.timer=null; this.notice=false; this.state='connected';
    this.ready(true); this.paint();
  }
  expired() {
    this.generation++;
    this.cancel(this.timer); this.timer=null; this.state='expired'; this.notice=true;
    this.ready(false); this.paint();
    this.socket.disconnect();
  }
  resume() {
    if(this.state==='expired') return;
    if(!this.online()) {this.lost();return;}
    if(this.state==='connected' && this.socket.connected) return;
    this.lost();
    if(this.socket.connected) this.socket.disconnect();
    this.socket.connect();
  }
}

export function isServerControl(target) {
  // Camera gestures and the local pause/reset/recenter controls keep working.
  if(target.closest('.se-connection-status,[data-se-local]')) return false;
  return !!target.closest('button,a,input,select,textarea,[contenteditable="true"],'
    +'[role="button"],[role="tab"],[role="checkbox"],.se-pattern-canvas');
}

let installAttempts=0;
function install() {
  const socket=window.socket;
  // Component imports can finish after DOMContentLoaded on a slow first load.
  if(!socket) {
    if(++installAttempts<1200) setTimeout(install,50);
    return;
  }
  const notice=document.createElement('aside');
  notice.className='se-connection-status'; notice.hidden=true;
  notice.setAttribute('aria-label','Connection status');
  notice.innerHTML='<div class="se-connection-copy" role="status" aria-live="polite" aria-atomic="true">'
    +'<strong></strong><span></span></div><button type="button" hidden>Retry</button>';
  document.body.append(notice);
  const title=notice.querySelector('strong'),detail=notice.querySelector('span'),button=notice.querySelector('button');
  const copy={
    connecting:['Reconnecting…','Your view is still available. Editing is paused.','Retry'],
    offline:['You’re offline','Your view is still available. We’ll reconnect automatically.','Retry'],
    expired:['Ready to reconnect',window.location.pathname==='/studio'?
      'Reload to restore your latest draft.':'Reload to continue browsing.','Reload'],
  };
  const recovery=new ConnectionRecovery({
    socket,
    initialReady:window.did_handshake,
    initialHandshake:done=>{
      const deadline=Date.now()+10000;
      const check=()=>{
        if(!socket.connected) return;
        if(window.did_handshake) done();
        else if(Date.now()>=deadline) done(false);
        else setTimeout(check,50);
      };
      check();
    },
    online:()=>navigator.onLine,
    ready:value=>{window.did_handshake=value;},
    handshake:done=>socket.timeout(10000).emit('handshake',{
      client_id:window.clientId,document_id:window.documentId,
      tab_id:sessionStorage.__nicegui_tab_id,
      old_tab_id:typeof OLD_TAB_ID==='undefined'?null:OLD_TAB_ID,
      next_message_id:window.nextMessageId,
    },(error,ok)=>done(error?null:ok)),
    render:({state,visible})=>{
      document.documentElement.dataset.seConnection=state;
      notice.hidden=!visible;
      if(!visible) return;
      const words=copy[state];
      // Don't repeatedly announce identical retry messages to screen readers.
      if(title.textContent!==words[0]) title.textContent=words[0];
      if(detail.textContent!==words[1]) detail.textContent=words[1];
      if(button.textContent!==words[2]) button.textContent=words[2];
      button.hidden=false;
    },
  });
  button.addEventListener('click',()=>{
    if(recovery.state==='expired') window.location.reload();
    else recovery.resume();
  });
  // Pause server-backed actions instead of buffering stale clicks and saves.
  // Scrolling, selecting text, and browser-only 3D controls remain available.
  const guard=event=>{
    if(recovery.state==='connected' || !isServerControl(event.target)) return;
    if(event.type==='keydown' && ['Tab','Escape','Shift','Control','Meta','Alt'].includes(event.key)) return;
    event.preventDefault(); event.stopImmediatePropagation();
    recovery.notice=true; recovery.paint();
  };
  for(const event of ['pointerdown','click','keydown','beforeinput','submit']) document.addEventListener(event,guard,true);
  window.addEventListener('offline',()=>recovery.lost());
  window.addEventListener('online',()=>recovery.resume());
  window.addEventListener('pageshow',event=>{if(event.persisted)recovery.resume();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)recovery.resume();});
}

if(typeof document!=='undefined') {
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',install,{once:true});
  else install();
}
