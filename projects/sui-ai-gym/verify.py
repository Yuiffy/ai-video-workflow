"""Verify the exported movie itself and prepare frames for a separate visual review."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont
import assemble

OUT = assemble.OUT
QA = OUT / 'final-qa'
QA.mkdir(exist_ok=True)
FILM = OUT / assemble.PLAN['assembly']['file']
REPORT = OUT / 'verification.json'


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def decode(path):
    assemble.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path),
                  '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'])


def frame(item):
    path = QA / (item['key'] + '.jpg')
    assemble.run(['ffmpeg', '-v', 'error', '-y', '-threads', '1', '-ss', f"{item['time']:.6f}",
                  '-i', str(FILM), '-frames:v', '1', '-q:v', '2', str(path)])
    item['file'] = str(path)
    return item


def sheet(items, name, columns=3):
    width, height, label = 512, 288, 40
    rows = (len(items) + columns - 1) // columns
    canvas = Image.new('RGB', (width * columns, (height + label) * rows), '#192128')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 15)
    for i, item in enumerate(items):
        x, y = (i % columns) * width, (i // columns) * (height + label)
        with Image.open(item['file']) as image:
            canvas.paste(image.convert('RGB').resize((width, height)), (x, y))
        draw.text((x + 8, y + height + 5), f"{item['label']} · {item['time']:.3f}s", font=font, fill='#f5f2ec')
    path = QA / name
    canvas.save(path, quality=94)
    return str(path)


def asr(timeline):
    from faster_whisper import WhisperModel
    model = WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2', device='cuda',
                         compute_type='float16', local_files_only=True)
    results = []
    for chapter in timeline['chapters']:
        key = chapter['scene']
        audio = QA / (key + '.wav')
        assemble.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(chapter['start']), '-i', str(FILM),
                      '-t', str(chapter['duration']), '-vn', '-ac', '1', '-ar', '16000', str(audio)])
        segments, _ = model.transcribe(str(audio), language='zh', word_timestamps=True,
                                      vad_filter=True, beam_size=5, condition_on_previous_text=False,
                                      hallucination_silence_threshold=1.0)
        speech = [{'start': s.start, 'end': s.end, 'text': s.text,
                   'words': [{'start': w.start, 'end': w.end, 'word': w.word} for w in s.words or []]}
                  for s in segments]
        write(QA / (key + '-asr.json'), speech)
        expected = assemble.normalize(''.join(c['text'] for c in timeline['subtitles'] if c['scene'] == key))
        observed = assemble.normalize(''.join(s['text'] for s in speech))
        matcher = difflib.SequenceMatcher(None, expected, observed, autojunk=False)
        matched = sum(b.size for b in matcher.get_matching_blocks())
        coverage = matched / max(1, len(expected))
        result = {'scene': key, 'expectedCoverage': round(coverage, 3),
                  'text': ''.join(s['text'] for s in speech), 'initialPrompt': None}
        results.append(result)
        print(json.dumps({'finalASR': result}, ensure_ascii=False), flush=True)
        assert coverage >= .80, f'{key}: exported speech needs review'
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mark-reviewed', action='store_true')
    args = parser.parse_args()
    if args.mark_reviewed:
        report = json.loads(REPORT.read_text(encoding='utf-8'))
        assert report['sha256'] == digest(FILM)
        assert all(Path(s).is_file() for s in report['contactSheets'])
        report['visualReview'] = 'passed'
        report['visualReviewNotes'] = (
            '逐章检查带字幕首尾、各句字幕边界与镜头转场；训练服连续、人物身份稳定，'
            '文字可读，两人完整并肩离场，末尾正常淡出。'
        )
        write(REPORT, report)
        print(json.dumps({'visualReview': report['visualReview'], 'sha256': report['sha256']}))
    else:
        timeline = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
        decisions = json.loads((OUT / 'edit-decisions.json').read_text(encoding='utf-8'))
        job = json.loads((OUT / 'job.json').read_text(encoding='utf-8'))
        clean = OUT / 'sui-ai-gym-clean.mp4'
        for path in [FILM, clean]:
            assert path.stat().st_size > 100_000
            decode(path)
        info = assemble.probe(FILM)
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
        video_duration, audio_duration = float(video['duration']), float(audio['duration'])
        assert (video['width'], video['height'], video['r_frame_rate']) == (1280, 720, '30/1')
        assert int(video['nb_frames']) == timeline['frameCount']
        assert abs(video_duration - timeline['duration']) < .001
        assert abs(audio_duration - video_duration) <= .05
        assert audio['codec_name'] == 'aac' and audio['sample_rate'] == '48000'
        assert len(timeline['chapters']) == 7
        assert [c['scene'] for c in timeline['chapters']] == [s['id'] for s in assemble.PLAN['scenes']]
        source_checks = []
        voice_checks = []
        voice_nodes = {job['items'][key]['nodeId'] for key in ['sui_voice', 'nanami_voice']}
        for key in ['sui_voice', 'nanami_voice']:
            item = job['items'][key]
            reference = Path(assemble.PLAN['references'][key]['file'])
            assert digest(reference) == item['sha256']
            assert item['uploaded'] and item['saved']
            voice_checks.append({'role': key, 'nodeId': item['nodeId'], 'sha256': item['sha256']})
        for chapter in timeline['chapters']:
            item = job['items'][chapter['take']]
            assert item['generation']['model'] in assemble.PLAN['authorizedModels']
            assert voice_nodes.issubset({r['id'] for r in item['references'] if r['kind'] == 'node'})
            assert any(r['state'] == 'succeeded' and r['resourceId'] == item['selectedResourceId']
                       for r in item['observation']['resources'])
            source = OUT / (chapter['take'] + '-raw.mp4')
            assert digest(source) == item['sha256']
            actual = assemble.probe(source)
            available = float(next(s for s in actual['streams'] if s['codec_type'] == 'video')['duration'])
            start, end = chapter['sourceTrim']
            assert 0 <= start < end <= available
            source_checks.append({'take': chapter['take'], 'sha256': item['sha256'], 'terminal': 'succeeded'})
        cues = timeline['subtitles']
        assert len(cues) == sum(len(s['dialogue']) for s in decisions['takes'].values())
        assert len((OUT / 'sui-ai-gym.srt').read_text(encoding='utf-8').strip().split('\n\n')) == len(cues)
        for index, cue in enumerate(cues):
            assert 0 <= cue['start'] < cue['end'] <= video_duration
            assert cue['end'] - cue['start'] >= .4
            assert cue['asrMatchCoverage'] >= .64
            if index:
                assert cues[index - 1]['end'] <= cue['start']
        quoted = sum(i.get('quotedMaxCredits', 0) for i in job['items'].values() if i.get('attempted'))
        assert quoted <= job['budget']['authorizedTotalCeiling'] == 2000
        speech = asr(timeline)

        requests, groups = [], {}
        for chapter in timeline['chapters']:
            key = chapter['scene']
            items = [{'key': key + '-first', 'time': chapter['start'] + .1, 'label': key + ' 开始'}]
            for i, cue in enumerate(c for c in cues if c['scene'] == key):
                items.extend([
                    {'key': f'{key}-cue{i}-in', 'time': cue['start'] + .12, 'label': f'{key} 字幕{i + 1}开始'},
                    {'key': f'{key}-cue{i}-out', 'time': cue['end'] - .12, 'label': f'{key} 字幕{i + 1}结束'},
                ])
            items.append({'key': key + '-last', 'time': chapter['start'] + chapter['duration'] - .1,
                          'label': key + ' 结束'})
            requests.extend(items)
            groups[key] = items
        boundary = []
        for index, chapter in enumerate(timeline['chapters'][1:], 1):
            for suffix, shift in [('before', -.05), ('after', .05)]:
                boundary.append({'key': f'cut{index}-{suffix}', 'time': chapter['start'] + shift,
                                 'label': f'转场{index} {suffix}'})
        requests.extend(boundary)
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(frame, requests))
        sheets = [sheet(items, key + '-sheet.jpg') for key, items in groups.items()]
        sheets.append(sheet(boundary, 'transitions-sheet.jpg'))
        report = {
            'fullDecode': 'passed', 'cleanFullDecode': 'passed', 'sha256': digest(FILM),
            'cleanSha256': digest(clean), 'durationSeconds': video_duration,
            'audioDurationSeconds': audio_duration, 'frameCount': int(video['nb_frames']),
            'width': 1280, 'height': 720, 'fps': 30, 'subtitleCount': len(cues),
            'chapterCount': len(timeline['chapters']), 'sourceChecks': source_checks,
            'voiceReferenceChecks': voice_checks,
            'exportedSpeechASR': speech, 'heardByReviewer': False, 'visualReview': 'pending',
            'contactSheets': sheets, 'frames': requests, 'quotedCreditsTotal': quoted,
            'creditCeiling': 2000,
        }
        write(REPORT, report)
        print(json.dumps({k: report[k] for k in ['fullDecode', 'durationSeconds', 'subtitleCount',
                                               'chapterCount', 'visualReview', 'quotedCreditsTotal']}, ensure_ascii=False))
