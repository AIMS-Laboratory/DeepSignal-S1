# 对比口径 / Comparisons

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
- 同样的相位转换和安全执行规则；固定配时使用场景内已冻结的调优配时表。
- 相机方法使用相同机位、观察窗和指定视觉扰动。闭环策略不同之后，车辆状态自然会不同，不宣称双方始终看到逐像素相同的画面。
- 三帧观察间隔为两秒；模型交通信息来自画面，信号时钟和静态路口信息作为必要执行上下文。

`summarize` 要求展示矩阵的全部回合齐备且完整。缺失、失败、到达计划不同或模型版本混用时，不生成有效对比结论。

## 辅助指标

平均排队车辆数：正式车辆中速度低于 0.1 m/s 的车辆数，对正式观察时段作时间平均。完成数与未完成数同时保留。API 请求时间包含网络往返，不冒充纯模型计算时间。

## 展示范围

这是选定仿真场景的功能展示，不是全路网评测。比较时明确场景和视觉条件，不把一个路口或某种模糊条件下的收益推广为普遍结论。

The demonstration suite is explicitly selected. A result applies to its named scene, traffic regime, model release and camera condition, not every intersection or condition.
