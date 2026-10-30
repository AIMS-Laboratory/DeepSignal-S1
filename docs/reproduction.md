# DeepSignal-S1-1.0 复现指南 / Reproduction

本页是融合权重 **DeepSignal-S1-1.0** 的唯一当前复现入口。正常视觉比较S1、冻结工程固定配时和YOLO+MP；特殊视觉只比较S1与YOLO+MP。机器可读案例定义为 `reproduction/fusion-release-matrix.json`，公开结果为 `results/fusion-2026-10-30.json`。

CPU测试和6/6固定动作样例已经通过；从公开下载开始的完整视觉闭环复跑尚未认证。以下命令提供可执行入口，不表示这些下载命令已经在全新机器上完成全部GPU矩阵。

## 1. 下载代码、模型与v3场景

模型与仿真资产分别采用审批下载，继续使用v3资产。[融合版媒体和结果数据](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media)无需审批，观看媒体不需要下载场景包。

```bash
pip install -U huggingface_hub
hf auth login
hf download AIMS2025/DeepSignal-S1 --local-dir ./DeepSignal-S1-model
hf download AIMS2025/DeepSignal-S1-Scenes DeepSignal-S1-Scenes-v3.tar.gz \
  --repo-type dataset --local-dir ./downloads
git clone https://github.com/AIMS-Laboratory/DeepSignal-S1.git DeepSignal-S1
cd DeepSignal-S1
```

必须使用GitHub最新代码。v3压缩包内的旧代码快照早于融合版最终入口，不能单独用于当前复现。

## 2. 分离三个Python环境

模型服务使用Python 3.12。南沙UE5/CARLA 0.10.0与Town CARLA 0.9.16客户端使用两个独立Python 3.10环境，两个CARLA wheel不能装进同一环境。

```bash
# Model inference
python3.12 -m venv .venv-inference
.venv-inference/bin/pip install -r ../DeepSignal-S1-model/requirements.txt

# Install shared v3 assets once
python3.10 -m venv .venv-bootstrap
.venv-bootstrap/bin/pip install -e '.[download]'
.venv-bootstrap/bin/deepsignal-s1 install-assets \
  --archive ../downloads/DeepSignal-S1-Scenes-v3.tar.gz

# Nansha: UE5 / CARLA 0.10.0
python3.10 -m venv .venv-nansha
.venv-nansha/bin/pip install -e '.[test,reproduction]'
.venv-nansha/bin/pip install \
  assets/runtime/python/carla-0.10.0-cp310-cp310-linux_x86_64.whl

# Town10HD: CARLA 0.9.16 archive runtime
python3.10 -m venv .venv-town
.venv-town/bin/pip install -r reproduction/legacy-town/requirements.txt
.venv-town/bin/pip install \
  assets/runtime/python/carla-0.9.16-cp310-cp310-manylinux_2_31_x86_64.whl
```

路径以v3实际解压目录为准。需要Linux、SUMO 1.18.0、NVIDIA GPU和Town归档运行环境所需的Docker/NVIDIA CDI。

## 3. 启动融合模型服务

```bash
CUDA_VISIBLE_DEVICES=0 .venv-inference/bin/python scripts/serve_model.py \
  --model ../DeepSignal-S1-model --port 18404 --device cuda:0
```

服务版本必须报告 `DeepSignal-S1-1.0`。模型输入为4秒观察窗内按2秒间隔取得的三帧画面、静态路口信息、当前信号状态与合法动作，不接收仿真车数或未来到达计划。

可先用仓库内的真实三帧失焦请求检查模型服务，无需下载或启动三维场景：

```bash
curl --fail http://127.0.0.1:18404/v1/decide \
  -H 'Content-Type: application/json' \
  --data-binary @examples/nansha-defocus-request.json
```

这个请求来自南沙J08、失焦σ=9的短时一致性检查，已验证研究环境与发布包的动作和全部概率相同。这里只验证模型推理接口，不将单次请求当作闭环交通效果测试，也不回放答案替代模型。

## 4. 启动场景

### 南沙：UE5 / CARLA 0.10.0

```bash
.venv-nansha/bin/deepsignal-s1 launch-scene \
  --scene scenarios/nansha-j02/scene.json \
  --assets assets/runtime --port 25020 --adapter 0
```

九个南沙路口按矩阵配置切换对应场景。渲染使用发布配置；每个仿真会话独占一个场景端口。

### Town10HD：CARLA 0.9.16 Docker

使用v3内的Town归档Docker运行环境和匹配0.9.16客户端。融合入口采用修正后的时序：决定切换后保留5秒绿灯，再执行3秒黄灯和2秒全红。pilot的YOLO+MP warm handoff `hist0` 为零占位。不要用UE5/CARLA 0.10.0 Town showcase替代主页评测环境。

```bash
docker load -i assets/runtime/runtime/town10hd-archive/carla-0.9.16.docker.tar
python3 scripts/launch_town_archive.py --gpu GPU-YOUR-UUID --port 25020
```

将 `GPU-YOUR-UUID` 替换为 `nvidia-smi -L` 显示的GPU UUID。启动后将同一CARLA RPC端口传给矩阵入口的 `--port`。

## 5. 启动YOLO+MP检测服务

```bash
CUDA_VISIBLE_DEVICES=1 /path/to/detector/python scripts/archived_detector_service.py \
  --model assets/runtime/reproduction/baselines/yolo11m.pt --port 8031
```

使用发行材料中的YOLO11m、置信度0.25和冻结车道区域。固定角度测试在正常机位画线后改变相机，整回合保持偏移且不重新标定。检测失败不得用仿真真值替代。

## 6. 正常视觉主表

南沙72案例使用 `nansha-fusion-clean`，只接受`clean`。三方分别运行：

```bash
.venv-nansha/bin/python scripts/run_fusion_matrix.py \
  --suite nansha-fusion-clean --controller fixed --condition clean \
  --output out/reproduction/nansha-fixed-clean

.venv-nansha/bin/python scripts/run_fusion_matrix.py \
  --suite nansha-fusion-clean --controller s1 --condition clean \
  --endpoint http://127.0.0.1:18404 --port 25020 \
  --output out/reproduction/nansha-s1-clean

.venv-nansha/bin/python scripts/run_fusion_matrix.py \
  --suite nansha-fusion-clean --controller visual-pressure --condition clean \
  --detector-endpoint http://127.0.0.1:8031/v1/detect2 --port 25020 \
  --output out/reproduction/nansha-mp-clean
```

Town正常视觉使用 `town10hd-fusion-pilot`，同样分别运行`fixed`、`s1`和`visual-pressure`。Town固定方案为31/6/31/6秒。

## 7. 特殊视觉小批

南沙特殊视觉使用 `nansha-fusion-pilot`，每条件九个高流量均衡案例、种子97001。Town使用 `town10hd-fusion-pilot`，每条件五类车流、种子18040。条件为 `df9`、`mb31`、`angle15`、`shake5`，只运行`s1`和`visual-pressure`。

```bash
.venv-nansha/bin/python scripts/run_fusion_matrix.py \
  --suite nansha-fusion-pilot --controller s1 --condition mb31 \
  --endpoint http://127.0.0.1:18404 --port 25020 \
  --output out/reproduction/nansha-s1-mb31

.venv-town/bin/python scripts/run_fusion_matrix.py \
  --suite town10hd-fusion-pilot --controller visual-pressure --condition angle15 \
  --detector-endpoint http://127.0.0.1:8031/v1/detect2 --port 25020 \
  --output out/reproduction/town-mp-angle15
```

`fixed`与非`clean`组合会被拒绝。失败记录保留，不因结果不利重复运行或筛选案例。

## 8. 指标与汇总

南沙使用1298秒时域内的截断平均行程时间 `J_H`；Town使用518秒时域内的截断行程总量 `J`。未完成车辆按时域末端计入。两个场景分别汇总，绝对值不能合并，也不能称为完整行程平均值。

改善率为：

```text
100 * (1 - sum(S1) / sum(baseline))
```

正常视觉可对冻结工程固定配时和YOLO+MP分别计算；特殊视觉只对YOLO+MP计算。完整公开口径、逐案例来源与已知南沙红龄限制见[融合评测](fusion-pilot-evaluation.md)。

## 9. 重新生成表格与图

```bash
python scripts/export_fusion_results.py --help
.venv-nansha/bin/pip install -e '.[plots]'
python scripts/render_fusion_pages.py
.venv-nansha/bin/python scripts/plot_homepage_results.py --language zh
.venv-nansha/bin/python scripts/plot_homepage_results.py --language en
```

表格由 `results/fusion-2026-10-30.json` 和对应的 `fusion-2026-10-30-traffic.json` 生成。`plots` extra安装Matplotlib 3.9或更高版本。中文图需要系统字体Noto Sans CJK；英文图不依赖中文字体。历史candidate与历史Town专用权重的旧入口见[历史复现说明](historical-reproduction.md)，不得与融合1.0混算。

主页两张三指标比较图由 `plot_homepage_results.py` 单独生成，直接读取表格生成器输出的 `results/fusion-2026-10-30-traffic.csv`，保留同一批次的等待、排队和行程，不读取历史归一化成绩。正常视觉比较 S1、冻结工程固定配时和 YOLO+MP；特殊视觉仅比较 S1 与 YOLO+MP，百分比为 `(YOLO+MP - S1) / YOLO+MP × 100%`。中英文分别保存为 `*-zh` 和 `*-en` 的 PNG 与可编辑 SVG，插入各自表格下方。图示为已公开的汇总均值，不添加置信区间。
