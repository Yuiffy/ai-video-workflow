"""Check the exported sound-design movies and their actual encoded dialogue."""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from sound_design import OUT, WORK, digest, loudness, run
from verify_voice_repair import normalize


def normalize_dialogue(text):
    # Whisper renders the same uncommon name / Mandarin syllables differently
    # with background music. Keep raw transcripts in the report for inspection.
    for old, new in [('启波', 'Tibo'), ('站起来灯', '站起来蹬'),
                     ('灯天哪', '蹬天哪')]:
        text = text.replace(old, new)
    return normalize(text)


def energy_windows(x, sr):
    # Independent 400 ms measurements, advancing every 100 ms.
    hop = sr // 10
    n = len(x) // hop
    energy = np.mean(x[:n * hop].reshape(n, hop, 2) ** 2, axis=(1, 2))
    return np.sqrt(np.convolve(energy, np.ones(4) / 4, mode='valid'))


def main():
    global WORK
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=['comedy', 'flirty'], default='comedy')
    args = parser.parse_args()
    if args.variant == 'flirty':
        WORK = OUT / 'sound-design-flirty'
    edit = json.loads((WORK / 'edit.json').read_text(encoding='utf-8'))
    timeline = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
    original, sr = sf.read(OUT / 'nanami-voice-repair/cosy_ready_trimmed-mix.wav',
                            dtype='float32', always_2d=True)
    voice, vsr = sf.read(WORK / 'stems/dialogue.wav', dtype='float32', always_2d=True)
    assert sr == vsr == 48000 and np.array_equal(original, voice)
    music, msr = sf.read(WORK / 'stems/music.wav', dtype='float32', always_2d=True)
    effects, esr = sf.read(WORK / 'stems/effects.wav', dtype='float32', always_2d=True)
    premaster, psr = sf.read(WORK / 'stems/premaster.wav', dtype='float32', always_2d=True)
    assert msr == esr == psr == sr
    assert music.shape == effects.shape == premaster.shape == voice.shape
    demix_delta = float(np.abs(premaster - music - effects - voice).max())
    assert demix_delta < 1e-6
    master, master_sr = sf.read(WORK / 'master.wav', dtype='float32', always_2d=True)
    assert master_sr == sr and master.shape == voice.shape
    assert float(np.abs(master).max()) < 1

    voice_rms = energy_windows(voice, sr)
    music_rms = energy_windows(music, sr)
    effects_rms = energy_windows(effects, sr)
    speech = np.zeros(len(voice), dtype=np.float32)
    for start, end in edit['speech_intervals']:
        speech[round(start * sr):round(end * sr)] = 1
    hop = sr // 10
    speech_blocks = speech[:len(voice) // hop * hop].reshape(-1, hop).mean(axis=1)
    speech_coverage = np.convolve(speech_blocks, np.ones(4) / 4, mode='valid')
    valid = (speech_coverage > .98) & (voice_rms > 10 ** (-38 / 20))
    margin = 20 * np.log10(voice_rms[valid] / np.maximum(music_rms[valid], 1e-8))
    assert np.percentile(margin, 1) >= 18
    audible_effects = valid & (effects_rms > 10 ** (-65 / 20))
    effect_margin = 20 * np.log10(voice_rms[audible_effects] /
                                 np.maximum(effects_rms[audible_effects], 1e-8))
    assert len(effect_margin) == 0 or np.percentile(effect_margin, 1) >= 14
    qa = WORK / 'qa'
    qa.mkdir(exist_ok=True)
    reports = []
    for item in edit['files']:
        movie = OUT / item['file']
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', movie,
             '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'])
        probe = json.loads(run(['ffprobe', '-v', 'error', '-show_format',
                               '-show_streams', '-of', 'json', movie]))
        video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
        assert (video['width'], video['height'], video['r_frame_rate']) == (1280, 720, '30/1')
        assert video['codec_name'] == 'h264' and audio['codec_name'] == 'aac'
        assert int(video['nb_frames']) == 2724
        assert abs(float(video['duration']) - 90.8) < .001
        assert abs(float(audio['duration']) - 90.8) < .025
        hashes = [run(['ffmpeg', '-v', 'error', '-i', OUT / name,
                       '-map', '0:v:0', '-c:v', 'copy', '-f', 'streamhash',
                       '-hash', 'sha256', '-']).strip()
                  for name in [item['source'], item['file']]]
        assert hashes[0] == hashes[1]
        decoded = qa / f"{Path(item['file']).stem}-decoded.wav"
        run(['ffmpeg', '-v', 'error', '-y', '-i', movie, '-vn', '-ac', 2,
             '-ar', sr, '-c:a', 'pcm_f32le', decoded])
        encoded_audio, encoded_sr = sf.read(decoded, dtype='float32', always_2d=True)
        encoded_loudness = loudness(decoded)
        assert encoded_sr == sr
        assert float(np.abs(encoded_audio).max()) < 1
        assert float(encoded_loudness['input_tp']) <= -.5
        reports.append(dict(file=item['file'], sha256=digest(movie), full_decode='passed',
                            video_matches_approved=True, video_stream_hash=hashes[1],
                            frames=int(video['nb_frames']), video_seconds=float(video['duration']),
                            audio_seconds=float(audio['duration']), audio_codec=audio['codec_name'],
                            sample_rate=int(audio['sample_rate']),
                            integrated_lufs=float(encoded_loudness['input_i']),
                            true_peak_dbtp=float(encoded_loudness['input_tp'])))

    from faster_whisper import WhisperModel
    model = WhisperModel('deepdml/faster-whisper-large-v3-turbo-ct2', device='cuda',
                         compute_type='float16', local_files_only=True)
    checks = []
    for chapter in timeline['chapters']:
        wav = qa / f"{chapter['scene']}.wav"
        run(['ffmpeg', '-v', 'error', '-y', '-ss', chapter['start'],
             '-i', OUT / edit['files'][0]['file'], '-t', chapter['duration'],
             '-vn', '-ac', 1, '-ar', 16000, wav])
        segments, _ = model.transcribe(str(wav), language='zh', beam_size=5,
                                      vad_filter=True, condition_on_previous_text=False,
                                      hallucination_silence_threshold=1)
        observed = ''.join(s.text for s in segments)
        expected = ''.join(c['text'] for c in timeline['subtitles']
                           if c['scene'] == chapter['scene'])
        a, b = normalize_dialogue(expected), normalize_dialogue(observed)
        match = difflib.SequenceMatcher(None, a, b, autojunk=False)
        coverage = sum(m.size for m in match.get_matching_blocks()) / max(1, len(a))
        result = dict(chapter=chapter['scene'], expected=expected, observed=observed,
                      coverage=round(coverage, 3), initial_prompt=None)
        checks.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        assert coverage >= .82, f"Dialogue needs review: {chapter['scene']}"
    report = dict(files=reports, original_voice_samples_unchanged=True,
                  demixed_voice_max_delta=demix_delta,
                  master_gain_db=edit['master_gain_db'],
                  bgm_to_dialogue_400ms_margin_db=dict(
                      minimum=round(float(margin.min()), 2),
                      percentile_1=round(float(np.percentile(margin, 1)), 2),
                      median=round(float(np.median(margin)), 2),
                      measured_windows=int(valid.sum())),
                  effects_during_speech_margin_db=dict(
                      percentile_1=round(float(np.percentile(effect_margin, 1)), 2)
                      if len(effect_margin) else None,
                      measured_windows=int(audible_effects.sum())),
                  effect_count=len(edit['effect_events']), dialogue_checks=checks,
                  human_listening_review=False,
                  note='Level checks and ASR validate the export; voice likeness was approved by the user.',
                  added_dreamina_credits=0, uploaded=False)
    (WORK / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'dialogue_checks'},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
