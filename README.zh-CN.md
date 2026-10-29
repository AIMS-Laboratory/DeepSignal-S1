# DeepSignal-S1

**One system：从视觉交通观察到信号决策的一体化系统。**

[English](README.md) | 简体中文

**DeepSignal-S1 是面向实时交通信号控制、以视觉为主要交通观察输入的 System One 决策模型。S1 代表 one system**：将视觉交通理解与信号动作选择统一在一个多模态决策模型中。

DeepSignal-S1 采用 **Jev-style（以直接决策为核心）的功能定位**：接收路口摄像头画面与当前信号状态，直接选择允许执行的信号动作，而不是生成聊天式回答。交通观察来自画面，S1 控制器不需要单独的 YOLO 感知阶段。**YOLO+MP 是对照基线，不是 DeepSignal-S1 的组成模块。**

本仓库提供 DeepSignal-S1 的仿真测试场景、功能展示结果与模型调用客户端。完整模型文件与独立推理运行时通过 Hugging Face 单独提供。

**唯一固定基线：已冻结的工程固定配时。正常视觉比较S1、工程固定配时和YOLO+MP三方；特殊视觉只比较S1与YOLO+MP。历史其他固定参考及其视频不再作为当前复现入口。**

## 与基线对比

| 控制方法 | 交通观察方式 | 控制方式 | 测试入口 |
| --- | --- | --- | --- |
| **DeepSignal-S1** | 摄像头画面与当前信号状态 | 自适应决策 | `--controller s1` |
| 工程固定配时 | 既有工程方案，不针对最终测试搜索 | 固定相位循环 | `--controller fixed` |
| YOLO+MP | YOLO 摄像头车辆检测 | 按各转向交通压力决策 | `--controller visual-pressure` |

### 已完成结果

本次公开结果使用**两份明确标注的场景版本**，不声称同一权重跨场景取得这些成绩：南沙使用 `DeepSignal-S1-1.0-candidate`（UE5/CARLA 0.10.0），Town10HD 使用 `DeepSignal-S1-Town10HD-1.0-archive`（CARLA 0.9.16）。后台正在进行的补测**不计入**下表。

**Town 执行修正：** 下表 Town 行保留旧执行器的历史测量；该执行器漏掉了承诺的 5 秒绿灯尾段，因此这些数值**不是修正后执行规则下已验证的成绩**，也不是当前 HF 权重的成绩。当前权重的 Town 完整矩阵正在重跑，见[范围与修正说明](docs/intersection-metrics.md)。南沙测量不受此次 Town 修正影响。

| 场景 | 画面条件 | 成功配对 / 计划 | 对照 | 行程指标改善 |
| --- | --- | ---: | --- | ---: |
| 南沙九路口 | 清晰 | 72 / 72 | 工程固定配时 | **15.99%** |
| 南沙九路口 | 整回合固定的相机角度偏移，范围 ±8° | 72 / 72 | YOLO+MP | **1.12%** |
| 南沙九路口 | 失焦，sigma=2.5 | 65 / 72 | YOLO+MP | **25.69%** |
| Town10HD 存档版 | 清晰 | 20 / 20 | 工程固定配时 | **36.21%** |
| Town10HD 存档版 | 清晰 | 20 / 20 | YOLO+MP | **3.13%** |
| Town10HD 存档版 | 失焦，sigma=2.5 | 40 / 40 | YOLO+MP | **8.46%** |

南沙清晰画面下与 YOLO+MP 整体接近：**9 个路口中有 5 个的汇总截断行程指标相差不到 5%**。九个路口的完整数值均见[公开结果](results/released-2026-10-26.json)。

上述指标按指定时域截断，未完成行程仍计入。南沙失焦改善率来自双方均成功的 65 对，模型 6 个失败和 YOLO+MP 1 个失败的记录均保留。Town 清晰测试使用同一存档权重的四个种子、全部五类需求，不把早期权重成绩混入 40 回合汇总。[版本、复测命令及范围](docs/released-results.md) · [重新计算表格](scripts/summarize_released.py)。


### 工程固定配时测试

当前固定对照采用事先冻结的工程方案：南沙使用各路口既有配置（J02 为 **35/14/10/17 秒**），Town10HD 使用 **31/6/31/6 秒**，不针对最终测试车流搜索最优配时。**72 个南沙和 40 个 Town10HD 固定对照回合均已完成。** 在南沙 72 个清晰条件配对回合上，发布模型相对工程固定方案的逐回合截断平均行程汇总改善 **15.99%**。该有限时域指标与上方完整平均行程分别统计。[固定对照数据](results/engineering-fixed-2026-10-26.json) · [矩阵复现说明](docs/reproduction.md)。

其他历史固定参考和相应视频仅保留归档，不作为当前复现方案。发布模型与融合权重模型分别统计，不继承对方成绩。

## 仿真场景

![南沙路口四路摄像头画面](assets/nansha-scene.jpg)

*南沙 J02，UE5 Epic 画质。本轮新闭环测试中的四路摄像头画面。*

## 运行测试

需要 Linux、Python **3.10** 和 SUMO。三维画面还需要配套 CARLA 0.10.0 场景包及 NVIDIA GPU，录制需要 FFmpeg。

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e '.[test,download]'

deepsignal-s1 prepare --scene scenarios/nansha-j02/scene.json \
  --regime east-west --seed 99001 --output runs/example/plan.json

deepsignal-s1 run --scene scenarios/nansha-j02/scene.json \
  --plan runs/example/plan.json --controller fixed --cpu \
  --output runs/example/fixed
```

上述固定配时测试无需模型权限或三维素材。视觉闭环测试见[场景安装与模型访问](docs/testing.md)。

## 模型与场景下载

当前模型主页为 **[Hugging Face：AIMS2025/DeepSignal-S1](https://huggingface.co/AIMS2025/DeepSignal-S1)**，只提供 `DeepSignal-S1-1.0-candidate`，不包含历史 Town 权重。下载前请查看模型卡中的上传就绪状态并申请访问权限。历史 Town 成绩仍明确对应独立存档版本，不能归给这份 HF 权重。

统一的 **[南沙 + Town10HD 场景数据集](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes)** 托管 `DeepSignal-S1-Scenes-v3.tar.gz`（**27.60 GiB**），上传就绪状态以数据集卡片为准。无需 Google Drive；场景公开下载，模型另行申请权限。从公开下载开始的完整复跑尚未验收。

```bash
hf download AIMS2025/DeepSignal-S1-Scenes DeepSignal-S1-Scenes-v3.tar.gz \
  --repo-type dataset --local-dir downloads
deepsignal-s1 install-assets --archive downloads/DeepSignal-S1-Scenes-v3.tar.gz
```

v2 包包含两套 UE5 场景与历史 Town 的 CARLA 0.9.16 运行环境，不包含独立的历史模型权重。请按[安装及版本对应说明](docs/released-results.md)运行。访问本 GitHub 仓库不代表已获得模型权限，也不等于开通了远程托管 API。

获批下载完整模型后，也可以通过 `scripts/serve_model.py` 启动本地推理，不依赖远程 API。详见[本地推理与复现说明](docs/reproduction.md)。

获批后配置：

```bash
export HF_TOKEN="已获批账号的访问令牌"
export DEEPSIGNAL_ENDPOINT="分配给你的模型服务地址"
deepsignal-s1 run --scene scenarios/nansha-j02/scene.json \
  --plan runs/example/plan.json --controller s1 --port 25020 \
  --output runs/example/s1
```

运行前需启动场景服务器。测试不会用固定配时或历史答案替代模型返回结果。

## 测试产物

每个回合输出到达计划、逐车记录、信号时间线和结果报告。主要指标为完整平均行程时间，包含车辆进入仿真路网前的等待；不会删除未完成行程来获得更好的平均值。

对比双方使用同一到达计划。只有 `--realtime` 实测满足决策时限的回合才记录为实时运行，在线仿真录制不自动等于实时演示。

## 相关资源

- [测试场景与 API 使用](docs/testing.md)
- [统一场景包与原矩阵复现](docs/reproduction.md)
- [公开成绩与对应模型、场景版本](docs/released-results.md)
- [补充视觉条件测试方案](docs/supplementary-evaluation.md)
- [指标与对比口径](docs/comparisons.md)
- [交叉口排队、停车等待与通过量指标](docs/intersection-metrics.md)
- [此前 DeepSignal 项目](https://github.com/AIMS-Laboratory/DeepSignal)
- [场景素材及第三方说明](NOTICE.md)

联系：[dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
