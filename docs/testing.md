# 测试指南 / Testing

## 场景安装 / Scene Setup

南沙九路口与 Town10HD 共用一个 **27.60 GiB** 场景压缩包，公开托管于 [HF 场景数据集](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes)，无需 Google Drive。请先查看数据集卡片的上传就绪状态，下载后安装一次，再选择场景启动：

```bash
pip install -e '.[download]'
hf download AIMS2025/DeepSignal-S1-Scenes DeepSignal-S1-Scenes-v3.tar.gz \
  --repo-type dataset --local-dir downloads
deepsignal-s1 install-assets --archive downloads/DeepSignal-S1-Scenes-v3.tar.gz
pip install assets/runtime/python/carla-0.10.0-cp310-cp310-linux_x86_64.whl
deepsignal-s1 launch-scene --scene scenarios/nansha-j02/scene.json \
  --assets assets/runtime --port 25020 --adapter 0
```

服务器在前台运行，使用独立端口、Epic 画质。`--adapter` 指定 Vulkan 图形设备序号，不假设两张显卡的序号在所有机器上相同。另开终端运行测试；不要让两个测试进程同时操作同一个场景服务器。

The scene server runs in the foreground with Epic quality. Start tests in another terminal and give each simulation session its own server. The client refuses to remove vehicles or sensors belonging to an existing session.

Town10HD 已包含在同一个压缩包内，使用 `--scene scenarios/town10hd/scene.json` 启动；两套运行文件在包内分开存放，不覆盖彼此。原矩阵测试入口与指标见[复现指南](reproduction.md)。

Both UE5 scene runtimes are included in the same public HF archive. Install once and choose the scene with `--scene`; the Nansha and Town10HD engine directories remain separate. The v2 bundle also supplies the archived CARLA 0.9.16 Town environment; use the [release-specific instructions](released-results.md) and a separate matching client for it, not the UE5 commands above.

## 模型闭环 / Model Test

HF 模型文件和 API 均为申请制。地址尚未开放时，固定配时 CPU 测试仍可独立使用，模型测试不能用回放替代。

```bash
export HF_TOKEN="your_approved_account_token"
export DEEPSIGNAL_ENDPOINT="https://your-assigned-model-endpoint"
deepsignal-s1 run-suite --suite scenarios/showcase.json \
  --controller s1 --port 25020 --output runs/comparison
```

`--realtime` 启用按真实时间推进及一秒决策时限；推理在后台执行，仿真不暂停等待模型。没有该选项时为在线仿真测试，不能据此声称实际实时性。

`--record` 录制每秒五帧的四路摄像头画面和对应时间线，覆盖原有的三个模型观察时刻。仿真仍以 0.1 秒步长推进；视频保持原速，不删除真实推理等待。实时录制也必须单独验证时限；高画质编码可能使运行变慢。

录制保持 Epic 画质，摄像头直接按合成图的单格分辨率渲染（南沙为每路 800×450，合成为 1600×900）。不录制的观察测试采用场景配置的原生摄像头分辨率。两种配置在报告的 `capture_profile` 中区分；视频的整回合成绩单独计算，不替换评测矩阵的成绩。4K 是最终对比视频画布大小，不代表每路摄像头均为原生 4K。

Recording retains Epic settings and renders each camera at its composite tile size (800×450 per Nansha view). Non-recording tests use the configured native camera sizes. Reports distinguish these capture profiles; video results are measured from the recorded episodes, separately from the evaluation matrix. The final comparison canvas is 4K, not each native camera.

## YOLO+MP 基线 / YOLO+MP Baseline

YOLO+MP 基线使用独立检测服务，不读取仿真真值。命令中的控制器标识为 `visual-pressure`：

```bash
pip install -e '.[baseline]'
python scripts/detector_service.py --weights /path/to/yolo11m.pt --device cpu --port 8032
```

在另一个终端：

```bash
deepsignal-s1 run-suite --suite scenarios/showcase.json \
  --controller visual-pressure --detector-endpoint http://127.0.0.1:8032 \
  --port 25020 --output runs/comparison
deepsignal-s1 run-suite --suite scenarios/showcase.json \
  --controller fixed --cpu --output runs/comparison
deepsignal-s1 summarize --suite scenarios/showcase.json --runs runs/comparison
```

每个输出目录只能写入一次，避免覆盖原始回合。失败时保留局部记录。修复环境后使用新的输出根目录，不把失败回合重命名成成功结果。

## API

`POST {DEEPSIGNAL_ENDPOINT}/v1/decide`，认证头为 `Authorization: Bearer {HF_TOKEN}`。

请求包含 `frames`（按时间从早到晚的三个 JPEG Base64 图像）、`intersection`（静态路口配置）、`signal`（当前相位和已承诺绿灯时间）、`legal_actions`（当前允许的动作）。不发送车数、排队、路径或未来需求。

成功响应：

```json
{"choice": "extend_5s", "model_version": "DeepSignal-S1-1.0"}
```

`choice` 必须属于请求的 `legal_actions`，例如 `extend_5s` 或 `switch_to_n2`。权限不足、超时、缺失版本或非法动作均视为测试失败。

## 对比视频 / Comparison Video

两侧都录制完成后：

```bash
deepsignal-s1 make-video --model-run runs/recording/s1 \
  --fixed-run runs/recording/fixed --output dist/comparison
```

输出为 4K MP4 和封面 JPG。两侧使用相同到达计划和视觉条件；先完成的一侧保留最终画面并显示完成状态。视频上传 YouTube 后，使用封面图片链接到视频。
