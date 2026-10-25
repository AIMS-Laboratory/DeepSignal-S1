# DeepSignal-S1

**Vision-based traffic signal control. S1 means one system.**

English | [简体中文](README.zh-CN.md)

DeepSignal-S1 observes intersection camera views and produces adaptive signal-control actions. This repository provides the simulation scenarios and test client.

![Nansha intersection camera views](assets/nansha-scene.jpg)

*Nansha J02 simulation scene preview. This image illustrates the scene, not a measured control improvement.*

## Demonstration Video

The comparison video will show **DeepSignal-S1 on the left** and **tuned fixed timing on the right**, with synchronized traffic views, signal states and vehicle-level metrics. The YouTube link will be added after upload.

## Baseline Comparisons

| Controller | Traffic observation | Signal decisions | Public test entry |
| --- | --- | --- | --- |
| **DeepSignal-S1** | Camera frames and current signal context | Adaptive | `--controller s1` |
| Tuned fixed timing | Predefined timing plan | Fixed phase cycle | `--controller fixed` |
| Visual pressure | Camera-based vehicle detection | Movement-pressure control | `--controller visual-pressure` |

Numerical comparisons will be published from the same serving release and the paired scenarios in this repository. This preview does not substitute earlier model results for new measurements.

The selected demonstration scenarios focus on Nansha J02. Town10HD and specified blur conditions are supplementary candidates, not claims of network-wide or unrestricted robustness.

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
- [Metric and comparison definitions](docs/comparisons.md)
- [Related DeepSignal project](https://github.com/AIMS-Laboratory/DeepSignal)
- [Asset and third-party notices](NOTICE.md)

Contact: [dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
