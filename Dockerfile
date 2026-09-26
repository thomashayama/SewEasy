# syntax=docker/dockerfile:1

# The image deliberately ships without the patched NVIDIA Warp
# (maria-korosteleva/NvidiaWarp-GarmentCode): that fork is based on Warp
# 1.0.0-beta.6 under the NVIDIA Source Code License, which restricts use to
# non-commercial research/evaluation. The studio drapes in the browser, so the
# app never needs it; only the offline dataset pipeline and the legacy
# GUIPattern.drape_3d() do, and those run outside this image.
FROM python:3.11-slim-bookworm

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

# Application code
COPY . .

# Machine-local paths config expected at the repo root (docs/Installation.md);
# the template's relative defaults are correct inside the container.
RUN cp system.template.json system.json && mkdir -p Logs

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health')"

CMD ["python", "gui.py"]
