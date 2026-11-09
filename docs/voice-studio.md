# 本地配音工作台

打开 **http://127.0.0.1:7899/**。重启电脑后，在仓库目录运行：

```powershell
.\tools\start_voice_studio.ps1
```

默认选择 **CosyVoice 3 本地模式（已选方案②）**。它读取目标人声参考，直接从文字合成旁白，不再默认经过 RVC，也不使用 MiniMax API 额度。页面中填写口播，点击“本地生成试听”，完成后可以播放与下载 WAV。

备用 IndexTTS 模型使用独立目录 `D:/workspace/fun/IndexTTS-2.5`，独立 Python 3.11 / CUDA PyTorch 环境。推理禁用 DeepSpeed、可选编译加速和 Qwen 情绪模型，使用 BF16。当前轻量接口跟随参考音频的语气，并支持语速调整；暂未提供独立情绪参考或情绪向量控件。

每次生成启动独立推理进程，包含模型加载耗时，结束后释放显存。下载完依赖后，工作台推理设置 Hugging Face / Transformers 离线模式，不需要上传参考音频。不要把接口支持离线理解为尚未下载的资产也能使用。

## MiniMax 可选连接

页面顶部展开“可选：MiniMax 云端连接”，填入国内开放平台的 API Key。保存只落盘，不调用语音合成。查询音色会访问当前 API 账户的音色列表；只有点击明确标为“付费生成试听”的按钮才发起云端语音生成，不自动回退云端。

Key 通过 Windows DPAPI 加密，只有保存时的 Windows 用户环境能够解密。页面 API 仅返回是否已保存，不返回密钥。配置位于被 Git 忽略的 `outputs/voice-studio/settings.json`，音频位于同目录的 `audio/`。跨电脑不能直接复制加密 Key 使用。也可由服务进程读取 `MINIMAX_API_KEY` 环境变量。

- [国内开放平台](https://platform.minimax.cn/)
- [账户余额](https://platform.minimax.cn/user-center/payment/balance)
- [按量价格](https://platform.minimax.cn/docs/guides/pricing-paygo)

本轮用户已选择本地优先，验证流程不调用付费云端生成。克隆费用与合成费用分开；此前填写的 Key 可以保留供以后手动选择云端。

## 命令行与视频工作流

```powershell
python -m src.tts --provider cosy --text '大家好，今天我们来聊聊这套视频制作流程。' --output outputs/voice-studio/sample.wav
```

视频工作流可在本地 `config.json` 添加：

```json
{
  "tts": {
    "provider": "cosy",
    "settings_path": "D:/workspace/myrepo/ai-video-workflow/outputs/voice-studio/settings.json"
  }
}
```

这段是需要合并的配置片段，不要用它覆盖其他已有配置。之后正常使用 `python -m src.cli voice <project.json>`。

没有外部源音频的场景会将完整旁白交给直接 TTS，跳过 RVC；当前每场景最多 3000 字符。场景语速使用 `scene.voice.speed`。已配置 `source_audio` / 已选择生成音频的场景继续沿用已有音频路径与 RVC 跳过规则，不会被强制重配。

缓存包含设置、参考音频内容哈希和本地验证版本标记，不含 API Key。字幕目前仍按文本长度分配时间，尚未实现词级强制对齐。最终音色与自然度需要试听，能成功生成不等于已经确认听感胜出。

## 验证

`tests/test_voice_studio.py` 检查 Windows 密钥加密、页面请求保护、API 不泄露 Key、云端不自动重试，以及完整场景直接 TTS 跳过 RVC 和缓存失效。测试使用假的云端响应，不产生费用。

本机模型实际验证信息保存到模型目录的 `workflow-verified.json`；页面只有检测到该标记、配置和运行时之后才显示“本地模型已验证”。本地失败的详细日志位于生成 WAV 同名的 `.log` 文件。

2026-10-07 备用 IndexTTS 本机验证通过：5080 / PyTorch 2.8.0+cu128 / Python 3.11.13，使用既有 9.54 秒岁己参考，离线生成 9.38 秒、22.05kHz 单声道 WAV。模型加载与生成计时 47.7 秒（不含 Python 导入时间），PyTorch 分配显存峰值约 5.59GiB。音频已通过解码、有限数值及非静音检查；尚不是人工听感评估。

代码固定在 `d9e41aac89fd00b3d71497fddb287b7f24613712`，主模型版本为 `c39ce5ba981572cb187443877ff559dfb246ce63`。网络下载使用 ModelScope 主权重与交大镜像 PyTorch wheel，分别核对了官方模型 SHA-256 和上游 `uv.lock` 中的 SHA-256。安装来源与依赖版本记录在模型目录的 `workflow-install.json`、`workflow-environment.txt`。现有本机 `config.json` 已启用 `tts.provider=cosy`，切换前配置保存在忽略目录 `outputs/voice-studio/config-before-cosy.json`。

## 已选默认：第②组 CosyVoice 3

本机另有独立环境 `D:/workspace/fun/CosyVoice3`，使用官方
`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`。模型及代码版本、依赖和实际生成结果分别记录在
该目录的 `workflow-verified.json`、`workflow-environment.txt` 和模型目录的
`workflow-model-manifest.json` 中。没有修改现有 IndexTTS / RVC 环境。

自然克隆调用 `inference_zero_shot`，提供连续日常参考音频及相应转写；CosyVoice 3
使用官方示例的 `You are a helpful assistant.<|endofprompt|>` 前缀，不附加地域口音指令。
参考素材优先追溯 ASR 说话人参考库的原始录音，再截取完整连续语句；避免直接把多段拼接的
说话人识别参考当成一段连续 TTS 提示。字幕和重新 ASR 交叉核对仍不能替代人工听审。

试听页位于 `http://127.0.0.1:7900/cosyvoice3/`，包含同参考、同文案的 IndexTTS 对照及
另一段日常参考。文件保存在忽略目录 `outputs/voice-studio/style-ab-20261007/cosyvoice3/`。
用户已选择第②组的 Cosy 聊天效果，现已接入工作台与视频工作流（`provider=cosy`）。
使用参考 1 `chat1.wav`，不是参考 2，也不是 CosyVoice 2。稳定副本位于
`outputs/voice-studio/references/sui-daily-chat.wav`，对应文字随本机设置保存。
采用自然零样本克隆、原速 1.0、种子 20261007、FP16、`text_frontend=True`（断句对照 B），
关闭 TensorRT / vLLM，不加方言指令或音色后处理。更换参考音频时须同步更新转写。
参考为连续日常聊天约 10.75 秒；选中的聊天试音约 11.36 秒，24kHz 单声道。
各本地引擎分别保存参考设置，可以在工作台切换。
首次初始化补下载了 WeText 文本处理资源；语音合成在本机进行，未上传参考音频或调用付费 API。

2026-10-07 断句对照反馈：用户认可 B（自动文本规范化）、C（手动整理数字与英文边界），D（只换种子）也可接受。默认采用 B，设置字段为 `cosy_text_frontend=true`，页面可切回原文模式。上游规范化还可能按句子边界拆分长稿；参考转写包含官方特殊前缀，保持原文。固定种子便于在当前环境复现，不代表所有文案都能获得理想停顿；这次短句改善不能替代长稿试听。对照文件位于 `outputs/voice-studio/style-ab-20261007/phrasing/`。

## 可选：Fish Speech S2 Pro

2026-10-13 用户试听反馈“感觉不错”，已将 Fish 加入工作台、命令行和视频配音引擎选项。它属于**支持音色克隆的 TTS**：输入文字、参考音频和参考原文，直接合成目标音色；RVC / Seed-VC 等变声器则接收已说好的音频，转换音色。Fish 输出不再经过 RVC。

在配音引擎中选择 **Fish Speech S2 Pro · 本地 · 音色克隆**，确认参考音频和对应文字后生成。参考默认复用已验证的岁己连续聊天片段，与 CosyVoice 的设置独立保存。可在口播稿中加入 `[excited]`、`[whisper]` 等标签；视频字幕会去掉这些控制标签与 speaker 标记。缓存会随 Fish 参考音频内容、转写或模型版本变化而失效。

```powershell
python -m src.tts --provider fish --text '[excited]今天的天气真不错，我们出去走走吧。' --output outputs/voice-studio/fish-sample.wav
```

视频项目使用时将 `tts.provider` 设为 `fish`。当前短段接口每次最多 300 字符、原速 1.0；超长稿或其他语速会明确报错，不会自动改用其他引擎。使用 4K 上下文、BF16 原始权重、分阶段 codec；生成 token 上限为 2048，若生成触达上限则拒绝交付截断音频。该上限不是已验证 95 秒长音频质量的承诺。

环境位于 `D:/workspace/fun/fish-speech`，模型为 `fishaudio/s2-pro`，模型加载约 4 分钟，16GB 显卡已验证短句克隆。详细安装、显存、速度、许可与试听文件见 [本地调研记录](fish-speech-local-20261013.md)。每份工作台输出还保存同名 `.fish.json` 性能记录与 `.log` 日志。当前默认引擎仍为已选的 CosyVoice 3。

工作台实际验证：浏览器选择 Fish、填写标签文案并点击生成，任务 `47ebbcbb705547169fdd94c6bf29b6c3` 成功返回 4.551 秒、44.1kHz WAV；浏览器音频 `readyState=4`，下载接口字节与落盘文件一致，Whisper 转写完整匹配正文。此轮准备耗时 298.48 秒，生成加解码 20.83 秒，峰值分配显存 9.19GiB；机器负载会影响速度，加载可能接近 5 分钟。证据位于 `outputs/fish-speech-20261013/voice-studio-integration.json` 与 `voice-studio-fish.jpg`。11 项配音工作台测试、14 项工作流测试及 JS 语法检查通过；包含 Fish 参考隔离、失败不回退云端、缓存失效和字幕去标签验证。

## B 站弹幕姬实时朗读（PM2）

`Re:TTSCat` 的自定义引擎会以 GET 下载完整音频，并把文件固定保存为 `.mp3`，因此本仓库提供了一个常驻 `SAPI + RVC v3` 适配服务。HTTP 监督进程长期在线；检测到 `Bililive_dm.exe` 后在后台预热模型，弹幕姬关闭时自动卸载。这样不会把首次弹幕的等待时间压给插件。之后按弹幕逐条合成、变声并缓存相同文本。

服务在 Windows 上通过 `pythonw.exe` 启动。SAPI 合成本和 MP3 编码都在常驻 worker 内完成，每条弹幕不会再启动 `sapi_tts.py`、FFmpeg 或其他子进程，因此从结构上消除了逐条黑色命令行窗口。弹幕姬运行时模型保持热态；弹幕姬退出后 worker 自动退出，把内存和显存还给系统。需要立即给视频任务腾出资源时可调用 `/unload`，该手动卸载不会在弹幕姬继续运行时被自动预热线程立刻撤销。

零窗口启动请双击 `tools\start_danmaku_tts_silent.vbs`。它通过 `wscript.exe` 和
`pythonw.exe` 直接调用 PM2 的 Node 入口，不打开 PowerShell、CMD 或 Node 控制台。
需要停止、重启、预热或查看状态时，可以给同一个 VBS 传入 `/stop`、`/restart`、
`/warm` 或 `/status`：

```powershell
wscript.exe ".\tools\start_danmaku_tts_silent.vbs" /restart
wscript.exe ".\tools\start_danmaku_tts_silent.vbs" /stop
```

调试时仍可使用下面这个带控制台的命令；正常登录启动不要使用它，而应创建指向
`wscript.exe "D:\workspace\myrepo\ai-video-workflow\tools\start_danmaku_tts_silent.vbs"`
的快捷方式。

```powershell
.\tools\start_danmaku_tts.ps1
```

静默启动器直接运行 `node.exe` 和 PM2 的 `bin/pm2` 脚本，不经过 `pm2.cmd`，并把
`PM2_HOME` 固定到当前用户的 `.pm2`，避免误用 `D:\etc\.pm2`。PM2 配置也显式设置了
`windowsHide: true`。启动器通过仓库根目录的 `ecosystem.danmaku-tts.config.cjs`
启动 PM2 进程，并执行 `pm2 save`。弹幕姬未启动时只保留约 22 MiB 工作集的监督进程，
状态返回 `cold`。然后在 `Re:TTSCat` 的“高级选项”中设置：

- TTS 引擎：`用户自定义引擎`
- 自定义 TTS 引擎 URL：`http://127.0.0.1:7910/tts?text=$TTSTEXT`
- 请求方法：`GET`
- 启用 URL 编码：开启
- HTTP 身份验证：关闭

服务只监听本机回环地址。运行日志位于 `outputs/danmaku-tts/`，音频缓存位于 `outputs/danmaku-tts/cache/`。停止服务：

```powershell
.\tools\start_danmaku_tts.ps1 -Stop
.\tools\start_danmaku_tts.ps1 -Restart
.\tools\start_danmaku_tts.ps1 -Warm
pm2 logs danmaku-tts
```

RVC 是变声而非独立 TTS，所以音色相似度受 SAPI 源声线影响。当前 `config.json` 使用 `sui_v3_48k.pth` 和对应的 48 kHz 索引，默认音高为 `+1`；URL 不写 `pitch` 时使用该默认值。这套服务优先保证弹幕队列的低延迟，不等同于工作台里 CosyVoice 直接克隆的听感。实测本机 CosyVoice 单条约需 45–75 秒，不适合直播。

本机实测冷启动监督进程工作集约 22 MiB、私有内存约 12 MiB。v3 worker 加载后工作集约 2.15 GiB、私有内存约 7.19 GiB；热请求约 1.6–2.1 秒，缓存命中低于 0.1 秒。worker 单次合成的内部耗时约为 SAPI 0.1 秒、RVC 1.4–1.8 秒、MP3 0.03–0.05 秒。建立索引缓存时冷加载约 37–40 秒，复用缓存后约 24–37 秒，取决于系统和 GPU 当前负载。插件不会一直等待冷加载，所以不能在首条弹幕到达时才启动模型；进程检测预热就是为这个限制保留的。

v3 原始索引约 1.12 GB、36.3 万条向量。RVC 原本会在每条请求中重新读取整个索引并重建向量表，无法满足实时使用。本服务第一次加载时将其抽样为 6.5 万条并写成约 302 MB 的本地 flat L2 / 向量缓存，之后模型进程直接复用，不再逐条重读大索引。该抽样是为低延迟弹幕做的速度取舍，不等同于离线高质量长音频也应使用同一配置。

直播前可以预热，避免第一条弹幕等待模型加载：

```powershell
Invoke-RestMethod 'http://127.0.0.1:7910/warm'
Invoke-RestMethod 'http://127.0.0.1:7910/unload'
```

弹幕姬未运行时，也可以设置不同的闲置回收时间，最小 30 秒：

```powershell
.\tools\start_danmaku_tts.ps1 -Restart -IdleUnloadSeconds 600
```

若不需要进程检测预热，可设置 `DANMAKU_TTS_AUTO_WARM=0` 后重启；此时第一条请求会承担完整的模型加载时间。

需要换 RVC 权重时可用 PM2 环境变量覆盖本机配置，不修改 `config.json`：

```powershell
$env:DANMAKU_RVC_MODEL = 'D:/path/to/sui_v3_48k.pth'
$env:DANMAKU_RVC_INDEX = 'D:/path/to/sui_v3_48k.index'
$env:DANMAKU_RVC_PITCH = '1'
.\tools\start_danmaku_tts.ps1 -Restart
```

模型加载期间仍会占用显存；如果同时运行视频生成或其他大型 TTS，可以调用 `/unload` 立即释放。插件下载不到音频时会按自身设置重试，所以直播前应预热，或先访问 `http://127.0.0.1:7910/health` 确认 `status` 为 `ready`。

## 声音方案对照页

启动配音工作台后打开 `http://127.0.0.1:7899/tts-choice`，可试听 RVC v2、当前 RVC v3、CosyVoice 3、IndexTTS 2.5 和 Fish Speech 的样例，并对照 MiniMax、VoxCPM2 与 GPT-SoVITS 的延迟、占用和适用场景。页面也能预热或立即卸载弹幕模型；选择与备注保存在 `outputs/voice-studio/tts-choice.json`。

```powershell
.\tools\start_voice_studio.ps1
```

`pm2 save` 会保存当前进程列表，但 Windows 登录后还需要执行一次 `pm2 resurrect` 才会恢复进程。可以把下面的命令放进登录启动项，或创建一个“登录时运行”的 Windows 计划任务：

```powershell
wscript.exe "D:\workspace\myrepo\ai-video-workflow\tools\start_danmaku_tts_silent.vbs"
```
