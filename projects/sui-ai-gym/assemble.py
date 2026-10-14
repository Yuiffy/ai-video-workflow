"""Assemble reviewed takes, align dialogue subtitles, and write a viewing page."""
from __future__ import annotations
from pathlib import Path
import argparse
import difflib
import hashlib
import html
import json
import math
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = json.loads((HERE / 'production-plan.json').read_text(encoding='utf-8'))
OUT = ROOT / PLAN['output']
EDIT = OUT / 'edit'
EDIT.mkdir(exist_ok=True)

def run(command, cwd=None):
    result = subprocess.run(command, cwd=cwd, capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr[-2500:])
    return result.stdout

def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))

def normalize(text):
    text = text.lower().replace('cloud', 'claude')
    return ''.join(re.findall(r'[a-z0-9\u4e00-\u9fff]', text))

def align(scene, selected, trim_start, trim_end):
    take = selected['take']
    transcript_file = selected.get('asrFile', take + '-asr.json')
    transcript = json.loads((OUT / 'qa' / transcript_file).read_text(encoding='utf-8'))
    dialogue = selected.get('dialogue', scene['dialogue'])
    observed, times = '', []
    for segment in transcript:
        for word in segment['words']:
            chars = normalize(word['word'])
            if not chars or word['end'] <= word['start']:
                continue
            length = max(.02, word['end'] - word['start'])
            for index, char in enumerate(chars):
                observed += char
                times.append((word['start'] + length * index / len(chars), word['start'] + length * (index + 1) / len(chars)))
    expected = ''.join(normalize(line) for _, _, _, line in dialogue)
    matcher = difflib.SequenceMatcher(None, expected, observed, autojunk=False)
    mapping = {}
    for block in matcher.get_matching_blocks():
        for step in range(block.size):
            mapping[block.a + step] = block.b + step
    cues, cursor = [], 0
    for fallback_start, fallback_end, speaker, line in dialogue:
        count = len(normalize(line))
        matched = [mapping[i] for i in range(cursor, cursor + count) if i in mapping]
        coverage = len(matched) / max(1, count)
        if coverage < .64:
            raise RuntimeError(f'{take}: dialogue needs review ({speaker}, coverage {coverage:.2f}): {line}')
        spoken_start = min(times[i][0] for i in matched)
        spoken_end = max(times[i][1] for i in matched)
        assert trim_start <= spoken_start and spoken_end <= trim_end, f'{take}: edit cuts a spoken line'
        start = max(trim_start, spoken_start - .10)
        end = min(trim_end, spoken_end + .16)
        assert end > start
        cues.append({'start': start - trim_start, 'end': end - trim_start, 'speaker': speaker,
                     'text': line, 'asrMatchCoverage': round(coverage, 3),
                     'sourceSpeech': [spoken_start, spoken_end], 'asrFile': transcript_file})
        cursor += count
    for previous, current in zip(cues, cues[1:]):
        if previous['end'] > current['start']:
            boundary = (previous['end'] + current['start']) / 2
            previous['end'], current['start'] = boundary - .015, boundary + .015
    return cues, matcher.ratio()

def stamp(seconds, ass=False):
    scale = 100 if ass else 1000
    value = round(seconds * scale)
    hour, value = divmod(value, 3600 * scale)
    minute, value = divmod(value, 60 * scale)
    second, fraction = divmod(value, scale)
    return f'{hour}:{minute:02}:{second:02}.{fraction:02}' if ass else f'{hour:02}:{minute:02}:{second:02},{fraction:03}'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    decisions = json.loads((OUT / 'edit-decisions.json').read_text(encoding='utf-8'))
    assert decisions['reviewed'], 'Inspect actual takes before assembly'
    chapters, captions, segments = [], [], []
    offset_frames = 0
    for scene in PLAN['scenes']:
        selected = decisions['takes'][scene['id']]
        take = selected['take']
        raw = OUT / (take + '-raw.mp4')
        info = probe(raw)
        duration = float(next(s for s in info['streams'] if s['codec_type'] == 'video')['duration'])
        start = round(selected.get('start', 0) * 30) / 30
        end = math.floor(min(selected.get('end', duration), duration) * 30 + 1e-6) / 30
        assert 0 <= start < end <= duration
        frame_count = round((end - start) * 30)
        offset = offset_frames / 30
        cues, score = align(scene, selected, start, end)
        chapters.append({'scene': scene['id'], 'take': take, 'title': scene['title'], 'start': offset,
                         'duration': frame_count / 30, 'frameCount': frame_count,
                         'sourceTrim': [start, end], 'asrMatchRatio': score})
        captions.extend({**cue, 'start': cue['start'] + offset, 'end': cue['end'] + offset, 'scene': scene['id']} for cue in cues)
        segment = EDIT / (scene['id'] + '.mov')
        segments.append(segment)
        if args.render:
            video_filter = (
                f'trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,'
                'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,'
                f'fps=30:start_time=0,tpad=stop_mode=clone:stop=-1,trim=end_frame={frame_count},'
                'setsar=1'
            )
            audio_filter = (
                f'atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS,'
                'loudnorm=I=-18:TP=-1.5:LRA=8,aresample=48000:first_pts=0,apad,'
                f'atrim=end_sample={frame_count * 1600},asettb=1/48000,asetpts=N'
            )
            if scene == PLAN['scenes'][-1]:
                fade_start = end - start - .32
                video_filter += f',fade=t=out:st={fade_start:.4f}:d=0.32'
                audio_filter += f',afade=t=out:st={fade_start:.4f}:d=0.32'
            run(['ffmpeg', '-v', 'warning', '-y', '-i', str(raw),
                 '-vf', video_filter, '-af', audio_filter, '-c:v', 'libx264', '-preset', 'medium', '-crf', '19',
                 '-r', '30', '-fps_mode', 'cfr', '-enc_time_base', '1:30',
                 '-maxrate', '3500k', '-bufsize', '7000k', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le',
                 '-ac', '2', '-ar', '48000', '-video_track_timescale', '90000', str(segment)])
            segment_info = probe(segment)
            segment_video = next(s for s in segment_info['streams'] if s['codec_type'] == 'video')
            segment_audio = next(s for s in segment_info['streams'] if s['codec_type'] == 'audio')
            assert int(segment_video['nb_frames']) == frame_count, (take, segment_video)
            assert abs(float(segment_video['duration']) - frame_count / 30) < .00001, (take, segment_video)
            assert abs(float(segment_audio['duration']) - frame_count / 30) < .001, (take, segment_audio)
        offset_frames += frame_count

    offset = offset_frames / 30

    srt = '\n\n'.join(f"{index}\n{stamp(cue['start'])} --> {stamp(cue['end'])}\n" +
                        ('（内心）' if '内心' in cue['speaker'] else '') + cue['text'] for index, cue in enumerate(captions, 1)) + '\n'
    (OUT / 'sui-ai-gym.srt').write_text(srt, encoding='utf-8')
    ass = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sui,Microsoft YaHei,33,&H00EEF2FF,&H000000FF,&H00181924,&H80000000,-1,0,0,0,100,100,0,0,1,2.4,1,2,60,60,40,1
Style: Nanami,Microsoft YaHei,33,&H00FFF2D0,&H000000FF,&H00181924,&H80000000,-1,0,0,0,100,100,0,0,1,2.4,1,2,60,60,40,1
Style: Inner,Microsoft YaHei,30,&H00EEC1FE,&H000000FF,&H00181924,&H80000000,-1,0,0,0,100,100,0,0,1,2.4,1,2,60,60,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    for cue in captions:
        style = 'Inner' if '内心' in cue['speaker'] else 'Nanami' if cue['speaker'] == '七海' else 'Sui'
        line = ('（内心）' if '内心' in cue['speaker'] else '') + cue['text']
        if len(line) > 33:
            line = line.replace('，', '，\\N', 1)
        ass += f"Dialogue: 0,{stamp(cue['start'],True)},{stamp(cue['end'],True)},{style},,0,0,0,,{line}\n"
    (OUT / 'sui-ai-gym.ass').write_text(ass, encoding='utf-8')
    timeline = {'duration': offset, 'frameCount': offset_frames, 'fps': 30, 'size': [1280,720], 'chapters': chapters, 'subtitles': captions,
                'dialogueCueCount': len(captions)}
    (OUT / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.render:
        concat = '\n'.join("file '" + path.as_posix().replace("'", "'\\''") + "'" for path in segments)
        (EDIT / 'concat.txt').write_text(concat, encoding='utf-8')
        meta = ';FFMETADATA1\n'
        for chapter in chapters:
            meta += f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={round(chapter['start']*1000)}\nEND={round((chapter['start']+chapter['duration'])*1000)}\ntitle={chapter['title']}\n"
        (EDIT / 'chapters.txt').write_text(meta, encoding='utf-8')
        clean = OUT / 'sui-ai-gym-clean.mp4'
        final = OUT / PLAN['assembly']['file']
        run(['ffmpeg','-v','warning','-y','-f','concat','-safe','0','-i',str(EDIT/'concat.txt'),
             '-i',str(EDIT/'chapters.txt'),'-map_metadata','1','-map_chapters','1','-c:v','copy',
             '-c:a','aac','-b:a','160k','-movflags','+faststart',str(clean)])
        run(['ffmpeg','-v','warning','-y','-i',clean.name,'-vf','ass=sui-ai-gym.ass','-c:v','libx264','-preset','medium',
             '-r','30','-fps_mode','cfr','-enc_time_base','1:30',
             '-crf','19','-maxrate','3500k','-bufsize','7000k','-pix_fmt','yuv420p','-c:a','copy',
             '-movflags','+faststart',final.name],cwd=OUT)
        run(['ffmpeg','-v','error','-y','-ss',str(chapters[3]['start']+7),'-i',str(final),'-frames:v','1',str(OUT/'poster.jpg')])
        facts = {'file': str(final), 'bytes': final.stat().st_size, 'sha256': hashlib.sha256(final.read_bytes()).hexdigest(),
                 'probe': probe(final), 'timelineDuration': offset, 'dialogueCueCount': len(captions)}
        (OUT/'delivery.json').write_text(json.dumps(facts, ensure_ascii=False, indent=2),encoding='utf-8')
        jumps = ''.join(f'<button data-time="{c["start"]:.3f}">{html.escape(c["title"])}</button>' for c in chapters)
        page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI从业者遇到健身教练</title>
<style>body{{margin:0;background:#151b22;color:#f5f2ec;font:16px/1.6 "Microsoft YaHei",sans-serif}}main{{max-width:1100px;margin:38px auto;padding:0 24px}}h1{{font-size:28px;margin-bottom:8px}}p{{color:#bdc8d6}}video{{width:100%;border-radius:12px;background:#000}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}}button,a{{background:#293443;color:#e5efff;border:0;border-radius:7px;padding:8px 12px;text-decoration:none;cursor:pointer}}a{{display:inline-block;margin:4px}}button:hover,a:hover{{background:#40516a}}</style>
<main><h1>AI从业者遇到健身教练</h1><p>岁己 × 七海 · 健身房轻喜剧 · {offset:.0f}秒</p>
<video id="film" controls playsinline preload="metadata" poster="poster.jpg"><source src="{final.name}" type="video/mp4"></video>
<nav>{jumps}</nav><a href="{final.name}" download>下载带字幕成片</a><a href="{clean.name}" download>下载无字幕版</a><a href="sui-ai-gym.srt" download>下载字幕</a></main>
<script>document.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>{{film.currentTime=Number(b.dataset.time);film.play()}})</script></html>'''
        (OUT/'review.html').write_text(page,encoding='utf-8')
        print(json.dumps({k:facts[k] for k in ['file','bytes','sha256','timelineDuration','dialogueCueCount']},ensure_ascii=False))
    else:
        print(json.dumps(timeline, ensure_ascii=False))
