"""Content and acoustic diagnostics, explicitly separate from human listening."""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'outputs/sui-ai-gym-20261012/nanami-voice-repair'
SEED_ROOT = Path('D:/workspace/fun/SeedVC-Sui-20260928/seed-vc')


def normalize(text):
    text = text.lower().replace('？','').replace('，','')
    for token in ['harness','哈尼斯','哈内斯','汉尼斯','汉斯']:
        text = text.replace(token,'harness')
    text = text.replace('mini max','minimax').replace('mini-max','minimax')
    text = text.replace('克劳德','claude').replace('tibo','tibo').replace('提博','tibo')
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variants', nargs='+', default=['seed_off','seed_on','cosy'])
    parser.add_argument('--skip-source', action='store_true')
    parser.add_argument('--report', default='candidate-checks.json')
    parser.add_argument('--ids', nargs='*')
    args = parser.parse_args()
    import torch
    import torchaudio
    from faster_whisper import WhisperModel
    sys.path.insert(0,str(SEED_ROOT))
    from modules.campplus.DTDNN import CAMPPlus
    from huggingface_hub import hf_hub_download
    torch.set_num_threads(4)
    weight = hf_hub_download('funasr/campplus','campplus_cn_common.bin',
                            cache_dir=str(SEED_ROOT/'checkpoints'), local_files_only=True)
    speaker = CAMPPlus(feat_dim=80,embedding_size=192)
    speaker.load_state_dict(torch.load(weight,map_location='cpu',weights_only=True))
    speaker = speaker.eval()
    @torch.inference_mode()
    def embedding(path):
        wave,sr = sf.read(path,dtype='float32',always_2d=True)
        wave=torch.from_numpy(wave.mean(1))[None]
        wave=torchaudio.functional.resample(wave,sr,16000)
        fbank=torchaudio.compliance.kaldi.fbank(wave,num_mel_bins=80,dither=0,
                                              sample_frequency=16000)
        fbank -= fbank.mean(0,keepdim=True)
        return torch.nn.functional.normalize(speaker(fbank[None]).squeeze(0),dim=0)
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    target=embedding(manifest['reference'])
    model=WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2',device='cuda',
                      compute_type='float16',local_files_only=True)
    report=[]
    for variant in ([] if args.skip_source else ['source'])+args.variants:
        for cue in manifest['cues']:
            if args.ids and cue['id'] not in args.ids:
                continue
            path=WORK/variant/f"{cue['id']}.wav"
            if not path.exists():
                continue
            segments,info=model.transcribe(str(path),language='zh',beam_size=5,
                    word_timestamps=True,vad_filter=False,condition_on_previous_text=False,
                    hallucination_silence_threshold=1.)
            segments=[dict(start=s.start,end=s.end,text=s.text,
                           words=[dict(start=w.start,end=w.end,word=w.word) for w in s.words or []])
                      for s in segments]
            observed=''.join(s['text'] for s in segments)
            expected=normalize(cue['text'])
            matching=difflib.SequenceMatcher(None,expected,normalize(observed),autojunk=False)
            coverage=sum(b.size for b in matching.get_matching_blocks())/max(1,len(expected))
            wave,sr=sf.read(path,dtype='float32')
            row=dict(variant=variant,cue=cue['id'],expected=cue['text'],observed=observed,
                     coverage=round(coverage,3),seconds=len(wave)/sr,
                     source_window=cue['end']-cue['start'],target_similarity=float(target@embedding(path)),
                     rms=float(np.sqrt(np.mean(wave**2))),peak=float(np.abs(wave).max()),
                     segments=segments,initial_prompt=None)
            report.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='segments'},ensure_ascii=False),flush=True)
    (WORK/args.report).write_text(json.dumps(dict(
        results=report,human_listening_review=False,
        limitations='ASR and CAMPPlus similarity diagnose content/embedding changes, not voice naturalness or likeness.'),
        ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
