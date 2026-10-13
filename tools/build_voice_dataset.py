"""Build traceable, session-disjoint voice-training candidates from speaker SRTs.

The outputs are candidates, not approved clean training audio. Separation and
speaker/quality checks must happen before promoting them into a training split.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import re
import subprocess
from pathlib import Path


def seconds(value: str) -> float:
    h, m, s = value.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_candidates(source: dict, min_score: float, max_end: float = 7200, min_duration: float = 3) -> list[dict]:
    text = Path(source['srt']).read_text(encoding='utf-8-sig')
    candidates = []
    for block in re.split(r'\n\s*\n', text.strip()):
        match = re.search(r'(\d\d:\d\d:\d\d,\d+) --> (\d\d:\d\d:\d\d,\d+)\s+\[岁己SUI ([\d.]+)\]\s*(.*)', block, re.S)
        if not match:
            continue
        start, end = seconds(match[1]), seconds(match[2])
        score = float(match[3])
        if score < min_score or start < 300 or end > max_end or end <= start:
            continue
        row = dict(start=start, end=end, score=score, text=match[4].strip())
        if candidates and 0 <= start - candidates[-1]['end'] <= .25 and end - candidates[-1]['start'] <= 12:
            candidates[-1]['end'] = end
            candidates[-1]['score'] = min(score, candidates[-1]['score'])
            candidates[-1]['text'] += ' ' + row['text']
        else:
            candidates.append(row)
    return [dict(row, date=source['date'], media=source['media'], srt=source['srt'])
            for row in candidates if min_duration <= row['end'] - row['start'] <= 12]


def extract(row: dict, out: Path, ffmpeg: str) -> dict:
    target = out / 'raw' / row['split'] / (row['id'] + '.wav')
    target.parent.mkdir(parents=True, exist_ok=True)
    duration = row['end'] - row['start']
    if not target.exists():
        temporary = target.with_suffix('.partial.wav')
        subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-ss', str(row['start']), '-i', row['media'], '-t', str(duration),
                        '-map', '0:a:0', '-vn', '-ar', '44100', '-ac', '2',
                        '-c:a', 'pcm_s16le', str(temporary)], check=True, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        temporary.replace(target)
    row['raw_path'] = str(target.resolve())
    row['raw_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--per-session', type=int, default=100)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--min-score', type=float, default=.76)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    sessions = [s for s in inventory if s['date'] >= '2026_08_01' and s['strong'] >= 140
                and not any(t in s['media'] for t in ['3d演出', 'best_effort'])]
    # Include multiple recent sessions. Keep two entire dates out of training.
    sessions = sessions[-16:]
    holdout_dates = {s['date'] for s in sessions[-2:]}
    randomizer = random.Random(20260928)
    rows = []
    for source in sessions:
        candidates = parse_candidates(source, args.min_score)
        randomizer.shuffle(candidates)
        limit = 35 if source['date'] in holdout_dates else args.per_session
        for row in sorted(candidates[:limit], key=lambda r:r['start']):
            row['split'] = 'validation' if row['date'] in holdout_dates else 'train'
            key = f"{row['media']}:{row['start']:.3f}:{row['end']:.3f}"
            row['id'] = row['date'] + '_' + hashlib.sha256(key.encode()).hexdigest()[:12]
            rows.append(row)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'candidate-plan.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'sessions':len(sessions), 'clips':len(rows),
                      'minutes':round(sum(r['end']-r['start'] for r in rows)/60,2),
                      'holdout_dates':sorted(holdout_dates)},ensure_ascii=False),flush=True)
    if args.plan_only:
        return
    with (args.output/'raw-manifest.jsonl').open('w',encoding='utf-8') as manifest:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(extract,row,args.output,args.ffmpeg):row for row in rows}
            for i,future in enumerate(concurrent.futures.as_completed(futures),1):
                row=future.result()
                manifest.write(json.dumps(row,ensure_ascii=False)+'\n')
                manifest.flush()
                if i%50==0 or i==len(rows):print(f'extracted {i}/{len(rows)}',flush=True)
    (args.output/'extraction.done').write_text('complete\n',encoding='utf-8')


if __name__ == '__main__':
    main()
