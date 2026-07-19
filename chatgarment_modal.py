"""Modal photo-to-design service for SewEasy.

Runs ChatGarment (CVPR'25, https://github.com/biansy000/ChatGarment) — a
LLaVA-1.5-7B VLM fine-tuned to estimate GarmentCode designs from garment
photos. A photo goes in; a SewEasy-compatible design parameter tree comes
out, which the GUI applies like any other design and drafts against the
active body profile (the AI's output is body-independent).

Deploy (one-time, and after changing this file):

    modal deploy chatgarment_modal.py

Enable in the app by setting env vars (see .env.example):

    MODAL_PHOTO2DESIGN=1
    MODAL_TOKEN_ID=...      # shared with the drape service
    MODAL_TOKEN_SECRET=...

The ~14GB fine-tuned checkpoint is fetched once from the authors' SharePoint
into the `chatgarment-weights` volume; the LLaVA base model is cached there
too (HF_HOME). First deploy: run `modal run chatgarment_modal.py` to
prefetch weights before serving traffic.

NOTE: ChatGarment's design params target GarmentCodeRC, whose parameter
tree is a superset of ours (2 extra leaves we ignore); `set_new_design`'s
v-value sync makes application safe in both directions.
"""
import os
from copy import deepcopy

import modal

APP_NAME = 'seweasy-photo2design'
# GPU for inference, chosen at *deploy* time. The 7B bf16 model needs
# >=20GB and bf16 support: L4 and A10G fit, T4 does not.
GPU_KIND = os.getenv('CHATGARMENT_GPU', 'L4')

CHECKPOINT = 'try_7b_lr1e_4_v3_garmentcontrol_4h100_v4_final'
WEIGHTS_URL = (
    'https://sjtueducn-my.sharepoint.com/:u:/g/personal/biansiyuan_sjtu_edu_cn/'
    'EQayoB8ie7ZIsFrjLWdBASQBFexZHXcGjrS6ghgGCjIMzw?e=o60Y65&download=1'
)

app = modal.App(APP_NAME)
vol = modal.Volume.from_name('chatgarment-weights', create_if_missing=True)

image = (
    modal.Image.from_registry('nvidia/cuda:12.1.1-devel-ubuntu22.04', add_python='3.10')
    .apt_install('git', 'curl', 'libgl1', 'libglib2.0-0', 'libcairo2')
    .pip_install(
        # ChatGarment / LLaVA stack (pins from its pyproject.toml)
        'torch==2.1.2', 'torchvision==0.16.2',
        'transformers==4.37.2', 'tokenizers==0.15.1', 'sentencepiece==0.1.99',
        'accelerate==0.32.0', 'peft==0.10.0',
        'deepspeed==0.12.6',   # imported by llava.train, not used as launcher
        'einops==0.6.1', 'einops-exts==0.0.4', 'timm==0.6.13',
        'scikit-learn==1.2.2', 'shortuuid', 'easydict', 'tensorboard',
        'opencv-python-headless', 'numpy<2', 'tqdm', 'requests',
        # GarmentCodeRC drafting deps (2D drafting only, no sim stack)
        'pyyaml>=6.0', 'scipy', 'svgwrite', 'svgpathtools', 'psutil',
        'matplotlib', 'cairosvg',
    )
    .run_commands(
        'git clone --depth 1 https://github.com/biansy000/ChatGarment.git /root/ChatGarment',
        'git clone --depth 1 https://github.com/biansy000/GarmentCodeRC.git /root/GarmentCodeRC',
        'ln -s /root/GarmentCodeRC/assets /root/ChatGarment/assets',
        # Hardcoded cluster path in upstream -> our container layout
        "sed -i 's|/is/cluster/fast/sbian/github/GarmentCodeV2/|/root/GarmentCodeRC|g' "
        '/root/ChatGarment/llava/garment_utils_v2.py',
        f'mkdir -p /root/ChatGarment/checkpoints/{CHECKPOINT}',
    )
    .env({'HF_HOME': '/vol/hf', 'PYTHONUNBUFFERED': '1'})
)


@app.function(image=image, volumes={'/vol': vol}, timeout=7200)
def download_weights(force: bool = False) -> int:
    """Fetch the fine-tuned checkpoint into the volume (idempotent)."""
    import requests

    dst = '/vol/pytorch_model.bin'
    if os.path.exists(dst) and not force:
        return os.path.getsize(dst)

    with requests.Session() as s:
        # SharePoint rejects bare HEADs but streams anonymous share links
        # fine with a browser UA + cookies from the redirect chain
        s.headers.update({'User-Agent': 'Mozilla/5.0'})
        r = s.get(WEIGHTS_URL, stream=True, allow_redirects=True, timeout=600)
        r.raise_for_status()
        n = 0
        tmp = dst + '.part'
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(1 << 22):
                f.write(chunk)
                n += len(chunk)
        os.rename(tmp, dst)
    vol.commit()
    return n


@app.cls(
    image=image, gpu=GPU_KIND, volumes={'/vol': vol},
    memory=49152, timeout=1800, scaledown_window=300,
)
class ChatGarment:
    """The VLM, loaded once per container and kept warm between calls."""

    @modal.enter()
    def load(self):
        import sys
        sys.path.insert(0, '/root/ChatGarment')
        sys.path.insert(1, '/root/GarmentCodeRC')
        os.chdir('/root/ChatGarment')  # data files are cwd-relative

        import torch
        import transformers
        from peft import LoraConfig, get_peft_model
        from llava import conversation as conversation_lib
        from llava.model import GarmentGPTFloat50ForCausalLM
        from llava.train.train_garmentcode_outfit import (
            ModelArguments, DataArguments, TrainingArguments)

        # Same flags as ChatGarment's evaluate_garment_v2_imggen script,
        # parsed into its own dataclasses so defaults stay upstream's
        parser = transformers.HfArgumentParser(
            (ModelArguments, DataArguments, TrainingArguments))
        model_args, data_args, training_args = parser.parse_args_into_dataclasses(args=[
            '--lora_enable', 'True', '--lora_r', '128', '--lora_alpha', '256',
            '--mm_projector_lr', '2e-5',
            '--model_name_or_path', 'liuhaotian/llava-v1.5-7b',
            '--version', 'v1',
            '--data_path', './', '--image_folder', './',
            '--vision_tower', 'openai/clip-vit-large-patch14-336',
            '--mm_projector_type', 'mlp2x_gelu',
            '--mm_vision_select_layer', '-2',
            '--mm_use_im_start_end', 'False',
            '--mm_use_im_patch_token', 'False',
            '--image_aspect_ratio', 'pad',
            '--bf16', 'True',
            '--output_dir', '/tmp/unused',
            '--model_max_length', '3072',
            '--gradient_checkpointing', 'True',
            '--report_to', 'none',
        ])

        tokenizer = transformers.AutoTokenizer.from_pretrained(
            model_args.model_name_or_path,
            model_max_length=training_args.model_max_length,
            padding_side='right',
            use_fast=False,
        )
        tokenizer.pad_token = tokenizer.unk_token
        tokenizer.add_tokens('[SEG]')
        seg_token_idx = tokenizer('[SEG]', add_special_tokens=False).input_ids[-1]

        model = GarmentGPTFloat50ForCausalLM.from_pretrained(
            model_args.model_name_or_path,
            attn_implementation='sdpa',  # flash-attn equivalent, no compile
            torch_dtype=torch.bfloat16,
            seg_token_idx=seg_token_idx,
        )
        model.config.eos_token_id = tokenizer.eos_token_id
        model.config.bos_token_id = tokenizer.bos_token_id
        model.config.pad_token_id = tokenizer.pad_token_id
        model.config.use_cache = False

        conversation_lib.default_conversation = \
            conversation_lib.conv_templates[model_args.version]

        model.get_model().initialize_vision_modules(
            model_args=model_args, fsdp=training_args.fsdp)
        vision_tower = model.get_vision_tower()
        vision_tower.to(dtype=torch.bfloat16, device='cuda')

        # The checkpoint was saved from the LoRA-wrapped model: recreate the
        # identical wrapper before the strict state-dict load
        def lora_targets():
            targets = set()
            for name, module in model.named_modules():
                if (isinstance(module, torch.nn.Linear)
                        and all(x not in name for x in (
                            'mm_projector', 'vision_tower',
                            'vision_resampler', 'float_layer'))
                        and any(x in name for x in ('q_proj', 'v_proj'))):
                    targets.add(name)
            return sorted(targets)

        lora_config = LoraConfig(
            r=training_args.lora_r,
            lora_alpha=training_args.lora_alpha,
            target_modules=lora_targets(),
            lora_dropout=training_args.lora_dropout,
            bias=training_args.lora_bias,
            task_type='CAUSAL_LM',
        )
        model = get_peft_model(model, lora_config)
        model.resize_token_embeddings(len(tokenizer))

        state_dict = torch.load('/vol/pytorch_model.bin', map_location='cpu')
        model.load_state_dict(state_dict, strict=True)
        del state_dict

        self.model = model.bfloat16().cuda()
        self.tokenizer = tokenizer
        self.image_processor = vision_tower.image_processor
        self.conv_template = conversation_lib.conv_templates[model_args.version]
        vol.commit()  # persist HF cache from a cold first download

    def _generate(self, image_tensor, prompt):
        import torch
        from llava.constants import DEFAULT_IMAGE_TOKEN
        from llava.mm_utils import tokenizer_image_token

        conv = self.conv_template.copy()
        conv.messages = []
        conv.append_message(conv.roles[0], DEFAULT_IMAGE_TOKEN + '\n' + prompt)
        conv.append_message(conv.roles[1], None)

        input_ids = tokenizer_image_token(
            conv.get_prompt(), self.tokenizer, return_tensors='pt')
        input_ids = input_ids.unsqueeze(0).cuda()

        with torch.inference_mode():
            output_ids, float_preds, _ = self.model.evaluate(
                image_tensor, image_tensor, input_ids,
                max_new_tokens=2048, tokenizer=self.tokenizer)
        text = self.tokenizer.decode(
            output_ids[0, 1:], skip_special_tokens=False)
        return text.strip().replace('</s>', ''), float_preds

    @modal.method()
    def predict(self, image_bytes: bytes) -> dict:
        """Photo -> {description, designs: {upper|lower|wholebody: tree}}.

        Follows ChatGarment's two-step CoT: describe the garment geometry
        first, then generate the sewing pattern code conditioned on both
        the image and the description.
        """
        import io
        import tempfile
        from pathlib import Path

        import yaml
        from PIL import Image
        from llava.garment_utils_v2 import run_garmentcode_parser_float50
        from llava.json_fixer import repair_json

        pil = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        # Pad to square with the CLIP mean color (upstream 'pad' mode)
        w, h = pil.size
        if w != h:
            side = max(w, h)
            bg = tuple(int(x * 255) for x in self.image_processor.image_mean)
            square = Image.new('RGB', (side, side), bg)
            square.paste(pil, ((side - w) // 2, (side - h) // 2))
            pil = square
        image_tensor = self.image_processor.preprocess(
            pil, return_tensors='pt')['pixel_values'][0]
        image_tensor = image_tensor.unsqueeze(0).cuda().bfloat16()

        description, _ = self._generate(
            image_tensor,
            'Can you describe the geometry features of the garments worn '
            'by the model in the Json format?')

        code_text, float_preds = self._generate(
            image_tensor,
            'Can you estimate the sewing pattern code based on the image '
            'and Json format garment geometry description?\n'
            + description.replace('upper_garment', 'upperbody_garment')
                         .replace('lower_garment', 'lowerbody_garment'))

        code_text = (code_text.replace('[STARTS]', '')
                     .replace('[SEG]', '').replace('[ENDS]', ''))
        json_output = repair_json(code_text, return_objects=True)
        float_preds = float_preds.detach().float().cpu().numpy()

        result = {'description': description, 'raw_code': code_text,
                  'designs': {}, 'patterns': {}, 'error': None}
        out_dir = tempfile.mkdtemp()
        try:
            run_garmentcode_parser_float50([], json_output, float_preds, out_dir)
        except Exception as e:  # model output may be undraftable
            result['error'] = f'{type(e).__name__}: {e}'

        for design_file in Path(out_dir).rglob('design.yaml'):
            kind = design_file.parent.name.replace('valid_garment_', '')
            with open(design_file) as f:
                result['designs'][kind] = yaml.safe_load(f)['design']
            png = design_file.parent / f'valid_garment_{kind}_pattern.png'
            if png.exists():
                result['patterns'][kind] = png.read_bytes()

        if not result['designs'] and not result['error']:
            result['error'] = 'model returned no draftable garment'
        return result


@app.local_entrypoint()
def prefetch():
    """`modal run chatgarment_modal.py` — download weights ahead of serving"""
    size = download_weights.remote()
    print(f'weights ready: {size / (1 << 30):.2f} GiB')


# ---------------------------------------------------------------------------
# Client-side helpers (imported by the GUI)

# Sections of the design tree that belong to the lower garment: when the
# model returns a separate upper and lower garment, these are taken from
# the lower tree during the merge into one SewEasy design
_BOTTOM_SECTIONS = (
    'waistband', 'skirt', 'flare-skirt', 'godet-skirt',
    'pencil-skirt', 'levels-skirt', 'pants',
)


def is_enabled() -> bool:
    """Photo-to-design is opt-in via MODAL_PHOTO2DESIGN"""
    return os.getenv('MODAL_PHOTO2DESIGN', '').lower() in ('1', 'true', 'yes')


def photo_to_design(image_bytes: bytes) -> dict:
    """Run ChatGarment on the photo (blocking; call off the event loop)"""
    cls = modal.Cls.from_name(APP_NAME, 'ChatGarment')
    return cls().predict.remote(image_bytes)


def merge_designs(designs: dict) -> dict:
    """Combine the per-garment design trees of a prediction into a single
    SewEasy design parameter tree"""
    if 'wholebody' in designs:
        return designs['wholebody']

    upper, lower = designs.get('upper'), designs.get('lower')
    if not (upper and lower):
        return upper or lower or None

    merged = deepcopy(upper)
    for section in _BOTTOM_SECTIONS:
        if section in lower:
            merged[section] = deepcopy(lower[section])
    for meta_key in ('bottom', 'wb'):
        merged['meta'][meta_key] = deepcopy(lower['meta'][meta_key])
    return merged
