# Fabric editing in the sewing pattern

Hover over a pattern piece to highlight its outline and show the fabric brush
cursor. Click to select it. Shift-click or Ctrl-click toggles additional pieces;
Cmd-click also works on macOS. Dragging still pans the sheet without selecting
the pieces crossed by the pointer.

The **Fabric** panel on the right edits every selected piece. It offers solid
color or a print, base and print colors, spacing in centimetres, and bending
stiffness. Fields show **Mixed** when the selection differs. Changing one field
preserves the other settings on each piece. **Use garment fabric** clears the
selected pieces' fabric and stiffness overrides.

The panel can be closed and reopened with **Fabric** above the workspace.
Keyboard users can focus a piece and press Enter or Space to select it, hold a
modifier to add/remove it, use Ctrl/Cmd+A to select all, and Escape to clear.
Hover and selection outlines are browser-local SVG overlays and never become
part of the fabric or the downloaded sewing pattern.

Each garment's appearance stores its `panel_fabrics` alongside `panel_colors`
and `panel_stiffness`. Outfit panel names resolve into the owning garment, so a
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
