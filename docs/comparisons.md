# 对比口径 / Comparisons

主页新增的已完成原矩阵结果见[发行版本说明](released-results.md)。南沙与 Town 使用两份明确标注的权重和匹配的仿真环境；该矩阵采用有限时域截断行程，不与下述完整行程展示指标混算。

The completed finite-horizon suites use explicitly named scene-specific checkpoints and matching runtimes; see [release definitions](released-results.md). They are distinct from the complete-journey demonstrations below.

## 主指标

每辆正式车辆的行程时间为“到达时刻减计划出发时刻”，包含拥堵造成的路网外等待。所有正式车辆完成后，计算平均值，单位为秒。未完成时平均行程时间为空，不以只统计已完成车辆的方式代替。

Mean journey time is calculated over all formal vehicles, including waiting before insertion. An unfinished run has no final journey mean.

汇总采用车辆数加权平均。改善百分比为：

```text
100 * (1 - DeepSignal-S1 mean journey time / baseline mean journey time)
```

## 同条件配对

- 同一到达计划、路线、车辆参数、随机种子和停止规则。
- 同一模型版本完成全部选定展示回合，不混合不同模型的成绩。
- 同样的相位转换和安全执行规则。当前默认固定配时使用既有工程表；2026-10-25 存档和视频使用另一套已标明的调优参考表，不能与当前默认方案混淆。
- 相机方法使用相同机位、观察窗和指定视觉扰动。闭环策略不同之后，车辆状态自然会不同，不宣称双方始终看到逐像素相同的画面。
- 三帧观察间隔为两秒；模型交通信息来自画面，信号时钟和静态路口信息作为必要执行上下文。

Town 的自适应控制首段绿灯为 9 秒，以建立完整的四秒观察历史；后续仍允许 6 秒最短绿灯。后续观察窗可以跨越黄灯、全红和新绿灯阶段，帧按原始仿真时刻采集，不复制旧帧填充。

Town adaptive runs start with a 9-second green to establish the observation history; subsequent greens retain the 6-second minimum. Cross-phase observation windows use actual frames from their scheduled times.

上述 Town 自适应执行约束以修正后的 `town-5s-green-tail-v2` 为准：决定切换后仍执行完整 5 秒绿灯尾段，再执行 3 秒黄灯和 2 秒全红。旧 Town 执行器漏掉了这段绿灯，历史记录不能视为已满足这些约束，也不与修正后的补测混算。两侧首次决策均使用实际观察，观察末端统一为 518 秒。详见[执行修正说明](intersection-metrics.md)。

These Town adaptive timing constraints apply to corrected `town-5s-green-tail-v2`: retain the full five-second green tail before 3 seconds yellow and 2 seconds all-red. Legacy Town executors omitted that tail; their historical scores do not establish compliance and are not pooled with corrected runs. Both arms use real observations from their first decision and share the 518-second horizon. See [execution corrections](intersection-metrics.md).

`summarize` 要求展示矩阵的全部回合齐备且完整。缺失、失败、到达计划不同或模型版本混用时，不生成有效对比结论。

## YOLO+MP 对照

2026-10-25 的存档展示条件均同时比较 YOLO+MP 与当时的调优固定参考。该参考配置保留为各场景的 `scene.tuned-reference.json`；当前 `scene.json` 默认改为工程固定配时，不能用当前默认表复算旧固定数字。失焦条件重点比较 DeepSignal-S1 与 YOLO+MP：双方使用相同机位、同一失焦处理与同样的三帧观察时刻。固定配时不依赖画面，因此不能将失焦条件下相对固定配时的收益解释为视觉鲁棒性证据。

YOLO+MP 使用 YOLO11m 检测车辆，再按进口转向汇总相位压力；本测试场景的出口按无阻塞处理。三个观察时刻按 0.25、0.25、0.5 平滑，保留当前相位滞回；压力相同时按红灯等待时间、再按相位顺序选择。检测服务不接收 SUMO 的车辆数或排队真值。控制器命令标识为 `visual-pressure`，结果版本为 `yolo-mp-v1`。

The archived October 25 comparisons include YOLO+MP and the then-used tuned fixed reference. Reproduce those fixed numbers with `scene.tuned-reference.json`, not the current engineering-timing default. Defocus comparisons primarily target YOLO+MP under the same camera degradation and observation schedule. Fixed timing does not consume images, so its defocus comparison alone is not evidence of visual robustness. YOLO+MP uses image detections and incoming-movement pressure with unblocked exits; signal red age resolves equal-pressure ties. No simulator traffic counts are supplied to the detector.

## 辅助指标

精选展示客户端的平均排队车辆数按正式车辆中速度低于 0.1 m/s 的车辆数作时间平均。原矩阵新入口另记受控进口车道的平均排队车辆数、每车停车等待、停车次数、时间损失、入网等待与通过量，两者的统计人群不混用。具体字段、窗口和缺失处理见[交叉口指标](intersection-metrics.md)。旧回合未保存的指标不能事后填成实测值。API 请求时间包含网络往返，不冒充纯模型计算时间。

## 展示范围

这是选定仿真场景的功能展示，不是全路网评测。比较时明确场景和视觉条件，不把一个路口或某种模糊条件下的收益推广为普遍结论。

The demonstration suite is explicitly selected. A result applies to its named scene, traffic regime, model release and camera condition, not every intersection or condition.
