# 对比口径 / Comparisons

当前融合版机器可读结果为 `results/fusion-2026-10-30.json`，说明见[融合评测](fusion-pilot-evaluation.md)。正常视觉三方、特殊视觉双方的规则继续适用；历史权重与融合权重分别标注。

## 唯一固定基线

只采用**已冻结的工程固定配时**：南沙使用各路口既有工程表，J02为35/14/10/17秒；Town为31/6/31/6秒。配置在 `reproduction/configs/junctions/` 与对应 `scenarios/*/scene.json` 中，已完成固定记录为 `results/engineering-fixed-2026-10-26.json`。

不重新搜索、不替换固定表，也不根据模型成绩调整固定方案。其他历史固定参考和对应视频退出当前复现入口，原始材料保留内部归档，不改名冒充工程方案。

## 比较范围与开发目标

- **正常视觉三方比较：S1、冻结工程固定配时、YOLO+MP。** 对工程固定方案检查整体改善和多数案例胜出；S1相对YOLO+MP整体耗时最多高5%。
- **特殊视觉仅双方比较：S1与YOLO+MP。** 每种预先确定的极端视觉条件、每个场景内，整体耗时至少降低10%为开发目标。不输出相对固定方案的特殊条件成绩。
- 南沙与Town分开按整体判断，不要求每个交叉口获胜。局部短板、失败和未配齐结果如实保留，不能只挑获胜路口汇总。
- 上述数值门槛由用户于2026-10-29明确，用于后续开发，不改写历史结果。先小批检查再决定扩量；未达目标时检查模型和实验，不改变基线保证获胜。
- 发布专用权重与融合权重分别标注，不能把一种权重或执行器的成绩归给另一版本。

The sole fixed baseline is frozen engineering timing. Clean views compare S1, engineering fixed timing and YOLO+MP; perturbed views compare S1 with YOLO+MP only. Development targets set on October 29 are at most 5% slower than YOLO+MP for clean views and at least 10% faster for each predefined extreme condition, separately within each scene. These are targets, not presumed outcomes or every-intersection guarantees. Historical results retain their original checkpoint and protocol scope.

## 指标与汇总

完整行程从正式车辆的计划出发时刻计至离开路网，包含进入路网前的等待。所有正式车辆完成后才有完整平均行程，不能只统计完成车辆而删除未完成车辆。

原矩阵使用有限时域截断指标：南沙为H=1298秒的每回合平均行程 `J_H`；Town为H=518秒的每回合总行程 `J`。两域绝对值不合并，截断指标也不与完整平均行程混算。

原矩阵改善率为：

```text
100 * (1 - sum(S1) / sum(baseline))
```

`scripts/summarize_released.py` 仅在 `clean` 中输出 `engineering_fixed_comparison`；特殊视觉没有固定比较字段。正常视觉另报三方共同成功的相同案例子集。S1与固定方案的独立有效配对不因YOLO单侧失败丢弃。“平”只指已记录指标完全相等，不代表已经证明近似等效。完整报告列出计划数、成功配对数和各方法失败数；成功子集改善不等于全计划成功。

历史已完成成绩的版本、范围与复测入口见[发行版本说明](released-results.md)。

## 同条件配对

- 使用相同交通计划、路线、车辆参数、随机种子、评价时域与停止规则。
- 相机方法使用相同机位、三帧观察规则和指定扰动。闭环策略不同后车辆状态会不同，不声称双方看到逐像素相同的画面。
- YOLO画线在正常机位完成后冻结；偏角测试中不重新画线。固定角度偏移与动态抖动分别测试。
- 相同相位转换与安全执行规则；模型输入仅为画面、静态路口信息和必要信号上下文，不接收车辆真值或未来到达计划。
- `fixed`只代表冻结工程方案，运行器在启动前拒绝`fixed`与非`clean`条件的组合。

## Town历史执行范围

当前修正后的Town执行规则为 `town-5s-green-tail-v2`：决定切换后保留完整5秒绿灯尾段，再执行3秒黄灯和2秒全红。首段绿灯9秒以建立完整观察窗，之后允许最短6秒绿灯；跨相位观察仍取实际仿真时刻的帧。

旧Town执行器漏掉绿灯尾段的历史记录继续保留，但不能当作修正后协议或当前HF权重的新成绩，也不能与修正后结果混算。首次决策使用实际观察，评价末端统一为518秒。详见[交叉口指标和执行修正](intersection-metrics.md)。

## YOLO+MP与辅助指标

YOLO+MP使用YOLO11m检测车辆，再按进口转向汇总压力；出口按无阻塞处理。三帧按0.25、0.25、0.5平滑，保留当前相位滞回，压力相同按红灯等待时间与相位顺序选择。检测失败不能替换为仿真真值。

同时保留排队、每车停车等待、停车次数、时间损失、入网等待和通过量，不能只用停车次数少替代等待改善。旧记录未保存的指标不能补成实测值。API耗时包含网络往返，不冒充纯模型计算耗时。

所有结果仅适用于明确列出的模型、运行环境、案例与视觉条件，不推广为任意路口或真实道路下的保证。
