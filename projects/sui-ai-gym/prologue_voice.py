"""Synthesize new lines without changing any approved original-film voices."""
from __future__ import annotations

from functools import partial
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/sui-ai-gym-20261012/prologue'
COSY = Path('D:/workspace/fun/CosyVoice3')
VOICE = ROOT/'outputs/sui-ai-gym-20261012/nanami-voice-repair'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--speaker', choices=['nanami', 'sui'], default='nanami')
    parser.add_argument('--clear-diction', action='store_true')
    args = parser.parse_args()
    if args.speaker == 'nanami':
        reference = VOICE/'reference-clean-trimmed.wav'
        manifest = json.loads((VOICE/'manifest.json').read_text(encoding='utf-8'))
        reference_text = manifest['reference_text']
        text = '你好，今天带你训练。'
        target = OUT/'nanami-greeting.wav'
    else:
        settings = json.loads((ROOT/'outputs/voice-studio/settings.json').read_text(encoding='utf-8'))
        reference = Path(settings['cosy_reference_audio'])
        reference_text = settings['cosy_reference_text']
        text = '不能暴露我是虚拟主播。'
        target = OUT/'sui-private-identity.wav'
    synthesis_text = text
    if args.clear_diction:
        assert args.speaker == 'sui'
        target = OUT/'sui-private-identity-clear.wav'
        synthesis_text = '不能暴露，我是虚拟主播。'
    if target.exists() and target.with_suffix('.json').exists():
        print('Existing greeting retained.')
        raise SystemExit(0)
    import numpy as np
    import soundfile as sf
    import torch
    import wetext.wetext as wetext_impl
    torch.set_num_threads(4)
    os.chdir(COSY)
    sys.path.insert(0, str(COSY))
    sys.path.insert(0, str(COSY/'third_party/Matcha-TTS'))
    wetext_impl.snapshot_download = partial(wetext_impl.snapshot_download, local_files_only=True)
    from cosyvoice.cli.cosyvoice import AutoModel
    from cosyvoice.utils.common import set_all_random_seed
    model = AutoModel(model_dir=str(COSY/'pretrained_models/Fun-CosyVoice3-0.5B'),
                      fp16=True, load_trt=False, load_vllm=False)
    set_all_random_seed(20261012)
    began = time.monotonic()
    chunks = list(model.inference_zero_shot(
        synthesis_text, 'You are a helpful assistant.<|endofprompt|>'+reference_text,
        str(reference), stream=False, speed=1., text_frontend=True))
    wave = torch.cat([c['tts_speech'].cpu() for c in chunks], dim=1).squeeze().numpy()
    assert np.isfinite(wave).all() and len(wave)>1000
    gain = min(1., .98/max(float(np.abs(wave).max()), 1e-8))
    sf.write(target, wave*gain, model.sample_rate, subtype='PCM_16')
    data = dict(text=text, synthesis_text=synthesis_text, engine='Fun-CosyVoice3-0.5B-2512',
                reference=str(reference), reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                reference_text=reference_text, seed=20261012,
                sample_rate=model.sample_rate, seconds=len(wave)/model.sample_rate,
                elapsed=time.monotonic()-began, gain=gain,
                human_listening_review=False,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    target.with_suffix('.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(data,ensure_ascii=False),flush=True)
