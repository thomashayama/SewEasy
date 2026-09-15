// Arrange each open trouser leg around its own leg before sewing. Pulling two
// flat sheets together through the feet can close the hem on the wrong side of
// an ankle. Only initial positions change; UV rest lengths and stitches do not.
export function placeTrouserLegs(scene,positions) {
 const names=scene.vertex_panels||[],panels=new Map(),rings=new Map();
 names.forEach((name,i)=>{
  if(!/(^|__)pant_[fb]_[lr]$/.test(name))return;
  if(!panels.has(name))panels.set(name,[]);panels.get(name).push(i);
  const id=scene.sewn_ids?.[i];if(!rings.has(id))rings.set(id,[]);rings.get(id).push(i);
 });
 if(!panels.size||!scene.body_vertices?.length)return [];
 const height=Math.max(...scene.body_vertices.map(v=>v[1])),sections=new Map();
 const section=(y,side=0)=>{
  const level=Math.round(y*100)/100,key=`${level}:${side}`;
  if(sections.has(key))return sections.get(key);
  const ring=scene.body_vertices.filter(v=>Math.abs(v[1]-level)<.02&&(side?v[0]*side>0:Math.abs(v[0])<height*.2));
  const box=ring.length?{lo:[0,2].map(a=>Math.min(...ring.map(v=>v[a]))),hi:[0,2].map(a=>Math.max(...ring.map(v=>v[a])))}:null;
  sections.set(key,box);return box;
 };
 const torsoPoint=(y,angle,front)=>{
  const box=section(y);if(!box)return null;
  const {lo,hi}=box;
  return [(lo[0]+hi[0])/2+((hi[0]-lo[0])/2+.012)*Math.sin(angle),y,
   (lo[1]+hi[1])/2+front*((hi[1]-lo[1])/2+.012)*Math.cos(angle)];
 };
 const boundaries=new Map();
 for(const face of scene.faces||[])if(panels.has(names[face[0]])){
  for(let e=0;e<3;e++){
   const a=face[e],b=face[(e+1)%3],key=`${Math.min(a,b)}:${Math.max(a,b)}`;
   if(boundaries.has(key))boundaries.delete(key);else boundaries.set(key,[a,b]);
  }
 }
 const edges=new Map([...panels.keys()].map(name=>[name,[]]));
 for(const [a,b] of boundaries.values())edges.get(names[a]).push([positions[a],positions[b]]);
 const rowWidth=(name,y)=>{
  const xs=[];
  for(const [a,b] of edges.get(name)||[]){
   if(y<Math.min(a[1],b[1])-1e-6||y>Math.max(a[1],b[1])+1e-6)continue;
   const t=Math.abs(b[1]-a[1])<1e-7?0:Math.max(0,Math.min(1,(y-a[1])/(b[1]-a[1])));
   xs.push(a[0]+t*(b[0]-a[0]));
  }
  return xs.length?[Math.min(...xs),Math.max(...xs)]:null;
 };
 const adjusted=[];
 for(const prefix of new Set([...panels.keys()].map(name=>name.slice(0,-8)))){
  const junction=[...rings.values()].find(ids=>new Set(ids.filter(i=>names[i].startsWith(prefix)).map(i=>names[i])).size===4);
  if(!junction)continue;
  const crotch=junction.reduce((sum,i)=>sum+positions[i][1],0)/junction.length;
  for(const side of ['l','r']){
   const sign=side==='l'?1:-1;
   for(const face of ['f','b']){
    const name=`${prefix}pant_${face}_${side}`,other=`${prefix}pant_${face==='f'?'b':'f'}_${side}`;
    for(const i of panels.get(name)||[]){
     const p=positions[i],blend=Math.max(0,Math.min(1,(crotch+.06-p[1])/.12));
     const row=rowWidth(name,p[1]),opposite=rowWidth(other,p[1]);
     if(!row||row[1]-row[0]<.01)continue;
     const box=section(p[1],sign);if(!box)continue;
     const {lo,hi}=box;
     const center=lo.map((v,a)=>(v+hi[a])/2),radii=lo.map((v,a)=>(hi[a]-v)/2+.012);
     const circumference=row[1]-row[0]+(opposite?opposite[1]-opposite[0]:row[1]-row[0]);
     const scale=Math.max(1,circumference/(2*Math.PI*Math.hypot(...radii)/Math.SQRT2));
     const u=sign>0?(p[0]-row[0])/(row[1]-row[0]):(row[1]-p[0])/(row[1]-row[0]);
     const leg=[center[0]-sign*radii[0]*scale*Math.cos(Math.PI*u),p[1],center[1]+(face==='f'?1:-1)*radii[1]*scale*Math.sin(Math.PI*u)];
     const torso=torsoPoint(p[1],sign*Math.PI*u/2,face==='f'?1:-1);if(!torso)continue;
     positions[i]=leg.map((v,a)=>torso[a]+(v-torso[a])*blend);
    }
   }
  }
  for(const face of ['front','back']){
   const ids=names.flatMap((name,i)=>name===`${prefix}wb_${face}`?[i]:[]);
   if(!ids.length)continue;
   const lo=Math.min(...ids.map(i=>positions[i][0])),hi=Math.max(...ids.map(i=>positions[i][0]));
   for(const i of ids){const p=positions[i];positions[i]=torsoPoint(p[1],((p[0]-lo)/(hi-lo)-.5)*Math.PI,face==='front'?1:-1)||p;}
  }
  adjusted.push({prefix,part:'trouser legs',placement:'wrapped around each leg before sewing',crotch_y_m:crotch});
 }
 return adjusted;
}
