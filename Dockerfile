# syntax=docker/dockerfile:1

# ---------- Stage 1: build the patched NVIDIA Warp (CPU-only) ----------
# The cloth simulator needs maria-korosteleva/NvidiaWarp-GarmentCode, which has
# no prebuilt wheels. CUDA_PATH is left unset so the build is CPU-only —
# suitable for cloud hosts (Railway etc.) that have no GPU. Simulation on CPU
# works but is slow; for GPU simulation run outside this image.
FROM python:3.9-slim-bookworm AS warp-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git git-lfs ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN git lfs install --skip-repo \
    && git clone --depth 1 https://github.com/maria-korosteleva/NvidiaWarp-GarmentCode.git /opt/warp

WORKDIR /opt/warp
RUN chmod +x tools/packman/packman \
    && pip install --no-cache-dir numpy \
    && python build_lib.py \
    && pip wheel --no-deps --wheel-dir /wheels .

# ---------- Stage 2: runtime ----------
FROM python:3.9-slim-bookworm

# libcairo2 -> CairoSVG; libegl1/libgl1/mesa -> headless pyrender via EGL
# (seweasy/meshgen/render/pythonrender.py sets PYOPENGL_PLATFORM=egl on Linux);
# fonts-dejavu-core -> text in rendered patterns
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 libegl1 libgl1 libgl1-mesa-dri libglib2.0-0 libgomp1 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

# Dependency layer: setup.cfg only, so code changes don't re-install deps.
# The seweasy dist itself is empty here — imports resolve via PYTHONPATH=/app,
# as described in docs/Installation.md.
COPY pyproject.toml setup.cfg ./
RUN mkdir -p seweasy && pip install --no-cache-dir .

# Patched Warp simulator built in stage 1
COPY --from=warp-builder /wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

# Application code
COPY . .

# Machine-local paths config expected at the repo root (docs/Installation.md);
# the template's relative defaults are correct inside the container.
RUN cp system.template.json system.json && mkdir -p Logs

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health')"

CMD ["python", "gui.py"]
