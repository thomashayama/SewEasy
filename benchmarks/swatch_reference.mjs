// CPU reference of the browser swatch solver, for convergence studies.
//
// It repeats gui/webgpu/swatch_solver.js and membrane.js step for step:
// semi-implicit integration, coloured Gauss-Seidel XPBD over the orthotropic
// membrane and dihedral constraints with multipliers accumulated inside a
// substep, then a damped, clamped velocity update. Triangles within a colour
// share no vertex, so solving them in stored order equals the GPU's dispatch.
//
// The loaded fixtures have an exact answer. The energy has no Poisson coupling,
// a uniform strain is representable by linear triangles, and trapezoidal edge
// loads are consistent with them, so a converged strip extends by exactly
// traction / stiffness on any mesh. Any other reading is solver error.
//
//   node benchmarks/swatch_reference.mjs            sweep the documented samples
import {readFileSync} from 'node:fs';

const FRAME=1/60;

export function simulate(scene,{substeps,iterations,seconds=8,precision=32,order='forward',settle=1e-7}={}){
  // Unless told otherwise, step exactly as the application would for this scene.
  const bending0=scene.fabric_test.mode==='bend',sized=scene.fabric_test.numerics||{substeps:48,iterations:32};
  substeps??=bending0?12:sized.substeps;iterations??=bending0?4:sized.iterations;
  const Real=precision===32?Float32Array:Float64Array,r=precision===32?Math.fround:x=>x;
  const n=scene.vertices.length,p=new Real(n*3),old=new Real(n*3),v=new Real(n*3),w=Real.from(scene.inverse_mass);
  scene.vertices.forEach((q,i)=>p.set(q,i*3));
  const bending=scene.fabric_test.mode==='bend';
  const membranes=scene.membranes,hinges=bending?scene.interior_hinges:[];
  const lambdaM=new Real(membranes.length*3),lambdaH=new Real(hinges.length);
  const gravity=scene.fabric_test.gravity,damping=scene.fabric_test.damping,force=scene.external_forces;
  const dt=r(FRAME/substeps),inverseDt2=1/(dt*dt),decay=r(Math.exp(-damping*dt));
  // One sweep visits every colour; "symmetric" reverses alternate sweeps.
  const colours=[...scene.membrane_batches.map(b=>['m',...b]),...(bending?scene.interior_hinge_batches.map(b=>['h',...b]):[])];

  // Flat arrays and scalar arithmetic: this runs a few hundred thousand times per frame.
  const MI=Int32Array.from(membranes.flatMap(m=>m.ids.map(i=>i*3))),MU=Float64Array.from(membranes.flatMap(m=>m.u));
  const MV=Float64Array.from(membranes.flatMap(m=>m.v)),MC=Float64Array.from(membranes.flatMap(m=>m.compliance));
  function membrane(index,first){
    const o=index*3,ia=MI[o],ib=MI[o+1],ic=MI[o+2],ua=MU[o],ub=MU[o+1],uc=MU[o+2],va=MV[o],vb=MV[o+1],vc=MV[o+2];
    const wa=w[ia/3],wb=w[ib/3],wc=w[ic/3];
    for(let axis=0;axis<3;axis++){
      const compliance=MC[o+axis];if(compliance<0)continue;
      const fux=ua*p[ia]+ub*p[ib]+uc*p[ic],fuy=ua*p[ia+1]+ub*p[ib+1]+uc*p[ic+1],fuz=ua*p[ia+2]+ub*p[ib+2]+uc*p[ic+2];
      const fvx=va*p[ia]+vb*p[ib]+vc*p[ic],fvy=va*p[ia+1]+vb*p[ib+1]+vc*p[ic+1],fvz=va*p[ia+2]+vb*p[ib+2]+vc*p[ic+2];
      const lu=r(Math.sqrt(fux*fux+fuy*fuy+fuz*fuz)),lv=r(Math.sqrt(fvx*fvx+fvy*fvy+fvz*fvz));if(Math.min(lu,lv)<1e-8)continue;
      let error,gux=0,guy=0,guz=0,gvx=0,gvy=0,gvz=0;
      if(axis===0){error=r(lu-1);gux=fux/lu;guy=fuy/lu;guz=fuz/lu;}
      else if(axis===1){error=r(lv-1);gvx=fvx/lv;gvy=fvy/lv;gvz=fvz/lv;}
      else{
        const inv=1/(lu*lv);error=r((fux*fvx+fuy*fvy+fuz*fvz)*inv);
        const su=error/(lu*lu),sv=error/(lv*lv);
        gux=fvx*inv-su*fux;guy=fvy*inv-su*fuy;guz=fvz*inv-su*fuz;gvx=fux*inv-sv*fvx;gvy=fuy*inv-sv*fvy;gvz=fuz*inv-sv*fvz;
      }
      const ax=ua*gux+va*gvx,ay=ua*guy+va*gvy,az=ua*guz+va*gvz,bx=ub*gux+vb*gvx,by=ub*guy+vb*gvy,bz=ub*guz+vb*gvz;
      const cx=uc*gux+vc*gvx,cy=uc*guy+vc*gvy,cz=uc*guz+vc*gvz;
      const denominator=wa*(ax*ax+ay*ay+az*az)+wb*(bx*bx+by*by+bz*bz)+wc*(cx*cx+cy*cy+cz*cz);
      const alpha=compliance*inverseDt2,accumulated=first?0:lambdaM[o+axis];
      const step=r(-(error+alpha*accumulated)/Math.max(denominator+alpha,1e-12));
      lambdaM[o+axis]=accumulated+step;
      p[ia]+=wa*step*ax;p[ia+1]+=wa*step*ay;p[ia+2]+=wa*step*az;p[ib]+=wb*step*bx;p[ib+1]+=wb*step*by;p[ib+2]+=wb*step*bz;
      p[ic]+=wc*step*cx;p[ic+1]+=wc*step*cy;p[ic+2]+=wc*step*cz;
    }
  }
  const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]],dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  function hinge(index,first){
    const h=hinges[index];if(h.compliance<0)return;
    const at=i=>[p[i*3],p[i*3+1],p[i*3+2]],[a,b,c,d]=h.ids.map(at);
    const edge=sub(b,a),length2=dot(edge,edge);if(length2<1e-12)return;
    const len=Math.sqrt(length2),n0=cross(edge,sub(c,a)),n1=cross(sub(d,a),edge),area0=dot(n0,n0),area1=dot(n1,n1);
    if(Math.min(area0,area1)<1e-18)return;
    const u=n0.map(x=>x/Math.sqrt(area0)),normal=n1.map(x=>x/Math.sqrt(area1));
    const delta=Math.atan2(dot(cross(u,normal),edge.map(x=>x/len)),Math.max(-1,Math.min(1,dot(u,normal))))-h.angle;
    const error=r(Math.atan2(Math.sin(delta),Math.cos(delta)));
    const g2=n0.map(x=>-len*x/area0),g3=n1.map(x=>-len*x/area1);
    const t2=dot(sub(c,a),edge)/length2,t3=dot(sub(d,a),edge)/length2;
    const g0=[0,1,2].map(x=>-(1-t2)*g2[x]-(1-t3)*g3[x]),g1=[0,1,2].map(x=>-t2*g2[x]-t3*g3[x]);
    const gs=[g0,g1,g2,g3],weights=h.ids.map(i=>w[i]);
    const denominator=gs.reduce((s,gc,k)=>s+weights[k]*dot(gc,gc),0);
    const alpha=h.compliance*inverseDt2,accumulated=first?0:lambdaH[index];
    const step=r(-(error+alpha*accumulated)/Math.max(denominator+alpha,1e-12));
    lambdaH[index]=accumulated+step;
    h.ids.forEach((i,k)=>{for(let x=0;x<3;x++)p[i*3+x]+=weights[k]*step*gs[k][x];});
  }

  const tip=scene.swatch.tip,length=scene.swatch.length_m,height=scene.swatch.height_m;
  // `tilt` is how much lower one corner of the free edge hangs than the other: a symmetric strip has none.
  const reading=()=>({extension:(tip.reduce((s,i)=>s+p[i*3],0)/tip.length/length-1)*100,
    drop:(height-tip.reduce((s,i)=>s+p[i*3+1],0)/tip.length)*1000,shear:tip.reduce((s,i)=>s+p[i*3+2],0)/tip.length*1000,
    tilt:(p[tip[0]*3+1]-p[tip[tip.length-1]*3+1])*1000});
  const key=bending?'drop':scene.fabric_test.mode==='shear'?'shear':'extension',history=[];
  const frames=Math.round(seconds/FRAME);
  for(let frame=0;frame<frames;frame++){
    for(let step=0;step<substeps;step++){
      const ramp=Math.min(1,Math.max(0,(frame*FRAME+step*dt-.001)/.3));      // the fixture ramps its load in
      old.set(p);
      for(let i=0;i<n;i++){
        if(w[i]===0){v[i*3]=v[i*3+1]=v[i*3+2]=0;continue;}
        for(let x=0;x<3;x++){v[i*3+x]+=((x===1?-gravity:0)+force[i][x]*w[i])*ramp*dt;p[i*3+x]+=v[i*3+x]*dt;}
      }
      for(let iteration=0;iteration<iterations;iteration++){
        const sweep=order==='symmetric'&&iteration%2?[...colours].reverse():colours;
        for(const [kind,start,count] of sweep)for(let k=0;k<count;k++)(kind==='m'?membrane:hinge)(start+k,iteration===0);
      }
      for(let i=0;i<n;i++){
        const o=i*3,vx=(p[o]-old[o])/dt*decay,vy=(p[o+1]-old[o+1])/dt*decay,vz=(p[o+2]-old[o+2])/dt*decay;
        const limit=Math.min(1,3/Math.max(Math.sqrt(vx*vx+vy*vy+vz*vz),1e-8));
        v[o]=vx*limit;v[o+1]=vy*limit;v[o+2]=vz*limit;
      }
    }
    history.push(reading()[key]);
    const recent=history.slice(-30);
    if(frame>60&&Math.max(...recent)-Math.min(...recent)<settle*Math.max(1,Math.abs(recent[0])))
      return {...reading(),seconds:(frame+1)*FRAME,rested:true};
  }
  return {...reading(),seconds,rested:false};
}

export function fixtures(){return JSON.parse(readFileSync(new URL('./swatch_fixtures.json',import.meta.url),'utf8'));}

if(process.argv[1]?.endsWith('swatch_reference.mjs')){
  const all=fixtures(),args=Object.fromEntries(process.argv.slice(2).map(a=>a.replace(/^--/,'').split('=')));
  const options={substeps:args.substeps&&+args.substeps,iterations:args.iterations&&+args.iterations,
    precision:+(args.precision||32),seconds:+(args.seconds||8),order:args.order||'forward'};
  for(const [name,scene] of Object.entries(all)){
    if(scene.fabric_test.mode!==(args.mode||'stretch'))continue;
    const started=performance.now(),result=simulate(scene,options),expected=scene.fabric_test.expected_extension_percent;
    const used=scene.fabric_test.numerics||{};
    console.log(JSON.stringify({fixture:name,substeps:options.substeps??used.substeps,iterations:options.iterations??used.iterations,expected:expected&&+expected.toFixed(4),
      extension:+result.extension.toFixed(4),relative_error:expected?+(result.extension/expected-1).toFixed(4):null,
      drop_mm:+result.drop.toFixed(3),shear_mm:+result.shear.toFixed(4),rested:result.rested,sim_s:+result.seconds.toFixed(2),
      wall_s:+((performance.now()-started)/1000).toFixed(1)}));
  }
}
