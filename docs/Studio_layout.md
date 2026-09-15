# Pattern-first studio

The main page follows the first refined concept: the current outfit on the left,
a pattern canvas in the center, and a fabric inspector above a live 3D preview
on the right. The header contains the outfit name, measurements, Save outfit,
PDF export and the configured account/sign-in control.

- Click a garment card to edit its design. The card menu saves a version or
  removes a garment from the working outfit; saved library versions stay intact.
- Add garment offers starting designs and saved garment versions. Each item
  keeps its own design and appearance. Save outfit captures new versions only
  for garments that differ from their saved snapshots.
- Click pieces, use Shift/Ctrl to extend the selection, or drag a box to select
  a group. Fabric presets, swatches and prints apply to that selection. Drape
  exposes bending stiffness. Closing the inspector clears the selection.
- Fit centers the complete pattern. Plus/minus change its scale. A piece drag
  or a right/middle drag pans; these actions preserve manual framing on resize.
- The docked browser preview warms automatically. Expand uses the same mounted
  simulation. Pause, reset, recenter and further controls stay in its corner.

Below 980 px the outfit list opens from the menu. On phones the preview sits
below the pattern and selecting pieces opens a dismissible fabric inspector.
No backend GPU is used.

The thumbnails are schematic garment icons, not fabricated renderings. The
outfit title and saved status reflect the working library data, not mockup copy.
