# Wardrobe home

The app opens at `/`, a lightweight home page for the existing wardrobe library.
The pattern/3D editor is at `/studio`. The SewEasy logo in the studio stores the
working draft before returning home. The account page's logo also goes home;
its Back to studio button opens `/studio`.

Home provides:

- Garments and Outfits tabs, with library counts and name search. Outfit
  search also matches the names of its included garments.
- Editable copies of saved outfits and garments, preserving all per-panel fabric
  settings, colors, version metadata, and the currently selected measurements.
- A Continue editing area for the working draft. Successful studio updates retain
  that draft in browser-specific storage, so normal navigation and reloads can
  resume it without creating new saved garment versions.
- Six standard garments in the library alongside personal saved versions:
  dress shirt, T-shirt, tube top, trousers, circle skirt, and pencil skirt.
  These presets are always available without adding rows to a user's saved
  library. Opening one starts an independent copy; saving creates a personal version.
- A single New outfit action and a compact current-draft row. The first-garment
  chooser uses the same standards; add more pieces from the studio's outfit sidebar.
- Measurements and account/sign-in access.

Signed-in libraries continue to use `WardrobeLibrary`; guests use NiceGUI's
browser-specific user storage. Home uses the same `Wardrobe` service as the
studio and introduces no new database tables. Saved snapshots are copied before
editing. The garment flats are illustrations using the saved base color and print,
not simulated fits or detailed representations of individual panel overrides.
Home neither drafts a pattern nor creates a WebGPU renderer.

Garment design edits the active piece's fit and construction. The old Top/Bottom
composition selectors are removed; waistband style stays within Waistband.
Reset details uses that garment's standard defaults. Reset and Randomize preserve
composition and fabric, and imports must match the active garment type. The
underlying unrestricted sampler remains available outside the studio.

The earlier SQL Design library is still available in the account area and under
Earlier saved designs in the studio's outfit dialog.

Validation: `python -m unittest test_home_page test_wardrobe test_browser_preview test_fabric_selection -q`.
Browser checks cover starter-to-studio navigation,
saving and reopening a two-garment outfit, returning through the logo, garment
search, empty search results, draft recovery, and mobile home/chooser layouts.
