# DeepSignal-S1

**One system, from visual traffic observations to signal decisions.**

English | [简体中文](README.zh-CN.md)

**DeepSignal-S1 is a vision-first System One decision model for real-time traffic signal control. S1 means one system:** visual traffic understanding and signal-action selection are brought together in one multimodal decision model.

Following a **Jev-style, decision-first formulation**, DeepSignal-S1 takes intersection camera views and current signal context, then directly selects a permitted signal action rather than generating a conversational response. Traffic observations come from the images; a separate YOLO perception stage is not required by the S1 controller. **YOLO+MP is a comparison baseline, not a component of DeepSignal-S1.**

This repository provides DeepSignal-S1's simulation scenarios, demonstration results and test client. Model files and the standalone inference runtime are distributed separately through Hugging Face.

**The sole fixed baseline is the frozen engineering timing plan. Clean views compare S1, engineering fixed timing and YOLO+MP; perturbed views compare S1 with YOLO+MP only. Other historical fixed references and their videos are not current reproduction entrypoints.**

## Baseline Comparisons

| Controller | Traffic observation | Signal decisions | Public test entry |
| --- | --- | --- | --- |
| **DeepSignal-S1** | Camera frames and current signal context | Adaptive | `--controller s1` |
| Engineering fixed timing | Pre-existing timing plan, without final-test search | Fixed phase cycle | `--controller fixed` |
| YOLO+MP | YOLO camera-based vehicle detection | Movement-pressure control | `--controller visual-pressure` |

### Completed Results

The published suites use **two explicitly named scene-specific releases**, not one checkpoint evaluated in both scenes: `DeepSignal-S1-1.0-candidate` for Nansha (UE5/CARLA 0.10.0), and `DeepSignal-S1-Town10HD-1.0-archive` for the archived Town10HD environment (CARLA 0.9.16). The ongoing supplementary matrix is **not** used in these tables.

**Town timing correction:** the Town rows below retain historical measurements from a legacy executor that omitted the committed five-second green tail. They are **not validated scores under the corrected timing protocol**, nor results of the current HF checkpoint. The complete current-checkpoint Town suite is being rerun; see [scope and corrections](docs/intersection-metrics.md). Nansha measurements are unaffected by this Town correction.

| Scene | Camera Condition | Successful Pairs / Planned | Comparison | Journey-Metric Reduction |
| --- | --- | ---: | --- | ---: |
| Nansha, nine intersections | Clean | 72 / 72 | Engineering fixed timing | **15.99%** |
| Nansha, nine intersections | Static camera offsets within +/-8 degrees | 72 / 72 | YOLO+MP | **1.12%** |
| Nansha, nine intersections | Defocus, sigma=2.5 | 65 / 72 | YOLO+MP | **25.69%** |
| Town10HD, archive release | Clean | 20 / 20 | Engineering fixed timing | **36.21%** |
| Town10HD, archive release | Clean | 20 / 20 | YOLO+MP | **3.13%** |
| Town10HD, archive release | Defocus, sigma=2.5 | 40 / 40 | YOLO+MP | **8.46%** |

Nansha's clean aggregate is close to YOLO+MP: **5 of 9 intersections differ by less than 5%** in their aggregate capped journey metric. All nine intersection values are included in the [released measurements](results/released-2026-10-26.json).

These finite-horizon metrics include unfinished journeys capped at the specified horizon. Defocus improvements use the 65 successful matched Nansha pairs; all six S1 failures and one YOLO+MP failure remain in the published records. Town's clean suite uses four seeds and all five demand regimes from one archive checkpoint; it does not mix earlier weights into a 40-case score. [Exact versions, test commands and scope](docs/released-results.md) · [Recompute these tables](scripts/summarize_released.py).


### Engineering Fixed-Timing Tests

The current baseline uses frozen engineering plans: Nansha's existing per-intersection configuration (J02: **35/14/10/17 s**) and Town10HD's **31/6/31/6 s** plan, without search on the final traffic plans. All **72 Nansha and 40 Town10HD fixed-baseline cases** completed. On Nansha's 72 matched clean cases, the released model reduces the sum of per-case capped mean journey times by **15.99%** versus engineering fixed timing. This finite-horizon metric is distinct from the complete-journey table above. [Baseline measurements](results/engineering-fixed-2026-10-26.json) · [Reproduce the matrix](docs/reproduction.md).

Other historical fixed references and associated videos remain archived, not current reproduction options. Released-checkpoint and fused-checkpoint results are kept separate.

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

## Model and Scene Access

The current model page is **[AIMS2025/DeepSignal-S1 on Hugging Face](https://huggingface.co/AIMS2025/DeepSignal-S1)**. It contains only `DeepSignal-S1-1.0-candidate`, not the historical Town checkpoint. Check its model card for upload readiness and request access before downloading. Historical Town measurements remain explicitly associated with their separate archive release, not with this HF checkpoint.

The combined **[Nansha + Town10HD scene dataset](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes)** hosts `DeepSignal-S1-Scenes-v3.tar.gz` (**27.60 GiB**). Check the dataset card for upload readiness. No Google Drive download is needed. The scenes are public; model access is approved separately. A full public download-to-result replay has not yet been certified.

```bash
hf download AIMS2025/DeepSignal-S1-Scenes DeepSignal-S1-Scenes-v3.tar.gz \
  --repo-type dataset --local-dir downloads
deepsignal-s1 install-assets --archive downloads/DeepSignal-S1-Scenes-v3.tar.gz
```

The v2 bundle includes both UE5 scenes and the archived CARLA 0.9.16 Town runtime, not the separate archive model weights. See [installation and version matching](docs/released-results.md). Viewing this GitHub repository does not grant model access or create a hosted API service.

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
- [Published results and matching model/runtime releases](docs/released-results.md)
- [Supplementary camera-condition test protocol](docs/supplementary-evaluation.md)
- [Metric and comparison definitions](docs/comparisons.md)
- [Intersection queue, waiting-time and throughput metrics](docs/intersection-metrics.md)
- [Related DeepSignal project](https://github.com/AIMS-Laboratory/DeepSignal)
- [Asset and third-party notices](NOTICE.md)

Contact: [dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
