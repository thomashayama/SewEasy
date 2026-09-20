# Fabric editing in the sewing pattern

Hover over a pattern piece to highlight its outline and show the standard arrow
cursor. Click to select it. Shift-click or Ctrl-click toggles additional pieces;
Cmd-click also works on macOS. Dragging still pans the sheet without selecting
the pieces crossed by the pointer.

The **Fabric** panel on the right edits every selected piece. It offers solid
color or a print, base and print colors, spacing in centimetres, and bending
stiffness. Fields show **Mixed** when the selection differs. Changing one field
preserves the other settings on each piece. **Use garment fabric** clears the
selected pieces' fabric and stiffness overrides.

**Fabric type** lists the drape presets alongside saved fabrics: **Common
fabrics** for the read-only collection and **My fabrics** for the account's own
imports. Choosing one cuts the selected pieces from that fabric, which sets
their weight and bending from its measurements; see
[the support matrix](Fabrics.md). Select all pieces to apply one fabric to a
whole garment. A fabric assigned in a garment someone shared keeps its name even
when it is not in your library. **Browse fabrics…** opens the full library as a
picker, with search, weight classes and hearts; choosing a fabric there keeps the
current selection. A fabric that brings its own base-colour map is drawn on the
piece in both views, and **Pattern** reads **Fabric’s own texture** until the
piece is given a colour or print of its own.

Closing the panel clears the selection outlines and keeps the fabric edits.
Reopen it with **Fabric** above the workspace.
Keyboard users can focus a piece and press Enter or Space to select it, hold a
modifier to add/remove it, use Ctrl/Cmd+A to select all, and Escape to clear.
Hover and selection outlines are browser-local SVG overlays and never become
part of the fabric or the downloaded sewing pattern.

Each garment's appearance stores its `panel_fabrics` alongside `panel_colors`,
`panel_stiffness`, `panel_materials` and the detached `materials` it assigns. Outfit panel names resolve into the owning garment, so a
selection may span garments without copying another garment's other settings.
Saved garment versions preserve these overrides. The 2D pattern and browser
3D renderer consume the same fabric specifications; color and print updates do
not require another simulation.

Validation:

```powershell
tmp_webgpu_cpu/Scripts/python.exe -m unittest test_fabric_selection test_wardrobe test_browser_preview -q
node --test benchmarks/test_fabric_selection.mjs benchmarks/test_browser_drape.mjs
```

Browser checks cover hover/cursor, Shift/Ctrl toggling, mixed prints, grouped
color/print edits, keyboard selection, drag panning, and matching 3D appearance.
