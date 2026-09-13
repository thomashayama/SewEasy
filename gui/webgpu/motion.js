// Cloth stays in world space; only the collider and its mesh turn. Bounded
// acceleration avoids teleporting contact when a pointer moves a long way.
export class MannequinMotion {
  constructor(vertices) {
    this.center=[0,1,2].map(a=>{
      let lo=Infinity,hi=-Infinity;
      for(const p of vertices){lo=Math.min(lo,p[a]);hi=Math.max(hi,p[a]);}
      return (lo+hi)/2;
    });
    this.reset();
  }
  reset(){this.yaw=0;this.target=0;this.speed=0;}
  turn(angle){this.target=Math.max(this.yaw-Math.PI,Math.min(this.yaw+Math.PI,this.target+angle));}
  front(){this.target=this.yaw-Math.atan2(Math.sin(this.yaw),Math.cos(this.yaw));}
  advance(dt){
    const error=this.target-this.yaw;
    const acceleration=Math.max(-9,Math.min(9,80*error-18*this.speed));
    this.speed=Math.max(-2.4,Math.min(2.4,this.speed+acceleration*dt));
    this.yaw+=this.speed*dt;
    if(Math.abs(error)<1e-5&&Math.abs(this.speed)<1e-4){this.yaw=this.target;this.speed=0;}
  }
  uniform(previous=this.yaw){
    return new Float32Array([Math.cos(this.yaw),Math.sin(this.yaw),Math.cos(previous),Math.sin(previous),...this.center,0]);
  }
}

// Transform queries into the original body coordinates, preserving the cached
// SDF/BVH. Contact friction uses motion relative to the moving body surface.
export const bodyMotionWGSL=`
struct BodyMotion { angle:vec4<f32>, center:vec4<f32> }
fn turn(v:vec3<f32>,cs:vec2<f32>)->vec3<f32>{return vec3<f32>(cs.x*v.x+cs.y*v.z,v.y,-cs.y*v.x+cs.x*v.z);}
fn body_local(p:vec3<f32>)->vec3<f32>{return motion.center.xyz+turn(p-motion.center.xyz,motion.angle.xy*vec2<f32>(1,-1));}
fn body_normal(n:vec3<f32>)->vec3<f32>{return turn(n,motion.angle.xy);}
fn body_movement(p:vec3<f32>)->vec3<f32>{return p-(motion.center.xyz+turn(body_local(p)-motion.center.xyz,motion.angle.zw));}
`;
