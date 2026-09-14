# Studio UX review

Reviewed September 13, 2026, against commit `5ea1d24` and the running local studio.

The largest opportunity is to make the working garment, its body profile, and its saved state clear while keeping the pattern visible. Keep the existing paper canvas, restrained colors, direct piece selection, and compact 3D controls. Improve the workflow before changing the visual identity.

## Scope and evidence

Inspected the live pattern workspace, garment controls, fabric inspector, measurement dialog, save dialog, outfit library/composer, and browser 3D preview. Checked desktop at 1440 × 900, the existing narrower workspace at 817 × 854, and a fresh phone-sized session at 390 × 844. Phone findings concern responsive layout; this was not a physical touch-device test.

A temporary studio tab was used for the edit/reload test. No garments, outfits, or measurement profiles were saved or deleted. Signed-in account behavior and PDF export internals were reviewed in source, not exercised end to end. These are interface findings and recommendations, not a user study or a simulation-performance benchmark.

## Priorities

| Priority | Improvement | Evidence and consequence | Completion criterion |
| --- | --- | --- | --- |
| P0 | Recover working drafts; show save state | A temporary front-bodice color edit from `#b7cde5` to `#112233` reverted after reload. Navigation snapshots currently cover explicit account/auth transitions. The studio has no persistent dirty/saved indicator. | Reload restores draft design, appearance, body, outfit, and active garment. The header names the document and distinguishes draft recovery from a saved garment/outfit version. |
| P1 | Fit the pattern to the available canvas | The sheet is fixed at 1400 × 840. At desktop width, the 390 px configuration drawer and 280 px empty fabric inspector leave only 770 px for it. Pieces extend off-screen, with no visible 2D zoom or Fit action. | Initial framing includes all garment pieces. Add zoom, Fit pattern, and Fit selection. Preserve intentional pan/zoom during edits; account for inspector width. |
| P1 | Make narrow screens usable | At 390 px, the initial configuration drawer covers the screen. Closing it reveals an empty Fabric panel covering most of the canvas. View controls overlap the silhouette control; the pattern is still cropped after both drawers close. | Start with the canvas visible. Allow one editing sheet at a time, with reachable close/apply controls. Reserve toolbar space. Frame the garment appropriately in both views. |
| P1 | Make control values truthful and readable | Sliders hide values until interaction, use mixed units/ratios without explanation, and lack individual accessible names. An untouched collar front reports stiffness `1`, while its assembly default is `6`. | Give each slider a persistent numeric field, correct units or ratio explanation, and accessible label. Show the effective stiffness and whether it is inherited or overridden. |
| P1 | Provide general undo/redo | The existing Undo button is a one-step snapshot for selected bulk design actions. Ordinary parameter, fabric, and measurement changes are outside that history. | Undo/redo covers meaningful editing transactions. Coalesce continuous slider/color adjustments into one action; include keyboard shortcuts and disabled states. |
| P2 | Make outfits a visible working structure | Library browsing, version picking, composition, preview, and saving share one modal. Starting an outfit requires a previously saved garment. | Show a persistent garment list for the current outfit, with thumbnails, active garment, and visibility. Add the current garment directly; create a saved version when the outfit is saved. |
| P2 | Bring measurement guidance into the studio | Customize measurements exposes eleven numeric fields, centimeters only, and says related proportions adjust without explaining which. The account editor already has unit conversion and illustrated guidance. | Reuse that guidance and unit preference. Show an active-body summary, explain estimated proportions, and place validation next to the relevant fields. |
| P2 | Add a print setup step | Download pattern immediately generates the default Letter PDF. The exporter already supports A4, scale instructions, a calibration square, and an assembly map. | Offer Letter/A4 and show page count, layout preview, scale instructions, and the body/design being exported before download. |

## Recommended workspace structure

- **Header:** current outfit or garment name, active body, saved/draft status, Save, and Export. Put Resources and occasional import/reset/randomize actions in secondary menus.
- **Left panel:** current outfit's garments and the active garment's design controls. Use friendly garment names such as “Dress shirt” and explicit “None” options instead of raw class names or blank selections. Group basic shape controls separately from construction details.
- **Center:** the largest possible Pattern / 3D workspace, with a stable view toolbar. Fit the actual garment rather than reserving most of the screen for the mannequin's legs. Keep the body silhouette optional.
- **Right inspector:** open when a piece or garment needs editing. Avoid consuming canvas space with an empty inspector on first load. Keep selection outlines cleared when the inspector closes, as currently implemented.
- **Small screens:** a compact header and one temporary editing sheet. Keep controls clear of the garment; supply an explicit multiselect mode without requiring a keyboard.

This structure should keep outfits as collections of saved garment versions. A garment's design and appearance remain independent of the body used to draft it. A recoverable working draft must not silently overwrite versions referenced by saved outfits.

## Flow details

### Fabric editing

Keep the standard arrow cursor, local hover feedback, modifier multiselect, and mixed-value fields. Add selection shortcuts for corresponding pieces, such as both cuffs, collar pieces, or the entire garment. Small pieces should also be selectable from a named list.

Expose common colors and print swatches before raw hex values. Keep physical behavior in an expandable section with plain explanations. Material presets should only imply calibrated behavior when that calibration exists.

Fix inherited stiffness before expanding the controls. `panel_stiffness_of()` returns an override or `1.0`, while dress-shirt assembly assigns collar stand `15`, collar fall `6`, and cuff `12`; the exported overrides replace those defaults. The inspector therefore does not currently show the effective value. “Use garment fabric” also resets stiffness, so its scope should be explicit, or appearance and behavior resets should be separate.

### Saving and outfits

Use a straightforward Save action with the current name already filled. Keep version history available without making users understand it before their first save. Give the current outfit a recognizable title and its garments visual previews. Distinguish opening a library item from adding it to an outfit.

Disable Save when a required name is empty and disable preview/save of an empty outfit, with a short explanation beside the controls. The current buttons allow these attempts and report the problem afterward. Autosave and undo are prerequisites for making switching between garments feel safe.

### Measurements and 3D

Show the active measurement profile near the view switch, with a direct Edit measurements action. In the editor, reuse existing diagrams and unit conversion, and distinguish entered measurements from adjusted or estimated values. Preserve the current 3D dimension comparison; make it easy to discover from the body summary.

The 3D preview loaded during this review and retains useful minimal Pause, Reset, Recenter, and More controls. Preserve those and rotation around the mannequin's center. Improve the first-use gesture hint: dragging horizontally moves the mannequin while live, but changes the inspection view when paused. Make that mode distinction legible. Keep pan and zoom instructions discoverable, and consider an explicit Inspect / Move mannequin choice within the compact controls.

On narrow screens, the silhouette toggle and skin-tone control compete with the view switch and the mannequin's head. Move body appearance controls into the body inspector or the existing More menu. Frame hands and sleeves when they matter to the garment under review.

## Implementation sequence

1. **Protect work and fix misleading controls:** draft recovery, current document/save state, general undo/redo, and effective stiffness values. Handle overlapping tabs deliberately so one recovered draft cannot silently overwrite another.
2. **Give the garment room:** responsive canvas framing, 2D zoom/Fit, coordinated inspectors, and a compact toolbar. Preserve the existing selection and 3D interaction behavior.
3. **Simplify decisions:** numeric garment controls, visible outfit structure, guided measurements, and print setup.
4. **Polish:** swatches, paired-piece selection, contextual hints, and thumbnail browsing.

Validate the result with a complete flow: customize a body → change shirt dimensions → select both cuffs and edit fabric → inspect and move the mannequin → undo an edit → reload and recover → save a garment → combine it into an outfit → export the chosen paper size. Repeat canvas and inspector checks at desktop and phone widths, and verify keyboard operation as well as pointer input.

## Source entry points

- [Studio layout, controls, draft navigation snapshot, selection, and undo](../gui/callbacks.py)
- [Fabric inspector UI](../gui/fabric_panel.js) and [responsive styles](../gui/fabric_editor.css)
- [Appearance and stiffness accessors/export](../gui/gui_pattern.py)
- [Dress-shirt construction defaults](../assets/garment_programs/dress_shirt.py)
- [Outfit library and save flows](../webapp/wardrobe_ui.py)
- [Studio measurement dialog](../webapp/gui_widgets.py), [measurement guide](../webapp/measurement_guide.py), and [account editor](../webapp/account_page.py)
- [Browser drape UI](../gui/browser_drape.js)
- [Print exporter](../seweasy/pattern/print_export.py)
