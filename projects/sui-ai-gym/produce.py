"""Submit only approved new footage; resume existing work without duplicate charges."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid
from filelock import FileLock

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads(Path(__file__).with_name('production-plan.json').read_text(encoding='utf-8'))
OUT = ROOT / PLAN['output']
STATE = OUT / 'job.json'
EXE = 'C:/Users/yuiffy/bin/dreamina-canvas.exe'
job = json.loads(STATE.read_text(encoding='utf-8'))

def save():
    tmp = STATE.with_suffix(f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, STATE)

def identity():
    return {'nodeId': 'node_' + ''.join(secrets.choice('0123456789abcdefghjkmnpqrstvwxyz') for _ in range(10)),
            'resourceId': str(uuid.uuid4()), 'updateId': str(uuid.uuid4()), 'submitId': str(uuid.uuid4())}

def call(*args):
    result = subprocess.run([EXE, '--non-interactive', '--profile', job['profile'], '--region', job['region'],
                             *map(str, args)], capture_output=True, encoding='utf-8', errors='replace', timeout=65)
    response = json.loads(result.stdout or result.stderr)
    request_id = response.get('meta', {}).get('requestId')
    if request_id:
        job['requestIds'].append({'command': ' '.join(map(str, args[:2])), 'requestId': request_id})
        save()
    if not response.get('ok'):
        # Approval tokens and signed URLs are never stored.
        job['lastError'] = {key: response[key] for key in ['error', 'meta', 'creditConfirmation'] if key in response}
        save()
        raise RuntimeError(json.dumps(job['lastError'], ensure_ascii=False))
    return response['data']

def scenes():
    result = [s for s in PLAN['scenes'] + PLAN.get('repairs', []) if not args.keys or s['id'] in args.keys]
    if args.keys:
        assert {s['id'] for s in result} == set(args.keys), 'Unknown scene key'
    return result

def prepare():
    for key, ref in PLAN['references'].items():
        item = job['items'].setdefault(key, {**identity(), 'type': ref['type']})
        save()
        assert Path(ref['file']).is_file(), ref['file']
        if not item.get('uploaded'):
            uploaded = call('resource', 'upload', '--project-id', job['canvasId'], '--resource-id', item['resourceId'],
                            '--file', ref['file'], '--type', ref['type'], '--name', ref['title'],
                            '--import-kind', ref.get('importKind', 'local_upload'))
            assert uploaded['resourceId'] == item['resourceId'] and uploaded['mediaType'] == ref['type']
            item['uploaded'] = True
            item['sha256'] = hashlib.sha256(Path(ref['file']).read_bytes()).hexdigest()
            save()
        if not item.get('saved'):
            data = call('node', 'create', ref['type'], '--project-id', job['canvasId'], '--node-id', item['nodeId'],
                        '--update-id', item['updateId'], '--title', ref['title'], '--resource-id', item['resourceId'],
                        '--import-kind', ref.get('importKind', 'local_upload'), '--submit-id', item['submitId'])
            assert data['node']['type'] == ref['type']
            item['saved'] = True
            save()
        print(key + ' imported', flush=True)
    for scene in scenes():
        assert scene['model'] in PLAN['authorizedModels']
        item = job['items'].setdefault(scene['id'], {**identity(), 'type': 'video'})
        save()
        prompt = scene['prompt']
        for key in scene['refs']:
            prompt = prompt.replace('{{' + key + '}}', '{{node:' + job['items'][key]['nodeId'] + '}}')
        if item.get('saved'):
            assert item['generation']['prompt'] == prompt, 'Use a new scene key for a new paid take'
            continue
        command = ['node', 'create', 'video', '--project-id', job['canvasId'], '--node-id', item['nodeId'],
                   '--update-id', item['updateId'], '--title', scene['title'], '--mode', scene['mode'],
                   '--model', scene['model'], '--ratio', '16:9', '--resolution', '720p', '--duration', scene['duration'],
                   '--count', '1', '--prompt', prompt]
        for key in scene['refs']:
            command += ['--ref', 'node:' + job['items'][key]['nodeId']]
        if item.get('draftSaveAttempted'):
            shown = call('node', 'show', '--project-id', job['canvasId'], '--node-id', item['nodeId'])
            found = [x['node'] for x in shown['nodes'] if x.get('result') == 'FOUND']
            if not found:
                raise RuntimeError('Saved draft outcome unresolved; keep the same identity')
            node = found[0]
        else:
            item['draftSaveAttempted'] = True
            save()
            node = call(*command)['node']
        expected = {job['items'][key]['nodeId'] for key in scene['refs']}
        assert expected.issubset(set(node['upstreamNodeIds']))
        gen = node['generation']
        assert gen['prompt'] == prompt
        assert expected == {r['id'] for r in gen['references'] if r['kind'] == 'node'}
        parts = gen.get('promptParts', [])
        assert all(any(p.get('kind') == 'reference' and gen['references'][p['referenceIndex']]['id'] == ident
                       for p in parts) for ident in expected), 'Prompt reference binding missing'
        item.update(saved=True, generation={k: gen[k] for k in ['model', 'mode', 'prompt', 'durationSeconds'] if k in gen},
                    references=[{'kind': r['kind'], 'id': r['id']} for r in gen['references']],
                    upstreamNodeIds=node['upstreamNodeIds'])
        save()
        print(scene['id'] + ' saved', flush=True)

def node_args(selected):
    result = ['--project-id', job['canvasId']]
    for s in selected: result += ['--node-id', job['items'][s['id']]['nodeId']]
    return result

def quote():
    data = call('node', 'quote', *node_args(scenes()))
    job['lastQuote'] = data
    save()
    mapping = {job['items'][s['id']]['nodeId']: s['id'] for s in scenes()}
    print(json.dumps({'items': [{'scene': mapping[r['nodeId']], 'maxCredits': r.get('maxCredits'),
                                'error': r.get('error')} for r in data['items']],
                      'totalMaxCredits': data['totalMaxCredits'], 'confirmable': data.get('confirmable'),
                      'confirmationRequired': data.get('confirmationRequired')}, ensure_ascii=False), flush=True)
    return data

def run():
    selected = scenes()
    items = [job['items'][s['id']] for s in selected]
    assert all(not i.get('attempted') for i in items), 'Already attempted: use status on the same submit IDs'
    q = quote()
    assert q.get('confirmable', True) and all('maxCredits' in r and not r.get('error') for r in q['items'])
    reserved = sum(i.get('quotedMaxCredits', 0) for i in job['items'].values() if i.get('attempted'))
    remaining = job['budget']['authorizedTotalCeiling'] - reserved
    assert 0 <= q['totalMaxCredits'] <= remaining, 'Latest price exceeds remaining user authorization'
    token = None
    if q.get('confirmationRequired'):
        token = call('node', 'confirm', *node_args(selected), '--credit-ceiling', q['totalMaxCredits'])['creditConfirmationToken']
    costs = {r['nodeId']: r['maxCredits'] for r in q['items']}
    command = ['node', 'run', *node_args(selected)]
    for item in items:
        item.update(attempted=True, authorizedCreditCeiling=costs[item['nodeId']], quotedMaxCredits=costs[item['nodeId']])
        command += ['--submit-id', item['submitId']]
    job['budget'].update(nominalReservedCredits=reserved + q['totalMaxCredits'],
                         remainingCeiling=remaining - q['totalMaxCredits'])
    save()  # Freeze all identities and reserve the whole batch before the network call.
    if token: command += ['--credit-token', token]
    data = call(*command)
    for result in data['items']:
        item = next(i for i in items if i['nodeId'] == result['nodeId'])
        item['runResult'] = result
        save()
        print(json.dumps({'scene': next(s['id'] for s in selected if job['items'][s['id']] is item),
                          'submitId': item['submitId'], 'state': result['state']}, ensure_ascii=False), flush=True)

def status():
    for s in scenes():
        item = job['items'][s['id']]
        if not item.get('attempted'): continue
        data = call('operation', 'status', item['submitId'], '--project-id', job['canvasId'])
        item['observation'] = data
        save()
        print(json.dumps({'scene': s['id'], **data}, ensure_ascii=False), flush=True)

def download():
    for s in scenes():
        item = job['items'][s['id']]
        successes = [r for r in item.get('observation', {}).get('resources', []) if r['state'].lower() in ['success', 'succeeded']]
        if not successes:
            print(s['id'] + ' pending', flush=True)
            continue
        item['selectedResourceId'] = successes[0]['resourceId']
        target = OUT / (s['id'] + '-raw.mp4')
        if not target.exists():
            item['download'] = call('resource', 'download', item['selectedResourceId'], '--project-id', job['canvasId'], '--output', target)
        assert target.stat().st_size > 10000
        item['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        assert item['sha256'] == item['download']['sha256'].lower()
        item['localFile'] = str(target)
        save()
        print(s['id'] + ' downloaded ' + str(target.stat().st_size), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'quote', 'run', 'status', 'download'])
    parser.add_argument('keys', nargs='*')
    args = parser.parse_args()
    with FileLock(str(OUT / '.production.lock'), timeout=0):
        globals()[args.action]()
