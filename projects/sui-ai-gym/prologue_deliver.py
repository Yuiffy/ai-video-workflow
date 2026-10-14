"""Deliver the checked extended film and a local upload bundle, without posting."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

from prologue_edit import OUT, WORK, load, write_json
from sound_design import digest


def main():
    qa=load(WORK/'verification.json')
    timeline=load(WORK/'timeline.json')
    assert qa['visual_reviewed'] and qa['original_soundtrack_pcm_samples_unchanged']
    for movie in qa['files']:
        assert movie['full_decode']=='passed'
        assert movie['original_body_decoded_frames_unchanged']
        assert digest(OUT/movie['file'])==movie['sha256']
    credits=(OUT/'music-credits-flirty.txt').read_text(encoding='utf-8')
    (OUT/'music-credits-complete.txt').write_text(credits,encoding='utf-8')
    upload='''标题：岁己靠“做AI的”蒙混过关，直到遇上七海教练

简介（可直接复制）：
AI 二创小剧场：在美甲店靠一句“我是做AI的”轻松过关的岁己，
到了健身房，偏偏遇到真懂 AI 的七海教练。
栞栞出演美甲师。harness、Claude、站起来蹬、小视频……技术黑话越听越歪。

配乐与音效：
'''+credits+'''
建议标签：岁己、七海Nana7mi、栞栞Shiori、AI二创、虚拟UP主、搞笑、健身

投稿视频：sui-ai-gym-complete.mp4
封面：poster.jpg
视频已经烧录字幕；sui-ai-gym-complete.srt 可用于额外上传字幕。
规格：1280×720，30 fps，115.1 秒，H.264 / AAC，48 kHz 立体声。
'''
    (OUT/'bilibili-upload-complete.txt').write_text(upload,encoding='utf-8')
    prior=OUT/'sound-review-flirty.html'
    if not prior.exists():
        prior.write_bytes((OUT/'sound-review.html').read_bytes())
    page='''<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>岁己 × 七海 × 栞栞 · 完整前情版</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#151b22;color:#f5f2ec;font:16px/1.65 "Microsoft YaHei",sans-serif}
main{max-width:1100px;margin:32px auto;padding:0 24px}h1{font-size:28px;margin-bottom:8px}
p{color:#bdc8d6}a{color:#b9d7ff}video{display:block;width:100%;border-radius:12px;background:#000}
button{background:#293443;color:#e5efff;border:1px solid transparent;border-radius:7px;padding:10px 14px;cursor:pointer}
button:hover{background:#40516a}button[aria-pressed="true"]{border-color:#a4d4cc;background:#304d50}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.downloads{padding:16px 18px;background:#263341;border-radius:10px}
.downloads a{display:inline-block;margin:5px 15px 5px 0}.caption{font-size:14px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit;font-size:13px;line-height:1.7;color:#bdc8d6}
summary{cursor:pointer}details{margin-top:24px}footer{margin:24px 0;color:#8495a9;font-size:13px}
@media(max-width:680px){main{padding:0 14px;margin:20px auto}h1{font-size:23px}}
</style>
<main>
<h1>岁己 × 七海 × 栞栞 · 完整前情版</h1>
<p>先在美甲店蒙混过关，再遇上真懂 AI 的七海教练。1 分 55 秒。<br>
1:18 起渐渐切入暧昧萨克斯，陪着“小视频”的误会升级；对白期间音乐压低。</p>
<video id="film" controls playsinline preload="metadata" poster="poster.jpg" src="sui-ai-gym-complete.mp4"></video>
<nav aria-label="版本比较">
<button data-version="sui-ai-gym-complete.mp4" data-offset="24.3" data-label="完整前情版 · 字幕 + BGM + 音效" aria-pressed="true">完整前情版</button>
<button data-version="sui-ai-gym-bilibili-flirty.mp4" data-offset="0" data-label="上一版 · 90.8 秒" aria-pressed="false">上一版 · 对应剧情比较</button>
</nav>
<p class="caption" id="versionLabel" aria-live="polite">当前：完整前情版 · 字幕 + BGM + 音效</p>
<nav aria-label="剧情跳转">
<button data-time="0">美甲店回忆</button><button data-time="11.8">以后就这么回答</button>
<button data-time="17.9">见到七海教练</button><button data-time="24.3">开始训练</button>
<button data-time="46.8">Claude 露馅</button><button data-time="69.1">站起来蹬？</button>
<button data-time="77.1">暧昧配乐切入</button><button data-time="90.2">小视频误会</button>
<button data-time="103.5">结尾</button><button id="pauseFilm" type="button">暂停</button>
</nav>
<div class="downloads">
<strong>投稿文件</strong><br>
<a href="sui-ai-gym-complete.mp4" download>下载完整 MP4（含字幕）</a>
<a href="sui-ai-gym-complete-upload.zip" download>下载完整投稿包</a>
<a href="bilibili-upload-complete.txt" download>标题与简介</a><br>
<a href="poster.jpg" download>封面</a><a href="sui-ai-gym-complete.srt" download>字幕 SRT</a>
<a href="sui-ai-gym-complete-clean.mp4" download>无字幕版 MP4</a>
</div>
<p class="caption">投稿包内含完整视频、封面、字幕和可复制简介，已附配乐署名。</p>
<details><summary>配乐与音效来源</summary>
<p class="caption">Kevin MacLeod — Monkeys Spinning Monkeys / Mystery Sax（CC BY 4.0）；音效来自 Mixkit。</p>
<pre id="credits"></pre><a href="music-credits-complete.txt" download>下载完整署名</a>
</details>
<footer><a href="sound-review-flirty.html">查看上一版审片页</a> · 完整成片已导出，尚未投稿。</footer>
</main>
<script>
const film=document.getElementById('film');let generation=0,offset=24.3;
document.getElementById('pauseFilm').onclick=()=>film.pause();
document.querySelectorAll('[data-time]').forEach(b=>b.onclick=()=>{
 const target=Math.max(0,Number(b.dataset.time)-24.3+offset);
 film.currentTime=target;film.play().catch(()=>{});
});
document.querySelectorAll('[data-version]').forEach(b=>b.onclick=()=>{
 if(film.getAttribute('src')===b.dataset.version)return;
 const bodyPosition=film.currentTime-offset,wasPlaying=!film.paused,current=++generation;
 offset=Number(b.dataset.offset);film.pause();film.src=b.dataset.version;
 film.addEventListener('loadedmetadata',()=>{
  if(current!==generation)return;
  film.currentTime=Math.max(0,Math.min(bodyPosition+offset,film.duration));
  if(wasPlaying)film.play().catch(()=>{});
 },{once:true});
 document.querySelectorAll('[data-version]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
 document.getElementById('versionLabel').textContent='当前：'+b.dataset.label;
});
fetch('music-credits-complete.txt').then(r=>{if(!r.ok)throw Error(r.status);return r.text()})
 .then(t=>document.getElementById('credits').textContent=t)
 .catch(()=>document.getElementById('credits').textContent='请下载完整署名文件查看。');
</script></html>
'''
    (OUT/'sound-review.html').write_text(page,encoding='utf-8')
    (OUT/'complete-review.html').write_text(page,encoding='utf-8')
    names=['sui-ai-gym-complete.mp4','poster.jpg','sui-ai-gym-complete.srt',
           'bilibili-upload-complete.txt','music-credits-complete.txt']
    bundle=OUT/'sui-ai-gym-complete-upload.zip'
    with zipfile.ZipFile(bundle,'w') as z:
        for name in names:
            z.write(OUT/name,name,compress_type=zipfile.ZIP_STORED if name.endswith('.mp4') else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as z:
        assert z.testzip() is None and z.namelist()==names
    here=Path(__file__).resolve().parent
    project_path=here/'project.json'
    script_path=here/'script.md'
    if not (WORK/'project-before-extension.json').exists():
        (WORK/'project-before-extension.json').write_bytes(project_path.read_bytes())
        (WORK/'script-before-extension.md').write_bytes(script_path.read_bytes())
    original=load(WORK/'project-before-extension.json')
    plan=load(WORK/'production-plan.json')
    additions=[]
    for scene in plan['scenes']:
        chapter=next(c for c in timeline['chapters'] if c['scene']==scene['id'])
        cues=[c for c in timeline['subtitles'] if c['scene']==scene['id']]
        additions.append(dict(id=scene['id'],title=scene['title'],duration=chapter['duration'],
                              narration='\n'.join(c['speaker']+'：'+c['text'] for c in cues),
                              visual=scene['prompt'],image_prompt=scene['prompt'],
                              voice={'use_generated_audio':True,'local_replacements':
                                     'prologue/edit-decisions.json'},selected_take=scene['id']))
    project={**original,'scenes':additions+original['scenes'],
             'final_cut':dict(edit_decisions=str(WORK/'edit-decisions.json'),
                              timeline=str(WORK/'timeline.json'),movie=str(OUT/'sui-ai-gym-complete.mp4'))}
    write_json(project_path,project)
    old_script=(WORK/'script-before-extension.md').read_text(encoding='utf-8')
    text='# AI从业者遇到健身教练 · 完整前情版\n\n'
    text+='115.1 秒：美甲回忆 17.9 秒、健身房见面 6.4 秒，再接既有 90.8 秒正文。\n\n'
    text+='栞栞出演美甲师；七海的新招呼采用已选干净参考的本地 CosyVoice 3。\n\n'
    for scene in additions:
        text+='## '+scene['title']+'\n\n'+scene['narration']+'\n\n'
    text+=old_script[old_script.find('## 01_occupation'):]
    script_path.write_text(text,encoding='utf-8')
    delivery=dict(preview_url='http://127.0.0.1:8908/sound-review.html',film=qa['files'][0],
                  package=dict(file=bundle.name,bytes=bundle.stat().st_size,sha256=digest(bundle),files=names),
                  subtitle='sui-ai-gym-complete.srt',credits='music-credits-complete.txt',
                  duration=115.1,flirty_music_starts_at=78.0,added_quoted_credits=180,
                  cumulative_submitted_quotation=1404,uploaded=False)
    write_json(WORK/'delivery.json',delivery)
    print(json.dumps(delivery,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
