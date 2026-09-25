// Hair for the 3D preview, shaped from the fitted mannequin's own head.
//
// The scalp is the part of the head above a hairline that runs from the
// forehead over the ears to the nape. It is lifted along the surface normals
// into a shell (fuller on top, tapering to the hairline), so every fitted
// body gets hair that fits its head. A bun is an extra swirl at the back of
// the head. Hair is drawn only: it takes no part in cloth collision, and the
// preview hides it under a hood. Coordinates are the scene's metres, y up,
// the mannequin facing +z.

export const HAIR_STYLES = {none: 'None', short: 'Short', bun: 'Bun'};
export const HAIR_COLORS = {'#1f1a17': 'Black', '#3a2a22': 'Dark brown', '#6b4a33': 'Brown',
  '#8c4a2f': 'Auburn', '#c9a36b': 'Blonde', '#9c9a96': 'Grey'};
export const DEFAULT_HAIR = {style: 'short', color: '#3a2a22'};
// Strand width across the flow, in metres: fine enough to read as hair up close.
export const STRAND_M = .0016;

const REFERENCE_HALF_WIDTH = .08;      // the neutral mannequin's skull, at temple height

// Hairline depth below the crown (m, for the reference head) by angle from the front:
// forehead, temple recess, sideburn in front of the ear, over the ear, nape.
const HAIRLINE = [[0, .061], [.5, .066], [.9, .084], [1.2, .124], [1.36, .117], [1.55, .103], [1.82, .106],
                  [2.1, .138], [2.55, .172], [Math.PI, .19]];

function hairline(theta) {
  const a = Math.abs(theta);
  for (let i = 1; i < HAIRLINE.length; i++) {
    const [a0, d0] = HAIRLINE[i - 1], [a1, d1] = HAIRLINE[i];
    if (a <= a1) {
      const t = (a - a0) / (a1 - a0), s = t * t * (3 - 2 * t);
      return d0 + (d1 - d0) * s;
    }
  }
  return HAIRLINE[HAIRLINE.length - 1][1];
}

const smooth = (edge0, edge1, x) => {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
};
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = v => { const l = Math.hypot(...v) || 1; return v.map(x => x / l); };

/** Where the head is: crown height, a centre inside the skull, and a size factor. */
export function headFrame(vertices) {
  let top = -Infinity;
  for (const p of vertices) top = Math.max(top, p[1]);
  const band = (depth, half = .006) => vertices.filter(p => Math.abs(top - depth - p[1]) < half && Math.abs(p[0]) < .13);
  const skull = band(.05), temples = band(.08);
  const range = (points, axis) => [Math.min(...points.map(p => p[axis])), Math.max(...points.map(p => p[axis]))];
  const [x0, x1] = range(temples, 0), [z0, z1] = range(skull, 2);
  const halfWidth = (x1 - x0) / 2;
  return {top, centre: [(x0 + x1) / 2, top - .1 * halfWidth / REFERENCE_HALF_WIDTH, (z0 + z1) / 2],
          scale: halfWidth / REFERENCE_HALF_WIDTH, back: z0};
}

/** The hair mesh for a style, or null for none. Arrays are ready for GPU buffers. */
export function hairMesh(scene, style = DEFAULT_HAIR.style) {
  if (!HAIR_STYLES[style] || style === 'none') return null;
  const vertices = scene.body_vertices, normals = scene.body_normals;
  const head = headFrame(vertices), {top, centre, scale} = head;
  // Scalp: head vertices above the hairline, with how far above it each lies.
  const above = new Float32Array(vertices.length).fill(-1);
  for (let i = 0; i < vertices.length; i++) {
    const p = vertices[i];
    const depth = top - p[1];
    if (depth > .24 * scale || Math.abs(p[0] - centre[0]) > .13 * scale) continue;
    const theta = Math.atan2(p[0] - centre[0], p[2] - centre[2]);
    above[i] = hairline(theta) * scale - depth;
  }
  // Cut the scalp out along the hairline itself, not along the mesh's triangles,
  // so its edge is as smooth as the hairline curve.
  const points = [], norms = [], rise = [], faces = [], index = new Map(), cut = new Map();
  const vertexOf = i => {
    if (!index.has(i)) { index.set(i, points.length); points.push(vertices[i]); norms.push(normals[i]); rise.push(above[i]); }
    return index.get(i);
  };
  const crossing = (i, j) => {
    const key = i < j ? `${i},${j}` : `${j},${i}`;
    if (!cut.has(key)) {
      const t = above[i] / (above[i] - above[j]), p = vertices[i], q = vertices[j], m = normals[i], n = normals[j];
      points.push([0, 1, 2].map(k => p[k] + (q[k] - p[k]) * t));
      norms.push(unit([0, 1, 2].map(k => m[k] + (n[k] - m[k]) * t)));
      rise.push(0);
      cut.set(key, points.length - 1);
    }
    return cut.get(key);
  };
  for (const face of scene.body_faces) {
    const inside = face.map(i => above[i] > 0), count = inside.filter(Boolean).length;
    if (!count) continue;
    const polygon = [];
    for (let k = 0; k < 3; k++) {
      const here = face[k], next = face[(k + 1) % 3];
      if (inside[k]) polygon.push(vertexOf(here));
      if (inside[k] !== inside[(k + 1) % 3]) polygon.push(crossing(here, next));
    }
    for (let k = 1; k + 1 < polygon.length; k++) faces.push(polygon[0], polygon[k], polygon[k + 1]);
  }
  if (!faces.length) return null;
  // Lift the scalp: volume on top, close to the head at the sides, feathered at the hairline.
  const lifted = points.map((p, i) => {
    const n = norms[i], depth = top - p[1];
    const crown = 1 - smooth(0, .13 * scale, depth);
    const thickness = style === 'bun' ? .0045 : .006 + .011 * crown;
    const feather = Math.max(.12, smooth(0, .016 * scale, rise[i]));
    const t = thickness * feather * scale;
    return [p[0] + n[0] * t, p[1] + n[1] * t, p[2] + n[2] * t];
  });
  const parts = [{points: lifted, faces}];
  // Strands run from a whorl: the crown for short hair, into the bun for a bun.
  let pole = unit([0, 1, -.35]);
  if (style === 'bun') {
    const bun = bunMesh(head);
    parts.push(bun);
    pole = unit(sub(bun.centre, centre));
  }
  return assemble(parts, centre, pole, scale);
}

/** A swirl at the back of the head, a little above the nape so collars stay clear. */
function bunMesh(head) {
  const {centre, scale, back} = head;
  const radii = [.043 * scale, .037 * scale, .03 * scale];
  const middle = [centre[0], centre[1] - .012 * scale, back - .012 * scale];
  const points = [], normals = [], faces = [], swirl = [], rows = 14, cols = 28;
  for (let r = 0; r <= rows; r++) {
    const lat = -Math.PI / 2 + Math.PI * r / rows;
    for (let c = 0; c <= cols; c++) {
      const lon = 2 * Math.PI * c / cols;
      // Its axis points backwards (−z), so the swirl faces away from the head.
      const local = [Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), -Math.sin(lat)];
      points.push([middle[0] + local[0] * radii[0], middle[1] + local[1] * radii[1], middle[2] + local[2] * radii[2]]);
      // The ellipsoid's own normals: its poles sit only on zero-area triangles.
      normals.push(unit([local[0] / radii[0], local[1] / radii[1], local[2] / radii[2]]));
      swirl.push([lat * radii[0], lon * radii[0] * Math.cos(lat)]);
    }
  }
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const a = r * (cols + 1) + c, b = a + 1, d = a + cols + 1, e = d + 1;
      faces.push(a, d, b, b, d, e);
    }
  }
  return {points, normals, faces, centre: middle, uv: swirl};
}

function assemble(parts, centre, pole, scale) {
  const count = parts.reduce((n, part) => n + part.points.length, 0);
  const positions = new Float32Array(count * 4), normals = new Float32Array(count * 4);
  const uv = new Float32Array(count * 2), indices = [];
  // Flow coordinates about the pole: across the strands (u) and along them (v).
  const e1 = unit(cross(Math.abs(pole[1]) < .9 ? [0, 1, 0] : [1, 0, 0], pole)), e2 = cross(pole, e1);
  const radius = .085 * scale;
  let base = 0;
  for (const part of parts) {
    part.points.forEach((p, i) => {
      positions.set([...p, 1], (base + i) * 4);
      if (part.uv) {
        uv.set(part.uv[i], (base + i) * 2);
      } else {
        const q = sub(p, centre), along = Math.acos(Math.max(-1, Math.min(1, dot(unit(q), pole))));
        uv.set([Math.atan2(dot(q, e2), dot(q, e1)) * radius * Math.sin(Math.max(along, .2)), along * radius], (base + i) * 2);
      }
    });
    for (const f of part.faces) indices.push(base + f);
    base += part.points.length;
  }
  // Normals of the lifted surface itself, area-weighted, where a part brings none.
  for (let f = 0; f < indices.length; f += 3) {
    const [a, b, c] = [indices[f], indices[f + 1], indices[f + 2]];
    const pa = positions.subarray(a * 4, a * 4 + 3), pb = positions.subarray(b * 4, b * 4 + 3), pc = positions.subarray(c * 4, c * 4 + 3);
    const n = cross(sub(pb, pa), sub(pc, pa));
    for (const i of [a, b, c]) for (let k = 0; k < 3; k++) normals[i * 4 + k] += n[k];
  }
  for (let i = 0; i < count; i++) {
    const n = unit([normals[i * 4], normals[i * 4 + 1], normals[i * 4 + 2]]);
    normals.set([...n, 1], i * 4);
  }
  base = 0;
  for (const part of parts) {
    part.normals?.forEach((n, i) => normals.set([...n, 1], (base + i) * 4));
    base += part.points.length;
  }
  return {positions, normals, uv, faces: Uint32Array.from(indices), count};
}

/** A hood covers the head: hair would show through it, and it is not simulated. */
export function coveredHead(scene) {
  return (scene.vertex_panels || []).some(panel => /hood/i.test(panel));
}
