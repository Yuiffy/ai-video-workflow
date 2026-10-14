# 饼干岁飞盘大会

一段 16 秒的本地 Blender 3D 小动画：岁己拿饼干岁当飞盘，狗岁己扑起接住，
叼回来后被提醒「我是飞盘，不是晚饭」，最后三只角色跟 120 BPM 节奏一起弹扁。

成片、工程、配乐和审片图都在 `outputs/sui-frisbee-3d/`，该目录被 Git 忽略。

## 本机工具

- Blender 4.5.14 LTS：`D:/develop/Blender/blender-4.5.14-windows-x64/blender.exe`
- MMD Tools 4.5.14 已安装到 Blender 的 `user_default` 扩展库并启用，支持 PMX / PMD / VMD / VPD。
- 插件来源：<https://github.com/MMD-Blender/blender_mmd_tools>，固定标签 `v4.5.14`。
- FFmpeg / FFprobe：系统 PATH 中已有。
- Python 脚本使用现有的 NumPy / Pillow。

## 角色来源

主角使用用户下载的 `F:/fworkspace/workspace3d/Suifel_yora/Suifel.pmx`。
压缩包附带 Readme 标注：模型名 **Suifel**，作者 **Yora**，基于 **Kipfel** 改模。

- Yora：<https://space.bilibili.com/14999357>
- Kipfel 原模型：<https://booth.pm/ja/items/5813187>
- 饼干岁外观参考：`my-pixijs-game/public/images/materials/biscuit/饼干岁2.png`
- 视频参考：<https://www.bilibili.com/video/BV17jhj6sEbN/>，标题「［3D动画］小爱同学，六档全油」。

饼干岁、毛绒狗身体、小公园、关键帧、摄影、字幕和合成配乐均为本次编写。
狗岁己的头部来自同一份 Suifel 模型，保留原贴图。

## 重建

在仓库根目录，用 PowerShell 执行：

```powershell
$blender = 'D:\develop\Blender\blender-4.5.14-windows-x64\blender.exe'
& $blender --background --python-exit-code 1 --python projects/sui-frisbee-3d/inspect_import.py
python projects/sui-frisbee-3d/finish_video.py
& $blender --background --python-exit-code 1 --python projects/sui-frisbee-3d/build_animation.py -- --render
python projects/sui-frisbee-3d/finish_video.py
```

只检查场景时用 `--preview`，会输出 11 张动作关键帧。完整输出为 1920 × 1080、
24 fps、384 帧。脚本会覆盖同一输出目录的生成文件；不要把手工修改过的工程放在同名位置。

## 编辑工程

打开 `sui-frisbee.blend`，按数字键盘 0 看摄影机视图，空格播放。
所有动作已烘焙为普通关键帧，贴图和配乐已打包；播放不依赖脚本或 MMD 插件。
时间轴标记显示拿起、蓄力、扔出、扑接、返回和一起弹扁的时间。

- `Sui / thrower`：主角整体位置与弹性缩放，骨架上是扔出和表情动作。
- `Dog Sui / run & jump control`：狗的位移、跳跃和缩放。
- `Dog Sui / wag control`：尾巴；四个 `leg` 控制对象是跑步腿。
- `Biscuit Sui / frisbee & squash control`：饼干岁位置、旋转和变形。
- `Camera / animated little theatre`：镜头和正交摄影机缩放。

`finish_video.py` 会从 PNG 序列合成 H.264 / AAC MP4，附带中文烧录字幕、
轻量预览、独立字幕、关键帧联络表和本地观看页。视频时长和音频均为 16 秒。

在浏览器中观看并拖动进度条：`python projects/sui-frisbee-3d/serve_review.py`，
然后打开 <http://127.0.0.1:8770/watch.html>。该服务只监听本机，并支持媒体字节范围请求。
