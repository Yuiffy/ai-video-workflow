"""Create original 120-BPM music, captions, video, and visual review artifacts."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parents[2]
OUT = BASE / 'outputs/sui-frisbee-3d'
RATE, SECONDS = 48000, 16
FPS = 24


def music():
    rng = np.random.default_rng(120)
    audio = np.zeros((RATE*SECONDS,2),dtype=np.float64)

    def add(start,signal,gain=.1,pan=0):
        i = round(start*RATE)
        n = min(len(signal),len(audio)-i)
        if n<=0:
            return
        audio[i:i+n,0] += signal[:n]*gain*(1-pan*.4)
        audio[i:i+n,1] += signal[:n]*gain*(1+pan*.4)

    def pluck(note,duration=.27):
        t = np.arange(round(duration*RATE))/RATE
        f = 440*2**((note-69)/12)
        env = np.minimum(1,t/.008)*np.exp(-t*11)
        return env*(np.sin(2*np.pi*f*t)+.35*np.sin(2*np.pi*f*2*t)+.12*np.sin(2*np.pi*f*3*t))

    tune = [72,76,79,76,74,77,81,77,71,74,79,74,72,76,79,84]
    # Eight two-beat bars: C / F / G / C, repeated with a playful ending.
    roots = [48,53,55,48,48,53,55,48]
    for beat in range(32):
        start = beat*.5
        bar = beat//4
        root = roots[bar]
        add(start,pluck(root,.38),.16,-.3)
        if beat%2==0:
            t=np.arange(round(.20*RATE))/RATE
            phase=2*np.pi*(42*t+35*(1-np.exp(-30*t))/30)
            add(start,np.sin(phase)*np.exp(-25*t),.16)
        else:
            t=np.arange(round(.13*RATE))/RATE
            add(start,rng.normal(0,1,len(t))*np.exp(-40*t),.035,.2)
        for off in (0,.25):
            t=np.arange(round(.06*RATE))/RATE
            add(start+off,rng.normal(0,1,len(t))*np.exp(-90*t),.014,.45)
        for off in (0,.25):
            idx=(beat*2+int(off*4))%len(tune)
            note=tune[idx]+(12 if beat>=24 and idx%4==3 else 0)
            add(start+off,pluck(note),.065,.35)
        if beat%2==0:
            for n in (root+12,root+16,root+19):
                add(start+.03,pluck(n,.4),.03,-.45)
    # A small air swoosh, a bite pop, and two deliberately cartoonish puppy barks.
    t=np.arange(round(.40*RATE))/RATE
    noise=rng.normal(0,1,len(t))
    filtered=np.convolve(noise,np.ones(13)/13,mode='same')
    add(3.48,filtered*np.sin(np.pi*t/.4)**2,.13,.2)
    t=np.arange(round(.12*RATE))/RATE
    add(5.5,np.sin(2*np.pi*(1400*t-2500*t*t))*np.exp(-35*t),.20,.1)
    for start in (5.65,5.92):
        t=np.arange(round(.18*RATE))/RATE
        f=180-70*t/.18
        phase=2*np.pi*np.cumsum(f)/RATE
        env=np.minimum(1,t/.01)*np.exp(-16*t)
        bark=(np.sin(phase)+.6*np.sin(phase*3)+.45*np.sin(phase*5)+.25*np.sin(phase*7))
        add(start,env*bark,.055,.15)
    for beat in range(22,32):
        t=np.arange(round(.11*RATE))/RATE
        add(beat*.5,np.sin(2*np.pi*(440*t+650*t*t))*np.exp(-24*t),.038,-.1)
    audio *= np.minimum(1,np.arange(len(audio))/(RATE*.08))[:,None]
    audio *= np.minimum(1,(len(audio)-1-np.arange(len(audio)))/(RATE*.20))[:,None]
    # Leave headroom for mobile playback; no clipped samples.
    audio = np.tanh(audio*1.25)
    peak=float(np.abs(audio).max())
    audio*=.78/max(.78,peak)
    pcm=(audio*32767).astype('<i2')
    with wave.open(str(OUT/'original-biscuit-beat.wav'),'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return {'sample_rate':RATE,'seconds':SECONDS,'bpm':120,
            'peak':float(np.abs(audio).max()),'rms':float(np.sqrt(np.mean(audio**2))),
            'composition':'Original synthesized pluck / bass / drums; cartoon SFX'}


CAPTIONS = [
    (.25,1.9,'今天，饼干岁兼职飞盘。'),
    (2.1,3.7,'岁己：走你！'),
    (3.85,5.3,'狗岁己：收到！'),
    (5.5,6.7,'一口接住，满分！'),
    (7.0,9.1,'饼干岁：我是飞盘，不是晚饭！！'),
    (9.3,10.8,'岁己：还我饼干！'),
    (11.1,15.95,'算了，一起扁。'),
]


def stamp(sec,ass=False):
    h=int(sec//3600)
    m=int(sec//60)%60
    s=int(sec)%60
    if ass:
        return f'{h}:{m:02d}:{s:02d}.{round((sec-int(sec))*100):02d}'
    return f'{h:02d}:{m:02d}:{s:02d},{round((sec-int(sec))*1000):03d}'


def captions():
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,48,&H00FFFFFF,&H00FFFFFF,&H003D2947,&H40000000,-1,0,0,0,100,100,1,0,1,3.2,1,2,70,70,72,1
Style: Title,Microsoft YaHei,54,&H00473561,&H00473561,&H00FFFFFF,&H00000000,-1,0,0,0,100,100,1,0,1,0,0,7,90,90,55,1
Style: Credit,Microsoft YaHei,22,&H007A627C,&H007A627C,&H00FFFFFF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,9,90,90,73,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[f'Dialogue: 0,{stamp(a,True)},{stamp(b,True)},Caption,,0,0,0,,{{\\fad(90,90)}}{text}' for a,b,text in CAPTIONS]
    events += ['Dialogue: 0,0:00:00.00,0:00:16.00,Title,,0,0,0,,饼干岁飞盘大会',
               'Dialogue: 0,0:00:00.00,0:00:16.00,Credit,,0,0,0,,模型：Yora / Kipfel 改模']
    (OUT/'captions.ass').write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')
    (OUT/'captions.srt').write_text('\n'.join(f'{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n' for i,(a,b,text) in enumerate(CAPTIONS,1)),encoding='utf8')


def run(args):
    subprocess.run(args,cwd=OUT,check=True)


def assemble():
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required')
    run([ffmpeg,'-y','-hide_banner','-loglevel','warning','-framerate',str(FPS),
         '-start_number','1','-i','frames/frame_%04d.png','-i','original-biscuit-beat.wav',
         '-vf','ass=captions.ass','-c:v','libx264','-preset','medium','-crf','18',
         '-pix_fmt','yuv420p','-af','loudnorm=I=-18:LRA=7:TP=-1.5',
         '-c:a','aac','-ar','48000','-b:a','192k','-t',str(SECONDS),
         '-movflags','+faststart','sui-frisbee.mp4'])
    # A lightweight preview accompanies the editable master and final video.
    run([ffmpeg,'-y','-hide_banner','-loglevel','warning','-i','sui-frisbee.mp4',
         '-vf','scale=960:-2','-c:v','libx264','-crf','23','-preset','fast',
         '-c:a','aac','-b:a','128k','-movflags','+faststart','sui-frisbee-preview.mp4'])
    sample_times=[.5,2.7,3.7,4.8,5.6,6.5,8.4,9.7,11,11.25,12,15.8]
    for i,t in enumerate(sample_times):
        run([ffmpeg,'-y','-hide_banner','-loglevel','error','-ss',str(t),'-i','sui-frisbee.mp4',
             '-frames:v','1','-update','1',f'previews/review_{i:02d}.png'])
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
    sheet=Image.new('RGB',(1920,4*398),(245,236,231))
    draw=ImageDraw.Draw(sheet)
    for i,t in enumerate(sample_times):
        im=Image.open(OUT/f'previews/review_{i:02d}.png')
        im.thumbnail((640,360))
        x,y=(i%3)*640,(i//3)*398
        sheet.paste(im,(x,y))
        draw.text((x+14,y+364),f'{t:04.1f}s',font=font,fill=(82,55,70))
    sheet.save(OUT/'contact-sheet.jpg',quality=93)
    shutil.copy2(OUT/'previews/review_04.png',OUT/'poster.png')
    # This player uses relative paths and can be opened from disk or localhost.
    (OUT/'watch.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>饼干岁飞盘大会</title>
<style>body{margin:0;background:#efe2dc;color:#49354d;font:16px "Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:4vh auto;padding:24px}h1{font-size:30px;margin:0 0 18px}
video{width:100%;border-radius:20px;background:#251b2a;box-shadow:0 16px 50px #78586530}
p{line-height:1.8}a{color:#754c79}</style><main><h1>饼干岁飞盘大会</h1>
<video controls playsinline preload="metadata" poster="poster.png"><source src="sui-frisbee.mp4" type="video/mp4">
<track kind="subtitles" src="captions.vtt" srclang="zh" label="中文"></video>
<p>16 秒 · 原创 120 BPM 小曲 · 岁己扔出饼干岁，狗岁己扑接，最后一起扁。</p>
<p>角色模型：Suifel / Yora，基于 Kipfel 改模。狗岁己、饼干岁、场景与动画为本次本地制作。</p>
<p><a href="sui-frisbee.mp4" download>下载视频</a> · <a href="sui-frisbee.blend" download>可编辑 Blender 工程</a></p></main></html>''',encoding='utf8')
    (OUT/'captions.vtt').write_text('WEBVTT\n\n'+'\n'.join(f'{stamp(a).replace(",",".")} --> {stamp(b).replace(",",".")}\n{text}\n' for a,b,text in CAPTIONS),encoding='utf8')
    result=subprocess.run([shutil.which('ffprobe'),'-v','error','-show_format','-show_streams',
                           '-of','json','sui-frisbee.mp4'],cwd=OUT,check=True,capture_output=True,text=True)
    probe=json.loads(result.stdout)
    (OUT/'media-probe.json').write_text(json.dumps(probe,indent=2),encoding='utf8')
    print(json.dumps({'video':str(OUT/'sui-frisbee.mp4'),'bytes':(OUT/'sui-frisbee.mp4').stat().st_size,
                      'duration':probe['format']['duration'],'streams':[(s['codec_type'],s['codec_name']) for s in probe['streams']]}))


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    report=music()
    captions()
    (OUT/'audio-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if len(list((OUT/'frames').glob('frame_*.png'))) == FPS*SECONDS:
        assemble()
    else:
        print('Music and captions ready; waiting for the 384 rendered frames.')
