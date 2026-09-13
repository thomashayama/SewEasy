"""Measure browser-generated collar geometry against its draft and mannequin."""
import argparse
import json
from pathlib import Path

import igl
import numpy as np

ROOT=Path(__file__).resolve().parents[1]/'output/webgpu'


def analyze(path):
    capture=json.loads(path.read_text())
    report=capture['report']
    scene=json.loads((ROOT/f"{report['scene']}.json").read_text())
    q=np.asarray(capture['positions'])
    assert q.shape==(len(scene['vertices']),3) and np.isfinite(q).all()
    names=np.asarray(scene['vertex_panels'])
    mask=np.array(['collar' in n or 'stand' in n for n in names])
    faces=np.asarray(scene['faces'])
    cf=faces[mask[faces].all(axis=1)]
    world=q[cf]
    rest=np.asarray(scene['uv'])[cf]
    ds=np.stack([world[:,1]-world[:,0],world[:,2]-world[:,0]],axis=-1)
    dm=np.stack([rest[:,1]-rest[:,0],rest[:,2]-rest[:,0]],axis=-1)
    stretch=np.linalg.svd(ds@np.linalg.inv(dm),compute_uv=False)[:,0]
    seams=[c for c in scene['constraints'] if c[2]==2 and (mask[c[0]] or mask[c[1]])]
    gaps=[np.linalg.norm(q[c[0]]-q[c[1]])*1000 for c in seams]
    samples=np.concatenate([q[mask],world.mean(axis=1),*(.5*(world[:,a]+world[:,b]) for a,b in [(0,1),(1,2),(2,0)])])
    distance=igl.signed_distance(samples,np.asarray(scene['body_vertices']),np.asarray(scene['body_faces']),igl.SIGNED_DISTANCE_TYPE_PSEUDONORMAL)[0]
    fold_errors=[]
    for h in scene['hinges']:
        a,b,c,d,e,f=q[h['ids']]
        p0,p1=(a+d)*.5,(b+e)*.5
        axis=p1-p0;axis/=np.linalg.norm(axis)
        n0=np.cross(axis,c-p0);n0/=np.linalg.norm(n0)
        n1=np.cross(f-p0,axis);n1/=np.linalg.norm(n1)
        angle=np.arctan2(np.dot(np.cross(n0,n1),axis),np.dot(n0,n1))
        delta=angle-h['angle']
        fold_errors.append(abs(np.arctan2(np.sin(delta),np.cos(delta)))*180/np.pi)
    result=dict(scene=report['scene'],frames=report['frames'],ms_per_frame=report['msPerFrame'],
        collar_triangles=len(cf),collar_seam_max_mm=max(gaps),collar_stretch_p95=float(np.percentile(stretch,95)),
        collar_stretch_max=float(stretch.max()),fold_error_p95_deg=float(np.percentile(fold_errors,95)),
        body_samples=len(samples),inside_body_samples=int((distance < -1e-5).sum()),
        body_penetration_max_mm=max(0.,-float(distance.min()))*1000)
    result['tip_drop_cm']={side:float((q[names==f'{side}_stand_front',1].max()-q[names==f'{side}_collar_front',1].min())*100) for side in ['left','right']}
    path.with_suffix('.collar-analysis.json').write_text(json.dumps(result,indent=2))
    assert all(d>2 for d in result['tip_drop_cm'].values()), 'Collar tip flipped upward'
    assert result['collar_seam_max_mm']<5, 'Collar seam opened'
    assert result['body_penetration_max_mm']<1, 'Collar penetrated the mannequin'
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures',nargs='+',type=Path)
    for path in parser.parse_args().captures:
        print(json.dumps(analyze(path)))
