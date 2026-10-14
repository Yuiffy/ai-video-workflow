"""Import the verified movie and its editable shot sequence into the same canvas."""
from pathlib import Path
import hashlib
import json
from filelock import FileLock
import produce

qa = json.loads((produce.OUT / 'verification.json').read_text(encoding='utf-8'))
assert qa['fullDecode'] == 'passed'
assert qa['visualReview'] == 'passed'
film = produce.OUT / produce.PLAN['assembly']['file']
digest = hashlib.sha256(film.read_bytes()).hexdigest()
assert digest == qa['sha256']
timeline = json.loads((produce.OUT / 'timeline.json').read_text(encoding='utf-8'))
assert qa['subtitleCount'] == len(timeline['subtitles'])


def found(node_id):
    shown = produce.call('node', 'show', '--project-id', produce.job['canvasId'], '--node-id', node_id)
    nodes = [r['node'] for r in shown['nodes'] if r.get('result') == 'FOUND']
    return nodes[0] if nodes else None


def validate_sequence(node, expected):
    assert node['type'] == 'timeline'
    assert not node['timelineTracks'].get('clipsTruncated')
    clips = [c for t in node['timelineTracks']['tracks'] for c in t['clips']]
    assert len(clips) == len(expected) == 7
    assert [c['source']['id'] for c in clips] == expected
    assert all(c['kind'] == 'video' and c['source']['kind'] == 'node'
               and c['source']['type'] == 'video' and c['source']['writebackSupported'] for c in clips)
    assert set(expected).issubset(set(node['upstreamNodeIds']))

with FileLock(str(produce.OUT / '.production.lock'), timeout=0):
    item = produce.job['items'].setdefault('final', {**produce.identity(), 'type': 'video'})
    assert not item.get('sha256') or item['sha256'] == digest, 'Keep an already imported final intact'
    item.update(sha256=digest, localFile=str(film))
    produce.save()
    if not item.get('uploaded'):
        uploaded = produce.call('resource', 'upload', '--project-id', produce.job['canvasId'],
                                '--resource-id', item['resourceId'], '--file', film,
                                '--type', 'video', '--name', '岁己×七海·AI从业者遇到健身教练·带字幕成片')
        assert uploaded['resourceId'] == item['resourceId'] and uploaded['mediaType'] == 'video'
        item['uploaded'] = True
        produce.save()
    if not item.get('saved'):
        saved = found(item['nodeId']) if item.get('draftSaveAttempted') else None
        if saved is None:
            assert not item.get('draftSaveAttempted'), 'Saved final outcome unresolved; keep the same identity'
            item['draftSaveAttempted'] = True
            produce.save()
            saved = produce.call('node', 'create', 'video', '--project-id', produce.job['canvasId'],
                             '--node-id', item['nodeId'], '--update-id', item['updateId'],
                             '--title', '完整成片·岁己×七海·带字幕', '--resource-id', item['resourceId'],
                             '--import-kind', 'local_upload', '--submit-id', item['submitId'])['node']
        assert saved['type'] == 'video'
        assert any(r['resourceId'] == item['resourceId'] for r in saved['resources'])
        item.update(saved=True, selectedResourceId=item['resourceId'])
        produce.save()
    assembled = produce.job['items'].setdefault('editable_sequence', {**produce.identity(), 'type': 'timeline'})
    produce.save()
    if not assembled.get('saved'):
        command = ['node', 'create', 'timeline', '--project-id', produce.job['canvasId'],
                   '--node-id', assembled['nodeId'], '--update-id', assembled['updateId'],
                   '--title', '七段镜头顺序·可逐段升级重拍']
        expected = []
        for chapter in timeline['chapters']:
            source = produce.job['items'][chapter['take']]
            assert source.get('selectedResourceId')
            assert any(r['state'] == 'succeeded' and r['resourceId'] == source['selectedResourceId']
                       for r in source['observation']['resources'])
            node = source['nodeId']
            expected.append(node)
            start, end = chapter['sourceTrim']
            command += ['--clip', f'{node},kind=canvas_node,trim={round(start*1000)}-{int((end-start)*1000)},volume=1']
        saved = found(assembled['nodeId']) if assembled.get('draftSaveAttempted') else None
        if saved is None:
            assert not assembled.get('draftSaveAttempted'), 'Saved timeline outcome unresolved; keep the same identity'
            assembled['draftSaveAttempted'] = True
            produce.save()
            saved = produce.call(*command)['node']
        validate_sequence(saved, expected)
        assembled.update(saved=True, upstreamNodeIds=saved['upstreamNodeIds'])
        produce.save()
    shown = found(item['nodeId'])
    assert shown and shown['type'] == 'video'
    assert any(r['resourceId'] == item['resourceId'] and r['status'].lower() in ['success', 'succeeded']
               for r in shown['resources'])
    saved_sequence = found(assembled['nodeId'])
    validate_sequence(saved_sequence, [produce.job['items'][c['take']]['nodeId'] for c in timeline['chapters']])
    produce.job['delivery'] = {'state': 'verified', 'localFile': str(film), 'sha256': digest,
                               'canvasNodeId': item['nodeId'], 'timelineNodeId': assembled['nodeId'],
                               'durationSeconds': qa['durationSeconds'], 'subtitleCount': qa['subtitleCount'],
                               'chapterCount': 7, 'quotedCreditsTotal': qa['quotedCreditsTotal'],
                               'webUrl': produce.job['webUrl']}
    produce.save()
    print(json.dumps(produce.job['delivery'], ensure_ascii=False))
