"""Modal GPU draping service for SewEasy.

The GUI's 3D drape runs the patched NVIDIA Warp cloth simulation. Inside the
app container Warp is CPU-only (see Dockerfile), which makes a drape take
minutes. This module offloads meshgen + simulation + preview render to a
Modal (modal.com) GPU container, where the same simulation takes seconds.

Deploy (one-time, and after changing this file or the sim/meshgen code):

    modal deploy modal_drape.py

Enable in the app by setting env vars (see .env.example):

    MODAL_DRAPE=1
    MODAL_TOKEN_ID=...      # from `modal token new` (not needed if
    MODAL_TOKEN_SECRET=...  # ~/.modal.toml exists, e.g. bare local runs)

The GUI falls back to the local (CPU) simulation when Modal is disabled or
the remote call fails.

NOTE: `import seweasy` happens inside the remote function only — locally this
module is imported by the GUI just for `remote_drape()`/`is_enabled()`.
"""
import os
from pathlib import Path

import modal

APP_NAME = 'seweasy-drape'
# GPU type for the simulation, chosen at *deploy* time
GPU_KIND = os.getenv('MODAL_DRAPE_GPU', 'T4')

app = modal.App(APP_NAME)

_REPO = Path(__file__).parent

# The runtime image: CUDA toolchain to build the patched Warp for GPU, then
# the same Python dependency set as the Dockerfile (installed from setup.cfg
# so the two images cannot drift apart).
image = (
    modal.Image.from_registry(
        'nvidia/cuda:12.2.2-devel-ubuntu22.04', add_python='3.9')
    # Runtime libs mirror the Dockerfile: cairo for CairoSVG, EGL/GL for
    # headless pyrender previews, dejavu for text in renders
    .apt_install(
        'git', 'git-lfs', 'build-essential', 'ca-certificates', 'curl',
        'libcairo2', 'libegl1', 'libgl1', 'libgl1-mesa-dri', 'libglib2.0-0',
        'libgomp1', 'fonts-dejavu-core')
    # Patched NVIDIA Warp, CUDA build this time (CUDA_PATH set -> GPU kernels)
    .run_commands(
        'git lfs install --skip-repo',
        'git clone --depth 1 '
        'https://github.com/maria-korosteleva/NvidiaWarp-GarmentCode.git /opt/warp',
        'pip install --no-cache-dir "numpy<2"',
        'cd /opt/warp && chmod +x tools/packman/packman '
        '&& CUDA_PATH=/usr/local/cuda python build_lib.py '
        '&& pip install --no-cache-dir .',
    )
    # Dependency layer from setup.cfg (empty seweasy dist, same trick as the
    # Dockerfile -- actual code arrives via add_local_dir below)
    .add_local_file(_REPO / 'pyproject.toml', '/pkg/pyproject.toml', copy=True)
    .add_local_file(_REPO / 'setup.cfg', '/pkg/setup.cfg', copy=True)
    .run_commands('mkdir -p /pkg/seweasy && pip install --no-cache-dir /pkg')
    .env({'PYTHONPATH': '/app', 'PYTHONUNBUFFERED': '1'})
    # Code + assets, attached at container start so code changes don't
    # rebuild the image. NOTE: keep .env excluded -- never ship secrets.
    .add_local_dir(
        _REPO, '/app',
        ignore=[
            '.git', '.env', '.claude', '**/__pycache__', '**/*.pyc',
            'tmp_gui', 'data', 'Logs', 'docs', 'output',
        ])
)


@app.function(image=image, gpu=GPU_KIND, cpu=4.0, memory=8192, timeout=900)
def drape(spec_files: dict, in_name: str, out_name: str) -> dict:
    """Generate the box mesh and simulate the drape of one pattern spec.

    * spec_files -- {filename: bytes} of the serialized pattern spec folder
      (specification JSON, body measurements, design params)
    * in_name / out_name -- pattern tags, must match the caller's PathCofig
      so the produced filenames line up

    Returns {'files': {filename: bytes}, 'fails': dict, 'sim_time': float}
    """
    import shutil
    import tempfile
    import time

    # Work from a writable dir that mirrors the repo layout: the sim config
    # and system.json reference './assets/...' relative to cwd
    work = Path(tempfile.mkdtemp())
    os.symlink('/app/assets', work / 'assets')
    shutil.copy('/app/system.template.json', work / 'system.json')
    os.chdir(work)

    in_dir = work / 'pattern'
    in_dir.mkdir()
    for filename, data in spec_files.items():
        (in_dir / filename).write_bytes(data)

    import seweasy.data_config as data_config
    from seweasy.meshgen.boxmeshgen import BoxMesh
    from seweasy.meshgen.simulation import run_sim
    from seweasy.meshgen.sim_config import PathCofig

    # Same configuration flow as GUIPattern.drape_3d
    props = data_config.Properties('./assets/Sim_props/gui_sim_props.yaml')
    props.set_section_stats(
        'sim', fails={}, sim_time={}, spf={}, fin_frame={},
        body_collisions={}, self_collisions={})
    props.set_section_stats('render', render_time={})

    paths = PathCofig(
        in_element_path=in_dir,
        out_path=work / 'output',
        in_name=in_name,
        out_name=out_name,
        body_name='mean_all',
        smpl_body=False,
        add_timestamp=False
    )

    start_time = time.time()
    garment_box_mesh = BoxMesh(
        paths.in_g_spec, props['sim']['config']['resolution_scale'])
    try:
        garment_box_mesh.load()
    except BaseException as e:
        # Re-raise mesh-load failures (e.g. StitchingError) as a plain
        # RuntimeError so the message survives deserialization on clients
        # that lack the meshgen deps (igl/warp)
        raise RuntimeError(f'mesh load failed: {type(e).__name__}: {e}')
    garment_box_mesh.serialize(
        paths, store_panels=False,
        uv_config=props['render']['config']['uv_texture'])

    run_sim(
        garment_box_mesh.name,
        props,
        paths,
        save_v_norms=False,
        store_usd=False,
        optimize_storage=False,
        verbose=False
    )
    sim_time = time.time() - start_time

    # Ship back what the GUI needs to display (and later re-tint) the result:
    # the simulated OBJ and its material/texture files
    out_files = {}
    for path in (paths.g_sim, paths.g_mtl, paths.g_texture, paths.g_texture_fabric):
        if path.exists():
            out_files[path.name] = path.read_bytes()

    if not paths.g_sim.exists():
        raise RuntimeError(
            f'Simulation produced no output mesh; '
            f"failures: {props['sim']['stats'].get('fails', {})}")

    return {
        'files': out_files,
        'fails': props['sim']['stats'].get('fails', {}),
        'sim_time': sim_time,
    }


# ---------------------------------------------------------------------------
# Client-side helpers (imported by the GUI)

def is_enabled() -> bool:
    """Remote draping is opt-in via MODAL_DRAPE"""
    return os.getenv('MODAL_DRAPE', '').lower() in ('1', 'true', 'yes')


def remote_drape(pattern_folder, paths) -> None:
    """Drape the pattern spec in `pattern_folder` on Modal and materialize
    the simulation outputs into the local `paths` locations, as if the
    simulation had run locally."""
    fn = modal.Function.from_name(APP_NAME, 'drape')

    spec_files = {
        p.name: p.read_bytes()
        for p in Path(pattern_folder).iterdir() if p.is_file()
    }
    result = fn.remote(spec_files, paths.in_tag, paths.sim_tag)

    paths.out_el.mkdir(parents=True, exist_ok=True)
    for filename, data in result['files'].items():
        (paths.out_el / filename).write_bytes(data)

    if result['fails']:
        print(f"ModalDrape::WARNING::sim quality flags: {result['fails']}")
    print(f"ModalDrape::INFO::remote simulation took {result['sim_time']:.1f}s")
