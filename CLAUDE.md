# CLAUDE.md

## What this project is

SewEasy is a modular programming framework for designing parametric sewing patterns. Garments are defined as Python programs composed from reusable components (bodices, sleeves, skirts, collars, etc.), parameterized by body measurements and design options. Patterns can be rendered as 2D sewing patterns (SVG/PNG/JSON), configured interactively in a browser GUI, and draped into simulated 3D garments.

It is a commercial fork of [GarmentCode](https://github.com/maria-korosteleva/GarmentCode) v2.0.2 (MIT License, Maria Korosteleva et al., ETH Zurich), renamed and rebranded in July 2026. The fork lives at https://github.com/thomashayama/SewEasy.

## Goals

- Build a commercial product on top of the GarmentCode framework under the SewEasy brand.
- Longer term: explore AI-assisted pattern generation (the upstream ecosystem — ChatGarment, Design2GarmentCode — generates patterns targeting this framework's JSON/DSL representation).
- Stay mergeable with upstream: pull future GarmentCode improvements via `git pull upstream main`.

## Repo layout

- `seweasy/` — the core library (renamed from `pygarment`; the PyPI-style package name in `setup.cfg` is `seweasy`)
  - `seweasy/garmentcode/` — the DSL layer: Edge, Panel, Component, Interface, edge factory, operators. **Kept its upstream name deliberately** — renaming it would touch half the codebase and wreck upstream merges.
  - `seweasy/pattern/` — 2D pattern serialization (JSON wrappers, SVG/raster output, bundled cairo DLLs for Windows)
  - `seweasy/meshgen/` — box mesh generation and cloth simulation (uses a patched NVIDIA Warp)
  - `seweasy/mayaqltools/` — legacy Autodesk Maya + Qualoth simulation tools
- `assets/garment_programs/` — example garment components written against the library
- `assets/design_params/`, `assets/bodies/` — design and body-measurement presets (`default.yaml` is the GUI's initial state)
- `gui.py` + `gui/` — NiceGUI-based browser configurator (launch with `python gui.py`)
- `test_seweasy.py`, `test_garment_sim.py` — smoke-test scripts (not pytest suites)
- `pattern_sampler.py`, `pattern_data_sim.py`, `pattern_fitter.py` — dataset generation / fitting pipeline
- `docs/` — installation and usage docs

## Conventions and constraints

- **Naming**: user-facing branding is "SewEasy"; the Python package is `seweasy`. References to the GarmentCode/GarmentCodeData *papers*, the *dataset*, the `Body Measurements GarmentCode.pdf` doc, and the upstream `NvidiaWarp-GarmentCode` dependency intentionally keep their original names — do not "fix" them in a rename sweep.
- **Licensing**: MIT. `LICENSE` must retain Maria Korosteleva's original copyright line alongside the fork's line. Keep the Attribution and Citation sections in `ReadMe.md`.
- **SMPL caveat**: body-shape assets in the upstream ecosystem derive from SMPL/CAESAR, which carry non-commercial restrictions (see `assets/bodies/Readme.md`). Before shipping anything commercial that bundles body models or dataset-derived assets, verify their licenses separately from the code.
- The README file is `ReadMe.md` (not `README.md`).
- Line endings: repo content is LF; Windows checkout with autocrlf — expect CRLF warnings from git, they're harmless.

## Git workflow

- The project is in early dev: after completing a piece of work, commit it and push to `origin main` without asking. Work directly on `main` — no feature branches or PRs needed for now.

## Git remotes

- `origin` → https://github.com/thomashayama/SewEasy (this fork; push here)
- `upstream` → https://github.com/maria-korosteleva/GarmentCode (pull updates: `git pull upstream main`, then resolve renames — `pygarment` → `seweasy`)

## Environment notes

- Python >= 3.6 (upstream tested ~3.9+); install with `pip install -e .` per `docs/Installation.md`
- Simulation requires the patched NVIDIA Warp: https://github.com/maria-korosteleva/NvidiaWarp-GarmentCode (manual install)
- Quick sanity check without full deps: `python -m compileall -q seweasy gui assets`
