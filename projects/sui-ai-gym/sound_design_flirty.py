"""Crossfade the latter half into slow saxophone music, retaining the approved cut."""
from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from sound_design import (OUT, WORK as COMEDY_WORK, SR, HOP, db, digest,
                          duck_guard, expand, fade, grid_rms, loudness,
                          presence_curve, rms, run)

WORK = OUT / 'sound-design-flirty'
TRANSITION_START = 53.7
TRANSITION_LENGTH = 1.2
SOURCE_START = 16.0


def main():
    (WORK / 'prepared').mkdir(exist_ok=True)
    (WORK / 'stems').mkdir(exist_ok=True)
    old_edit = json.loads((COMEDY_WORK / 'edit.json').read_text(encoding='utf-8'))
    assets = json.loads((WORK / 'assets.json').read_text(encoding='utf-8'))
    for asset in assets:
        assert digest(WORK / asset['file']) == asset['sha256']
    sax = next(a for a in assets if a['id'] == 'bgm-flirty')
    voice, sr = sf.read(COMEDY_WORK / 'stems/dialogue.wav', dtype='float32', always_2d=True)
    old_music, msr = sf.read(COMEDY_WORK / 'stems/music.wav', dtype='float32', always_2d=True)
    effects, esr = sf.read(COMEDY_WORK / 'stems/effects.wav', dtype='float32', always_2d=True)
    assert sr == msr == esr == SR and voice.shape == old_music.shape == effects.shape
    samples = len(voice)
    duration = samples / SR
    count = (samples + HOP - 1) // HOP
    times = np.arange(count) * HOP / SR
    presence = presence_curve(times, old_edit['speech_intervals'])
    start = round(TRANSITION_START * SR)

    clip_path = WORK / 'prepared/mystery-sax-eq.wav'
    run(['ffmpeg', '-v', 'error', '-y', '-ss', SOURCE_START,
         '-i', WORK / sax['file'], '-t', duration - TRANSITION_START,
         '-af', 'highpass=f=110,lowpass=f=6500,equalizer=f=1800:t=q:w=0.8:g=-3',
         '-ar', SR, '-ac', 2, '-c:a', 'pcm_f32le', clip_path])
    clip, rate = sf.read(clip_path, dtype='float32', always_2d=True)
    assert rate == SR and len(clip) == samples - start
    clip /= max(rms(clip), 1e-8)
    romantic = np.zeros_like(voice)
    romantic[start:] = clip
    levels = -32.0 - 6.5 * presence
    ending = np.clip((times - 83.2) / 1.6, 0, 1)
    levels = levels * (1 - ending) + (-29.5) * ending
    romantic *= expand(10 ** (levels / 20), samples)[:, None]
    romantic = duck_guard(romantic, grid_rms(voice, count), presence, 19, count)
    romantic = fade(romantic, .01, 2.4)

    progress = np.clip((times - TRANSITION_START) / TRANSITION_LENGTH, 0, 1)
    music = old_music * expand(np.cos(progress * np.pi / 2), samples)[:, None]
    music += romantic * expand(np.sin(progress * np.pi / 2), samples)[:, None]
    music = duck_guard(music, grid_rms(voice, count), presence, 19, count)
    music[:start] = old_music[:start]
    assert np.array_equal(music[:start], old_music[:start])
    mixed = voice + music + effects
    for name, track in [('dialogue', voice), ('music', music), ('effects', effects),
                        ('premaster', mixed)]:
        sf.write(WORK / f'stems/{name}.wav', track, SR, subtype='FLOAT')
    measured = loudness(WORK / 'stems/premaster.wav')
    gain_db = min(-18 - float(measured['input_i']), -1.6 - float(measured['input_tp']))
    master = mixed * db(gain_db)
    assert float(np.abs(master).max()) < db(-1.5)
    master_path = WORK / 'master.wav'
    sf.write(master_path, master, SR, subtype='PCM_24')
    final_loudness = loudness(master_path)
    assert float(final_loudness['input_tp']) <= -1.5
    movies = []
    for source_name, target_name in [
        ('sui-ai-gym-nanami-cosy.mp4', 'sui-ai-gym-bilibili-flirty.mp4'),
        ('sui-ai-gym-nanami-cosy-clean.mp4', 'sui-ai-gym-bilibili-flirty-clean.mp4'),
    ]:
        run(['ffmpeg', '-v', 'error', '-y', '-i', OUT / source_name, '-i', master_path,
             '-map', '0:v:0', '-map', '1:a:0', '-map_metadata', '0', '-map_chapters', '0',
             '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-ar', SR, '-ac', 2,
             '-t', duration, '-movflags', '+faststart', OUT / target_name])
        movies.append(dict(source=source_name, file=target_name,
                           bytes=(OUT / target_name).stat().st_size,
                           sha256=digest(OUT / target_name)))
    report = {**old_edit, 'files': movies, 'master_gain_db': round(gain_db, 4),
              'master_loudness': final_loudness, 'variant': 'flirty',
              'music': {**old_edit['music'], 'assets': ['bgm', 'bgm-flirty'],
                        'transition_start': TRANSITION_START,
                        'transition_duration': TRANSITION_LENGTH,
                        'sax_source_start': SOURCE_START, 'sax_title': sax['title']},
              'first_half_music_samples_unchanged': True,
              'effects_samples_unchanged': True}
    (WORK / 'edit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                   encoding='utf-8')
    print(json.dumps(dict(files=movies, transition_start=TRANSITION_START,
                          sax=sax['title'], master_gain_db=gain_db,
                          loudness_lufs=final_loudness['input_i'],
                          true_peak_dbtp=final_loudness['input_tp']),
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
