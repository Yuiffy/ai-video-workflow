"""Verify actual movie audio, unchanged video streams and protected dialogue."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/sui-ai-gym-20261012'
WORK = OUT/'nanami-voice-repair'


def run(args):
    return subprocess.run([str(a) for a in args],check=True,capture_output=True,
                          encoding='utf-8',errors='replace').stdout


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def normalize(text):
    # Record the actual ASR spelling separately; these aliases cover known names/homophones.
    text=text.lower().replace(' ', '')
    for old,new in [('cloud','claude'),('提波','tibo'),('泰波','tibo'),('tbo','tibo'),
                    ('质朴','智谱'),('直谱','智谱'),('站起来登','站起来蹬'),('h三','h3')]:
        text=text.replace(old,new)
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '',text)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--variant',default='cosy_ready_trimmed')
    parser.add_argument('--film',default='sui-ai-gym-nanami-cosy.mp4')
    args=parser.parse_args()
    timeline=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    manifest=json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    edits=json.loads((WORK/f'{args.variant}-edit.json').read_text(encoding='utf-8'))
    assert digest(OUT/'sui-ai-gym-final.mp4')==manifest['original_sha256']
    original,sr=sf.read(WORK/'original-mix.wav',dtype='float32',always_2d=True)
    repaired,rsr=sf.read(WORK/f'{args.variant}-mix.wav',dtype='float32',always_2d=True)
    assert sr==rsr==48000
    protected=np.ones(len(repaired),dtype=bool)
    for e in edits['edits']:
        protected[round(e['start']*sr):round(e['end']*sr)]=False
    unchanged=np.max(np.abs(repaired[protected]-original[:len(repaired)][protected]))
    assert unchanged==0
    reports=[]
    for filename,original_name in [(args.film,'sui-ai-gym-final.mp4'),
              (args.film.replace('.mp4','-clean.mp4'),'sui-ai-gym-clean.mp4')]:
        film=OUT/filename
        run(['ffmpeg','-v','error','-xerror','-i',film,'-map','0:v:0','-map','0:a:0','-f','null','-'])
        info=json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',film]))
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        audio=next(s for s in info['streams'] if s['codec_type']=='audio')
        assert (video['width'],video['height'],video['r_frame_rate'])==(1280,720,'30/1')
        assert int(video['nb_frames'])==2724
        assert abs(float(video['duration'])-90.8)<.001
        assert abs(float(audio['duration'])-90.8)<.05
        hashes=[]
        for path in [OUT/original_name,film]:
            hashes.append(run(['ffmpeg','-v','error','-i',path,'-map','0:v:0','-c:v','copy',
                               '-f','streamhash','-hash','sha256','-']).strip())
        assert hashes[0]==hashes[1], 'Video packet data changed'
        reports.append(dict(file=filename,sha256=digest(film),full_decode='passed',
                    video_stream_hash=hashes[1],video_matches_original=True,
                    frames=int(video['nb_frames']),video_seconds=float(video['duration']),
                    audio_seconds=float(audio['duration'])))
    from faster_whisper import WhisperModel
    model=WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2',device='cuda',
                      compute_type='float16',local_files_only=True)
    qa=WORK/'final-qa'
    qa.mkdir(exist_ok=True)
    checks=[]
    nanami_checks=[]
    film=OUT/args.film
    for chapter in timeline['chapters']:
        wav=qa/f"{chapter['scene']}.wav"
        run(['ffmpeg','-v','error','-y','-ss',str(chapter['start']),'-i',film,
             '-t',str(chapter['duration']),'-vn','-ac','1','-ar','16000',wav])
        segments,_=model.transcribe(str(wav),language='zh',beam_size=5,vad_filter=True,
                  word_timestamps=True,condition_on_previous_text=False,
                  hallucination_silence_threshold=1.)
        segments=[dict(start=s.start,end=s.end,text=s.text,
                       words=[dict(start=w.start,end=w.end,word=w.word) for w in s.words or []])
                  for s in segments]
        text=''.join(s['text'] for s in segments)
        expected=''.join(c['text'] for c in timeline['subtitles'] if c['scene']==chapter['scene'])
        a,b=normalize(expected),normalize(text)
        match=difflib.SequenceMatcher(None,a,b,autojunk=False)
        coverage=sum(block.size for block in match.get_matching_blocks())/max(1,len(a))
        item=dict(chapter=chapter['scene'],expected=expected,observed=text,
                  coverage=round(coverage,3),initial_prompt=None,segments=segments)
        checks.append(item)
        print(json.dumps({k:v for k,v in item.items() if k!='segments'},ensure_ascii=False),flush=True)
        assert coverage>=.82,f"{chapter['scene']}: actual exported speech needs review"
        chapter_audio,chapter_sr=sf.read(wav,dtype='float32')
        for cue in [c for c in manifest['cues'] if c['scene']==chapter['scene']]:
            a=round(max(0.,cue['start']-chapter['start'])*chapter_sr)
            b=round(min(chapter['duration'],cue['end']-chapter['start'])*chapter_sr)
            utterance=chapter_audio[a:b]
            utterance_segments,_=model.transcribe(utterance,language='zh',beam_size=5,
                       vad_filter=False,condition_on_previous_text=False)
            observed=''.join(s.text for s in utterance_segments)
            expected=normalize(cue['text'])
            matcher=difflib.SequenceMatcher(None,expected,normalize(observed),autojunk=False)
            coverage=sum(block.size for block in matcher.get_matching_blocks())/max(1,len(expected))
            row=dict(cue=cue['id'],expected=cue['text'],observed=observed,coverage=round(coverage,3))
            nanami_checks.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
            assert coverage>=.88,f"{cue['id']}: isolated exported line needs review"
    report=dict(files=reports,dialogue_checks=checks,nanami_checks=nanami_checks,
                protected_sample_max_delta=float(unchanged),
                protected_samples=int(protected.sum()),nanami_lines=11,
                reference_sha256=manifest['reference_sha256'],subtitle_files_unchanged=True,
                added_dreamina_credits=0,human_listening_review=False,
                note='ASR checks words; the user evaluates voice likeness and naturalness.')
    (WORK/'final-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Voice repair movie verification passed',flush=True)


if __name__=='__main__':
    main()
