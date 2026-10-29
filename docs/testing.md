# 测试入口 / Testing

## 主页评测

正式融合权重 **DeepSignal-S1-1.0** 的当前入口是 [`scripts/run_fusion_matrix.py`](../scripts/run_fusion_matrix.py)，完整环境、模型服务、南沙UE5、Town CARLA 0.9.16 Docker、YOLO+MP与矩阵命令见[融合版复现指南](reproduction.md)。

主页结果使用：

- `nansha-fusion-clean`：南沙正常视觉72案例，三方比较。
- `nansha-fusion-pilot`：南沙四类特殊视觉，每条件9案例，只比较S1与YOLO+MP。
- `town10hd-fusion-pilot`：Town正常视觉三方及四类特殊视觉双方比较，每条件5案例。

条件标识为`clean`、`df9`、`mb31`、`angle15`和`shake5`。`fixed`只允许`clean`。模型版本必须为`DeepSignal-S1-1.0`。

## 场景资产

南沙与Town继续使用公开v3资产。只下载融合版GIF或视频时无需重复下载场景包；运行闭环时必须使用GitHub最新代码，不能直接使用v3压缩包内的旧代码快照。

```bash
hf download AIMS2025/DeepSignal-S1-Scenes DeepSignal-S1-Scenes-v3.tar.gz \
  --repo-type dataset --local-dir downloads
```

南沙主页评测使用UE5/CARLA 0.10.0。Town主页评测使用v3中的CARLA 0.9.16 Docker环境和匹配Python wheel，不使用UE5 Town showcase替代。两个CARLA客户端必须安装在不同Python 3.10环境；模型服务使用独立Python 3.12环境。

## 模型与检测服务

模型采用审批下载并在本地启动，不假定存在远程托管endpoint。请求包含三帧画面、静态路口信息、当前信号状态和合法动作；不发送仿真车数、未来需求或参考答案。

YOLO+MP使用独立YOLO11m检测服务、置信度0.25和冻结车道区域。检测失败不能用仿真真值替代。固定角度条件先在正常机位标定，再移动相机且不重新画线。

## Showcase入口

`deepsignal-s1 run-suite --suite scenarios/showcase.json`、UE5 Town10HD启动方式、`--record`和`make-video`属于功能展示及素材录制入口，**不是主页融合评测矩阵**。它们可以用于界面检查、视频录制和单案例演示，但其结果不能替代 `run_fusion_matrix.py` 的发布成绩。

Showcase录制采用独立捕获配置，可能改变渲染分辨率和运行速度。只有显式`--realtime`且满足决策时限的回合才能称为实时运行；普通在线仿真录制不自动证明实时性。

## 输出与失败

每个输出目录只写一次。保留到达计划、逐车记录、信号时间线、控制动作、推理或检测失败和结果报告。双方使用相同交通计划与扰动定义，但闭环动作会改变后续交通，因此不要求后续画面逐像素相同。

失败回合不得改名为成功结果，也不得因成绩不利重跑以筛选胜例。CPU测试与6/6固定动作样例已通过，但从公开下载开始的完整视觉闭环复跑尚未认证。

历史candidate、历史Town专用权重和旧迁移矩阵见[历史复现说明](historical-reproduction.md)。
