# 补充视觉测试 / Supplementary Visual Evaluation

本轮仅测试发布版本 **DeepSignal-S1-1.0-candidate**，使用发行包内的 UE5/CARLA 0.10.0 场景和 Epic 画质，不使用旧 Town 专用权重代替。计划在查看本轮成绩前确定。

This round evaluates the released **DeepSignal-S1-1.0-candidate** with the packaged UE5/CARLA 0.10.0 runtimes at Epic quality. Historical Town-specific weights are not substituted. The matrix is fixed before examining these results.

| 场景 / Scene | 条件 / Conditions | 交通案例 / Traffic Cases | 控制器 / Controllers | 回合 / Runs |
|---|---|---:|---|---:|
| 南沙九路口 / Nansha, nine intersections | angle-12, angle-16 | 72 | S1, YOLO+MP | 288 |
| Town10HD | clean, angle-8, defocus-2.5 | 40 | S1, YOLO+MP | 240 |

南沙使用原矩阵的九路口、八类需求及种子 97001；Town 使用原矩阵的五类需求与种子 18036 至 18043。到达计划与路线均位于 `reproduction/`，索引为 `reproduction/matrix.json`。工程固定配时不依赖图像，复用已经完成的固定对照，不针对每种扰动重复运行。

Nansha retains nine intersections, eight demand regimes and seed 97001. Town retains five regimes and seeds 18036 through 18043. Plans and routes are indexed by `reproduction/matrix.json`. Completed engineering fixed-timing runs remain the image-independent reference.

南沙清晰、±8° 与失焦属于此前已完成的矩阵，不在新增 528 回合中重复。南沙失焦为 65/72 对双方均成功、相对 YOLO+MP 改善 25.69%，同时保留模型 6 个失败和 YOLO+MP 1 个失败，见[已发布结果](released-results.md)。

Nansha clean, +/-8 degrees and defocus belong to the previously completed suite, not the new 528 runs. Nansha defocus has 65/72 jointly successful pairs and 25.69% improvement, with all controller failures retained; see [released results](released-results.md).

**2026-10-26 相机修正：** 修复前的 UE5 Town 补测因相机位姿初始化错误而作废，原始记录保留，完整 240 回合重跑，不按胜负筛选。南沙已结束的 288 回合保留。新回合另外记录交叉口排队、停车等待与通过量，具体定义及版本范围见[交叉口指标](intersection-metrics.md)。

**Camera correction, 2026-10-26:** pre-fix UE5 Town supplementary comparisons are invalidated due to camera initialization, with original records retained and all 240 Town runs rerun. Completed Nansha runs are retained. New runs add [intersection metrics](intersection-metrics.md).

**后续执行时序修正：** 相机修复后的逐车统计核对一致，但又发现旧 Town 执行器漏掉切换前承诺的 5 秒绿灯尾段、YOLO+MP 首轮采用全零观测，以及部分回合提前一秒结束。这批记录同样保留并排除，Town 全部 240 回合按 `town-5s-green-tail-v2` 统一重跑，南沙 288 回合不动。不预设修正后的胜负，也不按成绩挑选回合；原因及实际信号时间线见[执行时序修正](intersection-metrics.md#town-执行时序修正--town-signal-timing-correction)。

**Subsequent timing correction:** the camera-corrected trip statistics agree with raw records, but the Town executor also omitted its committed five-second green tail, initialized MP with zero observations, and could end one second early. Those runs are retained and excluded too. All 240 Town runs restart under `town-5s-green-tail-v2`; Nansha's 288 runs remain unchanged. Outcomes are not presumed and cases are not selected by performance. See the [timing correction](intersection-metrics.md#town-执行时序修正--town-signal-timing-correction).

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
