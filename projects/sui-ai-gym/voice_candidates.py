"""Batch local CosyVoice 3 / generic Seed-VC samples with the Nanami reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'outputs/sui-ai-gym-20261012/nanami-voice-repair'
SEED_ROOT = Path('D:/workspace/fun/SeedVC-Sui-20260928/seed-vc')
COSY_ROOT = Path('D:/workspace/fun/CosyVoice3')


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save_wave(path, wave, sr, meta):
    import numpy as np
    import soundfile as sf
    if not np.isfinite(wave).all() or not len(wave) or np.max(np.abs(wave)) < 1e-6:
        raise RuntimeError('Invalid generated speech')
    peak = float(np.abs(wave).max())
    gain = min(1., .98/max(peak, 1e-8))
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, wave*gain, sr, subtype='PCM_16')
    meta.update(sample_rate=sr, seconds=len(wave)/sr, peak_before_gain=peak, gain=gain,
                sha256=digest(path))
    write_json(path.with_suffix('.json'), meta)
    print(json.dumps(meta, ensure_ascii=False), flush=True)


def seed(manifest, cues, variants):
    import torch
    import numpy as np
    sys.path.insert(0, str(SEED_ROOT))
    sys.path.insert(0, str(ROOT / 'tools'))
    os.chdir(SEED_ROOT)
    from seed_convert import load_model
    from modules.v2.vc_wrapper import DEFAULT_CFM_CHECKPOINT, DEFAULT_AR_CHECKPOINT, DEFAULT_REPO_ID
    from hf_utils import load_custom_model_from_hf
    # Explicitly load the generic checkpoints, never the Sui-finetuned CFM.
    cfm = load_custom_model_from_hf(DEFAULT_REPO_ID, DEFAULT_CFM_CHECKPOINT)
    ar = load_custom_model_from_hf(DEFAULT_REPO_ID, DEFAULT_AR_CHECKPOINT)
    model = load_model(SEED_ROOT, None)
    model.setup_ar_caches(max_batch_size=1, max_seq_len=4096, dtype=torch.float16,
                          device=torch.device('cuda'))
    model_meta = dict(engine='Seed-VC v2', cfm_checkpoint=cfm, cfm_sha256=digest(cfm),
                      ar_checkpoint=ar, ar_sha256=digest(ar), seed=20261012,
                      diffusion_steps=30, intelligibility_cfg_rate=.7, similarity_cfg_rate=.7,
                      target_reference=manifest['reference'], target_sha256=manifest['reference_sha256'],
                      generic_model=True, human_listening_review=False)
    write_json(WORK / 'seed-model.json', model_meta)
    for variant in variants:
        style = variant == 'seed_on'
        for cue in cues:
            path = WORK / variant / f"{cue['id']}.wav"
            if path.exists() and path.with_suffix('.json').exists():
                continue
            torch.manual_seed(20261012)
            np.random.seed(20261012)
            began = time.monotonic()
            audio = None
            for _, chunk in model.convert_voice_with_streaming(
                    source_audio_path=cue['source'], target_audio_path=manifest['reference'],
                    diffusion_steps=30, length_adjust=1., intelligebility_cfg_rate=.7,
                    similarity_cfg_rate=.7, top_p=.9, temperature=1., repetition_penalty=1.,
                    convert_style=style, anonymization_only=False, device=torch.device('cuda'),
                    dtype=torch.float16, stream_output=True):
                if chunk is not None:
                    audio = chunk
            if audio is None:
                raise RuntimeError('Seed-VC returned no audio')
            sr, wave = audio
            meta = dict(variant=variant, cue=cue['id'], text=cue['text'],
                        source_sha256=digest(cue['source']), reference_sha256=manifest['reference_sha256'],
                        elapsed=time.monotonic()-began, convert_style=style, seed=20261012,
                        checkpoint_sha256=model_meta['cfm_sha256'], top_p=.9, temperature=1.,
                        repetition_penalty=1., peak_vram_gb=torch.cuda.max_memory_allocated()/1024**3)
            save_wave(path, wave, sr, meta)


def cosy(manifest, cues, variant='cosy'):
    import torch
    import wetext.wetext as wetext_impl
    os.chdir(COSY_ROOT)
    sys.path.insert(0, str(COSY_ROOT))
    sys.path.insert(0, str(COSY_ROOT / 'third_party/Matcha-TTS'))
    wetext_impl.snapshot_download = partial(wetext_impl.snapshot_download, local_files_only=True)
    from cosyvoice.cli.cosyvoice import AutoModel
    from cosyvoice.utils.common import set_all_random_seed
    model = AutoModel(model_dir=str(COSY_ROOT / 'pretrained_models/Fun-CosyVoice3-0.5B'),
                      fp16=True, load_trt=False, load_vllm=False)
    write_json(WORK / f'{variant}-model.json', dict(engine='Fun-CosyVoice3-0.5B-2512',
               verification=json.loads((COSY_ROOT/'workflow-verified.json').read_text(encoding='utf-8')),
               target_reference=manifest['reference'], target_sha256=manifest['reference_sha256'],
               reference_text=manifest['reference_text'], human_listening_review=False))
    for cue in cues:
        path = WORK / variant / f"{cue['id']}.wav"
        if path.exists() and path.with_suffix('.json').exists():
            continue
        set_all_random_seed(20261012)
        began = time.monotonic()
        synthesis_text = cue['text']
        if variant.startswith('cosy_clean') and cue['id'] == 'nanami-06':
            synthesis_text = '提波预告要重置了。你有站起来蹬吗？'
        if variant == 'cosy_clean_retry' and cue['id'] == 'nanami-09':
            synthesis_text = '能制作视频，拿去卖钱。'
        chunks = list(model.inference_zero_shot(
            synthesis_text, 'You are a helpful assistant.<|endofprompt|>'+manifest['reference_text'],
            manifest['reference'], stream=False, speed=1., text_frontend=True))
        wave = torch.cat([chunk['tts_speech'].cpu() for chunk in chunks], dim=1).squeeze().numpy()
        meta = dict(variant=variant, cue=cue['id'], text=cue['text'], synthesis_text=synthesis_text, seed=20261012,
                    reference_sha256=manifest['reference_sha256'], speed=1.,
                    elapsed=time.monotonic()-began, peak_vram_gb=torch.cuda.max_memory_allocated()/1024**3)
        save_wave(path, wave, model.sample_rate, meta)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('engine', choices=['seed','cosy'])
    parser.add_argument('--ids', nargs='*')
    parser.add_argument('--clean-reference', action='store_true')
    parser.add_argument('--output-variant', choices=['cosy','cosy_clean','cosy_clean_retry'])
    parser.add_argument('--variants', nargs='+', default=['seed_off','seed_on'],
                        choices=['seed_off','seed_on'])
    args = parser.parse_args()
    import torch
    torch.set_num_threads(4)
    if not torch.cuda.is_available():
        raise RuntimeError('Configured CUDA GPU is required')
    manifest = json.loads((WORK / 'manifest.json').read_text(encoding='utf-8'))
    if args.clean_reference:
        manifest['reference'] = str(WORK / 'reference-clean-trimmed.wav')
        manifest['reference_sha256'] = digest(manifest['reference'])
    cues = [c for c in manifest['cues'] if not args.ids or c['id'] in args.ids]
    assert cues
    if args.engine == 'seed':
        seed(manifest, cues, args.variants)
    else:
        cosy(manifest, cues, args.output_variant or ('cosy_clean' if args.clean_reference else 'cosy'))
