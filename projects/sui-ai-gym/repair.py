"""Create separate local retakes for the wardrobe continuity problem."""
from pathlib import Path
import copy
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
path = HERE / 'production-plan.json'
plan = json.loads(path.read_text(encoding='utf-8'))
plan['references']['gym_training'] = {
    'type': 'image', 'title': '训练中统一服装·imagen修正参考',
    'file': str(ROOT / plan['output'] / 'references/gym-training.png'), 'importKind': 'external_generated',
}

style = (
    '横屏16:9高质量半写实三维动漫电影轻喜剧，人物与暖色健身房以{{gym_training}}为统一标准。'
    '始终只有两个二十多岁的成年女性。左侧银白长卷双马尾黑发绳红瞳的岁己，'
    '全段只穿白色红滚边露肩运动背心、红色白滚边运动短裤、白运动鞋，裸露双肩和手臂。'
    '黑外套、黑包和肩带仅放在背景凳上，任何一帧都不穿外套、不背包，不在结尾换衣服。'
    '右侧七海是{{nanami}}中的同一成年女性：棕色短双辫、蓝挑染、黄笑脸夹、金瞳、'
    '藏蓝短袖运动衫、灰蓝运动长裤、白运动鞋和腕表。不要画出三视图中的多个复制人物。'
    '同一房间、同一窗光、正常成年比例和真实训练动作；24至28毫米近景广角，'
    '从运动鞋向上抬的低机位，表现腿部、肩背、前臂的肌肉受力与立体光影。'
    '轻重量训练，脚掌踩稳、动作自然，说话可以在动作顶端或者组间休息；'
    '头发和服装随身体运动，有汗珠、颈侧湿发、自然轻喘与极淡体热气流。'
    '脸红与紧张随对话逐步发生，两人对视和偷看清楚，七海认真坦然，岁己可爱慌张。'
    '音频{{sui_voice}}只绑定岁己声线；音频{{nanami_voice}}只绑定七海声线；'
    '不互换声线，不播放或复读参考原话。只用普通话说指定台词，英语品牌正常发音。'
    'harness读哈内斯，Claude读克劳德，Astra读阿斯特拉，Tibo读蒂博，MiniMax H3读MiniMax H三。'
    '内心台词仅作为同一角色轻轻的内心独白，嘴不动；其他说话口型同步。'
    '不新增台词、不读镜头说明，不要片尾致谢，不加字幕、文字、水印或配乐，'
    '保留轻微器械、脚步和运动呼吸声音，画面铺满，不分屏、不静态平移。'
)

retakes = []
for original in plan['scenes'][:6]:
    scene = copy.deepcopy(original)
    scene['id'] = original['id'] + '_v2'
    scene['title'] = original['title'] + '·训练服连续版'
    scene['repairOf'] = original['id']
    scene['repairReason'] = '首轮镜头把全片结尾穿外套误解成每段结束穿外套，局部重拍锁定训练服装。'
    scene['refs'] = ['gym_training', 'nanami', 'sui_voice', 'nanami_voice']
    scene['action'] = scene['action'].replace('训练时只穿原设白色红领边运动背心与红短裤', '全段只穿白色红领边运动背心与红短裤')
    if original['id'] == '05_twitter':
        scene['action'] += ' 岁己整个镜头双脚必须落在地板上，膝盖自然向前，不把双腿抱到凳上，不抬脚对着镜头；毛巾主要擦脸和颈侧，展示正常组间恢复。'
    scene['prompt'] = style + '\n本段动作与镜头：' + scene['action'] + '\n仅说以下台词：\n' + '\n'.join(
        f'{start:g}至{end:g}秒，{speaker}：“{line}”' for start, end, speaker, line in scene['dialogue'])
    assert len(scene['prompt']) < 4000
    retakes.append(scene)
plan['repairs'] = retakes
path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'retakes': [s['id'] for s in retakes], 'seconds': sum(s['duration'] for s in retakes)}, ensure_ascii=False))
