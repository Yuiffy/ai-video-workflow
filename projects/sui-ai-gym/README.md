# AI从业者遇到健身教练

运动岁己遇上真正懂AI的七海教练，被职业追问和技术黑话逐渐带进误会。
剧本见 `script.md`，逐段台词与动作源见 `project.json`，镜头提示词和参考素材见 `production-plan.json`。

本次授权仅使用 Seedance 2.0 mini 或 Fast VIP，总积分上限2000。
人物定妆和场景参考由内置 imagen 生成；运动岁己沿用已有三视图。
岁己和七海分别上传真实声线参考，七海参考来自本地本人直播的正常说话段。

成片、声线参考、原始视频、审片帧、字幕、剪辑时间轴和可恢复任务身份都在
`outputs/sui-ai-gym-20261012/`（Git 忽略目录）。
训练镜头使用独立修正版参考，防止黑外套在镜头末尾突然出现；结尾镜头穿回外套后一同离开。

```powershell
python projects/sui-ai-gym/produce.py status
python projects/sui-ai-gym/produce.py download
python projects/sui-ai-gym/qa_media.py
python projects/sui-ai-gym/finalize_edit.py
python projects/sui-ai-gym/assemble.py --render
python projects/sui-ai-gym/verify.py
python projects/sui-ai-gym/verify.py --mark-reviewed
python projects/sui-ai-gym/deliver.py
```

`produce.py run` 只接受从未尝试提交的镜头，并把逐项报价计入总预算。
已有任务只能用相同提交身份查询；更换模型或重拍要另建镜头键，保留原片。
`author.py` 和 `repair.py` 用于编写草稿，不应在已受理镜头上覆盖提示词。
后续可根据 `timeline.json` 和 `edit-decisions.json` 仅升级指定片段。

最终剪辑为90.8秒、720p、30fps，七章24句字幕，另有无字幕版本和SRT/ASS。
第4段实际多出一句害羞的内心反应，保留并同步字幕；第6段另拍清晰台词版，
采用“我在本地跑了一套MiniMax H3”，其余原剧情完整保留。
本次累计提交报价1224积分，授权上限2000；此数字不是已核实的最终净结算。
两个角色分别使用本人的声线参考；自动检查使用ASR，不代表完成真人听感评价。

`verify.py` 检查完整视频解码、准确帧数、音画时长、字幕边界、来源哈希、
生成终态、预算和导出后的独立无提示词ASR，并输出逐章字幕帧和转场接触表。
必须实际查看这些图后再执行 `--mark-reviewed`；交付脚本会核对视频哈希和此记录。
`author.py` / `repair.py` 是初稿工具；后续重拍用新镜头键追加，禁止覆盖已受理草稿。

## 七海声音修改

用户试听后认为 Seed-VC 直接换声沙哑、风格转换仍不像，更偏好 CosyVoice 3
小样的后半段，但指出前奏带背景音乐。后续采用本地 CosyVoice 3：先分离参考
背景声并裁掉非说话头尾，再生成、核对和裁剪配音，按原句时长对齐。
“能制作视频拿去卖钱”采用初次生成中台词准确的版本，并单独清理其背景。
没有调用岁己的专属 RVC/Seed-VC 权重，也没有更改全局配音设置。

新成片另存为 `sui-ai-gym-nanami-cosy.mp4` / `sui-ai-gym-nanami-cosy-clean.mp4`，
与声线处理记录、用户试听反馈和检查结果一起保存在原输出目录。
`voice-review.html` 可切换原版和修改版的同一位置，也提供原速单句试听。
本次只使用本地模型，新增即梦积分为 0；主观声线相似度仍由用户试听确认。

重制脚本为 `repair_voice.py`、`voice_candidates.py`、`check_voice_candidates.py`
和 `verify_voice_repair.py`。模型通过各自已经验证的 Python 环境运行，CUDA 工作
按顺序执行。`nanami-voice-repair/` 保存模型与参考哈希、选片、裁剪、变速、
混音记录、原始/处理后的人声和背景轨，便于回退及局部修正。
最终检查包含视频流哈希和帧数、完整解码、各章及 11 句七海语音的独立 ASR，
并验证替换窗口之外的混音 PCM 样本完全不变；ASR 不等于真人听感验收。

## 完整前情与配乐版

最终完整片为 115.1 秒：新增 17.9 秒美甲回忆（栞栞出演美甲师），
再用 6.4 秒让岁己和七海见面，接回已经选定的 90.8 秒健身正文。
美甲回忆交代岁己隐瞒虚拟主播身份、用“我是做AI的”应付询问，
并得意地决定以后继续这样回答。见面台词为“教练好”和“你好，今天带你训练”。
新增的“虚拟主播”独白和七海招呼用本地 CosyVoice 3 处理；旧正文配音保留。

配乐采用 Kevin MacLeod 的 Monkeys Spinning Monkeys 和 Mystery Sax（CC BY 4.0），
1:18 起淡入暧昧萨克斯。音乐在台词期间降低音量，保留此前的喜剧音效和罐头笑声。
完整片有 10 章、33 条字幕、3453 帧，H.264 / AAC、720p、30 fps、48 kHz 立体声。
带字幕与无字幕版本、投稿包、署名和可复制简介都保存于原输出目录，尚未投稿。

```powershell
python projects/sui-ai-gym/prologue_produce.py status
python projects/sui-ai-gym/prologue_produce.py download
python projects/sui-ai-gym/prologue_qa.py
python projects/sui-ai-gym/prologue_edit.py
python projects/sui-ai-gym/prologue_verify.py
# 实际查看导出的字幕帧和转场接触表后：
python projects/sui-ai-gym/prologue_verify.py --mark-visual-reviewed
python projects/sui-ai-gym/prologue_deliver.py
```

新增生成身份、计划和审片记录在 `prologue/`；原画布、参考和总预算仍由 `job.json` 管理。
新增三镜头提交报价 180 积分，累计提交报价 1404，剩余授权额度 596；
这些是提交报价累计，不是已经核实的净结算。不得因轮询超时再次提交。
完整导出检查证明旧正文的每一帧和混音 PCM 均保留，字幕整体后移 24.3 秒；
新增台词经过独立无提示词 ASR，导出字幕帧和转场已经查看，听感由用户审片确认。
