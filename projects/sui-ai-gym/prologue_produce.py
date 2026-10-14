"""Append the nail-salon memory and gym greeting to the existing paid job."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import produce

HERE = Path(__file__).resolve().parent
WORK = produce.OUT / 'prologue'
PLAN_PATH = WORK / 'production-plan.json'


def author():
    if PLAN_PATH.exists():
        print('Existing prologue plan retained; use a new key for a changed take.')
        return
    style = (
        '16:9横屏高质量半写实三维动漫电影轻喜剧，成年自然身体比例，'
        '立体精细面部、皮肤、发丝和服装材质，柔和暖窗光，真实空间、景深与相机运动。'
        '角色都是二十多岁的成年女性，绝非儿童，不画Q版，不画平面二维插画，'
        '参考图仅提供人物身份，不复制三视图、白底或分屏。'
        '普通话指定台词逐字说完，声音清楚自然，台词时序服务于表情和口型。'
        '内心独白是岁己自己的轻快声线，嘴唇始终不动；外部对话口型同步。'
        '不新增台词，不复读参考原话，不朗读角色名字或镜头说明。'
        '不加配乐、字幕、屏幕文字、水印。保留轻微场景环境音。'
    )
    salon = (
        style +
        '场景是温暖干净的现代美甲店，米色墙面、木色工作台、台灯、指甲油瓶、'
        '柔软手枕、美甲刷和指甲锉，让正在做美甲一眼可见。只有岁己和栞栞两个角色。'
        '岁己身份服装以{{sui}}为准：银白色长卷双马尾、黑发绳、红瞳，'
        '白色红领边运动背心、红色白边运动短裤、白鞋、敞开黑运动外套。'
        '小黑斜挎包挂在岁己椅背，长袖袖口向后推，左手放在桌上手枕。'
        '美甲师栞栞身份以{{shiori}}为准：浅米金色长发和一条侧麻花辫、蓝眼睛、'
        '棕色贝雷帽与白蝴蝶结、奶油色开衫；在原衣服外穿简洁浅米色工作围裙。'
        '岁己坐画面左侧，美甲师栞栞坐画面右侧，隔工作台相对，'
        '栞栞用小刷给岁己指甲上淡粉色指甲油。人物外观在镜头间完全一致。'
        '音频{{sui_voice}}仅绑定岁己外部台词和内心声线，绝不复读音频里的原话。'
        '栞栞用与岁己明显不同的自然温柔女声。'
    )
    scenes = [
        dict(id='00a_nail_memory', title='前情·美甲师的职业闲聊', duration=12,
             model='seedance_2.0_fast_vip', mode='m2v', refs=['sui', 'shiori', 'sui_voice'],
             dialogue=[
                 [.7, 2.3, '栞栞', '你是做什么的？'],
                 [2.8, 5.1, '岁己内心', '不能暴露我是虚拟主播。'],
                 [5.7, 7.7, '岁己', '我是做AI的。'],
                 [8.3, 10.4, '栞栞', '那好厉害啊。'],
             ],
             prompt=salon + '\n'
             '0至2.5秒从桌上的美甲小刷、岁己伸出的左手近景快速抬到双人中近景；'
             '栞栞一边自然上色一边抬眼问职业。2.5至5.4秒切岁己脸部特写，'
             '岁己眼睛轻轻转动想主意，嘴紧闭，内心很轻地说出秘密。'
             '5.4至8秒岁己突然自信微笑，抬下巴、看美甲师，开口回答。'
             '8至10.7秒切回栞栞，栞栞真诚地惊讶点头夸奖，手仍轻托岁己手指。'
             '10.7至12秒岁己嘴闭着，满意地笑一下，给下一段得意的内心独白留反应。'
             '\n严格四句台词，不能合并角色：'
             '\n0.7至2.3秒栞栞说：“你是做什么的？”'
             '\n2.8至5.1秒岁己内心说：“不能暴露我是虚拟主播。”（岁己嘴不动）'
             '\n5.7至7.7秒岁己说：“我是做AI的。”'
             '\n8.3至10.4秒栞栞说：“那好厉害啊。”'),
        dict(id='00b_nail_confidence', title='前情·以后就这么回答', duration=11,
             model='seedance_2.0_fast_vip', mode='m2v', refs=['sui', 'shiori', 'sui_voice'],
             dialogue=[[.5, 10.3, '岁己内心',
                        '不错，以后问我做什么的我就回答这个，别人也不懂，不会露馅。']],
             prompt=salon + '\n'
             '接同一个美甲店、同样的服装位置、同一次做美甲。'
             '近景从岁己脸部满意的笑容开始，岁己眉毛轻挑，眼里带得意，嘴始终闭着。'
             '相机轻缓推近再沿桌面侧移，带到栞栞安静地继续给她左手做美甲，'
             '指甲油刷正确接触指甲，手指自然。栞栞不说话。'
             '岁己看一眼自己做好的淡粉色指甲，又满足地笑一下。'
             '只有以下一段岁己内心独白，清楚轻快地逐字说完，不要把它当外部说话：'
             '\n0.5至10.3秒岁己内心：“不错，以后问我做什么的我就回答这个，'
             '别人也不懂，不会露馅。”'
             '语速自然，不吞词，岁己与栞栞全段嘴唇都不动，不增加对话。'),
        dict(id='00c_gym_arrival', title='现在·岁己见到七海教练', duration=7,
             model='seedance_2.0_fast_vip', mode='m2v',
             refs=['sui', 'nanami', 'gym', 'sui_voice', 'nanami_voice_clean'],
             dialogue=[[1.0, 2.3, '岁己', '教练好。'],
                       [2.8, 5.5, '七海', '你好，今天带你训练。']],
             prompt=style + '\n'
             '回到现在的健身房，空间和暖窗光以{{gym}}为准，只有岁己和七海。'
             '岁己身份以{{sui}}为准，银白长卷双马尾、黑发绳、红瞳，'
             '穿敞开黑外套、白色红领边运动背心、红色白边运动短裤、白鞋、背小黑斜挎包。'
             '七海身份以{{nanami}}为准：棕色短双辫、蓝发挑染、黄笑脸夹、金瞳、'
             '藏蓝短袖运动衫、灰蓝运动长裤、白鞋和腕表。'
             '音频{{sui_voice}}仅绑定岁己声线；音频{{nanami_voice_clean}}仅绑定七海声线；'
             '不互换声音，不复读参考原話，七海的声音清亮自然、不能沙哑。'
             '0至1秒28毫米中景，岁己从左边玻璃门走进健身房，七海在右边等她。'
             '1至2.3秒岁己轻轻点头向七海打招呼，银白双马尾自然晃动。'
             '2.8至5.5秒切双人半身近景，七海对岁己笑着说今天带她训练，'
             '同时伸出空手朝训练区做友善引导手势。'
             '5.5至7秒岁己点头，两人往器械方向走，岁己拉开黑外套拉链准备脱下，'
             '七海自然侧身为她指方向，准备接到既有训练镜头。'
             '\n只有两句普通话，按以下时序准确说完：'
             '\n1至2.3秒岁己：“教练好。”'
             '\n2.8至5.5秒七海：“你好，今天带你训练。”'),
    ]
    plan = dict(
        output=produce.PLAN['output'],
        authorizedModels=produce.PLAN['authorizedModels'],
        references={
            'shiori': dict(type='image', title='栞栞·三维制服定妆·美甲师身份参考',
                           file=str(produce.ROOT/'outputs/sui-last-cookie-v2/shiori.png'),
                           importKind='external_generated'),
            'nanami_voice_clean': dict(type='audio', title='七海·已选CosyVoice版的干净声线参考',
                                      file=str(produce.OUT/'nanami-voice-repair/reference-clean-trimmed.wav')),
        },
        scenes=scenes,
        budgetSource=str(produce.STATE),
        intendedAssembly='Prepend the memory and greeting to the approved flirty soundtrack film.',
        preserveOriginalSeconds=90.8,
        uploadingAuthorized=False,
    )
    WORK.mkdir(exist_ok=True)
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    (WORK/'script.md').write_text(
        '# AI从业者遇到健身教练 · 新增前情\n\n'
        + '\n\n'.join('## '+s['title']+'\n\n' + '\n'.join(
            '**'+d[2]+'**：'+d[3] for d in s['dialogue']) for s in scenes),
        encoding='utf-8')
    print(json.dumps({'plannedSeconds':sum(s['duration'] for s in scenes),
                      'scenes':[s['id'] for s in scenes]}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['author', 'prepare', 'quote', 'run', 'status', 'download'])
    parser.add_argument('keys', nargs='*')
    args = parser.parse_args()
    if args.action == 'author':
        author()
    else:
        produce.PLAN = json.loads(PLAN_PATH.read_text(encoding='utf-8'))
        # Keep the original job and budget, but put new media in their own folder.
        produce.OUT = WORK
        produce.args = SimpleNamespace(keys=args.keys)
        with produce.FileLock(str(produce.STATE.parent/'.production.lock'), timeout=0):
            getattr(produce, args.action)()
