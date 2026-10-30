# DeepSignal-S1-1.0

**A multimodal System One model for traffic signals: visual observations in, fast structured control decisions out.**

English | [简体中文](README.zh-CN.md)

[Model](https://huggingface.co/AIMS2025/DeepSignal-S1) · [Scenes](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes) · [Results](results/fusion-2026-10-30.json) · [Reproduction](docs/reproduction.md)

DeepSignal-S1 follows a **Jev-style structured probabilistic decision** approach. It reads temporal intersection views and signal context, scores candidate actions, and selects a legal control action directly. It does not generate a traffic-analysis essay for another program to parse, and does not require a separate YOLO detection stage.

The released **DeepSignal-S1-1.0** uses one fused checkpoint in Nansha and Town10HD. Its development addresses two practical questions: can visual control improve on frozen engineering timing in clean conditions, and can it remain more robust than detection plus Max Pressure when the camera feed degrades?

## Why System One

System One emphasizes fast, directly callable decisions, as illustrated by [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) and the open-source [OneJev](https://github.com/OmniJev/OneJev). DeepSignal-S1 applies this decision paradigm to traffic control: its inference interface returns an action and probabilities without generating a token-by-token reasoning narrative. It is not a wrapper around the commercial Jev service, and does not inherit another model's benchmark claims.

- **Vision to control:** temporal observations and signal context determine actions without operator-supplied live vehicle counts.
- **Structured decisions:** the model chooses among legal actions; the signal executor implements the committed green tail, yellow and all-red transitions.
- **One checkpoint across scenes:** the release covers T-junctions and four-arm intersections in Nansha as well as Town10HD.
- **Local deployment:** unquantized consumer-GPU inference is measured; quantization and edge deployment remain future work.

<!-- FUSION_HIGHLIGHTS:BEGIN -->
- **Effective clean control:** versus frozen engineering timing, S1 reduces vehicle-weighted mean journey time by **18.17%** across 72 Nansha cases and **33.77%** across five Town regimes.
- **Robust under visual disruption:** fixed camera shift reduces Town mean journey time by **82.93%** versus YOLO+MP; 31 px motion blur reduces Nansha mean journey time by **30.14%**.
- **Unquantized local inference:** 6823 RTX 5090 model calls average **485 ms**, with a 479 ms median.
<!-- FUSION_HIGHLIGHTS:END -->

## Town10HD: Decisions After Camera Repositioning

![Town10HD under fixed camera-angle shift](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/town-angle15.gif)

*Town10HD · fixed yaw ±15° / pitch ±8°. Both arms use the same traffic plan and aligned simulation timestamps; the 60-second simulation window plays at 5× speed.*

## Results

Results use **mean journey time in seconds per vehicle; lower is better**. Clean views compare S1, frozen engineering fixed timing and YOLO+MP. Perturbed views compare S1 with YOLO+MP only.

<!-- FUSION_RESULTS:BEGIN -->
### Clean views: three controllers

| Scene | Condition | Cases | Controller | Mean wait (s/veh) | Mean queue (veh) | Mean journey (s/veh) |
|---|---|---:|---|---:|---:|---:|
| Nansha | Clean | 72 | **S1** | 45.82 | 10.47 | 107.32 |
| Nansha | Clean | 72 | Engineering fixed | 68.55 | 15.52 | 131.15 |
| Nansha | Clean | 72 | YOLO+MP | 46.89 | 10.56 | 108.79 |
| Town10HD | Clean | 5 | **S1** | 20.45 | 3.56 | 38.22 |
| Town10HD | Clean | 5 | Engineering fixed | 40.46 | 5.40 | 57.70 |
| Town10HD | Clean | 5 | YOLO+MP | 20.22 | 3.59 | 38.22 |

### Perturbed views: S1 vs YOLO+MP

| Scene | Condition | Cases | Controller | Mean wait (s/veh) | Mean queue (veh) | Mean journey (s/veh) |
|---|---|---:|---|---:|---:|---:|
| Nansha | Defocus σ=9 | 9 | **S1** | 76.08 | 15.79 | 141.03 |
| Nansha | Defocus σ=9 | 9 | YOLO+MP | 104.86 | 31.04 | 167.48 |
| Nansha | 31 px motion blur | 9 | **S1** | 67.38 | 17.23 | 131.57 |
| Nansha | 31 px motion blur | 9 | YOLO+MP | 124.59 | 30.18 | 188.34 |
| Nansha | Fixed yaw ±15° / pitch ±8° | 9 | **S1** | 63.68 | 15.44 | 129.04 |
| Nansha | Fixed yaw ±15° / pitch ±8° | 9 | YOLO+MP | 87.01 | 21.18 | 154.36 |
| Nansha | Dynamic shake 5° | 9 | **S1** | 63.40 | 16.17 | 128.25 |
| Nansha | Dynamic shake 5° | 9 | YOLO+MP | 72.15 | 17.91 | 137.61 |
| Town10HD | Defocus σ=9 | 5 | **S1** | 27.51 | 4.10 | 44.43 |
| Town10HD | Defocus σ=9 | 5 | YOLO+MP | 92.97 | 9.75 | 109.15 |
| Town10HD | 31 px motion blur | 5 | **S1** | 20.28 | 3.58 | 38.10 |
| Town10HD | 31 px motion blur | 5 | YOLO+MP | 111.26 | 10.24 | 127.71 |
| Town10HD | Fixed yaw ±15° / pitch ±8° | 5 | **S1** | 19.23 | 3.45 | 37.11 |
| Town10HD | Fixed yaw ±15° / pitch ±8° | 5 | YOLO+MP | 205.09 | 13.67 | 217.40 |
| Town10HD | Dynamic shake 5° | 5 | **S1** | 19.13 | 3.32 | 37.20 |
| Town10HD | Dynamic shake 5° | 5 | YOLO+MP | 21.49 | 3.53 | 39.88 |

**Definitions:** mean wait includes stopped waiting and insertion waiting for formal evaluation vehicles. Mean queue is the time-averaged total halted vehicles on controlled incoming lanes during the common 98–398 s demand window, in vehicles rather than metres. Journey time starts at planned departure. Wait and journey means are vehicle-weighted; queues average equal-window case means.

Evaluation ends at 1298 s in Nansha and 518 s in Town. Unfinished vehicles contribute their elapsed time at the cutoff. Original records are unchanged; waiting and queue statistics come from recorded-action/signal SUMO replay checked against each original journey score.

Clean Nansha YOLO+MP was rerun on the same 72 cases with full logs. Its entire waiting/queue/journey row comes from that supplementary batch; S1 and engineering-fixed records are unchanged. The original unlogged MP results remain archived, not spliced into the new row.
<!-- FUSION_RESULTS:END -->

The clean Nansha main table covers all **72** predefined cases across nine intersections. The perturbation pilot is narrower: Nansha uses nine high-flow balanced cases at seed 97001; Town10HD uses five demand regimes at seed 18040. These are controlled simulation results, not claims of universal superiority or statistical significance.

Recorded cases show the actual visual condition and controller behavior; the on-screen score belongs to that recording. Overall effects are defined by the paired tables above, not by requiring every GIF case to be an S1 win.

## Eight Perturbation Views

<!-- FUSION_GALLERY:BEGIN -->
### Town10HD

#### Town10HD · Fixed yaw ±15° / pitch ±8°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/town-angle15.gif" alt="Town10HD · Fixed yaw ±15° / pitch ±8°">

https://github.com/user-attachments/assets/e7b4a406-1474-4d24-9514-ff6d6a2d8e91

#### Town10HD · Defocus σ=9

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/town-df9.gif" alt="Town10HD · Defocus σ=9">

#### Town10HD · 31 px motion blur

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/town-mb31.gif" alt="Town10HD · 31 px motion blur">

#### Town10HD · Dynamic shake 5°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/town-shake5.gif" alt="Town10HD · Dynamic shake 5°">

### Nansha

#### Nansha · Fixed yaw ±15° / pitch ±8°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/nansha-angle15.gif" alt="Nansha · Fixed yaw ±15° / pitch ±8°">

#### Nansha · Defocus σ=9

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/nansha-df9.gif" alt="Nansha · Defocus σ=9">

#### Nansha · 31 px motion blur

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/nansha-mb31.gif" alt="Nansha · 31 px motion blur">

https://github.com/user-attachments/assets/931d0d1f-338f-497d-ab87-d883c54ab54a

#### Nansha · Dynamic shake 5°

<img width="1280" src="https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/nansha-shake5.gif" alt="Nansha · Dynamic shake 5°">
<!-- FUSION_GALLERY:END -->

Media show only the actual model camera input, live traffic metrics and the most recent recorded decision. **Mean wait** is cumulative stopped waiting divided by all vehicles entered so far, including those already arrived. **Queue** is the current stopped-vehicle count. Both include shared warmup traffic and come from recorded-signal SUMO replay checked against every video frame, unlike the formal-cohort batch means that also include insertion waiting. Episode mean journeys belong to that recording, not the evaluation batch.

All displayed cases are four-arm intersections. Video previews use a large 4:3 dashboard with one controller per row, adapted to GitHub's player-height limit. Each 12-second preview covers the same 60 simulation seconds at 5x speed, using original recorded frames at 25 fps and H.264 Constrained Baseline. Complete recordings remain in the media archive. Shake GIFs retain 960-pixel width and show a 24-second simulation excerpt rather than shrinking the entire interface. Each video also has an alternate large-screen player.

Lane regions are calibrated on the clean camera pose and then frozen. For `angle15`, the camera is shifted **after calibration**, remains fixed for the episode, and is not recalibrated. `shake5` applies dynamic yaw/pitch peaks of 5° and roll peaks of 2.5°.

<!-- FUSION_CLEAN_VIDEOS:BEGIN -->
### Clean Nansha: Three Controllers

https://github.com/user-attachments/assets/c4347efa-b450-4b79-a554-1157ddccb1bf

### Clean Town10HD: Three Controllers

https://github.com/user-attachments/assets/679fea40-44b6-4954-88fa-c20e329ec29f
<!-- FUSION_CLEAN_VIDEOS:END -->

## Inference Performance

<!-- FUSION_LATENCY:BEGIN -->
| Scope | Count | Mean | Median | P95 | Max | Under 1 s |
|---|---:|---:|---:|---:|---:|---:|
| All calls | 6823 | 485.4 ms | 479.0 ms | 494.0 ms | 2304.0 ms | 99.08% |
| First call per run | 133 | 911.1 ms | 495.0 ms | 1460.2 ms | 2304.0 ms | 52.63% |
| Subsequent calls | 6690 | 476.9 ms | 479.0 ms | 493.0 ms | 675.0 ms | 100.00% |
<!-- FUSION_LATENCY:END -->

The unquantized BF16 checkpoint reads temporal intersection views; sampling details are in the reproduction guide. Statistics cover 133 S1 cases: 72 Nansha clean cases and 61 fusion-pilot S1 cases. Camera capture, rendering and control execution are excluded. First calls include initialization effects; subsequent calls characterize steady state.

**Deployment direction:** sub-second steady-state decisions on a consumer RTX 5090 make signal-control workstations a practical target. A colleague also reported approximately **900 ms on an RTX 4090** with the unquantized model; its measurement conditions remain unverified, so it is not included in the benchmark. Quantization and edge-device deployment are future work, not demonstrated capabilities. A universal sub-second guarantee has not been established.

## Download and Quickstart

Model and simulation-asset downloads require separate access approvals. Demo GIFs, videos and result data are openly available from [DeepSignal-S1-Media](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media). The release retains the v3 scene assets; use them with the latest GitHub code. Viewing media does not require downloading the scene package.

```bash
python3.12 -m venv .venv-inference
source .venv-inference/bin/activate
pip install -U huggingface_hub
hf auth login
hf download AIMS2025/DeepSignal-S1 --local-dir ./DeepSignal-S1-model

deactivate

git clone https://github.com/AIMS-Laboratory/DeepSignal-S1.git DeepSignal-S1
cd DeepSignal-S1
python3.10 -m venv .venv
.venv/bin/pip install -e '.[test,reproduction,download]'
```

The model server, a real three-frame request that needs no simulator, and closed-loop commands are documented in [Reproduction](docs/reproduction.md). Download the complete model folder; approved access does not create a hosted API. A full fresh-download closed-loop replay has not yet been certified.

## Evaluation Scope

- **Sole fixed baseline:** frozen engineering timing, with Nansha per-intersection plans and Town10HD `31/6/31/6 s`.
- **Signal transitions:** decisions retain a 5 s green tail, followed by 3 s yellow and 2 s all-red where applicable.
- **Finite horizon:** unfinished journeys remain counted; results are not complete-trip averages.
- **Known Nansha limitation:** the retained red-age accounting protocol can over-count one phase's red age after an immediate first switch. Both arms use the same protocol, but this pilot is not a full correctness certification.

See [fusion evaluation](docs/fusion-pilot-evaluation.md), [metric definitions](docs/comparisons.md), and [media delivery](docs/media-delivery.md).

## Historical Releases

Earlier `DeepSignal-S1-1.0-candidate` Nansha results and the separate historical Town checkpoint remain archived with their original protocol labels. They are not weights or scores of the fused 1.0 release. See [historical released results](docs/released-results.md).

Contact: [dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
