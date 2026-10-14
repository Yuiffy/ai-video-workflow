"""Local, reversible Nanami dialogue replacement; never submits paid jobs."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/sui-ai-gym-20261012'
WORK = OUT / 'nanami-voice-repair'


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True,
                          encoding='utf-8', errors='replace').stdout


def prepare():
    WORK.mkdir(exist_ok=True)
    (WORK / 'source').mkdir(exist_ok=True)
    timeline = json.loads((OUT / 'timeline.json').read_text(encoding='utf-8'))
    chapters = {c['scene']: c for c in timeline['chapters']}
    cues = []
    for sub in timeline['subtitles']:
        if sub['speaker'] != '七海':
            continue
        ch = chapters[sub['scene']]
        offset = ch['start'] - ch['sourceTrim'][0]
        speech_start, speech_end = [offset + t for t in sub['sourceSpeech']]
        start = max(ch['start'], speech_start - .10)
        end = min(ch['start'] + ch['duration'], speech_end + .16)
        cues.append(dict(id=f'nanami-{len(cues)+1:02}', text=sub['text'], scene=sub['scene'],
                         speech_start=speech_start, speech_end=speech_end, start=start, end=end,
                         source=str((WORK / 'source' / f'nanami-{len(cues)+1:02}.wav').resolve())))
    reference = OUT / 'references/nanami-voice.wav'
    provenance = json.loads((OUT / 'references/nanami-voice-provenance.json').read_text(encoding='utf-8'))
    assert len(cues) == 11
    assert digest(reference) == provenance['sha256']
    manifest = dict(original=str(OUT / 'sui-ai-gym-final.mp4'), original_sha256=digest(OUT / 'sui-ai-gym-final.mp4'),
                    reference=str(reference.resolve()), reference_sha256=digest(reference),
                    reference_text=provenance['transcript'], duration=timeline['duration'], cues=cues,
                    added_dreamina_credits=0, human_listening_review=False)
    write_json(WORK / 'manifest.json', manifest)
    if not (WORK / 'original-mix.wav').exists():
        run(['ffmpeg', '-v', 'error', '-y', '-i', OUT / 'sui-ai-gym-final.mp4', '-vn',
             '-ac', '2', '-ar', '48000', '-c:a', 'pcm_f32le', WORK / 'original-mix.wav'])
    print(json.dumps(dict(prepared=len(cues), work=str(WORK)), ensure_ascii=False), flush=True)


def separate():
    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    torch.set_num_threads(4)
    torch.manual_seed(20261012)
    manifest = json.loads((WORK / 'manifest.json').read_text(encoding='utf-8'))
    if not (WORK / 'original-vocals.wav').exists():
        wave, sr = sf.read(WORK / 'original-mix.wav', dtype='float32', always_2d=True)
        model = get_model('htdemucs').eval().to('cuda')
        mix = torch.from_numpy(wave.T.copy()).to('cuda')
        mix = torchaudio.functional.resample(mix, sr, model.samplerate)
        mean, std = mix.mean(), mix.std().clamp_min(1e-6)
        with torch.inference_mode():
            stems = apply_model(model, ((mix - mean) / std)[None], device='cuda',
                                shifts=0, split=True, overlap=.25, progress=False)[0]
            vocals = stems[model.sources.index('vocals')] * std
            vocals = torchaudio.functional.resample(vocals, model.samplerate, sr).T.cpu().numpy()
        vocals = np.pad(vocals, ((0, max(0, len(wave)-len(vocals))), (0, 0)))[:len(wave)]
        sf.write(WORK / 'original-vocals.wav', vocals, sr, subtype='FLOAT')
        sf.write(WORK / 'original-background.wav', wave-vocals, sr, subtype='FLOAT')
        write_json(WORK / 'separation.json', dict(model='htdemucs', sample_rate=sr, shifts=0,
                   overlap=.25, method='background = exact original mix minus extracted vocals',
                   peak_vram_gb=torch.cuda.max_memory_allocated()/1024**3))
    vocals, sr = sf.read(WORK / 'original-vocals.wav', dtype='float32', always_2d=True)
    mix, _ = sf.read(WORK / 'original-mix.wav', dtype='float32', always_2d=True)
    for cue in manifest['cues']:
        a, b = round(cue['start']*sr), round(cue['end']*sr)
        mono = vocals[a:b].mean(1)
        sf.write(cue['source'], mono, sr, subtype='PCM_16')
        sf.write(WORK/'source'/f"{cue['id']}-mix.wav", mix[a:b], sr, subtype='PCM_16')
    print('Separated dialogue and extracted 11 Nanami-only windows', flush=True)


def clean_reference():
    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    torch.set_num_threads(4)
    manifest = json.loads((WORK / 'manifest.json').read_text(encoding='utf-8'))
    wave, sr = sf.read(manifest['reference'], dtype='float32', always_2d=True)
    model = get_model('htdemucs').eval().to('cuda')
    stereo = np.repeat(wave, 2, axis=1) if wave.shape[1] == 1 else wave
    mix = torch.from_numpy(stereo.T.copy()).to('cuda')
    mix = torchaudio.functional.resample(mix, sr, model.samplerate)
    mean, std = mix.mean(), mix.std().clamp_min(1e-6)
    with torch.inference_mode():
        stems = apply_model(model, ((mix-mean)/std)[None], device='cuda',
                            shifts=0, split=True, overlap=.25, progress=False)[0]
        vocal = stems[model.sources.index('vocals')]*std
        vocal = torchaudio.functional.resample(vocal, model.samplerate, sr).mean(0).cpu().numpy()
    vocal = np.pad(vocal, (0,max(0,len(wave)-len(vocal))))[:len(wave)]
    original = wave.mean(1)
    background = original-vocal
    sf.write(WORK/'reference-clean.wav', vocal, sr, subtype='PCM_16')
    sf.write(WORK/'reference-background.wav', background, sr, subtype='PCM_16')
    meta = dict(source_sha256=manifest['reference_sha256'], clean_sha256=digest(WORK/'reference-clean.wav'),
                model='htdemucs', original_seconds=len(wave)/sr,
                original_rms=float(np.sqrt(np.mean(original**2))),
                vocal_rms=float(np.sqrt(np.mean(vocal**2))),
                background_rms=float(np.sqrt(np.mean(background**2))),
                background_energy_fraction=float(np.sum(background**2)/np.sum(original**2)))
    write_json(WORK/'reference-clean.json',meta)
    print(json.dumps(meta),flush=True)


def mux(variant):
    """Only subtract and replace the Nanami vocal stem inside documented windows."""
    manifest = json.loads((WORK / 'manifest.json').read_text(encoding='utf-8'))
    mix, sr = sf.read(WORK / 'original-mix.wav', dtype='float32', always_2d=True)
    vocals, vsr = sf.read(WORK / 'original-vocals.wav', dtype='float32', always_2d=True)
    assert sr == vsr == 48000
    total = round(manifest['duration']*sr)
    original = mix[:total].copy()
    result = original.copy()
    changed = np.zeros(total, dtype=bool)
    aligned_dir = WORK / 'aligned' / variant
    aligned_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for cue in manifest['cues']:
        a, b = round(cue['start']*sr), round(cue['end']*sr)
        target_len = b-a
        source = WORK / variant / f"{cue['id']}.wav"
        generated, gen_sr = sf.read(source, dtype='float32', always_2d=True)
        seconds = len(generated)/gen_sr
        ratio = seconds/(target_len/sr)
        if not .5 <= ratio <= 2.0:
            raise ValueError(f"{cue['id']}: timing ratio {ratio:.3f} requires review")
        aligned = aligned_dir / f"{cue['id']}.wav"
        run(['ffmpeg', '-v', 'error', '-y', '-i', source, '-af', f'atempo={ratio:.9f}',
             '-ac', '1', '-ar', str(sr), '-c:a', 'pcm_f32le', aligned])
        speech, _ = sf.read(aligned, dtype='float32')
        if abs(len(speech)-target_len) > .12*sr:
            raise ValueError(f"{cue['id']}: unexpected atempo sample count")
        speech = np.pad(speech, (0, max(0, target_len-len(speech))))[:target_len]
        # Match active speech energy; a single gain does not alter timbre or intonation.
        source_mono = vocals[a:b].mean(1)
        def active_rms(w):
            selected = np.abs(w) > max(.002, float(np.abs(w).max())*.04)
            return float(np.sqrt(np.mean(w[selected]**2))) if selected.any() else 0.
        gain = np.clip(active_rms(source_mono)/max(active_rms(speech), 1e-8), .3, 3.)
        speech *= gain
        # Fade only the window edges, retaining the residual stereo ambience.
        envelope = np.ones(target_len, dtype='float32')
        edge = min(round(.025*sr), target_len//4)
        if a > 0:
            envelope[:edge] = np.linspace(0, 1, edge)
        envelope[-edge:] = np.linspace(1, 0, edge)
        base = original[a:b]-vocals[a:b]*envelope[:,None]
        delta = speech[:,None]*envelope[:,None]
        mixed = base+delta
        peak_gain = 1.
        if np.max(np.abs(mixed)) > .95:
            assert np.max(np.abs(base)) < .95, 'Residual background requires manual review'
            delta_stereo = np.broadcast_to(delta, base.shape)
            active = np.abs(delta_stereo) > 1e-7
            boundaries = np.where(delta_stereo[active] > 0, .95, -.95)
            limits = (boundaries-base[active])/delta_stereo[active]
            peak_gain = min(1., float(np.min(limits))*.999)
            assert peak_gain > .25, 'Speech would become too quiet'
            speech *= peak_gain
            mixed = base+delta*peak_gain
        result[a:b] = mixed
        changed[a:b] = True
        sf.write(aligned, speech, sr, subtype='PCM_16')
        rows.append(dict(cue, generated_seconds=seconds, window_seconds=target_len/sr,
                         atempo_ratio=ratio, speech_gain=float(gain)*peak_gain,
                         peak_safety_gain=peak_gain, aligned=str(aligned),
                         generated_sha256=digest(source)))
    assert np.isfinite(result).all()
    assert np.max(np.abs(result[~changed]-original[~changed])) == 0
    peak = float(np.abs(result).max())
    if peak >= .999:
        raise ValueError(f'Mix peak {peak:.3f}; fix individual speech gains before mux')
    wav = WORK / f'{variant}-mix.wav'
    sf.write(wav, result, sr, subtype='FLOAT')
    export_name = 'cosy' if variant == 'cosy_ready_trimmed' else variant
    for clean in [False, True]:
        source_video = OUT / ('sui-ai-gym-clean.mp4' if clean else 'sui-ai-gym-final.mp4')
        target_video = OUT / f"sui-ai-gym-nanami-{export_name}{'-clean' if clean else ''}.mp4"
        run(['ffmpeg', '-v', 'error', '-y', '-i', source_video, '-i', wav,
             '-map', '0:v:0', '-map', '1:a:0', '-map_metadata', '0', '-c:v', 'copy',
             '-c:a', 'aac', '-b:a', '256k', '-ar', str(sr), '-t', str(manifest['duration']),
             '-movflags', '+faststart', target_video])
    write_json(WORK / f'{variant}-edit.json', dict(variant=variant, edits=rows, peak=peak,
               unchanged_samples_outside_nanami_windows=True, sample_rate=sr,
               video_copy=True, added_dreamina_credits=0))
    print(json.dumps(dict(muxed=variant, peak=peak, nanami_lines=len(rows))), flush=True)


def trim_tts(variant, report_file):
    """Combine independent ASR boundaries and VAD; retain consonant/tail margins."""
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    from scipy.signal import resample_poly
    checks = json.loads((WORK/report_file).read_text(encoding='utf-8'))['results']
    manifest = json.loads((WORK/'manifest.json').read_text(encoding='utf-8'))
    target_variant = variant+'_trimmed'
    target_dir = WORK/target_variant
    target_dir.mkdir(exist_ok=True)
    rows = []
    for cue in manifest['cues']:
        check = next(r for r in checks if r['variant']==variant and r['cue']==cue['id'])
        path = WORK/variant/f"{cue['id']}.wav"
        wave,sr = sf.read(path,dtype='float32')
        words = [w for s in check['segments'] for w in s['words']]
        assert words, f"{cue['id']}: no recognized speech"
        vad = get_speech_timestamps(resample_poly(wave,16000,sr).astype('float32'),
                                   vad_options=VadOptions(min_speech_duration_ms=100,
                                   min_silence_duration_ms=200,speech_pad_ms=60,threshold=.5))
        assert vad, f"{cue['id']}: no voice activity"
        start = float(words[0]['start'])
        if start < .10:
            start = vad[0]['start']/16000
        start = max(0.,start-.12)
        # VAD may extend a final consonant beyond the ASR word timestamp.
        end = min(len(wave)/sr,max(float(words[-1]['end']),vad[-1]['end']/16000)+.15)
        trimmed = wave[round(start*sr):round(end*sr)]
        target = target_dir/path.name
        sf.write(target,trimmed,sr,subtype='PCM_16')
        meta = dict(cue=cue['id'],source=str(path),source_sha256=digest(path),
                    trim_seconds=[start,end],seconds=len(trimmed)/sr,
                    alignment='ASR plus Silero VAD; 120 ms leading / 150 ms trailing margin',
                    observed_text=check['observed'],human_listening_review=False)
        write_json(target.with_suffix('.json'),meta)
        rows.append(meta)
    write_json(WORK/f'{target_variant}-trim.json',rows)
    print(json.dumps(dict(trimmed=len(rows),variant=target_variant)),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare','separate','clean-reference','trim-tts','mux'])
    parser.add_argument('--variant', default='seed_off')
    parser.add_argument('--report', default='candidate-checks.json')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'separate':
        separate()
    elif args.action == 'clean-reference':
        clean_reference()
    elif args.action == 'trim-tts':
        trim_tts(args.variant,args.report)
    else:
        mux(args.variant)
