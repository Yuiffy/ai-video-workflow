"""Add a new take for the invitation without changing any submitted draft."""
from pathlib import Path
import copy
import json

HERE = Path(__file__).resolve().parent
path = HERE / 'production-plan.json'
plan = json.loads(path.read_text(encoding='utf-8'))
key = '06_invitation_v3'
if not any(s['id'] == key for s in plan.get('repairs', [])):
    source = next(s for s in plan['repairs'] if s['id'] == '06_invitation_v2')
    scene = copy.deepcopy(source)
    scene.update(
        id=key,
        title='来我家看看模型·清晰台词版',
        repairReason='上一版把部署读成布置；改为自然的在本地跑了一套，保留模型、制作视频卖钱和到家邀请。',
        dialogue=[
            [1.0, 8.8, '七海', '我在本地跑了一套MiniMax H3，能制作视频拿去卖钱。'],
            [9.3, 13.8, '七海', '练完要不要来我家看看？'],
        ],
    )
    scene['action'] = (
        '同一健身房低位拉力器旁，岁己在左侧坐在训练凳边，双脚落地，拿毛巾恢复。'
        '七海在右侧完成一次轻重量站姿拉力划船，双脚稳、背平直、手臂肌肉受力自然。'
        '0至2秒24至28毫米近景广角低机位，从七海白鞋上移到腿、前臂和脸；'
        '七海从第1秒就开始说第一句，镜头运动与说话同步，不要先长时间无声。'
        '2至9秒七海放回握把，面向岁己自然介绍自己的本地AI模型。'
        '9至14秒双人近景，七海坦然微笑邀请岁己到家看模型；'
        '岁己听到视频和来我家后脸颊泛红，捏紧毛巾，偷看七海。'
        '14至15秒保留岁己害羞的反应，七海仍自然友好，汗光和轻微呼吸清楚。'
        '岁己全段保持训练背心、红短裤，不穿外套，不背包；不要任何新增台词。'
    )
    style = source['prompt'].split('\n本段动作与镜头：', 1)[0]
    scene['prompt'] = style + '\n本段动作与镜头：' + scene['action'] + (
        '\n普通话对话必须逐字准确，只有七海说以下两句。'
        '第一句里的“跑了一套”指在电脑本地运行模型，MiniMax H3读MiniMax H三。'
        '岁己只用表情反应，嘴不说话，不产生内心独白。\n'
    ) + '\n'.join(f'{start:g}至{end:g}秒，{speaker}：“{line}”'
                  for start, end, speaker, line in scene['dialogue'])
    assert len(scene['prompt']) < 4000
    plan['repairs'].append(scene)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
print(key)
