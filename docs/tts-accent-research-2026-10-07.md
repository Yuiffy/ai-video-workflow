# 岁己口音与说话习惯：本地 TTS 调研

查阅日期：2026-10-07。目标是岁己本人日常说话的音色、口音和韵律，不把“四川人”直接等同于必须讲浓重四川方言。

## 当前证据与结论

用户认为 IndexTTS-2.5 的 A/B/D 音色有些像，但鼻音偏重，语调听起来偏北方、东北。这是用户试听判断；尚无证据能把原因唯一归结为训练集、分离处理或参考片段。

优先比较 CosyVoice 3 的无指令克隆与四川话指令克隆，然后比较 VoxCPM2 的带转写续接式克隆。两者只是更符合问题的候选，不是已验证优于 IndexTTS。若个人习惯仍无法保留，再评估专人微调。

## 官方资料核查

| 方案 | 可核实的能力 | 对当前任务的意义与限制 |
|---|---|---|
| IndexTTS-2.5 | 参考音色、独立情绪参考、八维情绪、语速及拼音控制 | 官方没有给出专门的四川口音控制接口。`emo_text` 被转换成情绪向量，不能当成通用方言指令。换参考可实验，不能承诺迁移口音。 |
| Fun-CosyVoice3-0.5B-2512 | 支持含四川在内的中文方言/口音；`inference_instruct2` 接收参考音频和指令 | 最先试。官方控制列表确有四川话指令。需同时保留无指令克隆作对照，防止生成一般四川腔却失去岁己本人习惯。 |
| VoxCPM2 | 四川话、可控克隆、音频加转写的续接式克隆；SFT/LoRA | 第二候选。续接式克隆更贴近本轮要测的节奏/风格保留。官方列推理显存约 8 GB，不能当作训练需求或本机已验证结果。 |
| Qwen3-TTS Base | 参考音频加转写的克隆、单说话人微调 | 保留为备选。Base 的克隆接口不能与 CustomVoice/VoiceDesign 的指令控制混为一谈；只用说话人向量会舍弃参考音频代码与文本。 |
| GPT-SoVITS | 少样本微调、Windows 安装方案；当前仓库另有 V5 更新 | 可作专人训练候选；已有 RVC 模型不是 GPT-SoVITS 模型，不能直接替换。尚未找到足以证明其对岁己四川口音更好的对照证据。 |

来源：

- [IndexTTS 官方说明](https://github.com/index-tts/index-tts#usage-examples)：情绪与发音接口。
- [CosyVoice 官方仓库](https://github.com/QwenAudio/CosyVoice)：方言、模型版本及训练/推理入口。
- [CosyVoice 官方使用示例](https://github.com/QwenAudio/CosyVoice/blob/main/example.py)：参考音频与指令的正确调用方式。
- [CosyVoice 3 官方控制列表](https://github.com/QwenAudio/CosyVoice/blob/main/cosyvoice/utils/common.py)：`请用四川话表达。`。
- [VoxCPM 官方仓库](https://github.com/OpenBMB/VoxCPM)：四川话、两种克隆模式、显存及微调。
- [Qwen3-TTS 官方说明](https://github.com/QwenLM/Qwen3-TTS#voice-clone) 与 [微调文档](https://github.com/QwenLM/Qwen3-TTS/blob/main/finetuning/README.md)。
- [GPT-SoVITS 官方仓库](https://github.com/RVC-Boss/GPT-SoVITS)。

## 建议的实际验证

1. 选 3 段日常聊天原声，每段约 8–15 秒，人工确认代表性并校对逐字转写。这是本项目的实验设计，不是所有模型统一要求。不只用叫喊、撒娇或按钮短音效来代表她。
2. CosyVoice 3 先对比同一参考、同一文案下的无指令克隆与官方四川话指令。后者测试方言能力，不预设它就等于岁己的川普；“轻微四川口音”之类自由指令也不能未经实测就宣称有效。
3. VoxCPM2 对比纯参考克隆与参考音频加准确转写的续接克隆；前者可另测风格指令，避免混淆两个调用模式。
4. 用未出现在参考里的三种文本测试：自然聊天、情绪反问、视频解说。分别评价音色、地域口音、重音/尾音、错漏字和稳定性。第一轮相同种子，入围后再跨种子复测，避免只挑一次幸运输出。
5. 若仍不满意，先从现有素材筛选约 20–30 分钟校对过的普通聊天数据做专人微调试验，并独立留出验证片段。这是起步预算，不是保证有效的门槛；现有自动筛选语料并不等于可直接训练的准确 TTS 配对数据。

不要用 EQ、变调或增加“啥子”等词来替代对口音和韵律的验证。自然文案可以改善朗读感，但这同样不能证明地域口音已经学到。

## 已保存的诊断试听

`outputs/voice-studio/style-ab-20261007/accent/` 保存 E/F/G 及实验参数：E 是当前参考转写的同句复读；F 用素材库标注四川话的短片段作为完整参考；G 仅替换情绪参考。F/G 与 A 文案、语速和种子一致。音频生成完成并通过浏览器加载检查，尚未经过用户试听确认改善；未修改正式默认参考，未使用付费云接口。

社区案例仅作为风险线索：[CosyVoice #1308](https://github.com/QwenAudio/CosyVoice/issues/1308) 报告指令包装使用困惑；[VoxCPM #321](https://github.com/OpenBMB/VoxCPM/issues/321) 报告不同克隆模式产生口音差异。它们均不是针对岁己或四川口音的受控评测，不能据此判定模型优劣。
