# DeepSignal-S1

**基于视觉交通状态的实时信号控制。S1 代表 one system。**

[English](README.md) | 简体中文

DeepSignal-S1 观察路口摄像头画面，给出自适应信号控制动作。本仓库提供仿真测试场景与模型调用客户端。

![南沙路口四路摄像头画面](assets/nansha-scene.jpg)

*南沙 J02，UE5 Epic 画质。本轮新闭环测试中的四路摄像头画面。*

## 对比视频

对比视频采用**左侧 DeepSignal-S1、右侧调优固定配时**，同步展示车流、灯态和车辆行程指标。YouTube 上传后将在这里添加视频封面链接。

## 与基线对比

| 控制方法 | 交通观察方式 | 控制方式 | 测试入口 |
| --- | --- | --- | --- |
| **DeepSignal-S1** | 摄像头画面与当前信号状态 | 自适应决策 | `--controller s1` |
| 调优固定配时 | 预设配时表 | 固定相位循环 | `--controller fixed` |
| YOLO+MP | YOLO 摄像头车辆检测 | 按各转向交通压力决策 | `--controller visual-pressure` |

### 本轮新测试结果

测试日期为 **2026 年 10 月 25 日**。全部展示回合使用同一模型服务版本 **DeepSignal-S1-1.0-candidate**，每组包含三个新种子：**99001、99002、99003**。下表为按车辆数加权的完整平均行程时间，单位为秒，包含进入路网前的等待，**越低越好**。所有正式车辆均完成行程。

| 南沙 J02 车流 | 视觉条件 | DeepSignal-S1 | YOLO+MP | 相对 YOLO+MP 缩短 | 调优固定配时 | 相对固定配时缩短 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 东西向需求偏高 | **失焦** | **80.42** | 82.19 | **2.15%** | 93.29 | **13.80%** |
| 东西向需求偏高 | 清晰 | **78.85** | 80.75 | **2.36%** | 93.29 | **15.48%** |
| 南北向需求偏高 | 清晰 | **91.62** | 93.55 | **2.06%** | 97.27 | **5.80%** |

**失焦条件重点与 YOLO+MP 比较**，其他清晰条件也均包含 YOLO+MP 对照。两种视觉方法使用相同的失焦处理和观察时刻；固定配时不依赖摄像头画面。

[测试数据（JSON）](results/nansha-2026-10-25.json) · [表格（CSV）](results/nansha-2026-10-25.csv) · [对比口径](docs/comparisons.md)

以上为南沙 J02 选定场景的功能展示，不表述为每个种子、任意路口或所有视觉条件下均有收益。Town10HD 保留为可选测试场景，不计入主页展示结果。

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

## 模型访问

Hugging Face 模型主页与 API 发布后将在这里添加链接。模型下载与 API 调用均需要申请并获批；访问本 GitHub 仓库不代表已获得模型权限。

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
- [指标与对比口径](docs/comparisons.md)
- [此前 DeepSignal 项目](https://github.com/AIMS-Laboratory/DeepSignal)
- [场景素材及第三方说明](NOTICE.md)

联系：[dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
