"""Make the local final preview and a Bilibili upload bundle after verification."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from sound_design import OUT, WORK, digest

TITLE = '当岁己遇到真懂 AI 的七海教练，技术黑话越听越歪'
CREDITS = '''"Monkeys Spinning Monkeys" Kevin MacLeod (incompetech.com)
Licensed under Creative Commons: By Attribution 4.0 License
https://creativecommons.org/licenses/by/4.0/
原曲：https://incompetech.com/music/royalty-free/?isrc=USUAN1400011
处理：截取、均衡、淡入淡出、音量调整及对白期间自动降低音量。

音效：Mixkit — Sound Effects Free License
https://mixkit.co/license/#sfxFree
'''

PAGE = '''<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>岁己 × 七海 · 完成版</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#151b22;color:#f5f2ec;font:16px/1.65 "Microsoft YaHei",sans-serif}
main{max-width:1100px;margin:32px auto;padding:0 24px}h1{font-size:28px;margin-bottom:8px}h2{font-size:21px}
p{color:#bdc8d6}a{color:#b9d7ff}video{display:block;width:100%;border-radius:12px;background:#000}
button{background:#293443;color:#e5efff;border:1px solid transparent;border-radius:7px;padding:10px 14px;cursor:pointer}
button:hover{background:#40516a}button[aria-pressed="true"]{border-color:#a4d4cc;background:#304d50}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.downloads{padding:16px 18px;background:#263341;border-radius:10px}
.downloads a{display:inline-block;margin:5px 15px 5px 0}.caption{font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit;font-size:13px;line-height:1.7;color:#bdc8d6}
summary{cursor:pointer}details{margin-top:24px}footer{margin:24px 0;color:#8495a9;font-size:13px}
@media(max-width:680px){main{padding:0 14px;margin:20px auto}h1{font-size:23px}}
</style>
<main>
<h1>岁己 × 七海 · 完成版</h1>
<p>轻喜剧 BGM、误会音效和少量罐头笑声。说话时音乐降低，结尾轻轻抬起后淡出。90.8 秒。</p>
<video id="film" controls playsinline preload="metadata" poster="poster.jpg" src="sui-ai-gym-bilibili-ready.mp4"></video>
<nav aria-label="版本比较">
<button data-version="sui-ai-gym-bilibili-ready.mp4" data-label="完成版 · BGM + 音效" aria-pressed="true">完成版 · BGM + 音效</button>
<button data-version="sui-ai-gym-nanami-cosy.mp4" data-label="纯配音版" aria-pressed="false">纯配音版 · 同位置比较</button>
</nav>
<p class="caption" id="versionLabel" aria-live="polite">当前：完成版 · BGM + 音效</p>
<nav aria-label="剧情跳转">
<button data-time="0">从头播放</button><button data-time="22.5">Claude 露馅</button>
<button data-time="36.2">Astra 答案</button><button data-time="44.8">站起来蹬？</button>
<button data-time="65.9">小视频误会</button><button data-time="79.2">结尾</button>
</nav>
<div class="downloads">
<strong>上传文件</strong><br>
<a href="sui-ai-gym-bilibili-ready.mp4" download>下载完成版 MP4（含字幕）</a>
<a href="sui-ai-gym-bilibili-upload.zip" download>下载投稿包</a>
<a href="bilibili-upload.txt" download>标题与简介</a><br>
<a href="poster.jpg" download>封面</a><a href="sui-ai-gym.srt" download>字幕 SRT</a>
<a href="sui-ai-gym-bilibili-ready-clean.mp4" download>无字幕版 MP4</a>
</div>
<p class="caption">投稿包内含带字幕视频、封面、字幕和可复制的简介；简介已附配乐署名。</p>
<details><summary>配乐与音效来源</summary>
<p class="caption">BGM：Kevin MacLeod — Monkeys Spinning Monkeys（CC BY 4.0）。音效来自 Mixkit。</p>
<pre id="credits"></pre><p><a href="music-credits.txt" download>下载完整署名</a></p>
</details>
<footer><a href="voice-review.html?v=cosy">七海配音试听页</a> · 本轮新增即梦积分 0</footer>
</main>
<script>
const film=document.getElementById('film');
let generation=0;
document.querySelectorAll('[data-time]').forEach(button=>button.addEventListener('click',()=>{
  film.currentTime=Number(button.dataset.time);film.play().catch(()=>{});
}));
document.querySelectorAll('[data-version]').forEach(button=>button.addEventListener('click',()=>{
  if(film.getAttribute('src')===button.dataset.version)return;
  const position=film.currentTime,wasPlaying=!film.paused,current=++generation;
  film.pause();film.src=button.dataset.version;
  film.addEventListener('loadedmetadata',()=>{
    if(current!==generation)return;
    film.currentTime=Math.min(position,film.duration);
    if(wasPlaying)film.play().catch(()=>{});
  },{once:true});
  document.querySelectorAll('[data-version]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  document.getElementById('versionLabel').textContent='当前：'+button.dataset.label;
}));
fetch('music-credits.txt').then(r=>{if(!r.ok)throw Error(r.status);return r.text()})
  .then(text=>document.getElementById('credits').textContent=text)
  .catch(()=>document.getElementById('credits').textContent='请下载完整署名文件查看。');
</script>
</html>
'''


def flirty_page():
    page = PAGE
    for old, new in [
        ('sui-ai-gym-bilibili-ready-clean.mp4', 'sui-ai-gym-bilibili-flirty-clean.mp4'),
        ('sui-ai-gym-bilibili-ready.mp4', 'sui-ai-gym-bilibili-flirty.mp4'),
        ('sui-ai-gym-bilibili-upload.zip', 'sui-ai-gym-bilibili-flirty-upload.zip'),
        ('bilibili-upload.txt', 'bilibili-upload-flirty.txt'),
        ('music-credits.txt', 'music-credits-flirty.txt'),
        ('岁己 × 七海 · 完成版', '岁己 × 七海 · 暧昧喜剧版'),
        ('完成版 · BGM + 音效', '后半段暧昧萨克斯'),
        ('轻喜剧 BGM、误会音效和少量罐头笑声。说话时音乐降低，结尾轻轻抬起后淡出。90.8 秒。',
         '前半段轻喜剧，53.7 秒起渐渐切入暧昧萨克斯，陪着“小视频”的误会升级。对白期间自动压低音乐。90.8 秒。'),
        ('Kevin MacLeod — Monkeys Spinning Monkeys（CC BY 4.0）',
         'Kevin MacLeod — Monkeys Spinning Monkeys / Mystery Sax（CC BY 4.0）'),
    ]:
        page = page.replace(old, new)
    old_button = '<button data-version="sui-ai-gym-bilibili-ready.mp4" data-label="上一版 · 全程轻喜剧" aria-pressed="false">上一版 · 全程轻喜剧</button>\n'
    page = page.replace('<button data-version="sui-ai-gym-nanami-cosy.mp4"',
                        old_button + '<button data-version="sui-ai-gym-nanami-cosy.mp4"')
    page = page.replace('<button data-time="65.9">',
                        '<button data-time="52.8">暧昧配乐切入</button><button data-time="65.9">')
    return page


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=['comedy', 'flirty'], default='comedy')
    args = parser.parse_args()
    work = OUT / 'sound-design-flirty' if args.variant == 'flirty' else WORK
    verification = json.loads((work / 'verification.json').read_text(encoding='utf-8'))
    for movie in verification['files']:
        assert movie['full_decode'] == 'passed' and movie['video_matches_approved']
        assert digest(OUT / movie['file']) == movie['sha256']
    film = verification['files'][0]['file']
    suffix = '-flirty' if args.variant == 'flirty' else ''
    credits_name = f'music-credits{suffix}.txt'
    upload_name = f'bilibili-upload{suffix}.txt'
    bundle_name = 'sui-ai-gym-bilibili-flirty-upload.zip' if suffix else 'sui-ai-gym-bilibili-upload.zip'
    credits = CREDITS
    page = PAGE
    if suffix:
        credits = credits.replace('"Monkeys Spinning Monkeys" Kevin MacLeod',
                                  '"Monkeys Spinning Monkeys"\n"Mystery Sax"\nKevin MacLeod')
        credits = credits.replace('处理：', '另一首原曲：https://incompetech.com/music/royalty-free/?isrc=USUAN1700082\n处理：')
        page = flirty_page()
        backup = OUT / 'sound-review-comedy.html'
        if not backup.exists():
            backup.write_bytes((OUT / 'sound-review.html').read_bytes())
    upload_text = f'''标题：{TITLE}

简介（可直接复制）：
AI 二创小剧场：岁己遇到真懂 AI 的七海健身教练。
harness、Claude、站起来蹬、小视频……技术黑话越听越歪。

配乐与音效：
{credits}
建议标签：岁己、七海Nana7mi、AI二创、虚拟UP主、搞笑、健身

投稿视频：{film}
封面：poster.jpg
视频已经烧录字幕；sui-ai-gym.srt 可用于额外上传字幕。
规格：1280×720，30 fps，90.8 秒，H.264 / AAC，48 kHz 立体声。
'''
    (OUT / credits_name).write_text(credits, encoding='utf-8')
    (OUT / upload_name).write_text(upload_text, encoding='utf-8')
    (OUT / 'sound-review.html').write_text(page, encoding='utf-8')
    bundle = OUT / bundle_name
    names = [film, 'poster.jpg', 'sui-ai-gym.srt', upload_name, credits_name]
    with zipfile.ZipFile(bundle, 'w') as archive:
        for name in names:
            archive.write(OUT / name, name,
                          compress_type=zipfile.ZIP_STORED if name.endswith('.mp4')
                          else zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None and archive.namelist() == names
    delivery = dict(title=TITLE, preview_url='http://127.0.0.1:8908/sound-review.html',
                    film=verification['files'][0], package=dict(file=bundle.name,
                    bytes=bundle.stat().st_size, sha256=digest(bundle), files=names),
                    credits=credits_name, upload_text=upload_name, variant=args.variant,
                    added_dreamina_credits=0, uploaded=False)
    (work / 'delivery.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2),
                                      encoding='utf-8')
    print(json.dumps(delivery, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
