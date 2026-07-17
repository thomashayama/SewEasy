"""Visual identity for the SewEasy configurator.

Design language: the drafting atelier — pattern paper, basting stitches,
denim indigo, tailor's chalk. One signature element: the selvedge edge
under the header (cream band, stitched red line), echoed quietly by
dashed stitch borders on parameter cards.

Tokens live here; gui/callbacks.py consumes them.
"""

from argparse import Namespace

colors = Namespace(
    # Brand: denim indigo family
    primary='#35558a',    # denim — chrome, interactive elements
    secondary='#4a90d2',  # washed denim — secondary accents
    accent='#7fb2e5',     # faded denim — highlights
    dark='#1d2b42',       # midnight navy — footer, deep text
    # Semantics
    positive='#2e8540',
    negative='#d43d3d',
    info='#31ccec',
    warning='#e0a800',
)

HEAD_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700&family=Public+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
    --se-indigo: #35558a;
    --se-navy: #1d2b42;
    --se-paper: #fafaf7;
    --se-graphite: #2b2f36;
    --se-muted: #5a6270;
    --se-chalkline: #c5ccd8;
    --se-cream: #f3efe6;
    --se-selvedge: #c94f4f;
}

body {
    background: var(--se-paper) !important;
    font-family: 'Public Sans', system-ui, sans-serif !important;
    color: var(--se-graphite);
}

/* --- Brand --- */
.se-wordmark {
    font-family: 'Bricolage Grotesque', 'Public Sans', sans-serif;
    font-weight: 700;
    font-size: 1.3rem;
    letter-spacing: 0.01em;
    line-height: 1.1;
}
.se-eyebrow {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.6rem;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    opacity: 0.75;
    line-height: 1.1;
}

/* --- Signature: selvedge edge under the header --- */
.se-selvedge {
    height: 10px;
    background:
        repeating-linear-gradient(90deg,
            var(--se-selvedge) 0 7px, transparent 7px 13px)
            0 4px / 100% 2px no-repeat,
        var(--se-cream);
}

/* --- Basting-stitch cards for parameter groups --- */
.se-stitch-card {
    border: 1.5px dashed var(--se-chalkline);
    border-radius: 10px;
    box-shadow: none !important;
    background: #ffffff;
}
.se-section-label {
    font-family: 'Bricolage Grotesque', 'Public Sans', sans-serif;
    font-weight: 600;
    font-size: 0.92rem;
    color: var(--se-navy);
}
.se-param-label {
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--se-muted);
}

/* --- Measurement digits in mono --- */
.se-mono .q-field__native, .se-mono .q-field__input {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
}

/* --- Hint / warning chips --- */
.se-hint-chip {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: var(--se-muted);
    border: 1.5px dashed var(--se-chalkline);
    border-radius: 6px;
    padding: 2px 8px;
}
.se-warning-chip {
    font-size: 0.78rem;
    font-weight: 600;
    color: #8a6d00;
    background: #fdf5da;
    border: 1.5px dashed #e0a800;
    border-radius: 6px;
    padding: 2px 8px;
}

/* --- Quasar re-tailoring --- */
.q-btn {
    text-transform: none;
    border-radius: 8px;
    font-weight: 500;
    letter-spacing: 0.01em;
}
.q-tab {
    text-transform: none;
}
.q-tab__label {
    font-family: 'Bricolage Grotesque', 'Public Sans', sans-serif;
    font-weight: 600;
    font-size: 0.92rem;
}
/* Vertical tabs are section navigation (data-driven names), not headings */
.q-tabs--vertical .q-tab__label {
    font-family: 'Public Sans', system-ui, sans-serif;
    font-weight: 500;
    font-size: 0.85rem;
    text-transform: capitalize;
}
.q-field--outlined .q-field__control {
    border-radius: 8px;
}
/* Parameter-section expansions in the side panel */
.q-expansion-item .q-item__label {
    font-family: 'Bricolage Grotesque', 'Public Sans', sans-serif;
    font-weight: 600;
    font-size: 0.88rem;
    color: var(--se-navy);
}
.q-field__label {
    font-size: 0.85rem;
}

/* Full-bleed stage: overlays carry their own spacing */
.nicegui-content {
    padding: 0;
}

/* Floating controls over the workspace */
.se-overlay-chip {
    background: rgba(255, 255, 255, 0.88);
    backdrop-filter: blur(4px);
    border-radius: 8px;
    box-shadow: 0 1px 5px rgba(29, 43, 66, 0.14);
}

/* Quiet, thin scrollbars */
.q-scrollarea__thumb {
    background: var(--se-chalkline);
    opacity: 0.55;
}

/* --- Draggable pattern workspace --- */
/* Pan by dragging; native scroll bounds keep it inside the sheet */
.se-workspace {
    overflow: auto;
    cursor: grab;
    display: flex;
    scrollbar-width: none;
}
.se-workspace::-webkit-scrollbar {
    display: none;
}
.se-workspace.se-dragging {
    cursor: grabbing;
    user-select: none;
}
.se-workspace img {
    -webkit-user-drag: none;
    user-select: none;
}
</style>
<script>
document.addEventListener('pointerdown', (e) => {
    const ws = e.target.closest('.se-workspace');
    if (!ws || e.button !== 0) return;
    e.preventDefault();
    ws.classList.add('se-dragging');
    const sx = e.clientX, sy = e.clientY;
    const sl = ws.scrollLeft, st = ws.scrollTop;
    const move = (ev) => {
        ws.scrollLeft = sl - (ev.clientX - sx);
        ws.scrollTop = st - (ev.clientY - sy);
    };
    const up = () => {
        ws.classList.remove('se-dragging');
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', up);
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
});
</script>
<style>
</style>
"""
