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
