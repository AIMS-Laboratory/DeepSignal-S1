#!/usr/bin/env python3
"""Render public Markdown tables from results/fusion-2026-10-30.json."""

from __future__ import annotations

import argparse
import csv
from html import escape
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "results" / "fusion-2026-10-30.json"


def require(mapping: dict[str, Any], key: str, kind: type) -> Any:
    value = mapping.get(key)
    if not isinstance(value, kind):
        raise ValueError(f"{key!r} must be {kind.__name__}")
    return value


def validate(data: dict[str, Any]) -> None:
    if data.get("schema_version") != "fusion-results-v1":
        raise ValueError("unsupported schema_version; expected fusion-results-v1")
    normal = require(data, "normal", list)
    extreme = require(data, "extreme", list)
    degradation = require(data, "degradation", list)
    latency = require(data, "latency", dict)
    sources = require(data, "source_experiments", list)
    if set(sources) != {"unified-visual-20261028", "fusion-pilot-20261029"}:
        raise ValueError("unexpected source_experiments")
    if len(normal) != 2 or len(extreme) != 8 or len(degradation) != 16:
        raise ValueError("expected 2 normal, 8 extreme and 16 degradation rows")
    if {row.get("scene") for row in normal} != {"nansha", "town"}:
        raise ValueError("normal rows must contain nansha and town")
    if {(row.get("scene"), row.get("condition")) for row in extreme} != {
        (scene, condition)
        for scene in ("nansha", "town")
        for condition in ("df9", "mb31", "angle15", "shake5")
    }:
        raise ValueError("extreme rows do not match the published 2x4 matrix")
    for row in normal:
        for key in ("scene", "scene_label", "cases", "sums", "s1_vs_fixed_improvement_percent", "s1_vs_mp_improvement_percent"):
            if key not in row:
                raise ValueError(f"normal row missing {key!r}")
        sums = require(row, "sums", dict)
        for controller in ("s1", "fixed", "mp"):
            if not isinstance(sums.get(controller), (int, float)):
                raise ValueError(f"normal sums missing numeric {controller!r}")
    for row in extreme:
        for key in ("scene", "condition", "cases", "sums", "improvement_percent"):
            if key not in row:
                raise ValueError(f"extreme row missing {key!r}")
    for key in ("all_calls", "first_call_per_run", "subsequent_calls", "samples_ms"):
        if key not in latency:
            raise ValueError(f"latency missing {key!r}")


def scene_label(row: dict[str, Any], chinese: bool) -> str:
    if chinese:
        return str(row["scene_label"])
    return "Nansha" if row["scene"] == "nansha" else "Town10HD"


def condition_label(code: str, chinese: bool) -> str:
    labels = {
        "df9": ("Defocus σ=9", "失焦σ=9"),
        "mb31": ("31 px motion blur", "31像素运动模糊"),
        "angle15": ("Fixed yaw ±15° / pitch ±8°", "固定偏航±15° / 俯仰±8°"),
        "shake5": ("Dynamic shake 5°", "动态抖动峰值5°"),
    }
    return labels[code][1 if chinese else 0]


def render_town_demand(chinese: bool) -> str:
    tags = json.loads((ROOT / 'reproduction/fusion-release-matrix.json').read_text())['suites']['town10hd-fusion-pilot']['tags']
    shifted_tag = next(tag for tag in tags if tag.startswith('varyshuf-'))
    directory = 'reproduction/configs/vlm-realtime-control'
    files = ('episode-balanced.formal.json', 'episode-sustained-uneven.formal.json',
             'ood-uneven125-6001.json', 'episode-time-varying.formal.json', f'ood-{shifted_tag}.json')
    params = [json.loads((ROOT / directory / name).read_text())['regime_params'] for name in files]
    balanced, uneven, heavier, varying, shifted = params
    increase = 100 * (heavier['asymmetric_heavy_vph'] / uneven['asymmetric_heavy_vph'] - 1)

    def flows(value: dict[str, Any]) -> str:
        return ' → '.join(f'{rate:g}' for _, rate in value['time_varying_rates_vph'])

    def periods(value: dict[str, Any]) -> str:
        offsets = [offset for offset, _ in value['time_varying_rates_vph']]
        segments = [f'{start:g}-{end:g}' + ('秒' if chinese else ' s')
                    for start, end in zip(offsets, offsets[1:])]
        segments.append(f'{offsets[-1]:g}秒起' if chinese else f'from {offsets[-1]:g} s')
        return ' / '.join(segments)

    if chinese:
        lines = ['五类车流均设置在**同一个十字路口**，区别在方向分配、流量大小和高峰出现时点，而不是五个不同路口。下表列出当前评测使用的设置。', '',
                 '| 交通需求场景 | 每个进口方向的流量（辆/小时） | 时间变化 | 考察重点 |',
                 '|---|---|---|---|']
        rows = [
            ('均衡车流', f"东、西、南、北各{balanced['balanced_rate_vph']:g}", '全程恒定', '四向需求相近时的基本控制能力'),
            ('持续方向不均衡', f"东、西各{uneven['asymmetric_heavy_vph']:g}；南、北各{uneven['asymmetric_light_vph']:g}", '全程恒定，主次方向流量比5:1', '持续向高需求方向分配绿灯'),
            ('更高流量的不均衡', f"东、西各{heavier['asymmetric_heavy_vph']:g}；南、北各{heavier['asymmetric_light_vph']:g}", '全程恒定，仍为5:1', f'比上一类总需求增加{increase:g}%，考察较高负荷'),
            ('时变高峰', f'四向均为{flows(varying)}', periods(varying), '适应车流上升及高峰消退'),
            ('高峰时序变化', f'四向均为{flows(shifted)}', periods(shifted), '改变高峰出现时点，考察时序适应能力'),
        ]
        split = balanced['turn_split']
        notes = (f"流量是**每个进口方向**的期望到达率，不是每车道流量，也不是每小时固定生成的车辆数；车辆按该流率随机到达。五类均采用直行{100*split['s']:g}%、左转{100*split['l']:g}%、右转{100*split['r']:g}%。"
                 '时间从仿真启动计，末档流量保持至需求生成结束。“高峰时序变化”按种子重排时变流量，上表为当前结果对应的配置。各控制器使用相同的车辆计划。')
    else:
        lines = ['All five regimes use **the same four-way junction**, varying directional demand, load and peak timing rather than road geometry. The table gives the settings used in the current evaluation.', '',
                 '| Traffic-demand scenario | Flow per approach (vehicles/hour) | Temporal pattern | Control challenge |',
                 '|---|---|---|---|']
        rows = [
            ('Balanced flow', f"E, W, N and S: {balanced['balanced_rate_vph']:g} each", 'Constant throughout', 'Basic control with similar demand in all directions'),
            ('Sustained directional imbalance', f"E and W: {uneven['asymmetric_heavy_vph']:g} each; N and S: {uneven['asymmetric_light_vph']:g} each", 'Constant; major-to-minor demand ratio 5:1', 'Allocate green time to persistently busier directions'),
            ('Higher-load directional imbalance', f"E and W: {heavier['asymmetric_heavy_vph']:g} each; N and S: {heavier['asymmetric_light_vph']:g} each", 'Constant; still 5:1', f'{increase:g}% more total demand than the preceding regime'),
            ('Time-varying peak', f'All approaches: {flows(varying)}', periods(varying), 'Adapt to rising demand and peak recovery'),
            ('Shifted peak timing', f'All approaches: {flows(shifted)}', periods(shifted), 'Adapt when the peak occurs at a different time'),
        ]
        split = balanced['turn_split']
        notes = (f"Flows are expected arrival rates **per approach**, not per lane or exact hourly vehicle counts; arrivals are sampled randomly. All regimes use {100*split['s']:g}% straight, {100*split['l']:g}% left and {100*split['r']:g}% right turns. "
                 'Time starts at simulation startup, with the final rate held until demand generation ends. Shifted peak timing reorders the time-varying rates by seed; the table shows the configuration behind the current results. Controllers receive identical vehicle plans.')
    for row, filename in zip(rows, files):
        label, *cells = row
        lines.append('| ' + ' | '.join([f'[{label}]({directory}/{filename})', *cells]) + ' |')
    return '\n'.join([*lines, '', notes])


def traffic_means(group: dict[str, Any]) -> dict[str, float]:
    cases = group['case_results']
    vehicles = sum(row['source_records']['s1']['vehicles'] for row in cases)
    controllers = ('s1', 'fixed', 'mp') if 'fixed' in cases[0] else ('s1', 'mp')
    return {
        controller: sum(
            row[controller] * row['source_records']['s1']['vehicles']
            if group['scene'] == 'nansha' else row[controller]
            for row in cases
        ) / vehicles for controller in controllers
    }


def traffic_stats(group: dict[str, Any], controller: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [row for row in records if row['scene'] == group['scene']
               and row['condition'] == group.get('condition', 'clean') and row['controller'] == controller]
    complete = len(matched) == group['cases'] and all(row['status'] == 'complete' for row in matched)
    vehicles = sum(row['vehicles'] for row in matched) if complete else 0
    fresh_batch = complete and all(row.get('evaluation_batch') == 'nansha-mp-metrics-20261030' for row in matched)
    return {
        'mean_journey_s_per_vehicle': sum(row['mean_journey_s'] * row['vehicles'] for row in matched) / vehicles if fresh_batch else traffic_means(group)[controller],
        'mean_wait_s_per_vehicle': sum(row['sum_observed_stopped_time_s'] + row['mean_insertion_wait_s'] * row['vehicles'] for row in matched) / vehicles if complete else None,
        'mean_queue_vehicles': sum(row['mean_queue_vehicles'] for row in matched) / len(matched) if complete else None,
        'complete_cases': sum(row['status'] == 'complete' for row in matched),
    }


def improvement_percent(group: dict[str, Any], baseline: str, records: list[dict[str, Any]],
                        metric: str = 'mean_journey_s_per_vehicle') -> float:
    s1 = traffic_stats(group, 's1', records)[metric]
    reference = traffic_stats(group, baseline, records)[metric]
    return 100 * (1 - s1 / reference)


def render(data: dict[str, Any], chinese: bool, records: list[dict[str, Any]]) -> str:
    lines = []
    for key, title in (('normal', '正常视觉：三方比较' if chinese else 'Clean views: three controllers'),
                       ('extreme', '特殊视觉：S1与YOLO+MP' if chinese else 'Perturbed views: S1 vs YOLO+MP')):
        lines += [f'### {title}', '']
        if chinese:
            headers = ('场景', '条件', '案例数', '控制方法', '平均等待（秒/车）', '平均排队长度（辆）', '平均行程（秒/车）')
        else:
            headers = ('Scene', 'Condition', 'Cases', 'Controller', 'Mean wait (s/veh)', 'Mean queue (veh)', 'Mean journey (s/veh)')
        lines += ['<table>', '<thead>', '<tr>' + ''.join(f'<th scope="col">{escape(label)}</th>' for label in headers) + '</tr>',
                  '</thead>', '<tbody>']
        for group in data[key]:
            controllers = ('s1', 'fixed', 'mp') if key == 'normal' else ('s1', 'mp')
            condition = ('正常' if chinese else 'Clean') if key == 'normal' else condition_label(group['condition'], chinese)
            for index, controller in enumerate(controllers):
                values = traffic_stats(group, controller, records)
                label = {'s1': '<strong>S1</strong>', 'fixed': '固定配时方案' if chinese else 'Fixed-time plan', 'mp': 'YOLO+MP'}[controller]
                cells = [f"{values[name]:.2f}" if values[name] is not None else ('未记录' if chinese else 'Not recorded')
                         for name in ('mean_wait_s_per_vehicle', 'mean_queue_vehicles', 'mean_journey_s_per_vehicle')]
                shared = ''.join(f'<td rowspan="{len(controllers)}" align="center" valign="middle">{escape(str(value))}</td>'
                                 for value in (scene_label(group, chinese), condition, group['cases'])) if index == 0 else ''
                lines.append('<tr>' + shared + f'<td>{label}</td>' + ''.join(f'<td align="right">{value}</td>' for value in cells) + '</tr>')
        lines += ['</tbody>', '</table>', '']
    if chinese:
        lines += ['**指标说明：** 三项指标均越低越好。平均等待包括停车等待和入网等待；平均排队长度以停车车辆数计；平均行程从计划出发计时，未完成车辆计入评估截止时的已耗时。[详细指标定义](docs/traffic-metrics.md)。']
    else:
        lines += ['**Metrics:** lower is better for all three. Mean wait includes stopped and insertion waiting; mean queue counts halted vehicles; journey time starts at planned departure, with unfinished vehicles contributing elapsed time at the evaluation cutoff. [Detailed definitions](docs/traffic-metrics.md).']
    lines += ['', render_discussion(data, chinese, records)]
    return '\n'.join(lines)


def render_discussion(data: dict[str, Any], chinese: bool, records: list[dict[str, Any]]) -> str:
    normal = {row['scene']: row for row in data['normal']}
    extreme = {(row['scene'], row['condition']): row for row in data['extreme']}
    fixed_ns = improvement_percent(normal['nansha'], 'fixed', records)
    fixed_town = improvement_percent(normal['town'], 'fixed', records)
    wait_ns = improvement_percent(normal['nansha'], 'fixed', records, 'mean_wait_s_per_vehicle')
    wait_town = improvement_percent(normal['town'], 'fixed', records, 'mean_wait_s_per_vehicle')
    mp_ns = improvement_percent(normal['nansha'], 'mp', records)
    mp_wait_ns = improvement_percent(normal['nansha'], 'mp', records, 'mean_wait_s_per_vehicle')
    df_ns = improvement_percent(extreme[('nansha', 'df9')], 'mp', records)
    df_town = improvement_percent(extreme[('town', 'df9')], 'mp', records)
    mb_ns = improvement_percent(extreme[('nansha', 'mb31')], 'mp', records)
    mb_town = improvement_percent(extreme[('town', 'mb31')], 'mp', records)
    angle_ns = improvement_percent(extreme[('nansha', 'angle15')], 'mp', records)
    angle_town = improvement_percent(extreme[('town', 'angle15')], 'mp', records)
    angle_wait = improvement_percent(extreme[('town', 'angle15')], 'mp', records, 'mean_wait_s_per_vehicle')
    shake_ns = improvement_percent(extreme[('nansha', 'shake5')], 'mp', records)
    shake_town = improvement_percent(extreme[('town', 'shake5')], 'mp', records)
    latency = data['latency']['all_calls']
    steady = data['latency']['subsequent_calls']
    if chinese:
        return '\n\n'.join([
            '### 结果解读',
            '#### 正常视觉：高水平控制，不依赖独立车辆检测',
            f"与固定配时方案相比，S1在南沙和Town10HD的平均行程分别降低 **{fixed_ns:.2f}%** 和 **{fixed_town:.2f}%**，平均等待分别降低 **{wait_ns:.2f}%** 和 **{wait_town:.2f}%**。收益不仅是车辆更早到达，也体现在更少的停车等待与更短的排队。",
            f"与YOLO+MP相比，S1在南沙的平均行程再降低 **{mp_ns:.2f}%**、平均等待降低 **{mp_wait_ns:.2f}%**；Town10HD的平均行程基本持平。这说明，直接从视觉作出信号决策，可以在省去独立检测环节的同时达到有竞争力的交通控制效果，并在南沙取得小幅领先。",
            '#### 特殊视觉：更值得关注的部署优势',
            '现实路口的车流未必改变，摄像头输入却可能因光照变化、设备维护或风振而发生变化。四类测试分别对应不同的成像问题，考察S1在画面不再清晰、稳定或保持原机位时，能否继续作出有效的信号决策。',
            '\n'.join([
                f"- **失焦：对焦不准，车辆轮廓变软。** 夜间车灯等复杂光源可能干扰自动对焦，人工调焦或更换镜头后也可能没有重新调好焦点。车辆边缘和车道细节随之变得模糊，增加识别与计数的难度。在失焦测试中，S1相对YOLO+MP的平均行程在南沙、Town分别降低 **{df_ns:.2f}%**、**{df_town:.2f}%**。",
                f"- **运动模糊：曝光期间的移动形成拖影。** 傍晚或夜间光照不足时，摄像头可能采用更长曝光；车辆运动或曝光期间的相机晃动便可能形成方向性拖影，使车辆形状和相邻车辆的边界更难分辨。在运动模糊测试中，S1的平均行程分别降低 **{mb_ns:.2f}%**、**{mb_town:.2f}%**。",
                f"- **固定角度偏移：调整后稳定在新的机位。** 例如检修后重新调整视角，或支架发生偏转：画面已经稳定，但停车线和车道在图像中的位置改变了，原先画好的车道区域可能不再对应。我们的对比先在正常机位为YOLO画线，再固定改变相机角度，不重新画线。S1的平均行程在南沙降低 **{angle_ns:.2f}%**，在Town降低 **{angle_town:.2f}%**；Town的平均等待同时降低 **{angle_wait:.2f}%**。",
                f"- **动态抖动：视角随时间来回变化。** 高杆摄像头可能受到阵风或邻近重型车辆引起的振动影响，车辆和车道在连续画面中的位置随之摆动；这与调整后保持不动的固定偏角不同。动态抖动测试中，S1的平均行程在南沙、Town分别降低 **{shake_ns:.2f}%**、**{shake_town:.2f}%**。抖动下仍有收益，模糊和机位偏移下的优势更突出。",
            ]),
            '这些变化既可能影响车辆检测与计数，也可能使画面与原有车道区域错位，进而影响依赖检测计数的信号控制。S1直接依据时序画面和信号状态决策，不依赖这条独立检测计数链路。在本次两个场景、四种特殊视觉条件的对比中，S1的平均等待、平均排队长度和平均行程均低于YOLO+MP，体现出对这些输入变化的鲁棒性，优势直接落在车辆少等待、少排队和平均行程更短上。',
            '上述测试模拟的是这些现实问题可能造成的视觉变化，不等同于已经完成夜间现场或真实恶劣天气验证。[现实场景对应与资料依据](docs/visual-robustness.md)。',
            '#### 亚秒级决策：视觉模型也能快速响应',
            f"未量化模型在RTX 5090上的 **{latency['count']}** 次决策请求平均耗时 **{latency['mean_ms']:.0f}毫秒**，**{100*latency['under_1s_fraction']:.2f}%** 的请求低于1秒；稳态请求平均 **{steady['mean_ms']:.0f}毫秒**。System One直接输出结构化控制动作，无需等待长篇文字生成，让视觉理解、交通控制效果与快速响应能够同时兼顾。",
        ])
    return '\n\n'.join([
        '### What the Results Show',
        '#### Clean Views: Competitive Control Without a Separate Detector',
        f"Against the fixed-time plan, S1 reduces mean journey time by **{fixed_ns:.2f}%** in Nansha and **{fixed_town:.2f}%** in Town10HD, while mean waiting falls by **{wait_ns:.2f}%** and **{wait_town:.2f}%**, respectively. The gains extend beyond earlier arrivals to less stopped waiting and shorter queues.",
        f"Against YOLO+MP, S1 further reduces Nansha mean journey time by **{mp_ns:.2f}%** and mean waiting by **{mp_wait_ns:.2f}%**; Town10HD mean journey time is essentially tied. Direct visual decisions therefore deliver competitive traffic control without a separate vehicle-detection stage, with a modest clean-view lead in Nansha.",
        '#### Visual Disruption: A More Distinctive Deployment Advantage',
        'Traffic demand may stay the same while camera input changes because of lighting, maintenance or vibration. The four tests target distinct imaging problems: can S1 continue making effective signal decisions when images lose sharpness or stability, or no longer match the original viewpoint?',
        '\n'.join([
            f"- **Defocus: inaccurate focus softens vehicle outlines.** Mixed lighting, including headlights at night, can disrupt autofocus; manual focus adjustment or lens replacement can also leave the intersection out of focus. Softer vehicle and lane edges make recognition and counting harder. Under simulated defocus, S1 mean journey time is **{df_ns:.2f}%** lower than YOLO+MP in Nansha and **{df_town:.2f}%** lower in Town.",
            f"- **Motion blur: movement during exposure creates directional smearing.** In low light at dusk or night, a camera may use longer exposures. Moving vehicles or camera movement during exposure can then smear outlines and obscure separation between vehicles. Under the motion-blur test, S1 mean journey time is **{mb_ns:.2f}%** lower in Nansha and **{mb_town:.2f}%** lower in Town.",
            f"- **Fixed camera-angle shifts: a stable view from a changed direction.** For example, maintenance-related re-aiming or a shifted mount can move lane and stop-line positions in the image, even after the camera becomes steady. Previously drawn lane regions may no longer align. Our comparison calibrates YOLO at the original pose, then holds the changed camera angle fixed without recalibration. S1 mean journey time is **{angle_ns:.2f}%** lower in Nansha and **{angle_town:.2f}%** lower in Town; Town mean waiting is **{angle_wait:.2f}%** lower.",
            f"- **Dynamic shake: the viewpoint keeps moving over time.** Wind gusts or vibrations from nearby heavy vehicles can shake a pole-mounted camera, shifting vehicle and lane positions across successive frames. Unlike a fixed angle shift, this disturbance continues over time. S1 retains a mean-journey advantage of **{shake_ns:.2f}%** in Nansha and **{shake_town:.2f}%** in Town. Shake still yields gains, while blur and camera shifts show the more pronounced advantages.",
        ]),
        'These changes can affect vehicle detection and counting or misalign the image with calibrated lane regions, with downstream consequences for count-based signal control. S1 decides directly from temporal images and signal state, without that separate detection-and-counting pipeline. Across both evaluated scenes and all four perturbations, S1 has lower mean waiting, queue length and journey time than YOLO+MP: robustness translates into less waiting, shorter queues and shorter average journeys.',
        'The tests simulate visual changes that these real-world problems can produce; they are not completed night-time field or real-world adverse-weather validation. [Real-world context and technical sources](docs/visual-robustness.md).',
        '#### Sub-Second Decisions From a Visual Model',
        f"Across **{latency['count']}** unquantized RTX 5090 decision requests, latency averages **{latency['mean_ms']:.0f} ms**, with **{100*latency['under_1s_fraction']:.2f}%** below one second; steady-state requests average **{steady['mean_ms']:.0f} ms**. System One emits structured control actions directly, without waiting for a long textual response, combining visual understanding, traffic-control performance and fast decisions.",
    ])


def render_highlights(data: dict[str, Any], chinese: bool, records: list[dict[str, Any]]) -> str:
    normal = {row["scene"]: traffic_means(row) for row in data["normal"]}
    nansha = next(row for row in data['normal'] if row['scene'] == 'nansha')
    mp_ns = improvement_percent(nansha, 'mp', records)
    extreme = {(row["scene"], row["condition"]): traffic_means(row) for row in data["extreme"]}
    latency = data["latency"]["all_calls"]
    if chinese:
        return "\n".join(
            [
                f"- **正常控制有效：** 相对固定配时方案，平均行程时间在南沙72案例降低 **{100*(1-normal['nansha']['s1']/normal['nansha']['fixed']):.2f}%**，在Town五类车流降低 **{100*(1-normal['town']['s1']/normal['town']['fixed']):.2f}%**。",
                f"- **正常视觉对标YOLO+MP：** 南沙平均行程进一步降低 **{mp_ns:.2f}%**，Town10HD基本持平，无需独立车辆检测环节。",
                f"- **特殊视觉稳健：** 固定机位偏移下，Town平均行程比YOLO+MP降低 **{100*(1-extreme[('town', 'angle15')]['s1']/extreme[('town', 'angle15')]['mp']):.2f}%**；31像素运动模糊下，南沙降低 **{100*(1-extreme[('nansha', 'mb31')]['s1']/extreme[('nansha', 'mb31')]['mp']):.2f}%**。",
                f"- **未量化本地推理：** RTX 5090共{latency['count']}次模型请求，平均 **{latency['mean_ms']:.0f}毫秒**，中位数{latency['median_ms']:.0f}毫秒。",
            ]
        )
    return "\n".join(
        [
            f"- **Effective clean control:** versus the fixed-time plan, S1 reduces vehicle-weighted mean journey time by **{100*(1-normal['nansha']['s1']/normal['nansha']['fixed']):.2f}%** across 72 Nansha cases and **{100*(1-normal['town']['s1']/normal['town']['fixed']):.2f}%** across five Town regimes.",
            f"- **Competitive with YOLO+MP in clean views:** Nansha mean journey time is a further **{mp_ns:.2f}%** lower, while Town10HD is essentially tied, without a separate detector.",
            f"- **Robust under visual disruption:** fixed camera shift reduces Town mean journey time by **{100*(1-extreme[('town', 'angle15')]['s1']/extreme[('town', 'angle15')]['mp']):.2f}%** versus YOLO+MP; 31 px motion blur reduces Nansha mean journey time by **{100*(1-extreme[('nansha', 'mb31')]['s1']/extreme[('nansha', 'mb31')]['mp']):.2f}%**.",
            f"- **Unquantized local inference:** {latency['count']} RTX 5090 model calls average **{latency['mean_ms']:.0f} ms**, with a {latency['median_ms']:.0f} ms median.",
        ]
    )


def render_latency(data: dict[str, Any], chinese: bool) -> str:
    latency = data["latency"]
    rows = [
        ("all_calls", "All calls", "全部请求"),
        ("first_call_per_run", "First call per run", "每回合首请求"),
        ("subsequent_calls", "Subsequent calls", "后续请求"),
    ]
    if chinese:
        lines = [
            "| 范围 | 数量 | 平均 | 中位数 | P95 | 最大值 | 小于1秒 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    else:
        lines = [
            "| Scope | Count | Mean | Median | P95 | Max | Under 1 s |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    for key, en, zh in rows:
        stats = latency[key]
        lines.append(
            f"| {zh if chinese else en} | {stats['count']} | {stats['mean_ms']:.1f} ms | "
            f"{stats['median_ms']:.1f} ms | {stats['p95_ms']:.1f} ms | {stats['max_ms']:.1f} ms | "
            f"{100.0 * stats['under_1s_fraction']:.2f}% |"
        )
    return "\n".join(lines)


def video_tag(scene: str, condition: str, chinese: bool) -> str:
    language = 'zh' if chinese else 'en'
    key = f'{language}/{scene}-{condition}.mp4'
    # Bare attachment URLs activate GitHub's signed-in media URL rewriting.
    return json.loads((ROOT / 'results/fusion-2026-10-30-github-videos.json').read_text())['videos'][key]


def render_gallery(chinese: bool) -> str:
    language = 'zh' if chinese else 'en'
    base = f'https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/{language}'
    lines = []
    for scene, label in (('town', 'Town10HD'), ('nansha', '南沙' if chinese else 'Nansha')):
        lines += [f'### {label}', '']
        for condition in ('angle15', 'df9', 'mb31', 'shake5'):
            title = f'{label} · {condition_label(condition, chinese)}'
            preview = f'{base}/{scene}-{condition}.gif'
            lines += [f'#### {title}', '', f'<img width="1280" src="{preview}" alt="{title}">', '']
            if (scene, condition) in (('town', 'angle15'), ('nansha', 'mb31')):
                lines += [video_tag(scene, condition, chinese), '']
    return '\n'.join(lines).rstrip()


def render_hf_card(english: str, chinese: str, homepage: str) -> str:
    body = (english.replace('](README.zh-CN.md)', '](#简体中文)').rstrip()
            + '\n\n## 简体中文\n\n' + chinese.removeprefix('# DeepSignal-S1-1.0\n').lstrip())
    media_headings = {
        '## Town10HD: Decisions After Camera Repositioning', '## Eight Perturbation Views',
        '## Town10HD：机位改变后仍直接决策', '## 八组特殊视觉',
        '## Junctions at a Glance', '## 展示路口鸟瞰',
    }
    lines = []
    skip = False
    for line in body.splitlines():
        if line.startswith('## '):
            skip = line in media_headings
        if skip and line.startswith(('Lane regions are calibrated', 'YOLO车道画线')):
            lines += ['', line, '']
        if not skip and not line.startswith(('Recorded cases show', '录制案例展示')):
            lines.append(line)
    body = '\n'.join(lines).rstrip() + '\n'
    github = 'https://github.com/AIMS-Laboratory/DeepSignal-S1/blob/main'
    for directory in ('docs', 'results', 'reproduction'):
        body = body.replace(f']({directory}/', f']({github}/{directory}/')
    body = body.replace('](README.zh-CN.md)', f']({homepage}/blob/main/README.zh-CN.md)')
    body = body.replace('](README.md)', f']({homepage})')
    header = '---\nlanguage:\n- en\n- zh\ntags:\n- traffic-signal-control\n- system-one\n- multimodal\n- simulation\n---\n\n'
    return header + body


def replace_block(path: Path, marker: str, body: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = f"<!-- {marker}:BEGIN -->"
    end = f"<!-- {marker}:END -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"missing or duplicate {marker} markers in {path}")
    before, tail = text.split(start)
    _, after = tail.split(end)
    path.write_text(f"{before}{start}\n{body}\n{end}{after}", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--model-card",
        type=Path,
        help=(
            "also render a publisher model card; when set to "
            ".local/HF_MODEL_CARD.md, the HF public copy is synchronized"
        ),
    )
    args = parser.parse_args()
    data = json.loads(args.results.read_text(encoding="utf-8"))
    traffic_records = json.loads((ROOT / 'results/fusion-2026-10-30-traffic.json').read_text())['records']
    validate(data)
    with (ROOT / 'results/fusion-2026-10-30-traffic.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['scene', 'condition', 'cases', 'vehicles', 'controller', 'mean_journey_s_per_vehicle', 'mean_wait_s_per_vehicle', 'mean_queue_vehicles', 'complete_cases'], lineterminator='\n')
        writer.writeheader()
        for group in [*data['normal'], *data['extreme']]:
            for controller, mean in traffic_means(group).items():
                writer.writerow(dict(scene=group['scene'], condition=group.get('condition', 'clean'),
                                     cases=group['cases'], vehicles=sum(r['source_records']['s1']['vehicles'] for r in group['case_results']),
                                     controller=controller, **traffic_stats(group, controller, traffic_records)))
    readme = ROOT / "README.md"
    readme_zh = ROOT / "README.zh-CN.md"
    replace_block(readme, "FUSION_HIGHLIGHTS", render_highlights(data, False, traffic_records))
    replace_block(readme, "FUSION_RESULTS", render(data, False, traffic_records))
    replace_block(readme, "FUSION_LATENCY", render_latency(data, False))
    replace_block(readme, 'FUSION_GALLERY', render_gallery(False))
    replace_block(readme_zh, "FUSION_HIGHLIGHTS", render_highlights(data, True, traffic_records))
    replace_block(readme_zh, "FUSION_RESULTS", render(data, True, traffic_records))
    replace_block(readme_zh, "FUSION_LATENCY", render_latency(data, True))
    replace_block(readme_zh, 'FUSION_GALLERY', render_gallery(True))
    for path, chinese in ((readme, False), (readme_zh, True)):
        replace_block(path, 'TOWN_DEMAND', render_town_demand(chinese))
        replace_block(path, 'FUSION_CLEAN_VIDEOS', '\n\n'.join(
            f"### {('正常视觉：南沙三方对比' if scene == 'nansha' else '正常视觉：Town10HD三方对比') if chinese else ('Clean Nansha: Three Controllers' if scene == 'nansha' else 'Clean Town10HD: Three Controllers')}\n\n{video_tag(scene, 'clean', chinese)}"
            for scene in ('nansha', 'town')))
    if args.model_card is not None:
        card = args.model_card.resolve()
        card.write_text(render_hf_card(readme.read_text(encoding='utf-8'), readme_zh.read_text(encoding='utf-8'),
                                       'https://huggingface.co/AIMS2025/DeepSignal-S1'), encoding='utf-8')
        local_card = (ROOT / ".local" / "HF_MODEL_CARD.md").resolve()
        if card == local_card:
            public_card = ROOT / ".local" / "hf-public" / "DeepSignal-S1" / "README.md"
            public_card.parent.mkdir(parents=True, exist_ok=True)
            public_card.write_text(card.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"rendered fusion pages from {args.results}")


if __name__ == "__main__":
    main()
