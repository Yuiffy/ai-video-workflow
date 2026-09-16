# AI Video Workflow

一个可自托管、可替换供应商的 AI 视频制作工作流：剧本 → 网页 PPT → 本地 RVC 声音 → 即梦/Seedance 画面 → FFmpeg 合成。

第一期示例是《鹿饼暖心回复发展史》，用来讲解 `danmaku-to-summary-ts` 从人工让 GPT 网页写回复，逐步发展到可复用的直播摘要、字幕、漫画和切片系统。

## 设计目标

- **供应商可替换**：即梦 CLI、RVC 服务、LLM 和 FFmpeg 都是适配器；没有服务时可以 `--dry-run` 生成确定性的执行计划。
- **本地优先**：RVC 通过本地 HTTP 服务调用；旁白可以使用同一个服务的 TTS 接口；原片已有声线参考时可以跳过变声。
- **网页即 PPT**：每个章节是一个普通 HTML 页面，可在浏览器里预览，也可用 Playwright + FFmpeg 录制成视频。
- **人工可审阅**：每个阶段都写入 manifest，保留提示词、输入、输出和状态，不自动发布。

## 快速开始

```powershell
cd ai-video-workflow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 只生成计划、剧本旁白和即梦任务，不调用外部服务
python -m src.cli plan projects/development-history/project.json --dry-run

# 录制网页 PPT（需要安装 Playwright 浏览器）
python -m playwright install chromium
python -m src.cli record projects/development-history/project.json

# 合成已有素材
python -m src.cli render projects/development-history/project.json
```

完整配置复制 `config.example.json` 为 `config.json`。Windows 上可以把 `<RVC_ROOT>` 替换为本机 RVC 目录；`dreamina.exe` 需要在 PATH 中，或把 `jimeng.executable` 改成绝对路径。

## 目录

```text
ai-video-workflow/
├── src/
│   ├── cli.py              # plan / voice / record / render / run
│   ├── models.py           # 项目、分镜、素材合同
│   ├── pipeline.py         # 阶段编排与 manifest
│   ├── rvc_client.py       # 本地 RVC TTS/变声 HTTP 适配器
│   ├── jimeng_cli.py       # 即梦 CLI 适配器
│   ├── ppt_recorder.py     # Playwright 网页 PPT 录制
│   └── media.py            # FFmpeg 检查和合成
├── projects/development-history/
│   ├── project.json        # 第一个视频的完整输入
│   ├── script.md           # 可人工编辑的旁白稿
│   ├── storyboard.json     # 即梦镜头提示词和网页章节
│   └── ppt/index.html      # 可直接录制的科普网页 PPT
└── .agents/skills/...      # Codex 操作本工作流的技能说明
```

## 外部适配器

### RVC

框架不绑定某个 WebUI。默认支持 HTTP 服务，也支持本机 RVC WebUI 的离线命令桥接。离线模式会先用 RVC 运行时自带的 `edge-tts` 生成语音，再调用 `tools/rvc_convert.py` 加载 `suiV2.pth` 和 index 转换声线；权重永远留在本机，不进入 Git。

如果你自己运行 HTTP 服务，只要提供以下兼容接口即可：

```text
POST /api/tts       JSON {text, speaker, speed} -> audio/wav 或 {audio_path}
POST /api/convert   multipart audio + JSON {speaker, pitch} -> audio/wav 或 {audio_path}
GET  /health
```

通过 `config.json` 的 `rvc.tts_path`、`rvc.convert_path` 调整路径。若输入音频已经带有目标声线参考，在 scene 中设置 `voice_reference: true`，流程会记录并跳过 convert。

### 即梦 / Seedance

`jimeng.command` 是一个参数模板，例如：

```json
"command": ["jimeng", "generate", "--model", "{model}", "--prompt", "{prompt}", "--ratio", "{ratio}", "--duration", "{duration}"]
```

框架只负责生成任务清单和调用命令，不猜测具体 CLI 的登录、VIP 或上传行为。当前示例默认 `seedance2.0fast_vip`，可改成 `seedance2.0mini`。

## 许可

MIT。外部模型、图片、声音和平台服务遵循各自条款；发布前请确认素材授权和声音使用权。
