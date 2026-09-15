// Native scrolling and keyboard behavior stay intact; only its chrome fades.
const style=document.createElement('style');
style.textContent=`
@property --se-scroll-thumb {syntax:'<color>';inherits:true;initial-value:transparent;}
* {--se-scroll-thumb:transparent;scrollbar-width:thin;scrollbar-color:var(--se-scroll-thumb) transparent;transition:--se-scroll-thumb 180ms;}
*.se-scrolling {--se-scroll-thumb:var(--se-scroll-active,rgba(72,94,110,.42));}
@supports selector(::-webkit-scrollbar) {
 * {scrollbar-width:auto;scrollbar-color:auto;}
 *::-webkit-scrollbar {width:4px;height:4px;}
 *::-webkit-scrollbar-track, *::-webkit-scrollbar-corner {background:transparent;}
 *::-webkit-scrollbar-thumb {background:var(--se-scroll-thumb);border-radius:4px;}
 *::-webkit-scrollbar-thumb:hover {background:var(--se-scroll-hover,rgba(72,94,110,.65));}
 *::-webkit-scrollbar-button {display:none;width:0;height:0;}
}
@media (prefers-reduced-motion:reduce) {* {transition:none;}}
`;
document.head.append(style);
const timers=new WeakMap();
document.addEventListener('scroll',event=>{
 const target=event.target===document?document.scrollingElement:event.target;
 if(!(target instanceof Element))return;
 target.classList.add('se-scrolling');clearTimeout(timers.get(target));
 timers.set(target,setTimeout(()=>{target.classList.remove('se-scrolling');timers.delete(target);},800));
},{capture:true,passive:true});
