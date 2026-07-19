"""Prototype: run ChatGarment (CVPR'25) image->GarmentCode inference on Modal.

Usage:
    modal run chatgarment_modal.py --img-dir ./test_imgs --out results.tgz
"""
import os

import modal

app = modal.App("chatgarment-proto")
vol = modal.Volume.from_name("chatgarment-weights", create_if_missing=True)

WEIGHTS_URL = (
    "https://sjtueducn-my.sharepoint.com/:u:/g/personal/biansiyuan_sjtu_edu_cn/"
    "EQayoB8ie7ZIsFrjLWdBASQBFexZHXcGjrS6ghgGCjIMzw?e=o60Y65&download=1"
)
CKPT_DIR = "/root/ChatGarment/checkpoints/try_7b_lr1e_4_v3_garmentcontrol_4h100_v4_final"

image = (
    modal.Image.from_registry("nvidia/cuda:12.1.1-devel-ubuntu22.04", add_python="3.10")
    .apt_install("git", "curl", "libgl1", "libglib2.0-0", "libcairo2")
    .pip_install(
        "torch==2.1.2", "torchvision==0.16.2",
        "transformers==4.37.2", "tokenizers==0.15.1", "sentencepiece==0.1.99",
        "accelerate==0.32.0", "peft==0.10.0",
        "deepspeed==0.12.6",
        "einops==0.6.1", "einops-exts==0.0.4", "timm==0.6.13",
        "scikit-learn==1.2.2", "shortuuid", "easydict", "tensorboard",
        "opencv-python-headless", "numpy<2", "tqdm", "requests",
        # GarmentCodeRC drafting deps (no sim/warp needed for 2D patterns)
        "pyyaml>=6.0", "scipy", "svgwrite", "svgpathtools", "psutil",
        "matplotlib", "cairosvg",
    )
    .run_commands(
        "git clone --depth 1 https://github.com/biansy000/ChatGarment.git /root/ChatGarment",
        "git clone --depth 1 https://github.com/biansy000/GarmentCodeRC.git /root/GarmentCodeRC",
        "ln -s /root/GarmentCodeRC/assets /root/ChatGarment/assets",
        # cluster paths hardcoded upstream -> our container layout
        "sed -i 's|/is/cluster/fast/sbian/github/GarmentCodeV2/|/root/GarmentCodeRC|g' "
        "/root/ChatGarment/llava/garment_utils_v2.py",
        # avoid flash-attn compile; sdpa is numerically equivalent for inference
        "sed -i \"s|attn_implementation = 'flash_attention_2'|attn_implementation = 'sdpa'|\" "
        "/root/ChatGarment/scripts/evaluate_garment_v2_imggen_1float.py",
        f"mkdir -p {CKPT_DIR}",
    )
    .env({"HF_HOME": "/vol/hf", "PYTHONUNBUFFERED": "1"})
)


@app.function(image=image, volumes={"/vol": vol}, timeout=7200)
def download_weights(force: bool = False) -> int:
    import os
    import requests

    dst = "/vol/pytorch_model.bin"
    if os.path.exists(dst) and not force:
        return os.path.getsize(dst)

    with requests.Session() as s:
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        r = s.get(WEIGHTS_URL, stream=True, allow_redirects=True, timeout=600)
        r.raise_for_status()
        n = 0
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 22):
                f.write(chunk)
                n += len(chunk)
                if n % (1 << 30) < (1 << 22):
                    print(f"downloaded {n / (1<<30):.1f} GiB")
        os.rename(tmp, dst)
    vol.commit()
    return n


@app.function(
    image=image, gpu=os.getenv("CHATGARMENT_GPU", "L4"), volumes={"/vol": vol}, timeout=3600, memory=65536
)
def infer_images(images: dict) -> bytes:
    import io
    import os
    import subprocess
    import tarfile

    ckpt = os.path.join(CKPT_DIR, "pytorch_model.bin")
    if not os.path.exists(ckpt):
        os.symlink("/vol/pytorch_model.bin", ckpt)

    img_dir = "/tmp/eval_imgs"
    os.makedirs(img_dir, exist_ok=True)
    for name, data in images.items():
        with open(os.path.join(img_dir, name), "wb") as f:
            f.write(data)

    cmd = [
        "python", "scripts/evaluate_garment_v2_imggen_1float.py",
        "--lora_enable", "True", "--lora_r", "128", "--lora_alpha", "256",
        "--mm_projector_lr", "2e-5",
        "--model_name_or_path", "liuhaotian/llava-v1.5-7b",
        "--version", "v1",
        "--data_path", "./",
        "--data_path_eval", img_dir,
        "--image_folder", "./",
        "--vision_tower", "openai/clip-vit-large-patch14-336",
        "--mm_projector_type", "mlp2x_gelu",
        "--mm_vision_select_layer", "-2",
        "--mm_use_im_start_end", "False",
        "--mm_use_im_patch_token", "False",
        "--image_aspect_ratio", "pad",
        "--group_by_modality_length", "True",
        "--bf16", "True",
        "--output_dir", "./checkpoints/llava-v1.5-7b-task-lora",
        "--model_max_length", "3072",
        "--gradient_checkpointing", "True",
        "--lazy_preprocess", "True",
        "--report_to", "none",
    ]
    subprocess.run(cmd, cwd="/root/ChatGarment", check=True)
    vol.commit()  # persist HF cache downloaded on first run

    out_root = (
        "/root/ChatGarment/runs/try_7b_lr1e_4_v3_garmentcontrol_4h100_v4_final/"
        "eval_imgs_img_recon"
    )
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(out_root, arcname="results")
    return buf.getvalue()


@app.local_entrypoint()
def main(img_dir: str, out: str = "results.tgz"):
    import pathlib

    imgs = {
        p.name: p.read_bytes()
        for p in pathlib.Path(img_dir).iterdir()
        if p.suffix.lower() in (".png", ".jpg", ".jpeg")
    }
    print(f"{len(imgs)} images: {sorted(imgs)}")
    size = download_weights.remote()
    print(f"weights ready: {size / (1<<30):.2f} GiB")
    data = infer_images.remote(imgs)
    pathlib.Path(out).write_bytes(data)
    print(f"wrote {out} ({len(data) / (1<<20):.1f} MiB)")
