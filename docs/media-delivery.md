# 融合版素材交付 / Fusion Media Delivery

不制作最终90秒成片，不添加旁白。公开交付以可复用原始媒体、结果图和元数据为主。

## HF数据集媒体

目录：`media/fusion-1.0/`

- 代表GIF：`nansha-mb31.gif`、`town-angle15.gif`
- 完整GIF：`{nansha,town}-{df9,mb31,angle15,shake5}.gif`
- 正常视觉视频：`nansha-clean.mp4`、`town-clean.mp4`

公开URL前缀：

```text
https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes/resolve/main/media/fusion-1.0/
```

GIF用于README和模型卡内嵌。每个GIF画布为960×540，内部已经左右排列S1与YOLO+MP，并同时展示交通总览、模型实际输入和指标，因此代表GIF必须逐个全宽显示，不能再将两个GIF横向并排压缩。

每个GIF覆盖60秒模拟时间，默认5倍速播放为约12秒。窗口按两臂**合计在网车辆数**最高的60秒区间自动选择；若多个窗口达到同一最高密度，选择时间最早的并列窗口。该规则不查看控制器优势，也不根据胜负挑选展示时段。最初计划中的“可见车辆数量”在实现中采用active在网车辆密度作为代理，并非逐帧目标检测可见数。

录制案例展示真实条件与闭环行为，不保证单个GIF中S1获胜。新录制的南沙J08失焦σ=9案例中，S1为133.73、YOLO+MP为133.27，S1略差0.35%；原批次同案例为110.46与133.27。两次闭环在仿真25.1秒已出现首次动作分歧，早于120秒录像起点，因此不能把录像片段视为原批次轨迹的重放。录制分数与批次分数严格分开，主页整体效果以预定配对表为准。

已用5个相同图像、相同state的请求比较research与public推理路径，动作一致且全部动作概率最大差为0；正式HTTP按A-C-A顺序重复调用也保持稳定。当前没有发现权重打包或推理路径不同。独立闭环中的观测或渲染初始化差异尚未精确定位，不据此声称已经找到具体TAA原因。预选案例不因录像胜负更换；其余22个素材继续按原计划处理，不因该单例重录或筛选赢家。

公共MP4保留180秒素材，用于下载、后续剪辑和核对，不是最终90秒成片，也不添加旁白。正常视觉三方比较为2880×1080，依次展示S1、冻结工程固定配时和YOLO+MP；特殊视觉双方比较为1920×1080，展示S1与YOLO+MP。输出完成后，媒体目录中的index记录每项素材的条件、控制器、分辨率、时长与文件名。不得把旧candidate或历史Town专用权重的视频改名成融合1.0素材。

## 结果图

GitHub目录：`assets/results-fusion/`

- `normal.{png,svg,pdf}`：正常视觉三方比较
- `extreme.{png,svg,pdf}`：特殊视觉双方比较
- `degradation.{png,svg,pdf}`：相对正常视觉退化
- `latency.{png,svg,pdf}`：三帧模型请求延迟

GitHub README使用相对路径；HF模型卡使用GitHub raw绝对地址。图中南沙和Town保持独立指标范围，不能为了视觉统一而合并绝对值。

重画结果图前安装 `.[plots]` extra，其中要求Matplotlib 3.9或更高版本。中文图需要系统安装Noto Sans CJK SC；英文图不依赖中文字体。

## 数据来源

所有公开表图从 `results/fusion-2026-10-30.json` 生成。该文件记录来源实验、逐案例相对记录路径、指标值、失败状态、模型、时域、车辆数和到达数，不包含本机内部绝对路径。外部clone直接运行 `python scripts/render_fusion_pages.py` 只更新中英文README。发布者额外运行下列命令更新模型卡，并同步HF公开目录：

```bash
python scripts/render_fusion_pages.py --model-card .local/HF_MODEL_CARD.md
```

场景资产继续沿用 `DeepSignal-S1-Scenes-v3.tar.gz`，只上传新增 `media/fusion-1.0/` 与元数据，不重新传输27.60 GiB大包。
