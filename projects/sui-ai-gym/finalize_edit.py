"""Freeze the reviewed cut and synchronize its readable dialogue sources."""
from pathlib import Path
import copy
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
plan = json.loads((HERE / 'production-plan.json').read_text(encoding='utf-8'))
out = ROOT / plan['output']
catalog = {s['id']: s for s in plan['scenes'] + plan['repairs']}
cuts = {
    '01_occupation': ('01_occupation_v2', 0, 14.7),
    '02_company': ('02_company_v2', 1.0, 14.6),
    '03_model': ('03_model_v2', 1.6, 13.5),
    '04_pedal': ('04_pedal_v2', 1.5, 15.0),
    '05_twitter': ('05_twitter_v2', 2.5, 12.0),
    '06_invitation': ('06_invitation_v3', 0, 12.6),
    '07_departure': ('07_departure', 0, 15.0),
}
decisions = {
    'reviewed': True,
    'reviewBasis': '各段实际接触表和字级ASR；第4段采用无提示词独立确认结果。',
    'notes': [
        '训练中统一白色红边背心和红短裤；只有结尾穿回黑外套。',
        '减少连续多个从鞋开始的重复镜头，不裁掉剧情台词。',
        '保留第4段额外的害羞反应，字幕与实际声音一致。',
        '第6段改为在本地跑了一套，避免部署的错误发音。',
        '保留第7段完整的答应、走吧和二人并肩离场。',
    ],
    'takes': {},
}
for original in plan['scenes']:
    key = original['id']
    take, start, end = cuts[key]
    assert (out / (take + '-raw.mp4')).is_file()
    assert (out / 'qa' / (take + '-sheet.jpg')).is_file()
    selection = {'take': take, 'start': start, 'end': end,
                 'dialogue': copy.deepcopy(catalog[take]['dialogue'])}
    if key == '01_occupation':
        selection['dialogue'][-1][3] = 'harness。对，harness。'
    elif key == '04_pedal':
        selection['asrFile'] = '04_pedal_v2-confirmed-asr.json'
        selection['dialogue'] = [
            [3.31, 6.37, '七海', 'Tibo预告要重置了，你有站起来蹬吗？'],
            [6.87, 8.37, '岁己', '站起来……蹬？'],
            [8.95, 11.87, '岁己内心', '蹬……天哪，她在说什么奇怪的话？'],
            [11.87, 14.81, '岁己', '你在说什么啦……好害羞哦。'],
        ]
    elif key == '05_twitter':
        selection['dialogue'] = [
            [3.66, 5.9, '七海', '就是推特上看的那个呀。'],
            [6.8, 9.42, '岁己', '推特上……看的那种？'],
            [9.96, 11.66, '岁己', '别说了……'],
        ]
    elif key == '06_invitation':
        selection['dialogue'] = [
            [1, 5.8, '七海', '我在本地跑了一套MiniMax H3，'],
            [5.8, 8.8, '七海', '能制作视频拿去卖钱。'],
            [9.3, 13.8, '七海', '练完要不要来我家看看？'],
        ]
    decisions['takes'][key] = selection
(out / 'edit-decisions.json').write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding='utf-8')

project_path = HERE / 'project.json'
project = json.loads(project_path.read_text(encoding='utf-8'))
for scene in project['scenes']:
    selection = decisions['takes'][scene['id']]
    scene['narration'] = '\n'.join(f'{speaker}：{text}' for _, _, speaker, text in selection['dialogue'])
    scene['selected_take'] = selection['take']
project['final_cut'] = {'edit_decisions': str(out / 'edit-decisions.json'),
                        'movie': str(out / plan['assembly']['file'])}
project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')

duration = sum(end - start for _, start, end in cuts.values())
script = (
    '# AI从业者遇到健身教练\n\n'
    f'岁己 × 七海的健身房轻喜剧。成片剪辑约{duration:.1f}秒，完整保留职业追问、AI黑话误会和并肩离场。\n\n'
    '画面：暖色健身房，成年角色，训练与组间休息、近景广角和低机位、汗光与自然呼吸。'
    '训练时岁己穿白色红边运动背心和红短裤，离场时穿回黑外套。\n\n'
)
for scene in plan['scenes']:
    selected = decisions['takes'][scene['id']]
    script += f"## {scene['id']} · {scene['title']}\n\n动作：{scene['exercise']}。\n\n"
    script += '\n'.join(f'**{speaker}**：{text}' for _, _, speaker, text in selected['dialogue']) + '\n\n'
script += '生成草稿和所有候选镜头保留在 production-plan.json；最终台词与选片以剪辑决定和时间轴为准。\n'
(HERE / 'script.md').write_text(script, encoding='utf-8')
print(json.dumps({'duration': duration, 'subtitles': sum(len(s['dialogue']) for s in decisions['takes'].values())}, ensure_ascii=False))
