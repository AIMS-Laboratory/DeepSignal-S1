# DeepSignal-S1

**One system, from visual traffic observations to signal decisions.**

English | [简体中文](README.zh-CN.md)

**DeepSignal-S1 is a vision-first System One decision model for real-time traffic signal control. S1 means one system:** visual traffic understanding and signal-action selection are brought together in one multimodal decision model.

Following a **Jev-style, decision-first formulation**, DeepSignal-S1 takes intersection camera views and current signal context, then directly selects a permitted signal action rather than generating a conversational response. Traffic observations come from the images; a separate YOLO perception stage is not required by the S1 controller. **YOLO+MP is a comparison baseline, not a component of DeepSignal-S1.**

This repository provides DeepSignal-S1's simulation scenarios, demonstration results and test client. Model files and the standalone inference runtime are distributed separately through Hugging Face.

## Demonstration Video

[![DeepSignal-S1 comparison video](assets/comparison-cover.jpg)](https://github.com/AIMS-Laboratory/DeepSignal-S1/releases/download/v0.1.0/DeepSignal-S1-vs-fixed.mp4)

**[Watch / download the 4K comparison](https://github.com/AIMS-Laboratory/DeepSignal-S1/releases/download/v0.1.0/DeepSignal-S1-vs-fixed.mp4)** · YouTube link to follow after upload.

**DeepSignal-S1 on the left; tuned fixed timing on the right.** Both episodes ran in real time with Epic rendering, the same arrival plan and seed 99001. All 121 formal vehicles completed their journeys. Mean complete journey time is **81.42 s vs 90.82 s: 10.35% shorter**.

The video preserves real timing at 1× playback, with signal actions and countdowns. Its single-episode measurements are separate from the three-seed table below. [Recorded-case measurements](results/video-nansha-99001.json).

## Baseline Comparisons

| Controller | Traffic observation | Signal decisions | Public test entry |
| --- | --- | --- | --- |
| **DeepSignal-S1** | Camera frames and current signal context | Adaptive | `--controller s1` |
| Engineering fixed timing | Pre-existing timing plan, without final-test search | Fixed phase cycle | `--controller fixed` |
| YOLO+MP | YOLO camera-based vehicle detection | Movement-pressure control | `--controller visual-pressure` |

### Selected Visual Comparisons

Measured on **October 25, 2026**, using one serving release, **DeepSignal-S1-1.0-candidate**, and three new seeds per case: **99001, 99002, 99003**. Values are vehicle-weighted mean complete journey time in seconds, including waiting before insertion. **Lower is better.** Every formal vehicle completed its journey.

| Nansha J02 Demand | Camera Condition | DeepSignal-S1 | YOLO+MP | Shorter vs YOLO+MP |
| --- | --- | ---: | ---: | ---: |
| East-west heavy | **Defocus** | **80.42** | 82.19 | **2.15%** |
| East-west heavy | Clean | **78.85** | 80.75 | **2.36%** |
| North-south heavy | Clean | **91.62** | 93.55 | **2.06%** |

**YOLO+MP is the primary comparison for defocus**, and is also evaluated in every clean case. Both camera-based methods receive the same degradation and observation schedule. Fixed timing does not consume camera images.

[Measurements (JSON)](results/nansha-2026-10-25.json) · [Table (CSV)](results/nansha-2026-10-25.csv) · [Comparison definitions](docs/comparisons.md)

These are selected Nansha J02 demonstrations, not a claim that every seed, intersection or visual condition improves. Town10HD remains an optional test scenario and is not included in the displayed results.

### Engineering Fixed-Timing Tests

The current baseline uses frozen engineering plans: Nansha's existing per-intersection configuration (J02: **35/14/10/17 s**) and Town10HD's **31/6/31/6 s** plan, without search on the final traffic plans. All **72 Nansha and 40 Town10HD fixed-baseline cases** completed. On Nansha's 72 matched clean cases, the released model reduces the sum of per-case capped mean journey times by **15.99%** versus engineering fixed timing. This finite-horizon metric is distinct from the complete-journey table above. [Baseline measurements](results/engineering-fixed-2026-10-26.json) · [Reproduce the matrix](docs/reproduction.md).

The video and the archived October 25 fixed-timing numbers used a different, tuned reference. They retain their original labels and are not measurements of the engineering baseline. The two evaluation protocols are reported separately.

## Simulation Scene

![Nansha intersection camera views](assets/nansha-scene.jpg)

*Nansha J02, UE5 Epic quality. Four camera views from the new closed-loop tests.*

## Run a Test

Linux, Python **3.10**, and SUMO are required. UE5 rendering additionally needs the matching CARLA 0.10.0 scene runtime and an NVIDIA GPU. FFmpeg is required for recording.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e '.[test,download]'

deepsignal-s1 prepare --scene scenarios/nansha-j02/scene.json \
  --regime east-west --seed 99001 --output runs/example/plan.json

deepsignal-s1 run --scene scenarios/nansha-j02/scene.json \
  --plan runs/example/plan.json --controller fixed --cpu \
  --output runs/example/fixed
```

This fixed-timing test runs without model access or 3D assets. For camera-based tests, see [scene setup and model access](docs/testing.md).

## Model Access

The Hugging Face model page and API address will be linked here after they are published. Model downloads and API calls both require an approved access request. Viewing this repository does not grant model access.

Approved complete model downloads can also run locally with `scripts/serve_model.py`; a hosted API is not required. See [local inference and reproduction](docs/reproduction.md).

After approval:

```bash
export HF_TOKEN="your_approved_account_token"
export DEEPSIGNAL_ENDPOINT="https://your-assigned-model-endpoint"
deepsignal-s1 run --scene scenarios/nansha-j02/scene.json \
  --plan runs/example/plan.json --controller s1 --port 25020 \
  --output runs/example/s1
```

The scene server must be running before this command. No fallback controller or recorded answers are used in place of the model.

## Test Outputs

Each run writes the arrival plan, vehicle records, signal timeline and a result report. The primary metric is mean complete journey time, including waiting before a vehicle enters the simulation. Incomplete journeys are not omitted to obtain a better average.

Use the same plan for paired comparisons. Live operation is reported only when `--realtime` completes within the decision deadline; online simulation recordings are not automatically real-time demonstrations.

## Resources

- [Test scenarios and API usage](docs/testing.md)
- [Combined scene package and paired-matrix reproduction](docs/reproduction.md)
- [Metric and comparison definitions](docs/comparisons.md)
- [Related DeepSignal project](https://github.com/AIMS-Laboratory/DeepSignal)
- [Asset and third-party notices](NOTICE.md)

Contact: [dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
