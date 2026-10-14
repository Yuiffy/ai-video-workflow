"""Prepend verified new material while preserving the approved body of the film."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from assemble import stamp
from sound_design import (SR, HOP, db, digest, duck_guard, expand, fade,
                          grid_rms, loudness, presence_curve, rms, run)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/sui-ai-gym-20261012'
WORK = OUT/'prologue'
CUTS = [('00a_nail_memory', 0., 11.8),
        ('00b_nail_confidence', 0., 6.1),
        ('00c_gym_arrival', .6, 7.)]


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))


def read_audio(path):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    if sr != SR:
        divisor = math.gcd(sr, SR)
        x = resample_poly(x, SR//divisor, sr//divisor, axis=0).astype('float32')
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    assert x.shape[1] == 2 and np.isfinite(x).all()
    return x


def mute_interval(x, start, end):
    a,b = round(start*SR), round(end*SR)
    x[a:b] = 0
    n = round(.035*SR)
    if a >= n:
        x[a-n:a] *= np.linspace(1, 0, n)[:,None]
    if b+n <= len(x):
        x[b:b+n] *= np.linspace(0, 1, n)[:,None]


def replacement(x, path, asr_path, at, target_rms):
    speech = load(asr_path)
    start = min(s['start'] for s in speech)
    end = max(s['end'] for s in speech)
    clip = read_audio(path)[:round((end+.15)*SR)]
    gain = min(target_rms/max(rms(clip[round(start*SR):round(end*SR)]),1e-8),
               db(-3)/max(float(np.abs(clip).max()),1e-8))
    clip = fade(clip*gain, .007, .05)
    a=round(at*SR)
    assert a+len(clip) <= len(x)
    x[a:a+len(clip)] += clip
    return dict(file=path.name, start=at, speech_start=at+start, speech_end=at+end,
                end=(a+len(clip))/SR, gain_db=20*math.log10(gain),
                sha256=digest(path), time_stretched=False)


def base_ass():
    original=(OUT/'sui-ai-gym.ass').read_text(encoding='utf-8').split('[Events]')[0]
    return original + (
        'Style: Shiori,Microsoft YaHei,33,&H00DDF4FE,&H000000FF,&H00181924,&H80000000,'
        '-1,0,0,0,100,100,0,0,1,2.4,1,2,60,60,40,1\n'
        'Style: Label,Microsoft YaHei,23,&H00FFFFFF,&H000000FF,&H80312C28,&H80312C28,'
        '-1,0,0,0,100,100,0,0,3,8,0,7,48,48,40,1\n\n'
        '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')


def labels_for(key):
    labels={
        '00a_nail_memory':[(.1,2.9,'此前 · 美甲店',48,52),
                           (1.45,3.05,'栞栞 · 美甲师',990,52),
                           (6.5,8.25,'岁己',48,52)],
        '00b_nail_confidence':[],
        '00c_gym_arrival':[(.05,2.2,'现在 · 健身房',48,52),
                           (2.25,4.9,'七海 · 健身教练',965,52)]}
    result=base_ass()
    for start,end,text,x,y in labels[key]:
        result+=(f'Dialogue: 1,{stamp(start,True)},{stamp(end,True)},Label,,0,0,0,,'
                 f'{{\\pos({x},{y})\\fad(100,160)}}{text}\n')
    return result


def subtitle_ass(cues):
    result=base_ass()
    for cue in cues:
        speaker=cue['speaker']
        style='Inner' if '内心' in speaker else 'Nanami' if speaker=='七海' else 'Shiori' if speaker=='栞栞' else 'Sui'
        text=('（内心）' if style=='Inner' else '')+cue['text']
        if len(text)>28:
            text=text.replace('，','，\\N',1)
        result+=f"Dialogue: 0,{stamp(cue['start'],True)},{stamp(cue['end'],True)},{style},,0,0,0,,{text}\n"
    return result


def main():
    (WORK/'edit').mkdir(exist_ok=True)
    (WORK/'stems').mkdir(exist_ok=True)
    original_qa=load(OUT/'sound-design-flirty/verification.json')
    for film in original_qa['files']:
        assert film['full_decode']=='passed'
        assert digest(OUT/film['file'])==film['sha256']
    plan=load(WORK/'production-plan.json')
    catalog={s['id']:s for s in plan['scenes']}
    original=load(OUT/'timeline.json')
    body,rate=sf.read(OUT/'sound-design-flirty/master.wav',dtype='float32',always_2d=True)
    assert rate==SR and len(body)==4358400
    identity=WORK/'sui-private-identity-clear.wav'
    identity_asr=WORK/'qa/sui-private-identity-clear-asr.json'
    assert '虚拟主播' in ''.join(s['text'] for s in load(identity_asr))
    greeting=WORK/'nanami-greeting.wav'
    greeting_asr=WORK/'qa/nanami-greeting-asr.json'
    chapters,captions,tracks,changes,segments=[],[],[],[],[]
    offset_frames=0
    for key,start,end in CUTS:
        source=WORK/(key+'-raw.mp4')
        info=probe(source)
        actual=float(next(s for s in info['streams'] if s['codec_type']=='video')['duration'])
        assert 0<=start<end<=actual
        count=round((end-start)*30)
        seconds=count/30
        offset=offset_frames/30
        raw_audio=WORK/'edit'/(key+'-source.wav')
        run(['ffmpeg','-v','error','-y','-i',source,'-vn','-ar',SR,'-ac','2','-c:a','pcm_f32le',raw_audio])
        wave=read_audio(raw_audio)
        if key=='00a_nail_memory':
            target=rms(wave[round(6.75*SR):round(7.89*SR)])
            mute_interval(wave,3.22,6.1)
            rep=replacement(wave,identity,identity_asr,3.34,target)
            assert rep['end']<6.4
            changes.append(dict(scene=key,reason='Clear pronunciation of 虚拟主播.',**rep))
            cues=[(1.55,2.95,'栞栞','你是做什么的？'),
                  (rep['speech_start']-.08,rep['speech_end']+.16,'岁己内心','不能暴露我是虚拟主播。'),
                  (6.65,8.05,'岁己','我是做AI的。'),
                  (9.17,10.85,'栞栞','那好厉害啊。')]
        elif key=='00b_nail_confidence':
            cues=[(.11,1.07,'岁己内心','不错。'),
                  (1.27,3.47,'岁己内心','以后问我做什么的，我就会回答这个。'),
                  (3.49,5.88,'岁己内心','别人也不懂，不会露馅。')]
        else:
            target=rms(body[round(2.83*SR):round(4.25*SR)])
            mute_interval(wave,2.94,5.48)
            rep=replacement(wave,greeting,greeting_asr,3.06,target)
            changes.append(dict(scene=key,reason='Use the approved clean Nanami CosyVoice reference; remove extra vocalization.',**rep))
            cues=[(1.56,2.64,'岁己','教练好。'),
                  (rep['speech_start']-.10,rep['speech_end']+.16,'七海','你好，今天带你训练。')]
        wave=wave[round(start*SR):round(end*SR)]
        assert len(wave)==count*1600
        local=[dict(start=a-start,end=b-start,speaker=s,text=t,scene=key)
               for a,b,s,t in cues]
        assert all(0<=c['start']<c['end']<=seconds for c in local)
        speaking=np.concatenate([wave[round(c['start']*SR):round(c['end']*SR)] for c in local])
        gain=min(db(-23)/max(rms(speaking),1e-8),db(-2)/max(float(np.abs(wave).max()),1e-8))
        wave=fade(wave*gain,.015,.08)
        tracks.append(wave)
        captions.extend([{**c,'start':c['start']+offset,'end':c['end']+offset} for c in local])
        chapters.append(dict(scene=key,take=key,title=catalog[key]['title'],start=offset,
                             duration=seconds,frameCount=count,sourceTrim=[start,end],sourceSha256=digest(source)))
        label=WORK/'edit'/(key+'-labels.ass')
        label.write_text(labels_for(key),encoding='utf-8')
        segment=WORK/'edit'/(key+'-video.mp4')
        # Keep the requested trim phase: the generated VFR timestamps do not
        # always put a source frame exactly on the audio cut boundary.
        vf=f'trim=start={start}:end={end},setpts=PTS-({start})/TB,fps=fps=30:start_time=0,format=yuv420p'
        if key!='00b_nail_confidence':
            vf+=f',ass={label.name}'
        if key=='00b_nail_confidence':
            vf+=f',fade=t=out:st={seconds-.14:.4f}:d=0.14:color=white'
        vf+=',format=yuv420p'
        # Relative ASS paths avoid nested Windows drive-colon escaping.
        import subprocess
        command=['ffmpeg','-v','error','-y','-i',str(source),'-vf',vf,'-an','-frames:v',str(count),
                 '-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','-profile:v','high','-level:v','3.1',
                 '-maxrate','3500k','-bufsize','7000k','-r','30','-fps_mode','cfr','-enc_time_base','1:30',
                 '-video_track_timescale','15360',str(segment)]
        result=subprocess.run(command,cwd=WORK/'edit',capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8',errors='replace')[-2000:])
        assert int(next(s for s in probe(segment)['streams'] if s['codec_type']=='video')['nb_frames'])==count
        segments.append(segment)
        offset_frames+=count
    duration=offset_frames/30
    voice=np.concatenate(tracks)
    count=(len(voice)+HOP-1)//HOP
    times=np.arange(count)*HOP/SR
    presence=presence_curve(times,[[c['start'],c['end']] for c in captions])
    guard_presence=presence_curve(times,[[max(0,c['start']-.4),c['end']+.4] for c in captions])
    music_path=WORK/'edit/music.wav'
    run(['ffmpeg','-v','error','-y','-ss','40','-i',OUT/'sound-design/assets/monkeys-spinning-monkeys.mp3',
         '-t',duration,'-af','highpass=f=110,lowpass=f=6500,equalizer=f=1800:t=q:w=0.8:g=-3',
         '-ar',SR,'-ac','2','-c:a','pcm_f32le',music_path])
    music=read_audio(music_path)[:len(voice)]
    music/=max(rms(music),1e-8)
    music*=expand(10**((-33-6*presence)/20),len(voice))[:,None]
    music=fade(duck_guard(music,grid_rms(voice,count),guard_presence,22,count),.45,.8)
    effects=np.zeros_like(voice)
    events=[dict(time=8.15,asset='pop',source=[0,.18],label='成功蒙混过关',rms_db=-32,peak_db=-22),
            dict(time=17.65,asset='crowd-laugh',source=[.22,1.02],label='不会露馅后的短笑声',rms_db=-33,peak_db=-24)]
    for i,event in enumerate(events):
        path=WORK/'edit'/f'effect-{i}.wav'
        run(['ffmpeg','-v','error','-y','-ss',event['source'][0],'-t',event['source'][1]-event['source'][0],
             '-i',OUT/'sound-design/assets'/(event['asset']+'.wav'),'-ar',SR,'-ac','2','-c:a','pcm_f32le',path])
        clip=read_audio(path)
        gain=min(db(event['rms_db'])/max(rms(clip),1e-8),db(event['peak_db'])/max(float(np.abs(clip).max()),1e-8))
        clip=fade(clip*gain,.008,.18)
        a=round(event['time']*SR)
        effects[a:a+len(clip)]+=clip
    effects=duck_guard(effects,grid_rms(voice,count),guard_presence,16,count)
    premaster=voice+music+effects
    sf.write(WORK/'stems/premaster.wav',premaster,SR,subtype='FLOAT')
    measured=loudness(WORK/'stems/premaster.wav')
    gain_db=min(0.,-1.8-float(measured['input_tp']))
    intro=premaster*db(gain_db)
    for name,track in [('dialogue',voice),('music',music),('effects',effects)]:
        sf.write(WORK/'stems'/(name+'.wav'),track,SR,subtype='FLOAT')
    sf.write(WORK/'intro-master.wav',intro,SR,subtype='PCM_24')
    master=np.concatenate([intro,body])
    sf.write(WORK/'master.wav',master,SR,subtype='PCM_24')
    full_captions=captions+[{**c,'start':c['start']+duration,'end':c['end']+duration}
                            for c in original['subtitles']]
    full_chapters=chapters+[{**c,'start':c['start']+duration} for c in original['chapters']]
    timeline=dict(duration=len(master)/SR,frameCount=offset_frames+original['frameCount'],fps=30,
                  size=[1280,720],chapters=full_chapters,subtitles=full_captions,
                  dialogueCueCount=len(full_captions),introDuration=duration,
                  flirtyMusicStartsAt=duration+53.7,originalBodySource='sui-ai-gym-bilibili-flirty.mp4')
    write_json(WORK/'timeline.json',timeline)
    (WORK/'intro.ass').write_text(subtitle_ass(captions),encoding='utf-8')
    (OUT/'sui-ai-gym-complete.ass').write_text(subtitle_ass(full_captions),encoding='utf-8')
    srt='\n\n'.join(f"{i}\n{stamp(c['start'])} --> {stamp(c['end'])}\n"+
                      ('（内心）' if '内心' in c['speaker'] else '')+c['text']
                      for i,c in enumerate(full_captions,1))+'\n'
    (OUT/'sui-ai-gym-complete.srt').write_text(srt,encoding='utf-8')
    concat=WORK/'edit/intro-concat.txt'
    concat.write_text('\n'.join("file '"+p.as_posix()+"'" for p in segments),encoding='utf-8')
    clean=WORK/'intro-clean.mp4'
    run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c:v','copy',clean])
    clean_body_info=next(s for s in probe(OUT/'sui-ai-gym-bilibili-flirty-clean.mp4')['streams'] if s['codec_type']=='video')
    clean_scale=int(clean_body_info['time_base'].split('/')[1])
    clean_for_body=WORK/'intro-clean-body-timescale.mp4'
    run(['ffmpeg','-v','error','-y','-i',clean,'-c:v','copy',
         '-video_track_timescale',clean_scale,clean_for_body])
    import subprocess
    subprocess.run(['ffmpeg','-v','error','-y','-i','intro-clean.mp4','-vf','ass=intro.ass',
                    '-an','-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','-profile:v','high','-level:v','3.1',
                    '-maxrate','3500k','-bufsize','7000k','-r','30','-fps_mode','cfr','-enc_time_base','1:30',
                    '-video_track_timescale','15360','intro-subtitled.mp4'],cwd=WORK,check=True,capture_output=True)
    meta=';FFMETADATA1\ntitle=AI从业者遇到健身教练 · 完整前情版\n'
    for chapter in full_chapters:
        meta+=f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(chapter['start']*1000)}\nEND={round((chapter['start']+chapter['duration'])*1000)}\ntitle={chapter['title']}\n"
    (WORK/'edit/chapters.txt').write_text(meta,encoding='utf-8')
    files=[]
    for prefix,body_name,target in [('intro-subtitled.mp4','sui-ai-gym-bilibili-flirty.mp4','sui-ai-gym-complete.mp4'),
                                    (clean_for_body.name,'sui-ai-gym-bilibili-flirty-clean.mp4','sui-ai-gym-complete-clean.mp4')]:
        listing=WORK/'edit'/(target+'.concat.txt')
        listing.write_text("file '"+(WORK/prefix).as_posix()+"'\nfile '"+(OUT/body_name).as_posix()+"'\n",encoding='utf-8')
        run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',listing,'-i',WORK/'master.wav',
             '-f','ffmetadata','-i',WORK/'edit/chapters.txt','-map','0:v:0','-map','1:a:0','-map_metadata','2',
             '-map_chapters','2','-c:v','copy','-c:a','aac','-b:a','256k','-ar',SR,'-ac','2',
             '-t',timeline['duration'],'-movflags','+faststart',OUT/target])
        files.append(dict(file=target,sha256=digest(OUT/target),bytes=(OUT/target).stat().st_size,body_source=body_name))
    write_json(WORK/'edit-decisions.json',dict(cuts=chapters,voice_replacements=changes,
                                             visual_reference_and_contact_sheets_reviewed=True,
                                             human_listening_review=False,original_master_sha256=digest(OUT/'sound-design-flirty/master.wav')))
    write_json(WORK/'render.json',dict(files=files,intro_seconds=duration,intro_frames=offset_frames,
                                      original_body_seconds=90.8,full_seconds=timeline['duration'],
                                      flirty_music_starts_at=duration+53.7,intro_master_gain_db=gain_db,
                                      intro_effects=events,original_body_samples_preserved=True,
                                      added_quoted_dreamina_credits=180,uploaded=False))
    print(json.dumps(dict(files=files,duration=timeline['duration'],intro=duration,
                          dialogue_cues=len(full_captions),flirty_music_starts_at=duration+53.7),
                     ensure_ascii=False,indent=2),flush=True)


if __name__ == '__main__':
    main()
