# Fish Speech 调研与本地测试

调研日期：2026-10-13。目标：安装并验证当前官方 Fish Speech / Fish Audio S2 Pro，在本机生成中文与参考音频克隆样例。

## 官方版本与能力

- 当前主分支项目版本为 2.0.0，推荐权重为 `fishaudio/s2-pro`。不能把旧 Fish Speech 1.5、OpenAudio S1 Mini 的教程和参数直接套用。
- S2 Pro 使用 Dual-AR：约 4B 慢速主干与约 400M 快速音频解码器。支持中文等多语言、短参考音频克隆、`[excited]` / `[whisper]` 等内嵌情绪标签，以及 `<|speaker:0|>` 多角色标记。
- 官方公开的 WER、自然度和 H200 吞吐是官方评测结果，不能视为本机、岁己音色或 Windows 的测试成绩。
- 官方安装页列出 Linux / WSL、24GB 推理显存；Windows / macOS 默认不支持 `torch.compile`。本次验证 Windows 原生、单请求、BF16 短音频推理。
- 代码和权重使用 Fish Audio Research License：个人评估与非商业研究可用，商业用途需要另外取得书面许可。安装不等于获得商业授权。

来源：[官方仓库](https://github.com/fishaudio/fish-speech)、[安装](https://speech.fish.audio/install/)、[推理](https://speech.fish.audio/inference/)、[模型卡](https://huggingface.co/fishaudio/s2-pro)、[许可](https://github.com/fishaudio/fish-speech/blob/main/LICENSE)、[技术报告](https://arxiv.org/abs/2603.08823)。

## 安装记录

- 独立目录：`D:/workspace/fun/fish-speech`；不修改现有 CosyVoice / IndexTTS 环境。
- 官方代码提交：`bdd39477922a89b904c6f2c7397f2a9bbcc60a0c`。
- 模型提交：`1de9996b6be38b745688de084d87a5633f714e4e`。
- Python 3.11.13；PyTorch / torchaudio 2.8.0 + CUDA 12.8。官方示例推荐 Python 3.12，项目元数据允许 >=3.10；本机复用已有、已校验的 cp311 CUDA wheel。
- RTX 5080，16303MiB 显存，驱动 616.92；推理开始前桌面程序约占 5.5GB。CUDA 12.8 包含 Blackwell 支持。
- S2 Pro 两个权重分片合计约 9.12GB，codec 约 1.87GB。全部文件大小与模型 API 对照，大文件 SHA-256 与官方 LFS oid 对照，记录见 `outputs/fish-speech-20261013/weights-verification.json`。
- `environment-freeze.txt` 保存完整安装版本。`uv pip check` 有一条已知元数据冲突：`descript-audiotools` 声明 protobuf<3.20，而官方 `pyproject.toml` 明确覆盖为 `protobuf>=3.20,<6`，实际为 5.29.6。保留官方覆盖，不为消除提示而降级；codec 的实际编解码作为运行兼容性证据。

安装命令（PowerShell，在 Fish Speech 目录内）：

```powershell
uv venv --python 3.11 .venv
uv sync --python 3.11 --extra cu128 --no-install-package torch
uv pip install --python .venv/Scripts/python.exe --no-deps D:/workspace/myrepo/ai-video-workflow/temp/tts-research-20261007/torch-2.8.0+cu128-cp311-cp311-win_amd64.whl
$env:HF_HUB_DISABLE_XET = '1'
uv tool run --from huggingface-hub hf download fishaudio/s2-pro --revision 1de9996b6be38b745688de084d87a5633f714e4e --local-dir checkpoints/s2-pro
```

没有本机 wheel 时，可使用官方的 `uv sync --python 3.12 --extra cu128` 完整安装。不要在上述复用 wheel 的安装之后直接执行 `uv sync --no-install-package torch`，它会移除以本地来源安装的 torch；需要先 sync，最后安装 wheel。

## 16GB 显存的测试方式

新增 `tools/fish_tts_worker.py`，从 Fish Speech 仓库工作目录、用它的 `.venv/Scripts/python.exe` 执行。调用原始官方模型和采样代码，没有量化或改写权重：

1. 官方权重默认 32768 上下文，36 层慢速模型的 BF16 KV 缓存约 4.5GiB。短音频使用官方 `from_pretrained(max_length=4096)` 接口，将上下文缓存缩为约 0.5625GiB。
2. 参考音频先由 codec 编码到 CPU token，释放 codec 后加载主干；主干完成全部文本采样后释放，再加载 codec 还原音频。
3. 模型初始化阶段使用 BF16 默认 dtype，避免先在系统内存临时初始化完整 FP32 主干。加载完成后恢复默认 dtype。
4. 不使用 `torch.compile`，固定 seed=42，temperature=0.8、top_p=0.9，最多 512 个新 token。检测 token 上限、空音频、非有限值与静音，输出性能和音频统计。

该入口用于短音频离线评估。4K 上下文不能代表官方 32K 长对话能力，阶段释放策略也不是常驻流式服务；官方 WebUI 的默认缓存仍可能超出本机当前可用显存。

## 复现测试

```powershell
Set-Location D:/workspace/fun/fish-speech
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
& .venv/Scripts/python.exe D:/workspace/myrepo/ai-video-workflow/tools/fish_tts_worker.py --request D:/workspace/myrepo/ai-video-workflow/outputs/fish-speech-20261013/smoke-request.json
& .venv/Scripts/python.exe D:/workspace/myrepo/ai-video-workflow/tools/fish_tts_worker.py --request D:/workspace/myrepo/ai-video-workflow/outputs/fish-speech-20261013/clone-request.json
```

测试目录：`outputs/fish-speech-20261013/`。参考为现有 `outputs/voice-studio/references/sui-daily-chat.wav`，10.75 秒、24kHz、单声道，转写取现有 Voice Studio 设置。本次无训练。

## 已验证的中文基础生成

`chinese-smoke.wav`：输入“你好，这是 Fish Speech 的本地中文语音测试。”，Whisper 转写“你好,这是Fish Speech的本地中文语音测试。”，去掉标点和空格后完全一致。44.1kHz、单声道，3.808 秒，无削波、非有限值或静音。

模型加载 226.54 秒，生成 22.67 秒，解码 1.03 秒，生成加解码 RTF=6.22；进程自身峰值 CUDA allocated=9.15GiB / reserved=9.30GiB。报告中的加载与总耗时从模型阶段开始计时，不包含前面的 Python import 时间。采样循环约 13 token/s，但首轮 CUDA 初始化与 prefill 也计入生成时间，因此不能用循环速度反推出完整请求速度。

通过 `py-spy dump` 核实首轮加载的大部分 CPU 等待处于官方模型 `_init_weights`：构造阶段随机初始化参数，随后才用 checkpoint 覆盖。权重加载日志为 `<All keys matched successfully>`，未启用编译。此模式可用于离线评估，当前速度不能当作实时配音服务。

## 克隆与情绪标签对照

同一参考音频、同一文案和 seed，对比无情绪标签与 `[excited]` / `[whisper]` 标签；使用原始 BF16 权重，未做训练或量化。

| 样例 | 音频时长 | 生成 + 解码 | RTF | ASR 字符错误率 |
| --- | ---: | ---: | ---: | ---: |
| `chinese-smoke.wav`，无参考中文 | 3.808 秒 | 23.698 秒 | 6.22 | 0% |
| `sui-neutral.wav`，岁己参考克隆 | 5.108 秒 | 10.939 秒 | 2.14 | 0% |
| `sui-emotion.wav`，同参考加情绪标签 | 4.551 秒 | 7.594 秒 | 1.67 | 0% |

两份克隆文案的可朗读文字都是“今天的天气真不错，我们出去走走吧。别着急，慢慢来就好。”，标签版在第一句前加 `[excited]`、第二句前加 `[whisper]`。两份转写均完整匹配文案，标签未被识别成朗读内容。三份输出均为 44.1kHz 单声道 PCM16，无非有限值、空音频、静音或削波，生成正常结束而未触达 512 token 上限。

克隆运行的模型准备耗时 241.44 秒（含参考编码），两个样例在同一模型加载中采样；进程峰值 allocated=9.19GiB / reserved=9.33GiB。此前观察的桌面 GPU 占用会变化，整卡总占用不能直接等同于进程峰值。

ASR 使用本机已缓存的 faster-whisper large-v3-turbo，CPU int8、beam=5、language=zh、关闭 VAD。比较时仅去除标点、空白、speaker/情绪标签并统一英文大小写；没有同义词替换。`asr-verification.json` 保存完整转写和参数。**0% 只适用于这三份短样例与这个识别器，不是模型总体 CER、人工听辨或音色相似度成绩。**

参考原音对已有设置转写的 ASR 差异为 4/47 字符（8.51%，例如“嘛/吧”“晃/换”）。这可能含 ASR 误差，本次保持已有参考转写，未自动改写。普通版与标签版 RMS 约为 -29.7dBFS / -30.4dBFS，响度低于无参考中文样例；试听时需注意音量差异，未额外做响度归一化。

## 结论与实际边界

当前 S2 Pro 已在本机 Windows + RTX 5080 16GB 原生环境完成中文生成、岁己参考克隆与情绪标签输入测试，三个测试样例均有有效音频，两个推理进程正常退出，模型代码工作树保持原样。

16GB 可用于本次 4K 上下文、单请求、分阶段 codec 的短句离线评估；不代表默认 32K、长音频、批量、流式服务或官方 WebUI 已通过。当前未编译速度慢于实时，模型准备需要约 4 分钟，并且会占用较多系统内存；若继续生产化，应另测加载优化、受支持的 Linux/WSL 编译或服务后端，以及完整长文稳定性。

音色相似度、四川口音迁移和情绪自然度仍需试听。本次没有做人类听感排名。用户随后试听反馈“感觉不错”，已将 Fish Speech 接入 Voice Studio、命令行和视频工作流的可选 TTS 引擎（`provider=fish`），保留已选默认 CosyVoice。工作台短段接口采用 4K 上下文、2048 token 上限、每次最多 300 字符与原速 1.0；性能表仍来自此前 512 token 上限的短句测试。音频、请求 JSON、运行日志、报告、权重校验和 ASR 核验均保存在 `outputs/fish-speech-20261013/`。
