# 补充视觉测试 / Supplementary Visual Evaluation

本轮仅测试发布版本 **DeepSignal-S1-1.0-candidate**，使用发行包内的 UE5/CARLA 0.10.0 场景和 Epic 画质，不使用旧 Town 专用权重代替。计划在查看本轮成绩前确定。

This round evaluates the released **DeepSignal-S1-1.0-candidate** with the packaged UE5/CARLA 0.10.0 runtimes at Epic quality. Historical Town-specific weights are not substituted. The matrix is fixed before examining these results.

| 场景 / Scene | 条件 / Conditions | 交通案例 / Traffic Cases | 控制器 / Controllers | 回合 / Runs |
|---|---|---:|---|---:|
| 南沙九路口 / Nansha, nine intersections | angle-12, angle-16 | 72 | S1, YOLO+MP | 288 |
| Town10HD | clean, angle-8, defocus-2.5 | 40 | S1, YOLO+MP | 240 |

南沙使用原矩阵的九路口、八类需求及种子 97001；Town 使用原矩阵的五类需求与种子 18036 至 18043。到达计划与路线均位于 `reproduction/`，索引为 `reproduction/matrix.json`。工程固定配时不依赖图像，复用已经完成的固定对照，不针对每种扰动重复运行。

Nansha retains nine intersections, eight demand regimes and seed 97001. Town retains five regimes and seeds 18036 through 18043. Plans and routes are indexed by `reproduction/matrix.json`. Completed engineering fixed-timing runs remain the image-independent reference.

## 角度与失焦 / Camera Conditions

`angle-a` 表示每个相机的偏航角和俯仰角分别在 ±a 度内取样，滚转角在 ±a/2 度内取样；整回合保持不变，不是逐帧随机抖动。南沙使用交通种子生成扰动，因此两个角度档位采用同一组归一化方向；每个档位两种方法的偏移相同。Town 两种方法使用相同的 `seed + int(a * 10)` 生成偏移。

Each `angle-a` condition samples static yaw/pitch offsets within +/-a degrees and roll within +/-a/2. Offsets remain fixed throughout an episode. Both controllers receive identical camera offsets for a given traffic case. Nansha uses the traffic seed; Town uses `seed + int(a * 10)`.

YOLO+MP 维持原车道区域和原检测阈值，不随测试结果调弱，也不在角度变化后重新标定。这评估安装角度变化后的适应性，不代表重新标定后的最优 YOLO+MP 表现。失焦采用相同的高斯处理（sigma=2.5）。运行时会保留仿真时间约 120 秒处的实际输入截图，供检查道路覆盖情况；截图不改变输入。

YOLO+MP retains the original lane regions and detection threshold, without outcome-driven weakening or re-calibration after a camera shift. This measures sensitivity to changed installation angles, not optimal re-calibrated YOLO+MP performance. Defocus uses Gaussian sigma=2.5 for both controllers. An actual input preview around simulation time 120 seconds is retained for road-coverage inspection without altering inputs.

## 复测与统计 / Running and Reporting

按 [复现说明](reproduction.md) 启动对应场景、模型服务和检测服务。每个条件分别运行两个控制器，例如：

Start the matching scene, model and detector as described in [Reproduction](reproduction.md), then run each controller separately for every condition:

```bash
python scripts/run_visual_matrix.py --scene nansha --controller s1 \
  --condition angle-12 --output runs/supplementary/nansha
python scripts/run_visual_matrix.py --scene nansha --controller visual-pressure \
  --condition angle-12 --output runs/supplementary/nansha
```

南沙使用 H=1298 秒的逐案例截断平均行程 `J_H`；Town 使用 H=518 秒的截断行程总量 `J`。两域只在域内、同案例之间配对，不直接混合其绝对指标。改善为 `100 * (1 - sum(S1) / sum(YOLO+MP))`。报告完整计划数、完成数、成功配对数和两种方法各自的失败数。失败记录保留，不因成绩不利重跑；成功配对子集的改善不等于全计划成功。

Nansha reports per-case truncated mean journey time `J_H` at H=1298 seconds; Town reports truncated total journey time `J` at H=518 seconds. Absolute metrics are not pooled across scenes. Improvement is `100 * (1 - sum(S1) / sum(YOLO+MP))` over matched successful cases, accompanied by planned/completed counts and failures for each controller. Failed runs are retained, not retried based on outcomes. Successful-subset improvement does not establish success on the full matrix.

旧入口将南沙 `angle-8` 的幅度误传为 9 度，本轮已修正为准确的 8 度；原存档的 ±8 度结果由独立的原测试脚本生成，不受此修正影响。

The previous public launcher incorrectly passed 9 degrees for Nansha `angle-8`; the launcher now passes exactly 8. Archived +/-8-degree results came from the separate original script and are unaffected.
