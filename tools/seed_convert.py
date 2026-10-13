"""Batch/local WAV conversion through an isolated Seed-VC v2 checkout."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def load_model(root: Path, checkpoint: Path | None):
    import torch
    from hydra.utils import instantiate
    from omegaconf import OmegaConf
    model=instantiate(OmegaConf.load(root/'configs/v2/vc_wrapper.yaml'))
    model.load_checkpoints(cfm_checkpoint_path=str(checkpoint) if checkpoint else None)
    model.eval().to('cuda')
    return model


def convert(model, source, reference, output, steps=30, seed=20260928):
    import numpy as np
    import torch
    import soundfile as sf
    torch.manual_seed(seed)
    began=time.time()
    audio=None
    for _,audio_out in model.convert_voice_with_streaming(
        source_audio_path=str(source),target_audio_path=str(reference),diffusion_steps=steps,
        convert_style=False,anonymization_only=False,device=torch.device('cuda'),
        dtype=torch.float16,stream_output=True,
        intelligebility_cfg_rate=.7,similarity_cfg_rate=.7):
        if audio_out is not None:audio=audio_out
    if audio is None:raise RuntimeError('Seed-VC produced no audio')
    sr,wave=audio
    if not np.isfinite(wave).all() or len(wave)==0:raise RuntimeError('Invalid generated audio')
    peak=float(np.abs(wave).max())
    wave=wave*min(1.,.98/max(peak,1e-8))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    sf.write(output,wave,sr,subtype='PCM_16')
    return dict(output=str(output),seconds=len(wave)/sr,elapsed=time.time()-began,
                peak_before_gain=peak,sample_rate=sr,steps=steps,seed=seed)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seed-root',type=Path,required=True)
    p.add_argument('--checkpoint',type=Path)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--input',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--batch',type=Path,help='JSON list of input/output pairs')
    p.add_argument('--steps',type=int,default=30)
    args=p.parse_args()
    root=args.seed_root.resolve();reference=args.reference.resolve()
    checkpoint=args.checkpoint.resolve() if args.checkpoint else None
    if args.batch:
        jobs=json.loads(args.batch.read_text(encoding='utf-8'))
        jobs=[dict(input=str(Path(j['input']).resolve()),output=str(Path(j['output']).resolve())) for j in jobs]
    elif args.input and args.output:
        jobs=[dict(input=str(args.input.resolve()),output=str(args.output.resolve()))]
    else:p.error('Use --input and --output, or --batch')
    sys.path.insert(0,str(root));os.chdir(root)
    import torch
    torch.set_num_threads(4)
    model=load_model(root,checkpoint)
    for job in jobs:
        result=convert(model,job['input'],reference,job['output'],args.steps)
        result.update(input=job['input'],reference=str(reference),checkpoint=str(checkpoint))
        Path(job['output']).with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
