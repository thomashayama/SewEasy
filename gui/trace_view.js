// Pattern projector: true-scale pattern pieces on a projector or TV.
//
// Calibrate: a rectangle of known size on the table (marks on a cutting mat,
// or whatever the corner markers measure apart) is pinned to four screen
// points. Each corner carries a square of known size to check with a ruler.
// The four points give a homography, which fixes scale and keystone together.
// Trace: pieces are placed on that table in centimetres; drag, turn and
// mirror them over the fabric or paper. Calibration and layouts stay in this
// browser (localStorage): they belong to a display, not to an account.
import {CM_PER_IN, NOMINAL_PX_PER_CM, apply, fittedQuad, invert, isConvex, localScale, multiply,
        pieceMatrix, rectToQuad, visibleTable} from './trace_geometry.js';

const DATA = JSON.parse(document.getElementById('se-trace-data').textContent || 'null');
const root = document.getElementById('se-trace');
const SVG_NS = 'http://www.w3.org/2000/svg';
const STORE = 'seweasy.trace.v1';
const ACCENT = '#ff9f1c';
const PALETTES = {dark: ['#ffe14d', '#ffffff', '#3de0ff', '#7dff6a', '#ff5ce1'],
                  light: ['#000000', '#1f4fd6', '#c81e1e']};

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function store(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private window: this session only */ }
}
const esc = text => String(text).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const round = (value, digits = 2) => Math.round(value * 10 ** digits) / 10 ** digits;

// ---------------------------------------------------------------- state

const saved = load(STORE, {});
const settings = {
  unit: saved.unit || DATA?.units || 'cm',
  profile: saved.profile || 'Projector',
  profiles: saved.profiles || {},
  view: {background: 'dark', color: PALETTES.dark[0], width: 2, labels: true, marks: true, grid: false,
         squares: true, ...(saved.view || {})},
};
let cal = settings.profiles[settings.profile] || defaultCalibration();
let mode = DATA?.pieces?.length && settings.profiles[settings.profile] ? 'trace' : 'calibrate';
let selected = null, selectedCorner = 0, dragging = null, frame = 0;

function viewport() {
  return [innerWidth, innerHeight, window.devicePixelRatio || 1];
}

function defaultCalibration() {
  const [width, height] = viewport();
  const unit = settings.unit === 'in' ? CM_PER_IN : 1;
  // A rectangle filling most of the window at the nominal CSS size, in whole units.
  const w = Math.max(1, Math.round(0.8 * width / NOMINAL_PX_PER_CM / unit)) * unit;
  const h = Math.max(1, Math.round(0.8 * height / NOMINAL_PX_PER_CM / unit)) * unit;
  return {width: w, height: h, square: settings.unit === 'in' ? 2 * CM_PER_IN : 5,
          corners: fittedQuad(w, h, width, height), viewport: viewport()};
}

function persist() {
  settings.profiles[settings.profile] = cal;
  store(STORE, settings);
}

const pieces = (DATA?.pieces || []).map(piece => ({
  ...piece,
  center: [(piece.bbox[0] + piece.bbox[2]) / 2, (piece.bbox[1] + piece.bbox[3]) / 2],
}));
const layoutKey = 'seweasy.trace.layout.' + hash(DATA?.key || '');
let placements = load(layoutKey, null) || defaultLayout();

function hash(text) {
  let h = 5381;
  for (let i = 0; i < text.length; i++) h = (h * 33 ^ text.charCodeAt(i)) >>> 0;
  return h.toString(36);
}

// The studio's cutting layout, its top-left corner 2 cm inside the calibrated rectangle.
function defaultLayout() {
  const x0 = Math.min(...pieces.map(p => p.bbox[0])), y0 = Math.min(...pieces.map(p => p.bbox[1]));
  return Object.fromEntries(pieces.map(p => [p.id, {x: p.center[0] - x0 + 2, y: p.center[1] - y0 + 2,
                                                   rotation: 0, flip: false, hidden: false}]));
}

function placement(piece) {
  if (!placements[piece.id]) placements[piece.id] = defaultLayout()[piece.id];
  return placements[piece.id];
}

function saveLayout() {
  store(layoutKey, placements);
}

// ---------------------------------------------------------------- geometry

function homography() {
  return isConvex(cal.corners) ? rectToQuad(cal.width, cal.height, cal.corners) : null;
}

function screenPoint(event) {
  const box = svg.getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
}

function toTable(point) {
  const H = homography(), back = H && invert(H);
  return back ? apply(back, point[0], point[1]) : null;
}

function pathThrough(m, points, close = true) {
  let d = '';
  for (const [x, y] of points) {
    const p = apply(m, x, y);
    if (!p) return '';
    d += (d ? 'L' : 'M') + p[0].toFixed(2) + ' ' + p[1].toFixed(2);
  }
  return d && close ? d + 'Z' : d;
}

function circlePoints(cx, cy, r, count = 24) {
  return Array.from({length: count}, (_, i) => [cx + r * Math.cos(2 * Math.PI * i / count),
                                                cy + r * Math.sin(2 * Math.PI * i / count)]);
}

function unitLabel(cm, digits = 1) {
  return settings.unit === 'in' ? `${round(cm / CM_PER_IN, digits)} in` : `${round(cm, digits)} cm`;
}

// ---------------------------------------------------------------- drawing

const svg = document.createElementNS(SVG_NS, 'svg');
svg.classList.add('se-trace-canvas');
svg.setAttribute('role', 'img');
root.append(svg);

function scheduleRender() {
  if (!frame) frame = requestAnimationFrame(() => { frame = 0; render(); });
}

function render() {
  const [width, height] = viewport();
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  root.classList.toggle('is-light', settings.view.background === 'light');
  const H = homography();
  const line = settings.view.color, stroke = settings.view.width;
  let out = '';
  if (H && (mode === 'calibrate' || settings.view.grid)) out += grid(H, width, height);
  if (H && mode === 'trace') out += drawPieces(H, line, stroke);
  if (mode === 'calibrate') out += calibrationMarks(H);
  else if (H && settings.view.squares) out += cornerSquares(H);
  svg.innerHTML = out;
  svg.setAttribute('aria-label', mode === 'calibrate' ? 'Calibration rectangle with corner squares'
                                                    : `${DATA?.title || 'Pattern'} at true scale`);
  updateStatus(H);
}

function grid(H, width, height) {
  const back = invert(H);
  let bounds = back && visibleTable(back, width, height);
  if (!bounds) bounds = [0, 0, cal.width, cal.height];
  const limit = 1000;   // near the horizon a keystoned table runs away; cm
  const [x0, y0, x1, y1] = bounds.map(v => Math.max(-limit, Math.min(limit, v)));
  const unit = settings.unit === 'in' ? CM_PER_IN : 1, major = settings.unit === 'in' ? 6 : 10;
  const scale = localScale(H, cal.width / 2, cal.height / 2);
  const dense = scale && Math.min(...scale) * unit >= 6;
  let minor = '', strong = '';
  for (const axis of [0, 1]) {
    const [from, to] = axis ? [y0, y1] : [x0, x1];
    for (let k = Math.ceil(from / unit); k * unit <= to; k++) {
      const isMajor = k % major === 0;
      if (!isMajor && !dense) continue;
      const v = k * unit;
      const d = pathThrough(H, axis ? [[x0, v], [x1, v]] : [[v, y0], [v, y1]], false);
      if (isMajor) strong += d; else minor += d;
    }
  }
  return `<path class="se-trace-grid" d="${minor}"/><path class="se-trace-grid is-major" d="${strong}"/>`;
}

function drawPieces(H, line, stroke) {
  let shapes = '', labels = '';
  for (const piece of pieces) {
    const place = placement(piece);
    if (place.hidden) continue;
    const m = multiply(H, pieceMatrix(piece.center, place));
    const d = pathThrough(m, piece.outline);
    if (!d) continue;
    const active = piece.id === selected;
    const color = active ? ACCENT : line;
    shapes += `<path class="se-trace-piece${active ? ' is-selected' : ''}" data-piece="${esc(piece.id)}" d="${d}"`
      + ` stroke="${color}" stroke-width="${active ? stroke + 1 : stroke}"/>`;
    if (settings.view.marks) shapes += marks(m, piece.markers, color, stroke);
    if (settings.view.labels) {
      const at = apply(m, ...piece.center), scale = localScale(m, ...piece.center);
      if (at && scale) {
        const size = Math.max(10, Math.min(48, 1.1 * Math.min(...scale)));
        labels += `<text x="${at[0].toFixed(1)}" y="${at[1].toFixed(1)}" font-size="${size.toFixed(1)}"`
          + ` fill="${color}" class="se-trace-label">${esc(piece.label)}</text>`;
      }
    }
  }
  return shapes + labels;
}

function marks(m, markers, color, stroke) {
  let d = '';
  for (const {kind, values: v} of markers || []) {
    if (kind === 'dot') {
      // A button's centre: a cross is easier to mark through than a dot.
      d += pathThrough(m, [[v[0] - 0.4, v[1]], [v[0] + 0.4, v[1]]], false)
        + pathThrough(m, [[v[0], v[1] - 0.4], [v[0], v[1] + 0.4]], false);
    } else if (kind === 'circle') {
      d += pathThrough(m, circlePoints(v[0], v[1], v[2]));
    } else if (kind === 'line') {
      d += pathThrough(m, [[v[0], v[1]], [v[2], v[3]]], false);
    } else if (kind === 'rect') {
      d += pathThrough(m, [[v[0], v[1]], [v[0] + v[2], v[1]], [v[0] + v[2], v[1] + v[3]], [v[0], v[1] + v[3]]]);
    }
  }
  return d ? `<path class="se-trace-mark" d="${d}" stroke="${color}" stroke-width="${Math.max(1, stroke - 0.5)}"/>` : '';
}

// Squares of the calibrated size just inside each corner of the rectangle.
function squarePaths(H) {
  const s = Math.min(cal.square, cal.width / 2, cal.height / 2), W = cal.width, Ht = cal.height;
  return [[0, 0], [W - s, 0], [W - s, Ht - s], [0, Ht - s]]
    .map(([x, y]) => pathThrough(H, [[x, y], [x + s, y], [x + s, y + s], [x, y + s]]));
}

function cornerSquares(H) {
  return `<path class="se-trace-square" d="${squarePaths(H).join('')}"/>`;
}

function calibrationMarks(H) {
  let out = '';
  const q = cal.corners;
  out += `<path class="se-trace-frame" d="M${q.map(p => p.map(v => v.toFixed(2)).join(' ')).join('L')}Z"/>`;
  if (H) {
    const s = Math.min(cal.square, cal.width / 2, cal.height / 2);
    out += `<path class="se-trace-square is-calibrating" d="${squarePaths(H).join('')}"/>`;
    // Guides running out past each corner, to line up with a mat's grid lines.
    const out4 = 4, W = cal.width, Ht = cal.height;
    const guides = [[[-out4, 0], [0, -out4]], [[W + out4, 0], [W, -out4]], [[W + out4, Ht], [W, Ht + out4]],
                    [[-out4, Ht], [0, Ht + out4]]];
    const corners = [[0, 0], [W, 0], [W, Ht], [0, Ht]];
    out += `<path class="se-trace-guide" d="${guides.map((g, i) => g.map(end => pathThrough(H, [corners[i], end], false)).join('')).join('')}"/>`;
    const text = (x, y, label, anchor = 'middle') => {
      const p = apply(H, x, y);
      return p ? `<text class="se-trace-dim" x="${p[0].toFixed(1)}" y="${p[1].toFixed(1)}" text-anchor="${anchor}">${esc(label)}</text>` : '';
    };
    out += text(W / 2, 1.8, unitLabel(W)) + text(1.2, Ht / 2, unitLabel(Ht), 'start');
    out += text(s / 2, s + 1.6, unitLabel(s)) + text(W - s / 2, s + 1.6, unitLabel(s))
      + text(W - s / 2, Ht - s - 0.8, unitLabel(s)) + text(s / 2, Ht - s - 0.8, unitLabel(s));
  }
  q.forEach(([x, y], i) => {
    out += `<g class="se-trace-handle${i === selectedCorner ? ' is-selected' : ''}" data-corner="${i}">`
      + `<circle cx="${x}" cy="${y}" r="26" class="se-trace-handle-hit"/>`
      + `<circle cx="${x}" cy="${y}" r="9" class="se-trace-handle-ring"/>`
      + `<path d="M${x - 16} ${y}H${x + 16}M${x} ${y - 16}V${y + 16}" class="se-trace-handle-cross"/></g>`;
  });
  return out;
}

// ---------------------------------------------------------------- pointer

svg.addEventListener('pointerdown', event => {
  document.activeElement?.blur?.();
  const point = screenPoint(event);
  const target = event.target.closest('[data-corner], [data-piece]');
  if (mode === 'calibrate') {
    if (!target || target.dataset.corner === undefined) return;
    selectedCorner = Number(target.dataset.corner);
    const [cx, cy] = cal.corners[selectedCorner];
    dragging = {kind: 'corner', offset: [cx - point[0], cy - point[1]]};
  } else {
    const table = toTable(point);
    if (!table) return;
    selected = target?.dataset.piece ?? null;
    dragging = {kind: selected ? 'piece' : 'pan', last: table};
    updatePieceTools();
  }
  svg.setPointerCapture(event.pointerId);
  scheduleRender();
});

svg.addEventListener('pointermove', event => {
  if (!dragging) return;
  const point = screenPoint(event);
  if (dragging.kind === 'corner') {
    cal.corners[selectedCorner] = [point[0] + dragging.offset[0], point[1] + dragging.offset[1]];
    cal.viewport = viewport();
  } else {
    const table = toTable(point);
    if (!table) return;
    const dx = table[0] - dragging.last[0], dy = table[1] - dragging.last[1];
    dragging.last = table;
    for (const piece of pieces) {
      if (dragging.kind === 'pan' || piece.id === selected) {
        const place = placement(piece);
        place.x += dx;
        place.y += dy;
      }
    }
  }
  scheduleRender();
});

function endDrag() {
  if (!dragging) return;
  if (dragging.kind === 'corner') persist(); else saveLayout();
  dragging = null;
}
svg.addEventListener('pointerup', endDrag);
svg.addEventListener('pointercancel', endDrag);

// ---------------------------------------------------------------- piece actions

function selectedPiece() {
  return pieces.find(p => p.id === selected) || null;
}

function turn(degrees) {
  const piece = selectedPiece();
  if (!piece) return;
  const place = placement(piece);
  place.rotation = round(((place.rotation + degrees) % 360 + 360) % 360, 3);
  changed();
}

function mirror() {
  const piece = selectedPiece();
  if (piece) { placement(piece).flip = !placement(piece).flip; changed(); }
}

function hidePiece(id, hidden = true) {
  const piece = pieces.find(p => p.id === id);
  if (!piece) return;
  placement(piece).hidden = hidden;
  if (hidden && selected === id) selected = null;
  changed();
}

function onScreen(piece) {
  const H = homography(), at = H && apply(H, placement(piece).x, placement(piece).y);
  return !!at && at[0] >= 0 && at[1] >= 0 && at[0] <= innerWidth && at[1] <= innerHeight;
}

// The selected piece to the middle of what the screen shows.
function bringToCentre() {
  const piece = selectedPiece(), H = homography(), back = H && invert(H);
  const centre = back && apply(back, innerWidth / 2, innerHeight / 2);
  if (!piece || !centre) return;
  const place = placement(piece);
  [place.x, place.y] = centre;
  changed();
}

function nudge(dx, dy, fine, coarse) {
  if (mode === 'calibrate') {
    const step = coarse ? 10 : fine ? 0.25 : 1;
    const corner = cal.corners[selectedCorner];
    cal.corners[selectedCorner] = [corner[0] + dx * step, corner[1] + dy * step];
    cal.viewport = viewport();
    persist();
  } else {
    const step = coarse ? 1 : 0.1;   // 1 cm or 1 mm on the table
    for (const piece of pieces) {
      if (!selected || piece.id === selected) {
        placement(piece).x += dx * step;
        placement(piece).y += dy * step;
      }
    }
    saveLayout();
  }
  scheduleRender();
}

function changed() {
  saveLayout();
  updatePieceTools();
  scheduleRender();
}

// ---------------------------------------------------------------- controls

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'on') Object.entries(value).forEach(([type, fn]) => node.addEventListener(type, fn));
    else if (key === 'text') node.textContent = value;
    else if (value !== false && value != null) node.setAttribute(key, value === true ? '' : value);
  }
  node.append(...children.filter(c => c != null));
  return node;
}

function button(label, onClick, attrs = {}) {
  return el('button', {type: 'button', ...attrs, on: {click: onClick}}, label);
}

function field(label, input) {
  return el('label', {class: 'se-trace-field'}, el('span', {text: label}), input);
}

const panel = el('aside', {class: 'se-trace-panel', 'aria-label': 'Projector controls'});
const reveal = button('Controls', () => showControls(true), {class: 'se-trace-reveal', hidden: true,
                                                           title: 'Show controls (H)'});
const banner = el('div', {class: 'se-trace-banner', role: 'status'});
root.append(panel, reveal, banner);

function showControls(visible) {
  panel.hidden = !visible;
  reveal.hidden = visible;
  if (visible) panel.querySelector('button')?.focus({preventScroll: true});
}

const tabs = {};
const modeBar = el('div', {class: 'se-trace-tabs', role: 'tablist'});
for (const [key, label] of [['trace', 'Trace'], ['calibrate', 'Calibrate']]) {
  tabs[key] = button(label, () => setMode(key), {role: 'tab'});
  modeBar.append(tabs[key]);
}

function setMode(next) {
  mode = next;
  panel.classList.toggle('is-centred', mode === 'calibrate');
  for (const [key, tab] of Object.entries(tabs)) {
    tab.setAttribute('aria-selected', String(key === mode));
    tab.classList.toggle('is-active', key === mode);
  }
  calibrateSection.hidden = mode !== 'calibrate';
  traceSection.hidden = mode !== 'trace';
  scheduleRender();
}

// --- Calibrate

const unitChoice = el('div', {class: 'se-trace-segmented', role: 'radiogroup', 'aria-label': 'Units'});
const widthInput = el('input', {type: 'number', min: '1', step: 'any', inputmode: 'decimal'});
const heightInput = el('input', {type: 'number', min: '1', step: 'any', inputmode: 'decimal'});
const squareInput = el('input', {type: 'number', min: '0.5', step: 'any', inputmode: 'decimal'});
const unitSpans = [];
const profileSelect = el('select', {'aria-label': 'Saved calibration'});
const scaleNote = el('p', {class: 'se-trace-note', role: 'status'});

function toUnit(cm) { return round(settings.unit === 'in' ? cm / CM_PER_IN : cm, 3); }
function fromUnit(value) { return settings.unit === 'in' ? value * CM_PER_IN : value; }

function refreshCalibrationFields() {
  widthInput.value = toUnit(cal.width);
  heightInput.value = toUnit(cal.height);
  squareInput.value = toUnit(cal.square);
  unitSpans.forEach(span => { span.textContent = settings.unit; });
  unitChoice.querySelectorAll('button').forEach(b => {
    b.setAttribute('aria-checked', String(b.dataset.unit === settings.unit));
    b.classList.toggle('is-active', b.dataset.unit === settings.unit);
  });
  profileSelect.replaceChildren(...Object.keys({[settings.profile]: 1, ...settings.profiles})
    .map(name => el('option', {value: name, selected: name === settings.profile}, name)));
}

for (const unit of ['cm', 'in']) {
  unitChoice.append(button(unit === 'cm' ? 'Centimetres' : 'Inches', () => {
    settings.unit = unit;
    store(STORE, settings);
    refreshCalibrationFields();
    scheduleRender();
  }, {role: 'radio', 'data-unit': unit}));
}

function sizeInput(input, key, minimum) {
  input.addEventListener('change', () => {
    const value = fromUnit(parseFloat(input.value));
    if (!(value >= minimum)) { refreshCalibrationFields(); return; }
    cal[key] = value;   // The markers stay put: typing a measured size is the calibration.
    cal.viewport = viewport();
    persist();
    scheduleRender();
  });
}
sizeInput(widthInput, 'width', 1);
sizeInput(heightInput, 'height', 1);
sizeInput(squareInput, 'square', 0.5);

// Measuring a square instead: a uniform correction, for a screen facing you squarely.
const measuredInput = el('input', {type: 'number', min: '0.1', step: 'any', inputmode: 'decimal',
                                   'aria-label': 'What a corner square measures'});
function applyMeasuredSquare() {
  const measured = fromUnit(parseFloat(measuredInput.value));
  if (!(measured > 0)) return;
  const factor = measured / cal.square;
  cal.width *= factor;
  cal.height *= factor;
  cal.viewport = viewport();
  measuredInput.value = '';
  persist();
  refreshCalibrationFields();
  scheduleRender();
}
measuredInput.addEventListener('keydown', event => { if (event.key === 'Enter') applyMeasuredSquare(); });

profileSelect.addEventListener('change', () => {
  persist();
  settings.profile = profileSelect.value;
  cal = settings.profiles[settings.profile] || defaultCalibration();
  persist();
  refreshCalibrationFields();
  scheduleRender();
});

const withUnit = input => {
  const span = el('span', {class: 'se-trace-unit'});
  unitSpans.push(span);
  return el('span', {class: 'se-trace-with-unit'}, input, span);
};

const calibrateSection = el('section', {class: 'se-trace-section'},
  el('p', {text: 'Put this window on the projector or TV and go full screen first. Then either:'}),
  el('ol', {},
    el('li', {}, el('strong', {text: 'Match marks. '}),
       'Enter how far apart four marks on your mat or table are, then drag each corner marker onto its mark.'),
    el('li', {}, el('strong', {text: 'Or measure. '}),
       'Leave the markers where they are, measure between their centres, and enter what you measured.')),
  el('p', {text: 'Arrow keys nudge the chosen marker by a pixel (Shift: 10, Alt: a quarter); N picks the '
    + 'next marker. When it is right, each corner square measures its stated size with a ruler.'}),
  unitChoice,
  el('div', {class: 'se-trace-row'},
     field('Width between markers', withUnit(widthInput)), field('Height between markers', withUnit(heightInput))),
  el('div', {class: 'se-trace-row'},
     field('Corner squares', withUnit(squareInput)),
     button('Reset markers', () => {
       cal.corners = fittedQuad(cal.width, cal.height, innerWidth, innerHeight);
       cal.viewport = viewport();
       persist();
       scheduleRender();
     })),
  el('div', {class: 'se-trace-row'},
     field('Or: one square measures', withUnit(measuredInput)),
     button('Apply', applyMeasuredSquare)),
  el('div', {class: 'se-trace-row'},
     field('Saved for', profileSelect),
     button('Save as…', () => {
       const name = (prompt('Name this calibration, e.g. Projector or Living-room TV') || '').trim().slice(0, 40);
       if (!name) return;
       settings.profile = name;
       cal = JSON.parse(JSON.stringify(cal));
       persist();
       refreshCalibrationFields();
     })),
  scaleNote,
  button('Done — trace', () => setMode('trace'), {class: 'se-trace-primary'}));

// --- Trace

const pieceList = el('ul', {class: 'se-trace-pieces', 'aria-label': 'Pieces'});
const pieceTools = el('div', {class: 'se-trace-tools'});
const colorChoice = el('div', {class: 'se-trace-swatches', role: 'radiogroup', 'aria-label': 'Line colour'});

function updatePieceTools() {
  pieceList.replaceChildren(...pieces.map(piece => {
    const place = placement(piece);
    const shown = el('input', {type: 'checkbox', checked: !place.hidden, 'aria-label': `Show ${piece.label}`,
                               on: {change: event => hidePiece(piece.id, !event.target.checked)}});
    const name = button(piece.label, () => {
      selected = piece.id;
      place.hidden = false;
      // At true scale most pieces lie off screen: a chosen piece comes into view.
      if (!onScreen(piece)) bringToCentre(); else changed();
    }, {class: piece.id === selected ? 'is-selected' : '', 'aria-pressed': String(piece.id === selected)});
    return el('li', {}, shown, name);
  }));
  const piece = selectedPiece();
  pieceTools.replaceChildren(piece
    ? el('div', {}, el('p', {class: 'se-trace-chosen', text: piece.label}),
         el('div', {class: 'se-trace-buttons'},
            button('⟲ 90°', () => turn(-90), {title: 'Shift+R'}), button('⟳ 90°', () => turn(90), {title: 'R'}),
            button('−1°', () => turn(-1), {title: '['}), button('+1°', () => turn(1), {title: ']'}),
            button('Mirror', mirror, {title: 'M'}), button('To centre', bringToCentre),
            button('Hide', () => hidePiece(piece.id), {title: 'Delete'})),
         el('p', {class: 'se-trace-note', text: `Turned ${round(placement(piece).rotation, 1)}°`
                                               + (placement(piece).flip ? ' · mirrored' : '')}))
    : el('p', {class: 'se-trace-note', text: pieces.length ? 'Drag a piece to move it, or the background to move them all.' : ''}));
}

function refreshColors() {
  const palette = PALETTES[settings.view.background];
  if (!palette.includes(settings.view.color)) settings.view.color = palette[0];
  colorChoice.replaceChildren(...palette.map(color => {
    const swatch = button('', () => { settings.view.color = color; store(STORE, settings); refreshColors(); scheduleRender(); },
                          {role: 'radio', 'aria-checked': String(color === settings.view.color),
                           'aria-label': `Lines ${color}`, class: color === settings.view.color ? 'is-active' : ''});
    swatch.style.background = color;
    return swatch;
  }));
}

function toggle(label, key) {
  return el('label', {class: 'se-trace-check'},
            el('input', {type: 'checkbox', checked: settings.view[key],
                         on: {change: event => { settings.view[key] = event.target.checked; store(STORE, settings); scheduleRender(); }}}),
            label);
}

const backgroundChoice = el('div', {class: 'se-trace-segmented', role: 'radiogroup', 'aria-label': 'Background'});
for (const [key, label] of [['dark', 'Dark · projector'], ['light', 'Light · trace on a screen']]) {
  backgroundChoice.append(button(label, () => {
    settings.view.background = key;
    store(STORE, settings);
    backgroundChoice.querySelectorAll('button').forEach(b => b.classList.toggle('is-active', b.dataset.bg === key));
    refreshColors();
    scheduleRender();
  }, {role: 'radio', 'data-bg': key, class: settings.view.background === key ? 'is-active' : ''}));
}

const widthRange = el('input', {type: 'range', min: '1', max: '8', step: '0.5', value: settings.view.width,
                                'aria-label': 'Line width',
                                on: {input: event => { settings.view.width = Number(event.target.value); store(STORE, settings); scheduleRender(); }}});

const traceSection = el('section', {class: 'se-trace-section'},
  pieces.length ? null : el('p', {class: 'se-trace-empty',
    text: 'No pattern yet. Open a garment in the studio and choose Export → Project for tracing; '
      + 'you can calibrate here meanwhile.'}),
  pieceList, pieceTools,
  el('div', {class: 'se-trace-row'},
     button('Show all', () => { pieces.forEach(p => { placement(p).hidden = false; }); changed(); }),
     button('Reset layout', () => { placements = defaultLayout(); selected = null; changed(); })),
  backgroundChoice,
  el('div', {class: 'se-trace-row'}, colorChoice, field('Line width', widthRange)),
  el('div', {class: 'se-trace-checks'}, toggle('Names', 'labels'), toggle('Button & zip marks', 'marks'),
     toggle('Grid', 'grid'), toggle('Corner squares', 'squares')),
  el('p', {class: 'se-trace-note', text: 'Lines are sewing lines: add your seam allowance when cutting. '
    + 'Keys: R turns 90° · [ ] turn 1° · M mirrors · arrows move 1 mm (Shift: 1 cm) · N picks the next piece · Delete hides it.'}));

panel.append(
  el('header', {class: 'se-trace-header'},
     el('div', {}, el('strong', {text: 'Pattern projector'}), el('span', {text: DATA?.title || ''})),
     el('div', {class: 'se-trace-header-actions'},
        button('⇆', () => panel.classList.toggle('is-right'), {title: 'Move these controls to the other side',
                                                               'aria-label': 'Move controls to the other side'}),
        button('Hide', () => showControls(false), {title: 'Hide controls (H)', 'aria-label': 'Hide controls'}))),
  modeBar, calibrateSection, traceSection,
  el('footer', {class: 'se-trace-footer'},
     button('Full screen', toggleFullscreen, {title: 'F'}),
     el('span', {text: 'F full screen · H hide controls · C calibrate'})));

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen?.();
  else document.documentElement.requestFullscreen?.().catch(() => {});
}

function updateStatus(H) {
  const warnings = [];
  const [width, height, ratio] = viewport(), [cw, ch, cr] = cal.viewport || [];
  if (cw && (Math.abs(cw - width) > 1 || Math.abs(ch - height) > 1 || Math.abs((cr || 1) - ratio) > 0.01)) {
    warnings.push(`Calibrated in a ${Math.round(cw)}×${Math.round(ch)} window; this one is `
      + `${Math.round(width)}×${Math.round(height)}${Math.abs((cr || 1) - ratio) > 0.01 ? ' at another zoom' : ''}. `
      + 'Go full screen, or calibrate again here.');
  }
  if (!H) warnings.push('The corner markers cross over. Drag them back into a four-sided shape.');
  banner.textContent = warnings.join(' ');
  banner.hidden = !warnings.length;
  const scale = H && localScale(H, cal.width / 2, cal.height / 2);
  const unit = settings.unit === 'in' ? CM_PER_IN : 1;
  scaleNote.textContent = scale
    ? `At the centre, 1 ${settings.unit} is ${round(scale[0] * unit, 1)} px across and ${round(scale[1] * unit, 1)} px down.`
      + (Math.abs(scale[0] - scale[1]) / Math.max(...scale) > 0.02 ? ' They differ: check the squares with a ruler.' : '')
    : '';
}

// ---------------------------------------------------------------- keys

document.addEventListener('keydown', event => {
  if (event.target.closest?.('input, select, textarea')) return;
  const key = event.key;
  const arrows = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
  if (arrows[key] && !event.target.closest?.('button')) {
    nudge(...arrows[key], event.altKey, event.shiftKey);
  } else if (key === 'f' || key === 'F') {
    toggleFullscreen();
  } else if (key === 'h' || key === 'H') {
    showControls(panel.hidden);
  } else if (key === 'c' || key === 'C') {
    setMode(mode === 'calibrate' ? 'trace' : 'calibrate');
  } else if (mode === 'trace' && (key === 'r' || key === 'R')) {
    turn(event.shiftKey ? -90 : 90);
  } else if (mode === 'trace' && (key === '[' || key === ']')) {
    turn((key === '[' ? -1 : 1) * (event.shiftKey ? 5 : 1));
  } else if (mode === 'trace' && (key === 'm' || key === 'M')) {
    mirror();
  } else if (mode === 'trace' && (key === 'Delete' || key === 'Backspace') && selected) {
    hidePiece(selected);
  } else if (mode === 'trace' && (key === 'n' || key === 'N') && pieces.length) {
    const shown = pieces.filter(p => !placement(p).hidden);
    if (!shown.length) return;
    const index = shown.findIndex(p => p.id === selected);
    selected = shown[(index + (event.shiftKey ? shown.length - 1 : 1)) % shown.length].id;
    changed();
  } else if (mode === 'calibrate' && (key === 'n' || key === 'N')) {
    selectedCorner = (selectedCorner + (event.shiftKey ? 3 : 1)) % 4;
    scheduleRender();
  } else if (key === 'Escape' && mode === 'trace') {
    selected = null;
    changed();
    return;
  } else {
    return;
  }
  event.preventDefault();
});

addEventListener('resize', scheduleRender);
document.addEventListener('fullscreenchange', scheduleRender);

refreshCalibrationFields();
refreshColors();
updatePieceTools();
setMode(mode);
