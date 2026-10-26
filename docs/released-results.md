# 已发布结果的复现 / Reproducing Published Results

本页对应 `v0.2.0` 的已完成测量，不使用正在进行的 528 回合补测。两套场景采用同一视觉到决策接口，但使用**两份明确标注的冻结权重**，不声称单一权重跨场景取得全部成绩。

This page covers completed measurements in `v0.2.0`, excluding the ongoing 528-run supplement. Both suites share the visual-to-decision interface but use **two explicitly identified frozen checkpoints**, not one cross-scene checkpoint.

**Town 历史成绩限定：** 2026-10-26 检查发现，Town 存档和早期 UE5 补测的自适应执行器均在决定切换后立即变黄，漏掉了承诺的 5 秒绿灯尾段。本页保留原始历史测量及其重算材料，不将其视为满足修正后绿灯执行约束的成绩。当前 HF 权重在修正后 UE5 Town 上的完整 240 回合另行重跑，不能继承本页 Town 数字。南沙不受此 Town 修正影响。详见[执行时序说明](intersection-metrics.md)。

**Historical Town scores:** the archived and early UE5 Town adaptive executors switched to yellow immediately after a switch decision, omitting the committed five-second green tail. Historical measurements and recomputation inputs remain available here, but do not establish compliance with corrected green timing. The current HF checkpoint is being evaluated separately across all 240 corrected UE5 Town runs and does not inherit these Town scores. Nansha is unaffected by this Town correction. See [timing corrections](intersection-metrics.md).

## 版本对应 / Matching Releases

| 测试 / Suite | HF 完整模型目录 / Model Folder | 服务版本 / Model Version | 仿真 / Runtime |
|---|---|---|---|
| 南沙 / Nansha | `DeepSignal-S1` | `DeepSignal-S1-1.0-candidate` | UE5 / CARLA 0.10.0 |
| Town 存档 / Town Archive | `DeepSignal-S1-Town10HD-Archive` | `DeepSignal-S1-Town10HD-1.0-archive` | CARLA 0.9.16, Town10HD_Opt |

统一场景包为 `DeepSignal-S1-Scenes-v2.tar.gz`，包含原 UE5 南沙与 Town10HD、Town 存档所需的 CARLA 0.9.16 Docker 镜像、两个匹配的 Python wheel、场景测试材料及许可。UE5 Town 用于迁移后的补测，**不能用来复算本页的 Town 存档成绩**。原 UE5 v1 包仍可使用，但没有 Town 存档环境。

The combined `DeepSignal-S1-Scenes-v2.tar.gz` includes the UE5 runtimes, the archived CARLA 0.9.16 Docker image, matching client wheels, fixed plans and licenses. UE5 Town is for the migration/supplementary suite, **not** the archived Town scores. The older UE5 v1 package lacks the archive environment.

当前模型为 [AIMS2025/DeepSignal-S1](https://huggingface.co/AIMS2025/DeepSignal-S1)，须申请访问权限；统一场景包公开托管于 [AIMS2025/DeepSignal-S1-Scenes](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes)，上传就绪状态以数据集卡片为准，不再需要 Google Drive。场景包不含模型权重，当前 HF 模型仓库也不含 Town 存档权重，因此尚不能仅靠上述下载复跑历史 Town 的模型成绩。`assets/links.json` 保存下载入口，下列 `/path/to/...` 是本地下载位置。

The current [model repository](https://huggingface.co/AIMS2025/DeepSignal-S1) requires approved access. The combined [public scene dataset](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes) replaces Google Drive; check its card for upload readiness. Neither the scene bundle nor the current HF model repository includes the archive Town checkpoint, so these downloads alone do not reproduce historical Town model scores. Download entrypoints are recorded in `assets/links.json`; `/path/to/...` denotes local paths.

```bash
pip install -U huggingface_hub
hf download AIMS2025/DeepSignal-S1-Scenes DeepSignal-S1-Scenes-v2.tar.gz \
  --repo-type dataset --local-dir downloads
```

## 环境准备 / Environment Setup

两套仿真均使用 **SUMO 1.18.0**。推理按各 HF 目录的依赖使用独立 Python 3.12 环境；客户端使用 Python 3.10。两个 CARLA wheel **不能装进同一个客户端环境**。

Both suites use **SUMO 1.18.0**. Inference uses the model folder's Python 3.12 requirements. Simulation clients use separate Python 3.10 environments; do **not** install both CARLA wheels into one environment.

```bash
tar -xzf /path/to/DeepSignal-S1-Scenes-v2.tar.gz -C /path/to/empty-assets-directory

# Nansha / UE5 client
python3.10 -m venv .venv-nansha
.venv-nansha/bin/pip install -e '.[reproduction]'
.venv-nansha/bin/pip install /path/to/assets/python/carla-0.10.0-cp310-cp310-linux_x86_64.whl

# Archived Town client
python3.10 -m venv .venv-town-archive
.venv-town-archive/bin/pip install -r reproduction/legacy-town/requirements.txt
.venv-town-archive/bin/pip install /path/to/assets/python/carla-0.9.16-cp310-cp310-manylinux_2_31_x86_64.whl
```

检测服务使用 Ultralytics 8.4.175、发行包内的 `reproduction/baselines/yolo11m.pt`、默认置信度 0.25 和固定车道区域。不得将检测失败替换成仿真车辆真值。检测服务可使用独立的 Python 环境，与 CARLA 客户端分离。

The detector uses Ultralytics 8.4.175, the packaged stock YOLO11m weights, confidence 0.25 and the frozen lane regions. Simulator traffic ground truth is not a detector fallback. The detector can run in an environment separate from the CARLA client.

```bash
CUDA_VISIBLE_DEVICES=1 /path/to/detector/python scripts/archived_detector_service.py \
  --model /path/to/assets/reproduction/baselines/yolo11m.pt --port 8031
```

## 南沙 / Nansha

```bash
CUDA_VISIBLE_DEVICES=0 /path/to/inference/python scripts/serve_model.py \
  --model /path/to/DeepSignal-S1 --port 18404

.venv-nansha/bin/python -m deepsignal_s1.cli launch-scene \
  --scene scenarios/nansha-j02/scene.json --assets /path/to/assets \
  --port 25020 --adapter 0
```

场景服务器须保持运行。使用同一服务、分别执行每个 `CONDITION` 与 `CONTROLLER`：

Keep the scene server running. Run each combination separately using the same model release:

```bash
# CONDITION: clean, angle-8, defocus-2.5
# CONTROLLER: s1, visual-pressure; fixed only needs the clean suite
.venv-nansha/bin/python scripts/run_released_matrix.py --suite nansha \
  --controller s1 --condition clean --port 25020 --output runs/released
```

每个条件包含九路口 × 八类需求，种子 97001，共 72 个计划。±8° 为整回合固定外参偏移，双方使用相同的偏移；不是逐帧抖动。失焦使用 sigma=2.5。清晰条件模型汇总 `J_H=7723.46`，YOLO+MP 为 `7642.21`，工程固定为 `9193.32`：相对固定改善 15.99%，与 YOLO+MP 整体接近。9 个路口中 5 个的汇总差异小于 5%，不意味着每个路口或每种需求都接近。

Each condition has nine intersections, eight regimes and seed 97001: 72 plans. Static +/-8-degree camera offsets are matched between controllers. Defocus uses sigma=2.5. Clean sums are S1 `7723.46`, YOLO+MP `7642.21`, engineering fixed `9193.32`: 15.99% lower than fixed and close to YOLO+MP overall. Five of nine intersection aggregates differ by less than 5%; this is not an every-intersection/every-regime claim.

失焦 72 个计划中，S1 有 6 个决策失败，YOLO+MP 有 1 个；双方均成功的 65 对改善 25.69%。保留全部失败记录，不把成功子集表述为全计划成功。角度偏移 72 对均成功，改善 1.12%。运动模糊不作为本次主页展示条件，但既有原始记录保留。

Nansha defocus retains six S1 failures and one YOLO+MP failure among 72 planned pairs; 65 jointly successful pairs show 25.69% improvement. Static angle offsets have 72 successful pairs and 1.12% improvement. Existing motion-blur records remain archived even though that condition is not a homepage showcase.

## Town10HD 存档 / Town10HD Archive

首次加载包内镜像需要 Docker；三维渲染还需要已配置 NVIDIA CDI 的容器环境。选择 GPU UUID，不要将 UE5 客户端用于该镜像。镜像默认启动 Town10HD_Opt，无需额外换图。

Load the packaged image with Docker. Rendering requires NVIDIA CDI configured for containers. Select a GPU UUID and use the CARLA 0.9.16 client, not the UE5 client. The image starts Town10HD_Opt by default.

```bash
docker load -i /path/to/assets/runtime/town10hd-archive/carla-0.9.16.docker.tar
python3 scripts/launch_town_archive.py --gpu GPU-YOUR-UUID --port 25020

CUDA_VISIBLE_DEVICES=0 /path/to/inference/python scripts/serve_model.py \
  --model /path/to/DeepSignal-S1-Town10HD-Archive --port 18404

# Run each controller and condition separately.
.venv-town-archive/bin/python scripts/run_released_matrix.py --suite town10hd-archive \
  --controller s1 --condition clean --port 25020 --output runs/released
```

Town 清晰条件采用种子 18040—18043、全部五类需求，共 20 对；模型 `J=36427.5`，YOLO+MP 为 `37604.3`，工程固定为 `57103.5`，分别改善 3.13% 和 36.21%。该 20 回合范围由权重版本一致性确定，不按胜负选取：不把更早权重的 20 回合拼成同一版本的 40 回合成绩。

Town clean uses seeds 18040–18043 and all five regimes: 20 pairs, S1 `36427.5`, YOLO+MP `37604.3`, engineering fixed `57103.5`, giving 3.13% and 36.21% improvement. This scope follows checkpoint consistency, not case outcomes; earlier-checkpoint runs are not merged into a 40-case score.

Town 失焦条件使用种子 18036—18043 和全部五类需求，共 40 对：`J=70586.9` 对 `77111.4`，相对 YOLO+MP 改善 8.46%。本次 Town 清晰和失焦均使用同一份存档权重。更早的 Town 角度汇总中两侧相机偏移采样不同，**不作为严格同扰动配对成绩发布**，也不能将先前的 49.12% 称为当前权重的已验证改善。

Town defocus uses seeds 18036–18043 and all five regimes: 40 pairs, `70586.9` versus `77111.4`, or 8.46% lower than YOLO+MP. Clean and defocus use the same archive checkpoint. Earlier Town angle aggregates used different sampled camera offsets between arms and are **not released as a strictly matched perturbation result**, nor is the earlier 49.12% a validated score of the current checkpoint.

## 汇总与验收 / Aggregation and Verification

```bash
# Recompute published reference tables without a GPU.
python3 scripts/summarize_released.py --output runs/reference-summary.json

# Recompute your own completed runs with the same case lists.
python3 scripts/summarize_released.py --reference runs/released \
  --fixed results/engineering-fixed-2026-10-26.json --output runs/my-summary.json

# For independently rerun fixed cases, pass their output root instead.
python3 scripts/summarize_released.py --reference runs/released \
  --fixed runs/released --output runs/my-independent-summary.json
```

`release-matrix.json` 固定公开表格的案例及模型版本；运行器拒绝错误的模型服务版本。完整复测需运行各条件下的两种视觉控制器；固定对照可通过相同入口在 clean 条件重算。上例复用已公开固定记录，若自行重算则替换为自己的固定记录。

`release-matrix.json` binds each published table to explicit cases and model versions; the runner rejects a mismatched model service. A complete rerun evaluates both visual controllers per condition. Fixed control can be rerun with the clean condition; replace the fixed reference records with your own when comparing a fully independent rerun.

南沙指标为 H=1298 秒的截断平均行程，Town 为 H=518 秒的截断总行程，两域绝对值不能合并。固定配时为事先确定的工程表，不是针对发布成绩反向调弱的方案。发布的是固定条件下的测量与可执行材料，不承诺不同硬件、驱动、依赖版本或相机布置下逐位一致；实际从远端下载后的完整复跑尚未完成，不能标成已经通过。

Nansha uses capped mean journey time at H=1298 s; Town uses capped total journey time at H=518 s. Absolute values are not pooled across scenes. Engineering fixed tables are not weakened based on release outcomes. Measurements and executable inputs are provided, not a bitwise guarantee across different hardware/drivers/dependencies/camera setups. A complete fresh-download rerun has not yet been performed and is not reported as passed.
