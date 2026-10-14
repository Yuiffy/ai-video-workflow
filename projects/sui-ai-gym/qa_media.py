"""Inspect generated frames, audio streams and spoken dialogue."""
from pathlib import Path
import argparse
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(Path(__file__).with_name('production-plan.json').read_text(encoding='utf-8'))
OUT = ROOT / PLAN['output']
QA = OUT / 'qa'
QA.mkdir(exist_ok=True)

def run(command):
    return subprocess.run(command, check=True, capture_output=True, encoding='utf-8', errors='replace').stdout

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('keys', nargs='*')
    p.add_argument('--no-asr', action='store_true')
    args = p.parse_args()
    scenes = [s for s in PLAN['scenes'] + PLAN.get('repairs', []) if not args.keys or s['id'] in args.keys]
    model = None
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 20)
    for scene in scenes:
        key = scene['id']
        source = OUT / (key + '-raw.mp4')
        if not source.exists():
            continue
        info = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)]))
        duration = float(info['format']['duration'])
        video = next(s for s in info['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in info['streams'] if s['codec_type'] == 'audio')
        stamps = [0.12, duration * .22, duration * .47, duration * .72, duration - .14]
        sheet = Image.new('RGB', (640 * 3, 390 * 2), '#192128')
        draw = ImageDraw.Draw(sheet)
        for index, sec in enumerate(stamps):
            target = QA / f'{key}-{index}.jpg'
            if not target.exists():
                run(['ffmpeg', '-v', 'error', '-y', '-ss', str(sec), '-i', str(source), '-frames:v', '1', '-q:v', '2', str(target)])
            frame = Image.open(target).convert('RGB').resize((640, 360))
            x, y = (index % 3) * 640, (index // 3) * 390
            sheet.paste(frame, (x, y))
            draw.text((x + 12, y + 364), f'{key} · {sec:.2f}s', font=font, fill='#f8f6ed')
        sheet.save(QA / (key + '-sheet.jpg'), quality=92)
        wav = QA / (key + '.wav')
        if not wav.exists():
            run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', str(wav)])
        asr_file = QA / (key + '-asr.json')
        if not args.no_asr and not asr_file.exists():
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2', device='cuda', compute_type='float16', local_files_only=True)
            segments, _ = model.transcribe(str(wav), language='zh', word_timestamps=True, vad_filter=True, beam_size=5,
                                            condition_on_previous_text=False, hallucination_silence_threshold=1.0,
                                            initial_prompt='岁己、七海。AI，大模型训练，harness开发。MiniMax、智谱、Claude。GPT、Gemini、Astra。Tibo，重置，站起来蹬。推特。MiniMax H3。')
            speech = [{'start': s.start, 'end': s.end, 'text': s.text,
                       'words': [{'start': w.start, 'end': w.end, 'word': w.word} for w in s.words]} for s in segments]
            asr_file.write_text(json.dumps(speech, ensure_ascii=False, indent=2), encoding='utf-8')
        speech = json.loads(asr_file.read_text(encoding='utf-8')) if asr_file.exists() else None
        result = {'scene': key, 'duration': duration, 'width': video['width'], 'height': video['height'],
                  'fps': video['r_frame_rate'], 'audioCodec': audio['codec_name'], 'audioDuration': audio.get('duration'),
                  'dialogue': [{'start': s['start'], 'end': s['end'], 'text': s['text']} for s in speech or []]}
        (QA / (key + '-media.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False), flush=True)
