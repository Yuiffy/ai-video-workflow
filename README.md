# AI Video Workflow

把 **Codex 剧本、HTML 技术图解、Dreamina / Seedance 镜头和本地 TTS → RVC 旁白**
合成一条有声音、有字幕、有章节的视频。适合项目发展史、科普和需要准确图表的讲解视频。

第一期：[鹿饼暖心回复发展史](projects/development-history/script.md)。
从人工让 GPT 网页写晚安，讲到弹幕整理、ASR、Webhook、漫画与自动切片。
[史料与 Git 提交依据](projects/development-history/sources.md)随示例维护。

[第二版](projects/development-history-v2/script.md)进一步解释上下文取舍、Prompt 演变、
漫画参考、两种构图、多人配置和发送时机，配套可按时间播放的原理动画。
[纯音频实验](docs/dreamina-audio.md)区分 Canvas TTS、suiV2 变声与 Seedance 音频参考。

## 安装

需要 Python 3.11+、FFmpeg / FFprobe。当前已在 Windows 上验证；
测试中的 HTML 与媒体渲染也在 Linux CI 运行。

```powershell
git clone https://github.com/Yuiffy/ai-video-workflow.git
cd ai-video-workflow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
Copy-Item config.example.json config.json
```

编辑本地 `config.json`：

- `jimeng.executable`：官方 `dreamina` CLI 的路径；登录交给 CLI 自己管理。
- `jimeng.images`、`audio_references`：本地参考文件。无图片时使用文生视频；
  有图片时使用全能参考。当前适配 `seedance2.0fast_vip` 和 `seedance2.0mini` 的 720p。
- `rvc.runtime_python`、`rvc.rvc_root`、`model`、`index`：已有 RVC WebUI 安装和模型。
  模型名相对于 RVC 的 `assets/weights/`，index 可为空。
- 默认 TTS 命令使用 Windows SAPI 慧慧，再由 RVC 变声。SAPI 桥接需要该 Python
  环境中的 `pywin32`。也可换成返回 WAV 的 TTS 命令或本地服务。

**RVC 本身是语音转换模型，不是文字转语音模型。** 文生旁白要先有 TTS，
再把合成声音交给 RVC。无需修改既有 RVC 安装或启动 WebUI。

```powershell
python -m src.cli doctor
python -m src.cli plan projects/development-history/project.json --dry-run
```

模型、声线、参考图和生成的视频不包含在源码仓库中。
`config.json`、`outputs/` 和 `temp/` 均被忽略。

## 制作视频

```powershell
# 提交新镜头，或继续查询已有 ID。会产生生成费用。
python -m src.cli jimeng projects/development-history/project.json

# 刷新远端状态并下载结果；只查询，不新建任务。
python -m src.cli poll projects/development-history/project.json

# 生成逐句 TTS，转换声线，记录准确的句段时间。
python -m src.cli voice projects/development-history/project.json

# 合成：每章先播放即梦片段，再接 HTML 图解，完整保留旁白。
python -m src.cli render projects/development-history/project.json
```

也可以使用 `run` 串联上述阶段。远端生成还在进行时退出码为 2，
稍后重新执行相同命令即可继续；完成的语音和画面会复用。
所有执行命令的 `--dry-run` 只写计划，不调用供应商。
用 `--scene opening` 可限定语音或镜头阶段。

每次付费提交前写入意图，得到提交 ID 后立即保存；CLI 超时不自动重提。
如果程序在收到 ID 前中断，用 Dreamina 的任务列表找回 ID，然后：

```powershell
python -m src.cli adopt projects/development-history/project.json --scene opening --submit-id <ID>
```

修改提示词不会自动购买新版本。要新拍一个镜头，可新增 scene ID，或使用新项目输出目录。
项目输出目录有进程锁，避免两个命令同时提交同一份工作。

## 本地 RVC 服务

```powershell
python -m src.voice_service --config config.json --port 7898
```

服务只监听 `127.0.0.1`。客户端将 `rvc.mode` 改成 `http`，
`base_url` 改为 `http://127.0.0.1:7898`。服务内部仍调用配置中的本地命令。

| 接口 | 输入 | 输出 |
| --- | --- | --- |
| GET /health | 无 | 当前模型、忙闲状态 |
| POST /api/tts | JSON：text、speed | WAV 字节 |
| POST /api/convert | JSON：audio_base64、pitch | WAV 字节 |

服务串行处理模型请求，每次转换结束释放子进程。若需要更高吞吐，
可用常驻模型服务替代这个桥接器。

已有音频通过 scene 的 `voice.source_audio` 指定。
如果要保留即梦生成的声音，设置 `voice.use_generated_audio: true`。
确认音频已是目标声线时，再设置 `voice.already_target_voice: true` 跳过 RVC。
`voice.reference_audio` 只作为 Dreamina 的音色参考；仅有参考文件不自动跳过旁白生成。

## 网页作为 PPT

示例是离线 HTML，方向键或空格翻页。每页展示一个技术概念。
新网页只需提供 `[data-slide]` 元素和：

```javascript
window.renderAt = ({ slide, time, duration }) => {
  // 显示从 0 开始的 slide，并把动画设置到 time 秒。
};
```

录制器用显式帧时钟渲染 HTML，再编码成视频，避免真实时间录屏的加载空白和计时漂移。
`record` 命令只使用网页画面与旁白；`render` 混合即梦和网页。
旁白长度决定每章时长，不会为了匹配 10 秒镜头截断声音。
成片为 H.264/AAC MP4，并包含烧录字幕、SRT 文件、章节和编辑时间轴。

Codex 工作流见 [.agents/skills/ai-video-workflow/SKILL.md](.agents/skills/ai-video-workflow/SKILL.md)。
Codex 负责研究、写稿、分镜和网页设计；框架不额外绑定一个付费 LLM API。

## 验证与边界

```powershell
python -m unittest discover -s tests -v
```

测试覆盖付费任务恢复、未知提交结果、重复请求锁、声线跳过、HTTP 音频传输，
以及真正的浏览器 → FFmpeg 有声合成。单元测试不调用付费服务。
独立搭建的原因和参考项目见 [设计说明](docs/design.md)。

当前 TTS 默认是 Windows SAPI，语气比较平实；RVC 改变声线，不会自动提高口播表现。
外部输入音频只有整段字幕时间，精细字幕需要额外对齐；TTS 输入有逐句计时。
输出视频在本地供审核，不自动发布到 B 站。
本项目源码为 MIT；外部模型、参考图、声音和生成媒体保留各自使用边界。
