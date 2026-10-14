"""Inspect the actual added clips without touching the approved original cut."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'outputs/sui-ai-gym-20261012/prologue'


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True,
                          encoding='utf-8', errors='replace').stdout


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('keys', nargs='*')
    args = parser.parse_args()
    scenes = json.loads((WORK/'production-plan.json').read_text(encoding='utf-8'))['scenes']
    qa = WORK/'qa'
    qa.mkdir(exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 18)
    model = None
    for scene in scenes:
        key = scene['id']
        if args.keys and key not in args.keys:
            continue
        source = WORK/(key+'-raw.mp4')
        if not source.exists():
            continue
        probe = json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',source]))
        duration = float(probe['format']['duration'])
        stamps = [.12] + [duration*i/8 for i in range(1,8)] + [duration-.14]
        sheet = Image.new('RGB', (1440,870), '#151b22')
        draw = ImageDraw.Draw(sheet)
        for i, sec in enumerate(stamps):
            frame = qa/f'{key}-{i}.jpg'
            if not frame.exists():
                run(['ffmpeg','-v','error','-y','-ss',sec,'-i',source,'-frames:v','1','-q:v','2',frame])
            x,y = i%3*480,i//3*290
            sheet.paste(Image.open(frame).convert('RGB').resize((480,270)),(x,y))
            draw.text((x+8,y+270),f'{key} · {sec:.2f}s',font=font,fill='#edf2fa')
        sheet.save(qa/(key+'-sheet.jpg'),quality=93)
        wav = qa/(key+'.wav')
        if not wav.exists():
            run(['ffmpeg','-v','error','-y','-i',source,'-vn','-ar','16000','-ac','1',wav])
        asr = qa/(key+'-asr.json')
        if not asr.exists():
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2',device='cuda',
                                     compute_type='float16',local_files_only=True)
            segments,_ = model.transcribe(str(wav),language='zh',word_timestamps=True,vad_filter=True,
                                          beam_size=5,condition_on_previous_text=False)
            speech = [dict(start=s.start,end=s.end,text=s.text,words=[
                dict(start=w.start,end=w.end,word=w.word) for w in s.words]) for s in segments]
            asr.write_text(json.dumps(speech,ensure_ascii=False,indent=2),encoding='utf-8')
        result = dict(scene=key,duration=duration,streams=[{k:s.get(k) for k in
            ['codec_type','codec_name','width','height','r_frame_rate','duration','sample_rate']}
            for s in probe['streams']],speech=[{k:s[k] for k in ['start','end','text']}
            for s in json.loads(asr.read_text(encoding='utf-8'))])
        (qa/(key+'-media.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    greeting = WORK/'nanami-greeting.wav'
    asr = qa/'nanami-greeting-asr.json'
    if greeting.exists() and not asr.exists():
        if model is None:
            from faster_whisper import WhisperModel
            model = WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2',device='cuda',
                                 compute_type='float16',local_files_only=True)
        segments,_ = model.transcribe(str(greeting),language='zh',word_timestamps=True,vad_filter=True,
                                      beam_size=5,condition_on_previous_text=False)
        speech=[dict(start=s.start,end=s.end,text=s.text,words=[
            dict(start=w.start,end=w.end,word=w.word) for w in s.words]) for s in segments]
        asr.write_text(json.dumps(speech,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Greeting',json.dumps(speech,ensure_ascii=False),flush=True)
