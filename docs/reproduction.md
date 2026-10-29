# 原矩阵复现 / Paired-Matrix Reproduction

**主页已完成成绩请优先使用[发行版本复现说明](released-results.md)及 `scripts/run_released_matrix.py`。** 本页的 UE5 Town 入口用于迁移后的测试，不是 CARLA 0.9.16 Town 存档成绩的复现入口。

**For published homepage results, use the [release-specific instructions](released-results.md) and `scripts/run_released_matrix.py`.** The UE5 Town entrypoints below do not reproduce the CARLA 0.9.16 archive scores.

## 材料 / Materials

- GitHub 提供测试代码、112 份固定交通计划、相机和路口配置，不含训练代码。
- 当前 [HF 仓库](https://huggingface.co/AIMS2025/DeepSignal-S1)只提供当前发布权重与完整推理运行时，不包含 Town 存档权重。请下载完整目录，不只下载小体积文件；不要将历史 Town 成绩归给当前 HF 模型。
- [HF 场景数据集](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes)公开托管 `DeepSignal-S1-Scenes-v3.tar.gz`（27.60 GiB），包含南沙九路口和 Town10HD 的 UE5 运行文件、Town 存档 Docker 镜像、匹配 CARLA wheel、YOLO+MP 使用的原版检测器及相应许可。无需 Google Drive，上传就绪状态见数据集卡片。安装方法见 [testing.md](testing.md)。

The GitHub repository contains test construction and evaluation code only. The complete current model is distributed through approved HF downloads. The public HF scene dataset hosts one v2 archive for both Nansha and Town10HD, including the archived runtime but not its separate model weights.

## 环境 / Environments

仿真客户端使用 Python 3.10，安装 SUMO 后执行：

```bash
pip install -e '.[test,reproduction]'
pip install assets/runtime/python/carla-0.10.0-cp310-cp310-linux_x86_64.whl
```

模型推理单独使用 Python 3.12 环境，按 HF 模型卡安装依赖：

```bash
CUDA_VISIBLE_DEVICES=0 /path/to/inference/python scripts/serve_model.py \
  --model /path/to/DeepSignal-S1 --port 18404
```

The simulator and model use separate Python environments. The local inference service does not require a remote hosted endpoint.

## 固定对照 / Fixed Baseline

**唯一固定基线为下述冻结工程方案。正常视觉比较S1、工程固定配时与YOLO+MP三方；特殊视觉只比较S1与YOLO+MP。固定运行器只接受正常视觉，不再提供其他调优固定参考。**

南沙采用各路口既有 `v2` 工程表，J02 为 35/14/10/17 秒；Town 采用 31/6/31/6 秒。均不针对正式测试搜索。Town 沿用原协议的首段绿灯及其首次倒计时接管点，不将正式车辆窗口起点 98 秒误作接管点；首段结束后按工程表轮转。南沙原协议为共同全红冷启动，不额外添加 Town 预热。

```bash
python scripts/reproduce.py --scene nansha --controller fixed \
  --tag J02-asym-mid-EW-flat-base-97001 --output runs/fixed-example

python scripts/run_fixed_matrix.py --jobs 4 --output runs/engineering-fixed
```

批处理保持四任务并行，在整机 CPU 达到 65% 时暂停本批、回落至 60% 以下恢复，给 70% 目标留余量。不能限制其他外部进程自身的负载。失败回合不会作为成功结果跳过。

Fixed control runs in SUMO without a GPU. The engineering tables are frozen before evaluation, not selected for their performance against the released model. The original warmup/cold-start protocol is preserved.

## 视觉闭环 / Visual Closed Loop

先单独启动对应的场景服务器，再运行：

```bash
python scripts/reproduce.py --scene town10hd --controller s1 \
  --tag balanced-18036 --condition clean --port 25020 \
  --endpoint http://127.0.0.1:18404 --output runs/town-clean

python scripts/reproduce.py --scene nansha --controller s1 \
  --tag J02-asym-mid-EW-flat-base-97001 --condition defocus-2.5 \
  --port 25020 --output runs/nansha-defocus
```

条件包括 `clean`、`motion-blur-9`、`defocus-2.5`、`angle-8`、`angle-12`、`angle-16`。角度条件指整回合固定的相机外参偏移，不是逐帧随机抖动。不同条件使用不同输出目录。新增角度条件属于独立补测，不混入已发布成绩。

原矩阵 YOLO+MP 使用对应检测服务；不要与精选展示客户端的不同服务接口混用：

```bash
CUDA_VISIBLE_DEVICES=1 /path/to/detector/python scripts/archived_detector_service.py \
  --model assets/runtime/reproduction/baselines/yolo11m.pt --port 8031

python scripts/reproduce.py --scene nansha --controller visual-pressure \
  --tag J02-asym-mid-EW-flat-base-97001 --condition defocus-2.5 \
  --detector-endpoint http://127.0.0.1:8031/v1/detect2 \
  --port 25020 --output runs/nansha-defocus-yolo
```

## 指标与版本 / Metrics and Versions

`reproduction/matrix.json` 列出全部原始车流。南沙 `J_H` 是 1298 秒时域内的截断平均行程；Town `J` 是 518 秒时域内的截断总行程。均从计划到达时刻计时，未完成车辆按时域末端计入，不删车；两种指标不能混合。

原始 Town 视觉程序使用 CARLA 0.9.16；本页迁移入口使用 v2 包中的 UE5/CARLA 0.10.0 及其实际提供的车辆素材。因此保留原车流与控制时序，但迁移后的视觉成绩必须重新验证，不能直接继承旧运行环境的数字。v2 另含原 0.9.16 Docker 环境，其入口见[发行版本说明](released-results.md)；当前 HF 模型不包含所需 Town 存档权重。最终南沙权重也不能继承早期 Town 专用权重的成绩。

Nansha reports capped mean journey time at 1298 s; Town reports capped total journey time at 518 s. The UE5 port preserves fixed traffic plans and signal rules, but historical Town visual results from a different runtime/checkpoint are not scores of this release. This matrix is distinct from the complete-journey showcase protocol and does not by itself certify real-time operation.
