# 交叉口指标 / Intersection Metrics

当前融合1.0结果与Town修正时序见[融合评测](fusion-pilot-evaluation.md)。本页保留指标定义与历史修正过程；旧Town成绩不进入当前融合主页。

单交叉口信控不只看行程时间。新运行的原矩阵入口会额外写出 `<tag>-metrics.json`，覆盖 S1、YOLO+MP 与工程固定配时。原有行程指标和原始结果不覆盖、不改写。

New matrix runs additionally write `<tag>-metrics.json` for all three controllers. These evaluation-only measurements do not change the original journey metrics or controller inputs.

| 指标 / Metric | 字段 / Field | 口径 / Definition |
|---|---|---|
| 平均排队车辆数 / Mean queue | `mean_queue_vehicles` | 唯一受控进口车道上的停车车辆数作时间平均，单位为辆 / Time-averaged halting count on unique incoming lanes, vehicles |
| 最大排队车辆数 / Peak queue | `max_queue_vehicles` | 同一观察时段内的最大总排队车辆数 / Maximum total halting count |
| 平均每车停车等待 / Mean stopped time | `mean_stopped_time_s` | 正式车辆的累计 `waitingTime`，单位秒/车 / Formal-vehicle cumulative waiting time, seconds per vehicle |
| 平均每车停车次数 / Mean stop count | `mean_stop_count` | 正式车辆的 `waitingCount` / Waiting episodes per formal vehicle |
| 平均每车时间损失 / Mean time loss | `mean_time_loss_s` | 相对理想速度的时间损失，包括低速行驶 / Time lost relative to ideal speed, including slow movement |
| 平均入网等待 / Mean insertion wait | `mean_insertion_wait_s` | 实际入网减计划出发；未入网车辆截断至观察末端 / Delay before insertion, capped at the observed end |
| 通过量及残留 / Throughput and residual | `arrived_vehicles`, `unfinished_inserted_vehicles`, `not_inserted_vehicles` | 分别保留已完成、已入网未完成、尚未入网车辆 / Completed, unfinished inserted and not-yet-inserted vehicles |

**排队车辆数不等于以米计的队列长度，不能直接相互替代。** 当前记录的是车辆数；若报告米制队列长度，需要另行记录空间队尾。SUMO 的车道停车阈值为速度小于 0.1 m/s；`waitingTime` 累计速度不超过 0.1 m/s 的等待。这里不使用 `stopTime`，后者是计划停车，不是信号或拥堵造成的停车。[车道指标](https://sumo.dlr.de/docs/TraCI/Lane_Value_Retrieval.html) · [逐车指标](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html)

**A queue in vehicles is not a spatial queue length in metres.** Queue counts use SUMO's lane halting metric. Vehicle stopped time uses `waitingTime`, not scheduled `stopTime`; `timeLoss` also includes slow movement.

## 观察范围 / Measurement Scope

- 队列覆盖全部受控进口机动车道上的车辆，包括仍在进口道上未离开的预热车流；重复的受控车道去重，路口内部连接车道不计作进口。
- 逐车等待、停车次数及时间损失只统计计划中的正式车辆，不混入预热车辆。它们覆盖本单路口测试路线，不是逐帧地理围栏内的局部等待。
- 队列观察从仿真 98 秒开始；Town 截止 518 秒，南沙最多至 1298 秒。若提前结束，`window_s` 和 `observed_seconds` 保留实际时段，`fixed_horizon_covered` 为假。**不把不同观察窗口的队列均值直接当作固定时域配对成绩。**
- 未完成车辆的已观察等待仍计入，并标注未完成。若有正式车辆未入网，完整人群的停车均值置空，单列未入网数量和入网等待，不能把缺失车辆当作零等待。
- 这些值来自仿真评估端，只用于评价，不送入 S1 或 YOLO+MP 决策。

Queue measurements cover incoming-lane traffic; trip measurements cover the formal cohort. Actual observation windows and unfinished/never-inserted vehicles are explicit. Compare queue means only over matching windows. Simulator measurements are evaluation-only, never policy observations.

## 已有记录 / Existing Records

早期南沙视觉矩阵没有保存这些队列时序及完整逐车停车字段，不能从一个行程汇总反推出平均排队或停车时间。旧表中的空缺不补成零，也不表述为已经测过；需要重新运行才会产生新指标。保存了 `tripinfo.xml` 的回合可以重算其已有逐车指标，但该文件本身不能还原每个时刻的排队队列。

Earlier Nansha matrix results do not contain these additional observations. They cannot be reconstructed from journey aggregates. TripInfo can recover recorded trip metrics, not a queue time series. Missing values are not zeros.

## Town 相机修正 / Town Camera Correction

2026-10-26 的 UE5 Town 补测检查发现：相机生成后立即读取位姿可能得到尚未发布的零变换。原清晰 YOLO+MP 入口即使角度幅度为零也会回写该变换，导致四路相机落在原点；非零角度入口也受该时序影响。

现已在角度为零时不回写相机，在非零角度时先推进一帧再读取挂载位姿。两种控制器使用相同规则和扰动种子。修复前的 Town 补测记录保留但不用于效果比较，全部 240 回合重新运行；已完成的南沙 288 回合保留。Town YOLO+MP 新回合另存 `<tag>-detector-trace.json`，记录实际视觉计数及控制动作，便于检查检测与控制是否正常。

The UE5 Town launcher now avoids zero-angle pose writes and waits for a world tick before reading poses for nonzero offsets. Pre-fix supplementary Town comparisons are invalidated, with records retained and the full 240-run Town suite rerun. Completed Nansha runs are retained. New Town baseline runs save detector counts and decisions for inspection.

场景压缩包内的测试代码快照早于此次修复。**使用包内运行素材，但执行 GitHub 当前版本的测试代码**；无需重新下载三维素材，也不能直接运行旧快照后将成绩视为已验证。

The scene archive's code snapshot predates this fix. Use its runtime assets with current GitHub test code; re-downloading the scene binaries is unnecessary.

## Town 执行时序修正 / Town Signal-Timing Correction

进一步核对发现，旧 Town 自适应执行器在预定绿灯结束前 5 秒请求决策，却在决定切换后立即变黄，漏掉了仍承诺执行的 5 秒绿灯。S1 和 YOLO+MP 都受影响；相同错误不代表对两种策略的影响相同。另有两个问题：YOLO+MP 首次决策使用人造全零观测，而不是实际三帧；末端转换可能使部分回合在 517 秒提前结束。

当前 `town-5s-green-tail-v2` 执行规则在两侧均保留完整绿灯尾段，随后执行 3 秒黄灯和 2 秒全红；YOLO+MP 首次决策改用实际三帧，所有 Town 回合统一推进至 518 秒。模型权重、交通计划、YOLO 检测阈值及原有校准不因比较输赢调整。新指标中的 `signal_timeline` 记录仿真信号实际状态的变化时刻，可核对真实绿灯、黄灯和全红持续时间；它不作为控制器输入。

相机已修复、但仍使用旧执行时序的 Town 补测也保留原始记录并排除，完整 240 回合按新规则重新运行。旧存档 Town 执行器也存在漏掉绿灯尾段的问题，历史数值不能作为新规则下的验收成绩。已完成的南沙 288 回合不受此次 Town 修正影响。

The old Town adaptive executors requested decisions five seconds before green expiry but switched to yellow immediately after a switch decision, omitting the committed green tail. Both controllers were affected, not necessarily equally. The first MP decision also used synthetic zero counts, and terminal transitions could stop runs at 517 seconds. The corrected `town-5s-green-tail-v2` protocol preserves the green tail, then 3 seconds yellow and 2 seconds all-red, uses real observations for MP from its first decision, and runs both arms through 518 seconds. Weights, traffic plans, detector thresholds and calibration are unchanged. `signal_timeline` records actual simulator signal-state transitions for verification only. All 240 Town runs are restarted with earlier records retained and excluded; completed Nansha runs are retained. Archived Town executors share the green-tail defect, so historical numbers are not acceptance results under the corrected protocol.
