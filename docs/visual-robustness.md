# 特殊视觉条件的现实意义 / Real-World Visual Disturbances

四类测试分别考察清晰度、曝光拖影、固定视角变化和持续视角变化。下面的现实原因解释测试的应用意义，不表示这些现场工况都已经实测。

## 失焦

复杂光源、车灯与移动目标可能使自动对焦难以稳定找到焦点；手动调焦或更换镜头后也可能需要重新对焦。这些问题会使物体边缘不清晰。Axis 的[对焦故障说明](https://help.axis.com/en-us/troubleshooting-focus)专门讨论了交通场景中的对焦搜索以及镜头调整问题。

本项目用失焦模糊近似考察细节损失，不将它等同于雨滴、镜头污渍、结露或雾天；这些现象的成像机制不同。

## 运动模糊

曝光时间较长时，车辆或相机在曝光期间的移动可能形成拖影。低光环境下提高画面亮度与减小运动模糊之间存在取舍，见 Axis 的[摄像机曝光与低光运动模糊说明](https://help.axis.com/en-us/axis-q1647-le#reduce-motion-blur-in-low-light-conditions)。

本项目的水平模糊是方向性拖影的简化压力测试，不是完整的低光、夜间或逐车辆运动成像模型。

## 固定角度偏移

重新调整摄像头方向后，即使画面稳定，车道和停车线在图像中的位置也会变化。摄像机厂商将设备被重新定向列为需要监测的画面变化，见 Axis 的[相机状态事件说明](https://developer.axis.com/vapix/network-video/event-and-action-services/)。将检修后重新定向、支架偏转作为现实例子，是本项目对这种视角变化的应用场景解释。

本项目先在正常机位完成 YOLO 车道区域标定，再改变并固定视角，不重新画线。这里考察原标定未更新时的表现，不表示重新标定后的 YOLO+MP 也会得到相同结果。

## 动态抖动

高杆上的摄像头可能受到阵风和邻近重型交通引起的振动影响，使视角连续变化；Axis 的[图像稳定白皮书](https://whitepapers.axis.com/en-us/image-stabilization)讨论了这类安装与环境因素。

本项目改变连续画面的相机姿态，考察画面不稳定时的控制效果。抖动幅度是测试设置，不对应某个已经标定的风速或车辆载荷。

## 为什么与交通控制有关

画面细节损失可能影响检测与计数，视角变化可能使车辆与原车道区域错位。这是根据检测计数控制链路作出的机制解释，不是对每种性能差异已经完成的独立因果验证。

S1 不使用独立的 YOLO 检测计数接口，而是根据时序画面与信号上下文直接选择动作。当前两个场景、四种视觉条件下更低的平均等待、平均排队长度和平均行程，支持在这组测试范围内具有更好的视觉鲁棒性。逐条件结果见 [README](../README.zh-CN.md#评测结果)。

## English Summary

The four tests address different imaging problems, with illustrative real-world causes:

- **Defocus:** mixed lighting and moving headlights can disrupt autofocus; manual focus or lens replacement can require refocusing. See the manufacturer's [focus troubleshooting guide](https://help.axis.com/en-us/troubleshooting-focus).
- **Motion blur:** vehicle or camera movement during a longer exposure can smear image detail. See the manufacturer's [low-light exposure guidance](https://help.axis.com/en-us/axis-q1647-le#reduce-motion-blur-in-low-light-conditions).
- **Fixed angle shifts:** a camera can become steady after being redirected, while lane positions no longer match previous image-space regions. Maintenance-related re-aiming and mount shifts are illustrative deployment scenarios; camera redirection is recognized in the manufacturer's [event documentation](https://developer.axis.com/vapix/network-video/event-and-action-services/).
- **Dynamic shake:** wind gusts and nearby heavy traffic can vibrate pole-mounted cameras. See the manufacturer's [image stabilization white paper](https://whitepapers.axis.com/en-us/image-stabilization).

These are controlled approximations of visual effects, not completed night-time or adverse-weather field tests. Defocus is not a fog, rain, condensation or dirty-lens model; horizontal blur is not a complete low-light imaging model; the shake amplitude is not calibrated to a particular wind speed. The fixed-angle comparison keeps YOLO's original lane calibration unchanged and does not establish the outcome after recalibration.

Detection/counting errors and lane-region misalignment are plausible mechanisms, not isolated causal findings from these comparisons. Robustness here means better measured traffic outcomes within the evaluated conditions, not immunity to every camera fault.
