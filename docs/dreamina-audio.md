# Dreamina 纯音频与 RVC 实测

2026-09-16 使用 dreamina-canvas 1.0.1、当前账号和 cn 区域实测。

## 结论

model list --type audio 返回两个独立音频模型：

- legacy_tts / tts：文本转语音，固定音色通过 --voice-name 选择；
- seed_music_1.0 / music：音乐生成，时长为 30–360 秒。

当前 TTS mode 的实时规格是 references: 0，因此不能把岁己音频样例作为
声线参考上传。它是固定音色 TTS，不是任意声音转换。当前验证过的音色是
“温柔软妹”，48 字示例文本的报价是 **1 积分**。

实验使用音频节点，不经过 Seedance 视频生成：

    dreamina-canvas node create audio --project-id <ID> --mode tts --prompt <正文> --voice-name 温柔软妹

先保存节点并查询报价，再按已批准上限运行。结果资源可用 resource download 下载。
本次约 9.5 秒 MP3 的本地 ASR 检查基本还原了指定文本。

## 与 suiV2 的对比

同一段文本做了三个版本，并分别归一化响度：

1. Dreamina legacy_tts 的“温柔软妹”；
2. 相同 TTS 音频经过本机 RVC suiV2.pth 和 index，移调为 0 半音；
3. 已有 Seedance 参考岁己声线视频中的音轨，不新增生成。

两段正文相同，适合主观听感比较。RVC 不负责文字转语音，只负责把已有语音
转换到目标声线。当前实验保留原始 TTS 和转换后音频，生成了顺序播放的 A/B/C 文件。
音色自然度与相似度仍需听审，ASR 结果不能代替听感结论。

Canvas 1.0.1 完整命令 schema 未暴露独立的音频变声／克隆命令；
该账号画布音频节点的模型菜单也只显示 Seed TTS。这个结论只覆盖已检查的版本
与界面，不能据此断言即梦其他产品或后续版本都没有该能力。

## 与 Seedance 音频参考的区别

官方 dreamina CLI 的 multimodal2video --audio 是视频任务的音频参考，
输出仍是 MP4，并按视频价格计费。它适合生成需要镜头声音的视频，
不应当当作便宜的纯 TTS 路由。

可选组合：

- 独立旁白：Dreamina Canvas TTS → 可选本地 suiV2；
- 即梦镜头：Dreamina 视频生成，用于画面和需要的镜头声音；
- 完全离线：Windows SAPI 或其他本地 TTS → suiV2。

这里记录的是已完成的小样实验。当前框架的默认自动 TTS 后端仍由 config.json
配置；Canvas 纯 TTS 尚未接入自动旁白阶段。不要把凭据、RVC 权重和生成媒体提交到 Git。
