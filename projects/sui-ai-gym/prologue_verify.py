"""Check the complete export and prove the approved film body was retained."""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
import re

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

from prologue_edit import OUT, WORK, load, probe, write_json
from sound_design import SR, HOP, digest, grid_rms, loudness, presence_curve, run


def normalize(text):
    return ''.join(re.findall(r'[a-z0-9\u4e00-\u9fff]',text.lower()))


def frame_hashes(path, target):
    run(['ffmpeg','-v','error','-y','-i',path,'-map','0:v:0','-an','-f','framemd5',target])
    return [line.rsplit(',',1)[-1].strip() for line in target.read_text(encoding='utf-8').splitlines()
            if line and not line.startswith('#')]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mark-visual-reviewed',action='store_true')
    args=p.parse_args()
    report_path=WORK/'verification.json'
    if args.mark_visual_reviewed:
        report=load(report_path)
        for movie in report['files']:
            assert digest(OUT/movie['file'])==movie['sha256']
        assert all((WORK/'qa'/name).exists() for name in report['visual_review_files'])
        report['visual_reviewed']=True
        report['visual_review_basis']='Actual exported subtitle frames and both scene transitions reviewed by the agent.'
        write_json(report_path,report)
        print('Visual review recorded for the verified hashes.')
        return
    render=load(WORK/'render.json')
    timeline=load(WORK/'timeline.json')
    qa=WORK/'qa'
    files=[]
    intro_frames=render['intro_frames']
    for film in render['files']:
        path=OUT/film['file']
        assert digest(path)==film['sha256']
        info=probe(path)
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        audio=next(s for s in info['streams'] if s['codec_type']=='audio')
        assert int(video['nb_frames'])==timeline['frameCount'],video
        assert video['avg_frame_rate']=='30/1' and [video['width'],video['height']]==[1280,720]
        assert abs(float(video['duration'])-timeline['duration'])<1e-5
        assert abs(float(audio['duration'])-timeline['duration'])<.001
        assert audio['codec_name']=='aac' and audio['sample_rate']=='48000'
        actual_chapters=json.loads(run(['ffprobe','-v','error','-show_chapters','-of','json',path]))['chapters']
        assert len(actual_chapters)==10
        for old,new in zip(timeline['chapters'],actual_chapters):
            assert old['title']==new['tags']['title'] and abs(old['start']-float(new['start_time']))<.001
        run(['ffmpeg','-v','error','-xerror','-i',path,'-map','0:v:0','-map','0:a:0','-f','null','-'])
        previous=frame_hashes(OUT/film['body_source'],qa/(film['body_source']+'.framemd5'))
        current=frame_hashes(path,qa/(film['file']+'.framemd5'))
        assert len(previous)==2724 and len(current)==timeline['frameCount']
        assert current[intro_frames:]==previous,'Original body changed during video concatenation.'
        measured=loudness(path)
        assert float(measured['input_tp'])<=-1.,measured
        files.append(dict(**film,full_decode='passed',frames=len(current),
                          video_seconds=float(video['duration']),audio_seconds=float(audio['duration']),
                          original_body_decoded_frames_unchanged=True,
                          true_peak_dbtp=float(measured['input_tp']),integrated_lufs=float(measured['input_i'])))
        print(json.dumps(files[-1],ensure_ascii=False),flush=True)
    master,sr=sf.read(WORK/'master.wav',dtype='float32',always_2d=True)
    body,bsr=sf.read(OUT/'sound-design-flirty/master.wav',dtype='float32',always_2d=True)
    assert sr==bsr==SR
    assert np.array_equal(master[round(timeline['introDuration']*SR):],body)
    original=load(OUT/'timeline.json')
    assert len(timeline['subtitles'])==33 and len(timeline['chapters'])==10
    for old,new in zip(original['subtitles'],timeline['subtitles'][9:]):
        assert old['text']==new['text'] and old['speaker']==new['speaker']
        assert abs(new['start']-old['start']-timeline['introDuration'])<1e-5
        assert abs(new['end']-old['end']-timeline['introDuration'])<1e-5
    for previous,current in zip(timeline['subtitles'],timeline['subtitles'][1:]):
        assert previous['end']<=current['start']+.001
    assert all(0<=s['start']<s['end']<=timeline['duration'] for s in timeline['subtitles'])
    assert timeline['flirtyMusicStartsAt']==timeline['introDuration']+53.7
    voice,sr=sf.read(WORK/'stems/dialogue.wav',dtype='float32',always_2d=True)
    music,msr=sf.read(WORK/'stems/music.wav',dtype='float32',always_2d=True)
    count=(len(voice)+HOP-1)//HOP
    presence=presence_curve(np.arange(count)*HOP/SR,[[s['start'],s['end']] for s in timeline['subtitles'][:9]])
    vr,mr=grid_rms(voice,count),grid_rms(music,count)
    speaking=(presence>.95)&(vr>.003)&(mr>1e-7)
    margins=20*np.log10(vr[speaking]/mr[speaking])
    assert np.percentile(margins,1)>=18.,float(np.min(margins))
    prefix_audio=qa/'exported-prefix.wav'
    run(['ffmpeg','-v','error','-y','-i',OUT/'sui-ai-gym-complete.mp4',
         '-t',timeline['introDuration'],'-vn','-ar','16000','-ac','1',prefix_audio])
    from faster_whisper import WhisperModel
    model=WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2',device='cuda',
                       compute_type='float16',local_files_only=True)
    segments,_=model.transcribe(str(prefix_audio),language='zh',word_timestamps=True,
                                vad_filter=True,condition_on_previous_text=False,beam_size=5)
    speech=[dict(start=s.start,end=s.end,text=s.text,words=[dict(start=w.start,end=w.end,word=w.word)
                                                      for w in s.words]) for s in segments]
    write_json(qa/'exported-prefix-asr.json',speech)
    observed=''.join(s['text'] for s in speech)
    expected=''.join(c['text'] for c in timeline['subtitles'][:9])
    coverage=difflib.SequenceMatcher(None,normalize(expected),normalize(observed),autojunk=False).ratio()
    assert coverage>=.95,(expected,observed,coverage)
    assert '虚拟主播' in observed and '教练好' in observed
    assert '训练' in observed and '露馅' in observed
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',18)
    visual_files=[]
    stamps=[(s['start']+s['end'])/2 for s in timeline['subtitles'][:9]]
    stamps += [11.7,11.9,17.7,17.9,18.1,24.1,24.3,24.5,timeline['duration']-.3]
    for page in range(2):
        sheet=Image.new('RGB',(1440,870),'#151b22')
        draw=ImageDraw.Draw(sheet)
        for i,sec in enumerate(stamps[page*9:page*9+9]):
            frame=qa/f'exported-frame-{page*9+i:02}.jpg'
            run(['ffmpeg','-v','error','-y','-ss',sec,'-i',OUT/'sui-ai-gym-complete.mp4',
                 '-frames:v','1','-q:v','2',frame])
            x,y=i%3*480,i//3*290
            sheet.paste(Image.open(frame).convert('RGB').resize((480,270)),(x,y))
            draw.text((x+8,y+270),f'完整成片 · {sec:.2f}s',font=font,fill='#eef5fe')
        name=f'exported-review-{page+1}.jpg'
        sheet.save(qa/name,quality=94)
        visual_files.append(name)
    job=load(OUT/'job.json')
    keys=[c['scene'] for c in timeline['chapters'][:3]]
    for key in keys:
        item=job['items'][key]
        assert item['attempted'] and item['selectedResourceId']
        assert item['observation']['state']=='succeeded'
    assert job['budget']['nominalReservedCredits']==1404
    assert job['budget']['nominalReservedCredits']<=job['budget']['authorizedTotalCeiling']
    report=dict(files=files,full_duration=timeline['duration'],intro_duration=timeline['introDuration'],
                chapters=10,dialogue_cues=33,original_soundtrack_pcm_samples_unchanged=True,
                original_subtitles_preserved_and_shifted=True,
                intro_music_speech_margin_db=dict(minimum=round(float(np.min(margins)),2),
                                                 percentile_1=round(float(np.percentile(margins,1)),2),
                                                 median=round(float(np.median(margins)),2)),
                intro_dialogue_check=dict(expected=expected,observed=observed,coverage=coverage,
                                          prompt=None),
                flirty_music_starts_at=timeline['flirtyMusicStartsAt'],
                visual_review_files=visual_files,visual_reviewed=False,human_listening_review=False,
                added_quoted_dreamina_credits=180,cumulative_submitted_quotation=1404,
                quotation_is_not_verified_settlement=True,uploaded=False)
    write_json(report_path,report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['files']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
