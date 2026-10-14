"""Keep the dialogue, readable script and generation plan synchronized."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/sui-ai-gym-20261012'

SCENES = [
    {
        'id': '01_occupation', 'title': '做AI的', 'duration': 15,
        'exercise': '轻哑铃反向箭步蹲',
        'dialogue': [
            [0.8, 3.0, '七海', '平时做什么工作的？'],
            [3.4, 5.4, '岁己', '我呀，做AI的。'],
            [5.8, 10.0, '七海', '大模型训练，还是harness开发？'],
            [10.5, 14.2, '岁己', '呃……harness。对，harness。'],
        ],
        'action': '开场0至3秒28毫米近景广角低机位，从岁己白色运动鞋踏稳地面开始，沿小腿向上抬到全身。岁己手持两只轻哑铃，完成一组反向箭步蹲：右脚向后、双膝屈曲、前脚掌踩稳、站起收回，身体稳定自然。黑外套和斜挎包已整齐放在旁边训练凳上，训练时只穿原设白色红领边运动背心与红短裤。七海站在右侧观察。4至10秒切腰部以上近景双人侧面，七海自然闲聊，岁己在每次站稳的间隙自信回答。10至15秒轻推到岁己脸部，她听到harness后短暂眼神空白、握哑铃的手停住，假装镇定点头。细微汗光和运动后呼气，保留最后半秒尴尬表情。',
    },
    {
        'id': '02_company', 'title': '我是Claude的', 'duration': 15,
        'exercise': '保加利亚分腿蹲',
        'dialogue': [
            [0.5, 4.0, '七海', '哪家公司？MiniMax，还是智谱？'],
            [4.4, 7.4, '岁己', '我……Claude的。'],
            [7.8, 11.6, '七海', 'Claude在中国没有研发呀。'],
            [12.0, 14.6, '岁己', '我是……远程的。'],
        ],
        'action': '同一健身房自由重量区。岁己身后是低训练凳，右脚脚背轻放凳上、左脚在前稳定，做一次轻哑铃保加利亚分腿蹲，下蹲时前膝跟脚尖同向，再稳定站起。七海在右侧示范直立的上半身姿态。0至7秒28毫米斜侧低机位，先带出白鞋、腿部受力与肌肉线条，再上抬到两人脸部，说话时岁己在动作顶端短暂停稳。7至12秒近景七海轻微挑眉，接岁己惊慌但努力维持职业笑容的反打。12至15秒岁己稳稳把后脚放回地面，小声补救，七海不嘲笑，只是困惑歪头。原设背心、红短裤、银白双马尾不变，运动汗光自然。',
    },
    {
        'id': '03_model', 'title': '免费用户的Astra', 'duration': 15,
        'exercise': '坐姿拉力练背',
        'dialogue': [
            [0.5, 3.8, '七海', '最近有什么新模型好用？'],
            [4.2, 9.2, '岁己内心', '坏了……我只用免费的GPT和Gemini啊……'],
            [9.6, 13.7, '岁己', 'GPT Astra吧，挺好用的。'],
        ],
        'action': '同一健身房的坐姿拉力划船器械。岁己坐稳，双脚踩踏板，双手持窄握把，从手臂前伸向后拉到下肋部再缓缓放回，肩背受力合理，钢索连接真实。七海站在右侧。0至4秒从岁己肩背斜侧近景广角切到双人中景，七海问模型。4至9秒岁己把握把慢慢放回、停在休息位置，近景脸部微微僵住，配岁己声线很轻的内心独白，嘴唇不动。9至14秒岁己转头对七海挤出自信微笑说出答案。镜头轻推近，手臂和锁骨汗光、胸背自然呼吸与一缕极淡运动热气。14至15秒七海点一下头，岁己偷偷松口气，不新增台词。',
    },
    {
        'id': '04_pedal', 'title': '站起来蹬？', 'duration': 15,
        'exercise': '哑铃深蹲后的站立休息',
        'dialogue': [
            [0.6, 6.5, '七海', 'Tibo预告要重置了，你有站起来蹬吗？'],
            [7.0, 9.1, '岁己', '站起来……蹬？'],
            [10.0, 14.5, '岁己', '你在说什么啦……好害羞哦。'],
        ],
        'action': '自由重量区，岁己完成最后一次轻哑铃高脚杯深蹲，双脚与肩同宽、屈髋屈膝下去、脚掌稳定、起身后把哑铃放回低架。0至6秒24至28毫米近景广角斜侧低机位，真实腿部力量、正常成年身体比例，镜头缓缓从脚向上抬到脸；七海站在右侧认真聊AI。7至10秒岁己忽然停住擦汗的手，眼神游移，脸和耳朵开始泛红，近景反打七海完全认真的表情。10至15秒岁己把小白毛巾抬到下巴，轻轻退半步，害羞低头又偷看七海。可爱的误会喜剧，不出现任何性行为、幻想插画或第三人；热气极淡、不像烟雾。',
    },
    {
        'id': '05_twitter', 'title': '推特上看的那个', 'duration': 12,
        'exercise': '组间坐姿擦汗',
        'dialogue': [
            [0.7, 4.4, '七海', '就是推特上看的那个呀。'],
            [5.0, 10.0, '岁己', '推特上……看的那种？啊……别说啦。'],
        ],
        'action': '岁己坐在训练凳边，双脚踩地自然休息，小白毛巾擦过额头和脸颊，七海在右侧轻松解释。0至4秒七海肩膀后方28毫米近景广角拍岁己，前景七海的肩部和袖口形成空间层次，两位成年女性脸部都清楚可辨。5至10秒缓慢切到岁己脸部特写，她误会得更深，耳朵和脸颊更红，毛巾挡住半张脸，声音变轻；七海只是温和困惑。汗珠沿太阳穴、颈侧发丝自然黏连，呼气轻微起伏。10至12秒岁己把毛巾拧在手里，抬眼偷看，再迅速低头。',
    },
    {
        'id': '06_invitation', 'title': '来我家看看模型', 'duration': 15,
        'exercise': '七海示范低位拉力练背，岁己组间休息',
        'dialogue': [
            [0.7, 8.7, '七海', '我本地部署了一套MiniMax H3，能制作视频拿去卖钱。'],
            [9.2, 14.2, '七海', '练完要不要来我家看看？'],
        ],
        'action': '同一健身房低位拉力器旁，七海先示范一次轻重量站姿拉力划船，双脚稳、背平直，拉握把向下肋部再控制回放，动作时手臂肌肉线条和织物受力自然。岁己在左侧训练凳坐着拿毛巾休息。0至5秒28毫米从七海运动鞋、蓝色运动裤和前臂受力向上抬到脸，展示立体身体与光影。5至9秒七海放回握把、面向岁己认真介绍自己的本地模型。9至15秒双人近景，七海笑着发出普通技术交流邀请；岁己听到视频和来我家，脸红蔓延，目光僵住，手指把毛巾捏紧，情绪误会清楚。没有新增旁白或岁己台词，七海语气自然坦然。',
    },
    {
        'id': '07_departure', 'title': '那……好呀', 'duration': 15,
        'exercise': '训练结束穿回外套，一起离开',
        'dialogue': [
            [0.6, 4.7, '岁己内心', '小、小视频……还要去她家？'],
            [5.3, 7.7, '岁己', '那……好呀。'],
            [8.0, 9.4, '七海', '走吧。'],
        ],
        'action': '训练区到健身房玻璃出口。0至5秒岁己穿回参考图中的敞开黑色运动外套并背好小黑斜挎包，仍是白色红领边运动背心、红短裤和白鞋，脸红低头，配同一岁己声线轻轻的内心独白，嘴唇不动。5至8秒侧面近景，岁己抬头害羞地点头答应，七海笑着拿上自己的小毛巾。8至10秒七海说走吧，两人一起转向出口。10至15秒低机位从并排迈出的两双白色运动鞋平滑升到背影中景，银白长双马尾与七海棕色短辫清楚，两人并肩走出玻璃门，阳光落在肩背，门轻轻合上。最后留一秒完整二人离开的收束，结束在健身房外，不拍她们到家后的任何情节。',
    },
]

STYLE = (
    '16:9横屏精致半写实三维动漫轻喜剧，匹配参考人物的成年比例、精细面部、发丝与运动服材质。'
    '两名角色都是二十多岁的成年女性。健身房布景和暖色窗光以{{gym}}为准，'
    '不要把三视图画成多人、分屏或静态海报。岁己身份以{{sui}}为准：银白长卷双马尾、黑发绳、红瞳；'
    '训练时黑外套和小斜挎包放在凳上，穿原设白色红领边运动背心、红色白滚边短裤和白鞋，'
    '结尾穿回外套并背包。七海身份以{{nanami}}为准：棕色短发双小辫、蓝色发挑染、黄色笑脸夹、'
    '金瞳、藏蓝短袖运动衫、灰蓝运动长裤、白鞋和腕表。始终只有这两位角色，'
    '同一房间的窗户、器械、白柱和地板连续。28毫米近景广角和低机位拍动作、体积与肌肉光影，'
    '人物比例自然，手脚和器械连接正确。运动是轻重量自然训练，说话在动作顶端或休息时，'
    '表情要有逐步紧张、脸红和偷看，不能一直保持微笑。少量皮肤汗光、颈侧湿发、'
    '呼吸起伏与极淡体热气流，保持画面清晰，声音自然亲近。'
    '音频{{sui_voice}}仅作为岁己声线参考，音频{{nanami_voice}}仅作为七海声线参考，'
    '两人声线不能互换，也不能复读参考音频的原话。普通话对话并按指定角色逐句说完，'
    '英语品牌按正常读音，harness读哈内斯，Claude读克劳德，Astra读阿斯特拉，Tibo读蒂博，'
    'MiniMax H3读MiniMax H三。内心独白用对应角色很轻的声线且嘴不动，其余说话口型同步。'
    '只说指定台词，不新增解释或旁白，保留轻微脚步、器械和运动呼吸现场音，'
    '无配乐、无字幕、无屏幕文字、无水印。'
)

references = {
    'sui': {'type': 'image', 'title': '运动岁己·原设三视图', 'file': str(OUT / 'references/sui-sport.png')},
    'nanami': {'type': 'image', 'title': '七海教练·imagen定妆三视图', 'file': str(OUT / 'references/nanami-trainer.png'), 'importKind': 'external_generated'},
    'gym': {'type': 'image', 'title': '健身房·imagen双人场景', 'file': str(OUT / 'references/gym-master.png'), 'importKind': 'external_generated'},
    'sui_voice': {'type': 'audio', 'title': '岁己·真实声线参考6秒', 'file': str(OUT / 'references/sui-voice.mp3')},
    'nanami_voice': {'type': 'audio', 'title': '七海·真实直播声线参考', 'file': str(OUT / 'references/nanami-voice.wav')},
}

for scene in SCENES:
    scene.update(model='seedance_2.0_fast_vip', mode='m2v', refs=list(references))
    cues = '\n'.join(f'{start:g}至{end:g}秒，{speaker}说：“{line}”' for start, end, speaker, line in scene['dialogue'])
    scene['prompt'] = STYLE + '\n本段动作与镜头：' + scene['action'] + '\n本段逐句台词时序：\n' + cues
    assert len(scene['prompt']) < 4000

plan = {
    'title': 'AI从业者遇到健身教练', 'output': 'outputs/sui-ai-gym-20261012',
    'authorizedModels': ['seedance_2.0_mini', 'seedance_2.0_fast_vip'],
    'creditCeiling': 2000, 'references': references, 'scenes': SCENES,
    'assembly': {'fps': 30, 'size': [1280, 720], 'plannedDuration': sum(s['duration'] for s in SCENES),
                 'preserveGeneratedDialogue': True, 'burnSubtitles': True,
                 'file': 'sui-ai-gym-final.mp4'},
}
(HERE / 'production-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')

script = ['# AI从业者遇到健身教练', '', '岁己与七海的健身房轻喜剧。全片计划约102秒。', '',
          '表演主线：岁己自信报职业，被技术问题问住，再把AI黑话逐步误会成暧昧邀请；七海始终认真、自然。', '',
          '画面主线：训练动作与对话同步，近景广角、由鞋向上抬的低机位、肌肉光影、汗光、轻微热气和组间休息。', '']
for scene in SCENES:
    script += [f"## {scene['id']} · {scene['title']} · {scene['duration']}秒", '',
               f"动作：{scene['exercise']}。", '', scene['action'], '']
    script += [f'**{speaker}**：{line}' for _, _, speaker, line in scene['dialogue']]
    script += ['']
(HERE / 'script.md').write_text('\n'.join(script), encoding='utf-8')

project = {
    'id': 'sui-ai-gym', 'title': plan['title'], 'description': '运动岁己遇到真懂AI的七海健身教练，技术黑话越听越歪。',
    'script': 'script.md', 'ppt': 'review.html', 'output': '../../outputs/sui-ai-gym-20261012/pipeline-plan',
    'scenes': [{'id': s['id'], 'title': s['title'], 'duration': s['duration'],
                'narration': '\n'.join(f'{speaker}：{line}' for _, _, speaker, line in s['dialogue']),
                'visual': s['action'], 'image_prompt': s['prompt'], 'voice': {'use_generated_audio': True}} for s in SCENES],
}
(HERE / 'project.json').write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')

print(json.dumps({'scenes': len(SCENES), 'seconds': plan['assembly']['plannedDuration'],
                  'promptLengths': [len(s['prompt']) for s in SCENES]}, ensure_ascii=False))
