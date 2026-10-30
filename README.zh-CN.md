# DeepSignal-S1-1.0

**面向交通信号控制的多模态 System One（系统一）模型：从路口视觉直接作出快速、结构化的控制决策。**

[English](README.md) | 简体中文

[模型](https://huggingface.co/AIMS2025/DeepSignal-S1) · [场景](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes) · [结果数据](results/fusion-2026-10-30.json) · [复现说明](docs/reproduction.md)

DeepSignal-S1 采用 **Jev 式结构化概率决策**路线：读取连续路口画面和信号状态，直接对候选控制动作给出概率并选择合法动作，而不是先生成长篇交通分析，再由外部程序解析文字。视觉理解与动作选择在同一个模型中完成，不依赖额外的YOLO车辆检测环节。

正式发布的 **DeepSignal-S1-1.0** 使用同一份融合权重控制南沙与Town10HD。项目围绕两个实际问题展开：正常视觉下，能否比已经冻结的工程固定配时更有效；摄像头失焦、运动模糊或机位变化后，能否比“目标检测＋最大压力控制”更稳健。

## 为什么是 System One

System One（系统一）强调快速、直接、可被软件调用的决策。[Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)与开源[OneJev](https://github.com/OmniJev/OneJev)体现了这一模型范式。DeepSignal-S1 将这种决策方式用于交通信号控制，当前推理接口直接返回动作及其概率，不逐字生成解释或推理过程；它不是调用商业Jev服务，也不把其他模型的性能归给本模型。

- **从视觉到控制：** 时序路口画面与当前信号上下文共同决定动作，无需人工提供实时车辆计数。
- **结构化输出：** 在当前合法动作中直接决策，信号执行器负责既定的绿灯尾段、黄灯和全红转换。
- **适应不同路口：** 同一模型覆盖南沙的丁字及十字路口和Town10HD场景，不为每个场景更换权重。
- **面向本地部署：** 使用未量化模型验证消费级GPU上的决策延迟，量化与边缘部署仍是后续工作。

<!-- FUSION_HIGHLIGHTS:BEGIN -->
- **正常控制有效：** 相对冻结工程固定配时，平均行程时间在南沙72案例降低 **18.17%**，在Town五类车流降低 **33.77%**。
- **特殊视觉稳健：** 固定机位偏移下，Town平均行程比YOLO+MP降低 **82.93%**；31像素运动模糊下，南沙降低 **30.14%**。
- **未量化本地推理：** RTX 5090共6823次模型请求，平均 **485毫秒**，中位数479毫秒。
<!-- FUSION_HIGHLIGHTS:END -->

## Town10HD：机位改变后仍直接决策

![Town10HD固定机位偏移](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/town-angle15.gif)

*Town10HD · 固定偏航±15° / 俯仰±8°。两臂使用同一交通计划并按相同仿真时刻对齐；60秒模拟窗口以5倍速播放。*

## 评测结果

以下使用交通领域常用的**平均行程时间（秒/车，越低越好）**。正常视觉比较S1、冻结工程固定配时和YOLO+MP三方；特殊视觉只比较S1与YOLO+MP。

<!-- FUSION_RESULTS:BEGIN -->
### 正常视觉：三方比较

| 场景 | 条件 | 案例数 | 控制方法 | 平均等待（秒/车） | 平均排队长度（辆） | 平均行程（秒/车） |
|---|---|---:|---|---:|---:|---:|
| 南沙 | 正常 | 72 | **S1** | 45.82 | 10.47 | 107.32 |
| 南沙 | 正常 | 72 | 工程固定 | 68.55 | 15.52 | 131.15 |
| 南沙 | 正常 | 72 | YOLO+MP | 未记录 | 未记录 | 109.36 |
| Town10HD | 正常 | 5 | **S1** | 20.45 | 3.56 | 38.22 |
| Town10HD | 正常 | 5 | 工程固定 | 40.46 | 5.40 | 57.70 |
| Town10HD | 正常 | 5 | YOLO+MP | 20.22 | 3.59 | 38.22 |

### 特殊视觉：S1与YOLO+MP

| 场景 | 条件 | 案例数 | 控制方法 | 平均等待（秒/车） | 平均排队长度（辆） | 平均行程（秒/车） |
|---|---|---:|---|---:|---:|---:|
| 南沙 | 失焦σ=9 | 9 | **S1** | 76.08 | 15.79 | 141.03 |
| 南沙 | 失焦σ=9 | 9 | YOLO+MP | 104.86 | 31.04 | 167.48 |
| 南沙 | 31像素运动模糊 | 9 | **S1** | 67.38 | 17.23 | 131.57 |
| 南沙 | 31像素运动模糊 | 9 | YOLO+MP | 124.59 | 30.18 | 188.34 |
| 南沙 | 固定偏航±15° / 俯仰±8° | 9 | **S1** | 63.68 | 15.44 | 129.04 |
| 南沙 | 固定偏航±15° / 俯仰±8° | 9 | YOLO+MP | 87.01 | 21.18 | 154.36 |
| 南沙 | 动态抖动峰值5° | 9 | **S1** | 63.40 | 16.17 | 128.25 |
| 南沙 | 动态抖动峰值5° | 9 | YOLO+MP | 72.15 | 17.91 | 137.61 |
| Town10HD | 失焦σ=9 | 5 | **S1** | 27.51 | 4.10 | 44.43 |
| Town10HD | 失焦σ=9 | 5 | YOLO+MP | 92.97 | 9.75 | 109.15 |
| Town10HD | 31像素运动模糊 | 5 | **S1** | 20.28 | 3.58 | 38.10 |
| Town10HD | 31像素运动模糊 | 5 | YOLO+MP | 111.26 | 10.24 | 127.71 |
| Town10HD | 固定偏航±15° / 俯仰±8° | 5 | **S1** | 19.23 | 3.45 | 37.11 |
| Town10HD | 固定偏航±15° / 俯仰±8° | 5 | YOLO+MP | 205.09 | 13.67 | 217.40 |
| Town10HD | 动态抖动峰值5° | 5 | **S1** | 19.13 | 3.32 | 37.20 |
| Town10HD | 动态抖动峰值5° | 5 | YOLO+MP | 21.49 | 3.53 | 39.88 |

**指标定义：** 平均等待包括正式评测车辆的停车等待和拥堵造成的入网等待；平均排队长度是共同发车窗口98—398秒内，受控进口车道停车车辆总数的时间平均，单位为辆，不是米；平均行程从计划出发计时。行程与等待按车辆数加权，排队按相同窗口的案例均值汇总。

南沙评估截止1298秒，Town截止518秒，未完成车辆的已耗时也计入，不能删除拥堵车辆后只报告已完成者。原始记录不变；等待和排队由原动作/灯态的SUMO重放补算，逐案例行程已核对。

南沙正常视觉YOLO+MP的72回合正在补跑完整日志；完成前这两项仍显示“未记录”，不推测或拿录像单例替代整批统计。
<!-- FUSION_RESULTS:END -->

南沙正常主表覆盖九个路口、预先确定的全部 **72** 个案例。特殊视觉小批范围更窄：南沙为种子97001的九个高流量均衡案例，Town10HD为种子18040的五类车流。这些是受控仿真结果，不代表统计显著、全面领先或任意真实道路都能复现。

录制案例展示真实视觉条件和控制行为，画面中的分数只属于该次录制；整体效果以以上配对表为准，不要求每个GIF案例都由S1获胜。

## 八组特殊视觉

<!-- FUSION_GALLERY:BEGIN -->
### Town10HD

#### Town10HD · 固定偏航±15° / 俯仰±8°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/town-angle15.gif" alt="Town10HD · 固定偏航±15° / 俯仰±8°">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/67b64f9e-47d5-47af-95d2-7ae426318c03"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/town-angle15.mp4)

#### Town10HD · 失焦σ=9

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/town-df9.gif" alt="Town10HD · 失焦σ=9">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/f6990fb6-bef9-4200-ab91-2ae09ce43782"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/town-df9.mp4)

#### Town10HD · 31像素运动模糊

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/town-mb31.gif" alt="Town10HD · 31像素运动模糊">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/366cd03c-7a6d-4c2d-89da-8a0314680d0d"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/town-mb31.mp4)

#### Town10HD · 动态抖动峰值5°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/town-shake5.gif" alt="Town10HD · 动态抖动峰值5°">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/13304020-699d-4deb-90fd-c4c074c20adf"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/town-shake5.mp4)

### 南沙

#### 南沙 · 固定偏航±15° / 俯仰±8°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/nansha-angle15.gif" alt="南沙 · 固定偏航±15° / 俯仰±8°">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/a71ed015-c2a2-4f48-b6a1-2cddfa2280a5"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/nansha-angle15.mp4)

#### 南沙 · 失焦σ=9

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/nansha-df9.gif" alt="南沙 · 失焦σ=9">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/7372c93c-ab9d-4413-afb8-be961502ceb5"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/nansha-df9.mp4)

#### 南沙 · 31像素运动模糊

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/nansha-mb31.gif" alt="南沙 · 31像素运动模糊">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/5c106b9c-bb21-403a-9d8a-8c6e0eb9b1d1"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/nansha-mb31.mp4)

#### 南沙 · 动态抖动峰值5°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v3/zh/nansha-shake5.gif" alt="南沙 · 动态抖动峰值5°">

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/62930adb-6543-4b10-894e-3867858ef9df"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/nansha-shake5.mp4)
<!-- FUSION_GALLERY:END -->

动图只展示模型实际看到的画面、实时交通指标与最近一次真实决策。**平均等待时间**是截至画面时刻，已进入车辆累计停车等待时间除以已进入车辆数，包含已经驶离的车辆。**排队车辆**是当前停车车辆数。两项动态统计包含共有预热车辆，来自已记录灯态的SUMO轨迹重放，并与录像逐帧核对；与主表正式车辆、含入网等待的汇总口径不同。底部平均行程只属于该录制回合，不替代整批结果。

展示案例全部为十字交叉口。视频改为控制器上下排列、各占整行，放大输入画面与决策面板；采用H.264基础配置、25帧/秒、模拟时间5倍速，不插造运动或决策。抖动GIF保留960像素宽，选取24秒模拟时间的短预览，不再缩小整个界面。每段视频另附大屏备用播放入口。

YOLO车道画线先在正常机位完成并冻结。`angle15`在画线后改变机位，整回合保持固定，不重新标定；`shake5`的偏航和俯仰峰值为5°，横滚峰值为2.5°。

<!-- FUSION_CLEAN_VIDEOS:BEGIN -->
### 正常视觉：南沙三方对比

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/4f915870-3ad5-41dd-8314-3b4850e8e51e"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/nansha-clean.mp4)

### 正常视觉：Town10HD三方对比

<video controls="controls" width="1280" playsinline="playsinline" src="https://github.com/user-attachments/assets/532d096f-047d-45b7-a5fa-eb8bb4f2a7ce"></video>

[大屏 / 备用播放](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v3/zh/town-clean.mp4)
<!-- FUSION_CLEAN_VIDEOS:END -->

## 推理性能

<!-- FUSION_LATENCY:BEGIN -->
| 范围 | 数量 | 平均 | 中位数 | P95 | 最大值 | 小于1秒 |
|---|---:|---:|---:|---:|---:|---:|
| 全部请求 | 6823 | 485.4 ms | 479.0 ms | 494.0 ms | 2304.0 ms | 99.08% |
| 每回合首请求 | 133 | 911.1 ms | 495.0 ms | 1460.2 ms | 2304.0 ms | 52.63% |
| 后续请求 | 6690 | 476.9 ms | 479.0 ms | 493.0 ms | 675.0 ms | 100.00% |
<!-- FUSION_LATENCY:END -->

当前未量化BF16模型读取时序路口画面。统计覆盖133个S1模型案例：南沙正常72案例和融合小批S1的61案例，不包含相机采集、渲染和控制执行。首请求包含初始化影响，后续请求更接近稳态；具体采样设置见复现文档。

**部署价值：** 消费级RTX 5090上的亚秒级稳态决策，使信控工作站成为切实可考虑的部署方向。同事另提供了未量化模型在**RTX 4090上约900毫秒**的观测，但测量条件尚未核对，因此不纳入正式统计。量化与边缘设备部署是后续优化方向，并非已经验证的能力；也不承诺所有请求都小于1秒。

## 下载与快速开始

模型与仿真资产下载分别需要申请审批。GIF、视频和结果数据在[DeepSignal-S1-Media](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media)免费公开，无需审批。当前版本沿用v3场景资产并配合GitHub最新代码；观看媒体无需下载场景包。

```bash
python3.12 -m venv .venv-inference
source .venv-inference/bin/activate
pip install -U huggingface_hub
hf auth login
hf download AIMS2025/DeepSignal-S1 --local-dir ./DeepSignal-S1-model

deactivate

git clone https://github.com/AIMS-Laboratory/DeepSignal-S1.git DeepSignal-S1
cd DeepSignal-S1
python3.10 -m venv .venv
.venv/bin/pip install -e '.[test,reproduction,download]'
```

模型服务、无需启动仿真器的真实三帧请求示例，以及闭环命令见[复现说明](docs/reproduction.md)。请下载完整模型目录；模型获批不代表提供远程托管API。从公开下载开始的完整闭环复跑尚未完成认证。

## 评测边界

- **唯一固定基线：** 冻结工程固定配时，南沙使用各路口工程表，Town10HD使用`31/6/31/6秒`。
- **信号转换：** 适用时保留5秒绿灯尾段，再执行3秒黄灯和2秒全红。
- **有限时域：** 未完成车辆仍计入，不能称为完整行程平均值。
- **南沙已知限制：** 首次立即切相后，旧红龄记账可能多算一个最小绿灯时段。双方沿用相同协议，但本小批不能视为控制协议已全面验收。

详见[融合评测说明](docs/fusion-pilot-evaluation.md)、[指标定义](docs/comparisons.md)和[素材交付说明](docs/media-delivery.md)。

## 历史版本

此前 `DeepSignal-S1-1.0-candidate` 的南沙结果和历史Town专用权重继续按原协议归档，不属于融合1.0权重及其成绩。见[历史发布结果](docs/released-results.md)。

联系：[dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
