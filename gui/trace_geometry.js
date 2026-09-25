// Plane-to-plane maths for the pattern projector (trace_view.js).
//
// Three planes: a piece's own pattern coordinates and the table are both in
// centimetres; the screen is in CSS pixels. Calibration fixes a table
// rectangle of known size (width x height cm) to four screen points, which is
// a homography: it corrects the projector's scale and keystone together.
// Matrices are 3x3, row-major, as flat arrays of nine numbers.

export const CM_PER_IN = 2.54;
// What CSS says a centimetre is. True on few screens and no projector; only
// the starting guess before calibration.
export const NOMINAL_PX_PER_CM = 96 / CM_PER_IN;

export function multiply(a, b) {
  const r = new Array(9);
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      r[i * 3 + j] = a[i * 3] * b[j] + a[i * 3 + 1] * b[3 + j] + a[i * 3 + 2] * b[6 + j];
    }
  }
  return r;
}

export function invert(m) {
  const [a, b, c, d, e, f, g, h, i] = m;
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-12) return null;
  return [A / det, -(b * i - c * h) / det, (b * f - c * e) / det,
          B / det, (a * i - c * g) / det, -(a * f - c * d) / det,
          C / det, -(a * h - b * g) / det, (a * e - b * d) / det];
}

// A point through a homography, or null when it falls behind the horizon.
export function apply(m, x, y) {
  const w = m[6] * x + m[7] * y + m[8];
  if (w <= 1e-9) return null;
  return [(m[0] * x + m[1] * y + m[2]) / w, (m[3] * x + m[4] * y + m[5]) / w];
}

// Table rectangle (0,0)-(width,height) cm onto a screen quad listed top-left,
// top-right, bottom-right, bottom-left (Heckbert's square-to-quad mapping).
export function rectToQuad(width, height, quad) {
  if (!(width > 0 && height > 0)) return null;
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = quad;
  const sx = x0 - x1 + x2 - x3, sy = y0 - y1 + y2 - y3;
  let g = 0, h = 0;
  if (Math.abs(sx) > 1e-9 || Math.abs(sy) > 1e-9) {
    const dx1 = x1 - x2, dx2 = x3 - x2, dy1 = y1 - y2, dy2 = y3 - y2;
    const den = dx1 * dy2 - dx2 * dy1;
    if (Math.abs(den) < 1e-12) return null;
    g = (sx * dy2 - dx2 * sy) / den;
    h = (dx1 * sy - sx * dy1) / den;
  }
  const a = x1 - x0 + g * x1, b = x3 - x0 + h * x3;
  const d = y1 - y0 + g * y1, e = y3 - y0 + h * y3;
  return [a / width, b / height, x0, d / width, e / height, y0, g / width, h / height, 1];
}

// Corners that keep one winding and no three in a line: anything else folds
// the table over itself and cannot be traced from.
export function isConvex(quad) {
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const [ax, ay] = quad[i], [bx, by] = quad[(i + 1) % 4], [cx, cy] = quad[(i + 2) % 4];
    const cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx);
    if (Math.abs(cross) < 1e-6) return false;
    if (sign && Math.sign(cross) !== sign) return false;
    sign = Math.sign(cross);
  }
  return true;
}

// Moves a piece from its own coordinates onto the table: turn it by
// `rotation` degrees (and mirror it) about its centre, then put that centre
// at (x, y) cm.
export function pieceMatrix(center, placement) {
  const turn = placement.rotation * Math.PI / 180;
  const cos = Math.cos(turn), sin = Math.sin(turn), mirror = placement.flip ? -1 : 1;
  const [cx, cy] = center;
  return [cos * mirror, -sin, placement.x - cos * mirror * cx + sin * cy,
          sin * mirror, cos, placement.y - sin * mirror * cx - cos * cy,
          0, 0, 1];
}

// Screen pixels per centimetre around a table point, along the table's x and
// y axes; they differ under keystone.
export function localScale(m, x, y) {
  const here = apply(m, x, y), right = apply(m, x + 1, y), down = apply(m, x, y + 1);
  if (!here || !right || !down) return null;
  return [Math.hypot(right[0] - here[0], right[1] - here[1]),
          Math.hypot(down[0] - here[0], down[1] - here[1])];
}

// The table region a viewport shows, as [x0, y0, x1, y1] cm.
export function visibleTable(toTable, width, height) {
  const corners = [[0, 0], [width, 0], [width, height], [0, height]].map(([x, y]) => apply(toTable, x, y));
  if (corners.some(c => !c)) return null;
  const xs = corners.map(c => c[0]), ys = corners.map(c => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// A starting calibration: a width x height rectangle centred in the viewport,
// as large as fits in `fill` of it.
export function fittedQuad(width, height, viewWidth, viewHeight, fill = 0.8) {
  const scale = Math.min(fill * viewWidth / width, fill * viewHeight / height);
  const w = width * scale, h = height * scale;
  const x = (viewWidth - w) / 2, y = (viewHeight - h) / 2;
  return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}
