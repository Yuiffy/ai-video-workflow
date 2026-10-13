"""Separate candidate speech and retain traceable acoustic screening evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio
from demucs.apply import apply_model
from demucs.pretrained import get_model
from huggingface_hub import hf_hub_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--seed-root', type=Path, required=True)
    parser.add_argument('--reference-root', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--follow', action='store_true')
    parser.add_argument('--catalog-mode', action='store_true',
                        help='Allow explicitly catalogued non-speech with weaker speaker evidence; record this exception')
    args = parser.parse_args()
    sys.path.insert(0, str(args.seed_root.resolve()))
    from modules.campplus.DTDNN import CAMPPlus
    torch.set_num_threads(4)
    torch.manual_seed(20260928)
    device = 'cuda'
    separator = get_model('htdemucs').eval().to(device)
    speaker = CAMPPlus(feat_dim=80, embedding_size=192)
    weight = hf_hub_download('funasr/campplus', 'campplus_cn_common.bin')
    speaker.load_state_dict(torch.load(weight, map_location='cpu', weights_only=True))
    speaker = speaker.eval().to(device)

    @torch.inference_mode()
    def embedding(wave, sr):
        wave = torch.as_tensor(wave, dtype=torch.float32, device=device)
        wave = torchaudio.functional.resample(wave, sr, 16000)
        fbank = torchaudio.compliance.kaldi.fbank(wave[None], num_mel_bins=80, dither=0, sample_frequency=16000)
        fbank -= fbank.mean(0, keepdim=True)
        result = speaker(fbank[None]).squeeze(0)
        return torch.nn.functional.normalize(result, dim=0)

    refs = json.loads((args.reference_root/'manifest.json').read_text(encoding='utf-8-sig'))
    bank = {}
    for ref in refs:
        path = args.reference_root / Path(ref['audio_path']).name
        if not path.exists():
            continue
        wave, sr = sf.read(path, dtype='float32')
        if wave.ndim > 1:
            wave = wave.mean(1)
        chunks = [wave[i:i+sr*8] for i in range(0, min(len(wave), sr*64), sr*8)]
        bank.setdefault(ref['speaker'], []).extend(embedding(c,sr) for c in chunks if len(c)>=sr*3)
    bank = {name:torch.stack(vectors) for name,vectors in bank.items() if vectors}
    if '岁己SUI' not in bank:
        raise ValueError('Missing target reference')

    @torch.inference_mode()
    def separate(wave):
        mix = torch.from_numpy(wave.T.copy()).to(device)
        mean, std = mix.mean(), mix.std().clamp_min(1e-6)
        stems = apply_model(separator, ((mix-mean)/std)[None], device=device,
                            shifts=0, split=True, overlap=.25, progress=False)[0]
        # Preserve original amplitude scale; mean belongs to mixture, not each stem.
        return (stems[separator.sources.index('vocals')]*std).mean(0).cpu().numpy()

    report = args.dataset/'clean-manifest.jsonl'
    done = set()
    if report.exists():
        done = {json.loads(line)['id'] for line in report.read_text(encoding='utf-8').splitlines()}
    processed = 0
    with report.open('a', encoding='utf-8') as stream:
        while True:
            rows = [json.loads(line) for line in (args.dataset/'raw-manifest.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            for row in rows:
                if row['id'] in done:
                    continue
                wave,sr = sf.read(row['raw_path'],dtype='float32',always_2d=True)
                assert sr==44100
                vocal = separate(wave)
                rawmono = wave.mean(1)
                vec = embedding(vocal,sr)
                scores = {name: float((vectors@vec).topk(min(3,len(vectors))).values.mean()) for name,vectors in bank.items()}
                target_score = scores.pop('岁己SUI')
                runner_name,runner_score=max(scores.items(),key=lambda item:item[1])
                rms=float(np.sqrt(np.mean(vocal*vocal)))
                peak=float(np.abs(vocal).max())
                ratio=float(np.sum(vocal*vocal)/(np.sum(rawmono*rawmono)+1e-8))
                clip_fraction=float(np.mean(np.abs(wave)>.999))
                reasons=[]
                catalog_exception = bool(args.catalog_mode and row.get('curated_catalog_sha256'))
                if target_score < (.35 if catalog_exception else .60): reasons.append('speaker_similarity')
                if target_score-runner_score < (-.10 if catalog_exception else .08): reasons.append('speaker_margin')
                if rms<.008: reasons.append('quiet_or_non_speech')
                if ratio<.15: reasons.append('background_dominated')
                if clip_fraction>.003: reasons.append('source_clipping')
                if not np.isfinite(vocal).all(): reasons.append('non_finite')
                accepted=not reasons
                row.update(speaker_similarity=target_score, runner_up=runner_name,
                           runner_up_similarity=runner_score, vocal_rms=rms, vocal_peak=peak,
                           vocal_energy_ratio=ratio, source_clipping=clip_fraction,
                           accepted=accepted, rejection_reasons=reasons,
                           separation='htdemucs', human_audited=False,
                           catalog_identity_exception=catalog_exception)
                directory = args.dataset/('clean' if accepted else 'rejected')/row['split']
                directory.mkdir(parents=True,exist_ok=True)
                output=directory/(row['id']+'.wav')
                # Peak limiting by one fixed gain, no compression or formant/pitch edits.
                vocal = vocal*min(1.,.95/max(peak,1e-8))
                sf.write(output,vocal,sr,subtype='PCM_16')
                row['clean_path']=str(output.resolve())
                row['clean_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
                stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                done.add(row['id']);processed+=1
                if processed%25==0:print(f'cleaned {len(done)}; last speaker={target_score:.3f} margin={target_score-runner_score:.3f} accepted={accepted}',flush=True)
                if args.limit and processed>=args.limit:return
            if not args.follow or (args.dataset/'extraction.done').exists():break
            time.sleep(5)
    print('Cleaning finished',len(done),flush=True)


if __name__=='__main__':
    main()
