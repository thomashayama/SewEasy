# Pattern projector

Studio → **Export → Project for tracing (projector or TV)** opens `/trace`: the
current pattern at true 1:1 scale on a black (or white) full-screen page, for
cutting or tracing under a projector, or tracing through paper laid on a TV.

## Calibrate once per display

A browser does not know how big a centimetre is on a projector, so the page
asks. Put the window on the projector or TV, press **F** for full screen, and
open **Calibrate** (**C**). Four corner markers mark a rectangle; each carries a
square of a stated size (5 cm, or 2 in).

- **Match marks** (best for a projector): enter how far apart four marks on the
  cutting mat or table are, then drag each marker onto its mark. The four
  points correct scale *and* keystone, so a projector need not face the table
  squarely. Arrow keys nudge the chosen marker by a pixel (Shift: 10, Alt: ¼);
  **N** picks the next marker. The grid should then lie on the mat's lines.
- **Or measure**: leave the markers where they are, measure between their
  centres with a tape, and enter the width and height you measured.
- **Or measure one square** (quickest on a TV facing you): enter what a corner
  square really measures. This is a uniform correction only.

When done, every corner square measures its stated size with a ruler. The
calibration is kept in this browser under a name (**Saved for**, e.g.
Projector or TV), with the window size it was made at; the page warns if the
window size or zoom differs later, since the pixels no longer line up. Leave
**Corner squares** on while cutting to spot a bumped projector.

## Trace

Pieces start in the studio's cutting layout. Drag a piece to move it, or the
background to move them all. Choosing a piece in the list brings it into view.
**R** / Shift+**R** turn 90°, **[** **]** turn 1° (Shift: 5°), **M** mirrors,
arrows move 1 mm (Shift: 1 cm), **N** picks the next piece, **Delete** hides a
piece already cut, **H** hides the controls. The layout is remembered for the
same set of pieces. Line colour, width, names, button and zip marks, and a
table grid are in the controls.

Lines are the pattern's sewing lines, the same as the print PDF: add seam
allowance when cutting.

## How it works

`gui/trace_view.py` turns the studio's drafted pieces (`panel_svg_paths`, in
centimetres) into polylines, curves sampled at most 2 mm apart, and hands them
to `/trace` through the browser's user storage together with the button and
zipper marks. `gui/trace_view.js` does everything else in the browser:
`gui/trace_geometry.js` fits the homography from the calibrated table
rectangle to the four screen points and maps every point through it, so lines
stay a fixed number of pixels wide at any scale.

Validation: `python -m unittest test_trace_view` (the calibration maths runs
under Node.js when it is installed).
