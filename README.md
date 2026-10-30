# DeepSignal-S1-1.0

**A multimodal System One model for traffic signals: visual observations in, fast structured control decisions out.**

English | [简体中文](README.zh-CN.md)

[Model](https://huggingface.co/AIMS2025/DeepSignal-S1) · [Scenes](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Scenes) · [Results](results/fusion-2026-10-30.json) · [Reproduction](docs/reproduction.md)

DeepSignal-S1 follows a **Jev-style structured probabilistic decision** approach. It reads temporal intersection views and signal context, scores candidate actions, and selects a legal control action directly. It does not generate a traffic-analysis essay for another program to parse, and does not require a separate YOLO detection stage.

**DeepSignal-S1-1.0** is trained on **simulation scenes from nine Nansha intersections**, including T-junctions and four-arm intersections, and **five traffic-demand scenarios at one four-arm intersection in CARLA's official Town10HD map**, covering balanced, uneven and time-varying flows. Its development addresses two practical questions: can visual control improve on the fixed-time plan in clean conditions, and can it remain more robust than detection plus Max Pressure when the camera feed degrades?

## Why System One

System One emphasizes fast, directly callable decisions, as illustrated by [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) and the open-source [OneJev](https://github.com/OmniJev/OneJev). DeepSignal-S1 applies this decision paradigm to traffic control: its inference interface returns an action and probabilities without generating a token-by-token reasoning narrative. It is not a wrapper around the commercial Jev service.

- **Vision to control:** temporal observations and signal context determine actions without operator-supplied live vehicle counts.
- **Structured decisions:** the model chooses among legal actions; the signal executor implements the committed green tail, yellow and all-red transitions.
- **One checkpoint across scenes:** the release covers T-junctions and four-arm intersections in Nansha as well as Town10HD.
- **Local deployment:** unquantized consumer-GPU inference is measured; quantization and edge deployment remain future work.

<!-- FUSION_HIGHLIGHTS:BEGIN -->
- **Effective clean control:** versus the fixed-time plan, S1 reduces vehicle-weighted mean journey time by **18.17%** across 72 Nansha cases and **33.77%** across five Town regimes.
- **Competitive with YOLO+MP in clean views:** Nansha mean journey time is a further **1.36%** lower, while Town10HD is essentially tied, without a separate detector.
- **Robust under visual disruption:** fixed camera shift reduces Town mean journey time by **82.93%** versus YOLO+MP; 31 px motion blur reduces Nansha mean journey time by **30.14%**.
- **Unquantized local inference:** 6823 RTX 5090 model calls average **485 ms**, with a 479 ms median.
<!-- FUSION_HIGHLIGHTS:END -->

## Town10HD: Decisions After Camera Repositioning

![Town10HD under fixed camera-angle shift](https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/en/town-angle15.gif)

*Town10HD · fixed yaw ±15° / pitch ±8°. Both arms use the same traffic plan and aligned simulation timestamps; the 60-second simulation window plays at 5× speed.*

## Results

Results compare **mean waiting time per vehicle, mean queue length and mean journey time per vehicle; lower is better for all three**. Clean views compare S1, the fixed-time plan and YOLO+MP. Perturbed views compare S1 with YOLO+MP.

<!-- FUSION_RESULTS:BEGIN -->
### Clean views: three controllers

<table>
<thead>
<tr><th scope="col">Scene</th><th scope="col">Condition</th><th scope="col">Cases</th><th scope="col">Controller</th><th scope="col">Mean wait (s/veh)</th><th scope="col">Mean queue (veh)</th><th scope="col">Mean journey (s/veh)</th></tr>
</thead>
<tbody>
<tr><td rowspan="3" align="center" valign="middle">Nansha</td><td rowspan="3" align="center" valign="middle">Clean</td><td rowspan="3" align="center" valign="middle">72</td><td><strong>S1</strong></td><td align="right">45.82</td><td align="right">10.47</td><td align="right">107.32</td></tr>
<tr><td>Fixed-time plan</td><td align="right">68.55</td><td align="right">15.52</td><td align="right">131.15</td></tr>
<tr><td>YOLO+MP</td><td align="right">46.89</td><td align="right">10.56</td><td align="right">108.79</td></tr>
<tr><td rowspan="3" align="center" valign="middle">Town10HD</td><td rowspan="3" align="center" valign="middle">Clean</td><td rowspan="3" align="center" valign="middle">5</td><td><strong>S1</strong></td><td align="right">20.45</td><td align="right">3.56</td><td align="right">38.22</td></tr>
<tr><td>Fixed-time plan</td><td align="right">40.46</td><td align="right">5.40</td><td align="right">57.70</td></tr>
<tr><td>YOLO+MP</td><td align="right">20.22</td><td align="right">3.59</td><td align="right">38.22</td></tr>
</tbody>
</table>

### Perturbed views: S1 vs YOLO+MP

<table>
<thead>
<tr><th scope="col">Scene</th><th scope="col">Condition</th><th scope="col">Cases</th><th scope="col">Controller</th><th scope="col">Mean wait (s/veh)</th><th scope="col">Mean queue (veh)</th><th scope="col">Mean journey (s/veh)</th></tr>
</thead>
<tbody>
<tr><td rowspan="2" align="center" valign="middle">Nansha</td><td rowspan="2" align="center" valign="middle">Defocus σ=9</td><td rowspan="2" align="center" valign="middle">9</td><td><strong>S1</strong></td><td align="right">76.08</td><td align="right">15.79</td><td align="right">141.03</td></tr>
<tr><td>YOLO+MP</td><td align="right">104.86</td><td align="right">31.04</td><td align="right">167.48</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Nansha</td><td rowspan="2" align="center" valign="middle">31 px motion blur</td><td rowspan="2" align="center" valign="middle">9</td><td><strong>S1</strong></td><td align="right">67.38</td><td align="right">17.23</td><td align="right">131.57</td></tr>
<tr><td>YOLO+MP</td><td align="right">124.59</td><td align="right">30.18</td><td align="right">188.34</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Nansha</td><td rowspan="2" align="center" valign="middle">Fixed yaw ±15° / pitch ±8°</td><td rowspan="2" align="center" valign="middle">9</td><td><strong>S1</strong></td><td align="right">63.68</td><td align="right">15.44</td><td align="right">129.04</td></tr>
<tr><td>YOLO+MP</td><td align="right">87.01</td><td align="right">21.18</td><td align="right">154.36</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Nansha</td><td rowspan="2" align="center" valign="middle">Dynamic shake 5°</td><td rowspan="2" align="center" valign="middle">9</td><td><strong>S1</strong></td><td align="right">63.40</td><td align="right">16.17</td><td align="right">128.25</td></tr>
<tr><td>YOLO+MP</td><td align="right">72.15</td><td align="right">17.91</td><td align="right">137.61</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Town10HD</td><td rowspan="2" align="center" valign="middle">Defocus σ=9</td><td rowspan="2" align="center" valign="middle">5</td><td><strong>S1</strong></td><td align="right">27.51</td><td align="right">4.10</td><td align="right">44.43</td></tr>
<tr><td>YOLO+MP</td><td align="right">92.97</td><td align="right">9.75</td><td align="right">109.15</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Town10HD</td><td rowspan="2" align="center" valign="middle">31 px motion blur</td><td rowspan="2" align="center" valign="middle">5</td><td><strong>S1</strong></td><td align="right">20.28</td><td align="right">3.58</td><td align="right">38.10</td></tr>
<tr><td>YOLO+MP</td><td align="right">111.26</td><td align="right">10.24</td><td align="right">127.71</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Town10HD</td><td rowspan="2" align="center" valign="middle">Fixed yaw ±15° / pitch ±8°</td><td rowspan="2" align="center" valign="middle">5</td><td><strong>S1</strong></td><td align="right">19.23</td><td align="right">3.45</td><td align="right">37.11</td></tr>
<tr><td>YOLO+MP</td><td align="right">205.09</td><td align="right">13.67</td><td align="right">217.40</td></tr>
<tr><td rowspan="2" align="center" valign="middle">Town10HD</td><td rowspan="2" align="center" valign="middle">Dynamic shake 5°</td><td rowspan="2" align="center" valign="middle">5</td><td><strong>S1</strong></td><td align="right">19.13</td><td align="right">3.32</td><td align="right">37.20</td></tr>
<tr><td>YOLO+MP</td><td align="right">21.49</td><td align="right">3.53</td><td align="right">39.88</td></tr>
</tbody>
</table>

**Metrics:** lower is better for all three. Mean wait includes stopped and insertion waiting; mean queue counts halted vehicles; journey time starts at planned departure, with unfinished vehicles contributing elapsed time at the evaluation cutoff. [Detailed definitions](docs/traffic-metrics.md).

### What the Results Show

#### Clean Views: Competitive Control Without a Separate Detector

Against the fixed-time plan, S1 reduces mean journey time by **18.17%** in Nansha and **33.77%** in Town10HD, while mean waiting falls by **33.15%** and **49.45%**, respectively. The gains extend beyond earlier arrivals to less stopped waiting and shorter queues.

Against YOLO+MP, S1 further reduces Nansha mean journey time by **1.36%** and mean waiting by **2.28%**; Town10HD mean journey time is essentially tied. Direct visual decisions therefore deliver competitive traffic control without a separate vehicle-detection stage, with a modest clean-view lead in Nansha.

#### Visual Disruption: A More Distinctive Deployment Advantage

Traffic demand may stay the same while camera input changes because of lighting, maintenance or vibration. The four tests target distinct imaging problems: can S1 continue making effective signal decisions when images lose sharpness or stability, or no longer match the original viewpoint?

- **Defocus: inaccurate focus softens vehicle outlines.** Mixed lighting, including headlights at night, can disrupt autofocus; manual focus adjustment or lens replacement can also leave the intersection out of focus. Softer vehicle and lane edges make recognition and counting harder. Under simulated defocus, S1 mean journey time is **15.79%** lower than YOLO+MP in Nansha and **59.29%** lower in Town.
- **Motion blur: movement during exposure creates directional smearing.** In low light at dusk or night, a camera may use longer exposures. Moving vehicles or camera movement during exposure can then smear outlines and obscure separation between vehicles. Under the motion-blur test, S1 mean journey time is **30.14%** lower in Nansha and **70.16%** lower in Town.
- **Fixed camera-angle shifts: a stable view from a changed direction.** For example, maintenance-related re-aiming or a shifted mount can move lane and stop-line positions in the image, even after the camera becomes steady. Previously drawn lane regions may no longer align. Our comparison calibrates YOLO at the original pose, then holds the changed camera angle fixed without recalibration. S1 mean journey time is **16.40%** lower in Nansha and **82.93%** lower in Town; Town mean waiting is **90.63%** lower.
- **Dynamic shake: the viewpoint keeps moving over time.** Wind gusts or vibrations from nearby heavy vehicles can shake a pole-mounted camera, shifting vehicle and lane positions across successive frames. Unlike a fixed angle shift, this disturbance continues over time. S1 retains a mean-journey advantage of **6.80%** in Nansha and **6.72%** in Town. Shake still yields gains, while blur and camera shifts show the more pronounced advantages.

These changes can affect vehicle detection and counting or misalign the image with calibrated lane regions, with downstream consequences for count-based signal control. S1 decides directly from temporal images and signal state, without that separate detection-and-counting pipeline. Across both evaluated scenes and all four perturbations, S1 has lower mean waiting, queue length and journey time than YOLO+MP: robustness translates into less waiting, shorter queues and shorter average journeys.

The tests simulate visual changes that these real-world problems can produce; they are not completed night-time field or real-world adverse-weather validation. [Real-world context and technical sources](docs/visual-robustness.md).

#### Sub-Second Decisions From a Visual Model

Across **6823** unquantized RTX 5090 decision requests, latency averages **485 ms**, with **99.08%** below one second; steady-state requests average **477 ms**. System One emits structured control actions directly, without waiting for a long textual response, combining visual understanding, traffic-control performance and fast decisions.
<!-- FUSION_RESULTS:END -->

**Evaluation scale:** clean views cover 72 cases across nine Nansha intersections and five Town10HD demand regimes. Each of the four perturbations covers nine Nansha cases and five Town10HD cases, using one traffic seed per scene.

Recorded cases show the actual visual condition and controller behavior; the on-screen score belongs to that recording. Overall effects are defined by the paired tables above.

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

Media show the actual model input, live traffic metrics and the latest recorded decision. Dynamic statistics describe the recorded episode; overall comparisons use the result tables. [Dynamic-metric definitions](docs/media-delivery.md) are documented separately.

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

Statistics cover 133 S1 evaluation cases and 6823 decision requests with the unquantized BF16 model. Latency measures model decision requests, excluding camera capture, rendering and signal execution; first calls include initialization effects.

**Deployment value:** sub-second model decisions make consumer-GPU signal-control workstations a practical target. We also tested the unquantized model on an **RTX 4090**, observing approximately **900 ms per decision**. This independent observation uses measurement conditions that have not yet been aligned and is not included in the table. Quantization and edge deployment are future directions for reducing compute requirements.

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

- **Sole fixed baseline:** the fixed-time plan, with timing parameters held constant throughout evaluation; Nansha uses the published per-intersection plans and Town10HD uses `31/6/31/6 s`.
- **Visual comparison:** clean views compare all three controllers; perturbations compare S1 with YOLO+MP. Camera shifts occur after YOLO lane-region calibration, without recalibration.
- **Scope:** results come from controlled Nansha and Town10HD simulations; deployment on real roads and under real weather remains to be validated.

See [evaluation protocol](docs/fusion-pilot-evaluation.md), [metric definitions](docs/comparisons.md), and [media delivery](docs/media-delivery.md).

## Historical Releases

Earlier `DeepSignal-S1-1.0-candidate` Nansha results and the separate historical Town checkpoint remain archived with their original protocol labels, distinct from the current 1.0 release and its results. See [historical released results](docs/released-results.md).

Contact: [dalei@scu.edu.cn](mailto:dalei@scu.edu.cn)
