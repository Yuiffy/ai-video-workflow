"""Add quiet music and sparse comedy effects to the approved CosyVoice cut.

All media and the downloaded assets manifest stay under the ignored output
directory. The existing movies, subtitles and voice repair are never overwritten.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d, minimum_filter1d, uniform_filter1d

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/sui-ai-gym-20261012'
WORK = OUT / 'sound-design'
SR = 48000
HOP = 480

# Source ranges are seconds in the actual downloaded sounds. Laughs are short
# excerpts, with a different part of the audience recording at each punchline.
EVENTS = [
    dict(time=13.08, asset='failure-piano', source=[0, 1.8], speed=1.2,
         rms_db=-30, peak_db=-19, fade_out=.25, label='硬接 harness 后的心虚'),
    dict(time=23.48, asset='sad-trombone', source=[0, 2.45], speed=1.12,
         rms_db=-29, peak_db=-18, fade_out=.20, label='Claude 在中国没有研发：露馅'),
    dict(time=27.83, asset='crowd-laugh', source=[.12, 1.47],
         rms_db=-31, peak_db=-21, fade_out=.35, label='我是远程的：补救后的罐头笑声'),
    dict(time=32.02, asset='pop', source=[0, .22],
         rms_db=-32, peak_db=-19, fade_out=.06, label='免费用户被问到新模型'),
    dict(time=38.77, asset='crowd-laugh', source=[1.30, 2.65],
         rms_db=-31, peak_db=-21, fade_out=.35, label='Astra 答案后的轻笑'),
    dict(time=47.22, asset='boing', source=[0, .46], speed=1.1,
         rms_db=-29, peak_db=-18, fade_out=.12, label='站起来蹬？误会弹簧'),
    dict(time=57.14, asset='pop', source=[0, .22],
         rms_db=-32, peak_db=-20, fade_out=.06, label='推特上看的那个：误会升级'),
    dict(time=68.47, asset='audience-laugh-applause', source=[.48, 2.38],
         rms_db=-32, peak_db=-22, fade_out=.50, label='制作视频卖钱：观众短笑声'),
    dict(time=74.64, asset='pop', source=[0, .22],
         rms_db=-33, peak_db=-21, fade_out=.06, label='来我家看看：邀请落点'),
    dict(time=81.63, asset='crowd-laugh', source=[.20, 1.55],
         rms_db=-33, peak_db=-23, fade_out=.40, label='那……好呀：收尾轻笑'),
]


def run(args: list) -> str:
    p = subprocess.run([str(a) for a in args], check=True, capture_output=True,
                       encoding='utf-8', errors='replace')
    return p.stdout


def digest(path: Path) -> str:
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def db(value: float) -> float:
    return 10 ** (value / 20)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x), dtype=np.float64)))


def grid_rms(x: np.ndarray, count: int) -> np.ndarray:
    """Centered 410 ms energy; curves run at 100 Hz, audio stays at 48 kHz."""
    padded = np.pad(x, ((0, count * HOP - len(x)), (0, 0)))
    energy = np.mean(padded.reshape(count, HOP, 2) ** 2, axis=(1, 2))
    return np.sqrt(np.maximum(0, uniform_filter1d(energy, 41, mode='nearest')))


def expand(curve: np.ndarray, count: int) -> np.ndarray:
    return np.interp(np.arange(count), np.arange(len(curve)) * HOP, curve)


def presence_curve(times: np.ndarray, intervals: list) -> np.ndarray:
    curve = np.zeros(len(times))
    for start, end in intervals:
        attack = np.clip((times - (start - .18)) / .18, 0, 1)
        release = np.clip((end + .38 - times) / .38, 0, 1)
        local = np.minimum(attack, release)
        curve = np.maximum(curve, .5 - .5 * np.cos(np.pi * local))
    return curve


def duck_guard(track: np.ndarray, voice_rms: np.ndarray, presence: np.ndarray,
               separation_db: float, count: int) -> np.ndarray:
    track_rms = grid_rms(track, count)
    guard = np.ones(count)
    speaking = presence > .9
    guard[speaking] = np.minimum(
        1, voice_rms[speaking] * db(-separation_db) /
        np.maximum(track_rms[speaking], 1e-8))
    # Anticipate quiet syllables and recover gently; never raise a constrained gain.
    guard = np.minimum(guard, gaussian_filter1d(
        minimum_filter1d(guard, 31, mode='nearest'), 4, mode='nearest'))
    return track * expand(guard, len(track))[:, None]


def fade(x: np.ndarray, fade_in: float = .01, fade_out: float = .15) -> np.ndarray:
    x = x.copy()
    for seconds, at_end in [(fade_in, False), (fade_out, True)]:
        n = min(len(x) // 2, round(seconds * SR))
        if n:
            ramp = .5 - .5 * np.cos(np.linspace(0, np.pi, n))
            if at_end:
                x[-n:] *= ramp[::-1, None]
            else:
                x[:n] *= ramp[:, None]
    return x


def loudness(path: Path) -> dict:
    p = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path),
                        '-af', 'loudnorm=I=-18:TP=-1.5:LRA=20:print_format=json',
                        '-f', 'null', '-'], check=True, capture_output=True,
                       encoding='utf-8', errors='replace')
    match = re.search(r'\{\s*"input_i".*?\}', p.stderr, re.S)
    if match is None:
        raise RuntimeError('FFmpeg did not return loudness measurements')
    return json.loads(match.group())


def main() -> None:
    WORK.mkdir(exist_ok=True)
    (WORK / 'stems').mkdir(exist_ok=True)
    (WORK / 'prepared').mkdir(exist_ok=True)
    timeline = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
    previous = json.loads((OUT / 'nanami-voice-repair/final-verification.json')
                          .read_text(encoding='utf-8'))
    assets = json.loads((WORK / 'assets.json').read_text(encoding='utf-8'))
    asset_by_id = {a['id']: a for a in assets}
    for item in assets:
        path = WORK / item['file']
        assert digest(path) == item['sha256'], f"Asset changed: {item['id']}"

    voice_path = OUT / 'nanami-voice-repair/cosy_ready_trimmed-mix.wav'
    voice, rate = sf.read(voice_path, dtype='float32', always_2d=True)
    assert rate == SR and voice.shape == (4358400, 2)
    sample_count = len(voice)
    duration = sample_count / SR
    grid_count = (sample_count + HOP - 1) // HOP
    times = np.arange(grid_count) * HOP / SR
    chapter_start = {c['scene']: c['start'] for c in timeline['chapters']}
    intervals = [[c['start'], c['end']] for c in timeline['subtitles']]
    for chapter in previous['dialogue_checks']:
        offset = chapter_start[chapter['chapter']]
        intervals += [[offset + s['start'], offset + s['end']]
                      for s in chapter['segments']]
    presence = presence_curve(times, intervals)
    voice_rms = grid_rms(voice, grid_count)

    music_path = WORK / 'prepared/music-eq.wav'
    run(['ffmpeg', '-v', 'error', '-y', '-i', WORK / asset_by_id['bgm']['file'],
         '-t', duration, '-af',
         'highpass=f=110,lowpass=f=6500,equalizer=f=1800:t=q:w=0.8:g=-3',
         '-ar', SR, '-ac', 2, '-c:a', 'pcm_f32le', music_path])
    music, rate = sf.read(music_path, dtype='float32', always_2d=True)
    assert rate == SR and len(music) >= sample_count
    music = music[:sample_count]
    music /= max(rms(music), 1e-8)
    # Absolute RMS targets before the additional protection for quiet dialogue.
    music_db = -32.5 - 6.0 * presence
    intro = times < 2.1
    music_db[intro] = np.maximum(music_db[intro], -31.0 - 7.5 * presence[intro])
    ending = np.clip((times - 83.2) / 1.6, 0, 1)
    music_db = music_db * (1 - ending) + (-29.5) * ending
    music *= expand(10 ** (music_db / 20), sample_count)[:, None]
    # Make the reveal breathe: dip the tune around the sad trombone.
    reveal = presence_curve(times, [[23.36, 25.45]])
    music *= expand(1 - .82 * reveal, sample_count)[:, None]
    music = duck_guard(music, voice_rms, presence, 19.0, grid_count)
    music = fade(music, .85, 2.40)

    effects = np.zeros_like(voice)
    events = []
    for i, event in enumerate(EVENTS):
        clip_path = WORK / f'prepared/effect-{i:02d}.wav'
        filters = [f"atempo={event.get('speed', 1)}", 'highpass=f=100', 'lowpass=f=8000']
        run(['ffmpeg', '-v', 'error', '-y', '-ss', event['source'][0],
             '-t', event['source'][1] - event['source'][0],
             '-i', WORK / asset_by_id[event['asset']]['file'],
             '-af', ','.join(filters), '-ar', SR, '-ac', 2,
             '-c:a', 'pcm_f32le', clip_path])
        clip, rate = sf.read(clip_path, dtype='float32', always_2d=True)
        assert rate == SR
        gain = min(db(event['rms_db']) / max(rms(clip), 1e-8),
                   db(event['peak_db']) / max(float(np.abs(clip).max()), 1e-8))
        clip = fade(clip * gain, .008 if event['asset'] == 'pop' else .025,
                    event['fade_out'])
        start = round(event['time'] * SR)
        end = min(sample_count, start + len(clip))
        effects[start:end] += clip[:end - start]
        events.append({**event, 'end': end / SR, 'clip_gain_db':
                       round(20 * np.log10(gain), 3)})
    effects *= expand(10 ** (-13 * presence / 20), sample_count)[:, None]
    effects = duck_guard(effects, voice_rms, presence, 15.0, grid_count)
    mixed = voice + music + effects

    for name, track in [('dialogue', voice), ('music', music), ('effects', effects),
                        ('premaster', mixed)]:
        sf.write(WORK / f'stems/{name}.wav', track, SR, subtype='FLOAT')
    measured = loudness(WORK / 'stems/premaster.wav')
    # Apply only a constant master gain. This retains the approved voice dynamics.
    # A second true-peak measurement verifies that no limiter or clipping is needed.
    gain_db = min(-18.0 - float(measured['input_i']),
                  -1.6 - float(measured['input_tp']))
    master = mixed * db(gain_db)
    assert float(np.abs(master).max()) < db(-1.5)
    master_path = WORK / 'master.wav'
    sf.write(master_path, master, SR, subtype='PCM_24')
    final_loudness = loudness(master_path)
    assert float(final_loudness['input_tp']) <= -1.5

    movies = []
    for source_name, target_name in [
        ('sui-ai-gym-nanami-cosy.mp4', 'sui-ai-gym-bilibili-ready.mp4'),
        ('sui-ai-gym-nanami-cosy-clean.mp4', 'sui-ai-gym-bilibili-ready-clean.mp4'),
    ]:
        run(['ffmpeg', '-v', 'error', '-y', '-i', OUT / source_name,
             '-i', master_path, '-map', '0:v:0', '-map', '1:a:0',
             '-map_metadata', '0', '-map_chapters', '0', '-c:v', 'copy',
             '-c:a', 'aac', '-b:a', '256k', '-ar', SR, '-ac', 2,
             '-t', duration, '-movflags', '+faststart', OUT / target_name])
        movies.append(dict(source=source_name, file=target_name,
                           bytes=(OUT / target_name).stat().st_size,
                           sha256=digest(OUT / target_name)))

    report = dict(duration=duration, sample_rate=SR, channels=2,
                  approved_voice_sha256=digest(voice_path),
                  speech_intervals=intervals, effect_events=events,
                  music=dict(asset='bgm', speech_rms_target_dbfs=-38.5,
                             pause_rms_target_dbfs=-32.5,
                             end_rms_target_dbfs=-29.5,
                             speech_minimum_separation_db=19.0,
                             fade_in=.85, fade_out=2.4),
                  effects_speech_minimum_separation_db=15.0,
                  master_gain_db=round(gain_db, 4),
                  master_loudness=final_loudness, files=movies,
                  video_encoder='copy', added_dreamina_credits=0,
                  voice_regenerated=False, uploaded=False)
    (WORK / 'edit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding='utf-8')
    print(json.dumps(dict(files=movies, effect_count=len(events),
                          master_gain_db=report['master_gain_db'],
                          loudness_lufs=final_loudness['input_i'],
                          true_peak_dbtp=final_loudness['input_tp']),
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
