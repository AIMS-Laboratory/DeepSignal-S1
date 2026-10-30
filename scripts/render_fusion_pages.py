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
            '户外摄像头可能受到风振、支架扰动或人工维护的影响，出现抖动、角度偏移或成像质量下降。我们通过可控的模糊、失焦、固定偏角和动态抖动，考察输入不再理想时的交通控制效果，而不仅是清晰画面下的表现。',
            '\n'.join([
                f"- **模糊与失焦：** 失焦条件下，S1相对YOLO+MP的平均行程在南沙、Town分别降低 **{df_ns:.2f}%**、**{df_town:.2f}%**；运动模糊下分别降低 **{mb_ns:.2f}%**、**{mb_town:.2f}%**。",
                f"- **摄像头角度偏移：** 在正常机位完成YOLO画线后改变相机角度，S1的平均行程在南沙降低 **{angle_ns:.2f}%**，在Town降低 **{angle_town:.2f}%**；Town的平均等待同时降低 **{angle_wait:.2f}%**。",
                f"- **动态抖动：** S1仍保持优势，南沙、Town的平均行程分别降低 **{shake_ns:.2f}%**、**{shake_town:.2f}%**。抖动下的收益较小，模糊和机位偏移下的优势更突出。",
            ]),
            '在本次两个场景、四种特殊视觉条件的对比中，S1的平均等待、平均排队长度和平均行程均低于YOLO+MP。其实际价值是：不仅在正常画面下保持高水平控制，也在视觉输入退化后减少交通效果的损失。上述测试模拟视觉输入变化，不等同于已经完成真实恶劣天气验证。',
            '#### 亚秒级决策：视觉模型也能快速响应',
            f"未量化模型在RTX 5090上的 **{latency['count']}** 次决策请求平均耗时 **{latency['mean_ms']:.0f}毫秒**，**{100*latency['under_1s_fraction']:.2f}%** 的请求低于1秒；稳态请求平均 **{steady['mean_ms']:.0f}毫秒**。System One直接输出结构化控制动作，无需等待长篇文字生成，让视觉理解、交通控制效果与快速响应能够同时兼顾。",
        ])
    return '\n\n'.join([
        '### What the Results Show',
        '#### Clean Views: Competitive Control Without a Separate Detector',
        f"Against the fixed-time plan, S1 reduces mean journey time by **{fixed_ns:.2f}%** in Nansha and **{fixed_town:.2f}%** in Town10HD, while mean waiting falls by **{wait_ns:.2f}%** and **{wait_town:.2f}%**, respectively. The gains extend beyond earlier arrivals to less stopped waiting and shorter queues.",
        f"Against YOLO+MP, S1 further reduces Nansha mean journey time by **{mp_ns:.2f}%** and mean waiting by **{mp_wait_ns:.2f}%**; Town10HD mean journey time is essentially tied. Direct visual decisions therefore deliver competitive traffic control without a separate vehicle-detection stage, with a modest clean-view lead in Nansha.",
        '#### Visual Disruption: A More Distinctive Deployment Advantage',
        'Outdoor cameras can experience vibration, mounting disturbances or maintenance-related changes that affect image stability, viewing angle or image quality. Controlled blur, defocus, fixed camera shifts and dynamic shake test traffic control beyond ideal, clear camera feeds.',
        '\n'.join([
            f"- **Blur and defocus:** under defocus, S1 mean journey time is **{df_ns:.2f}%** lower than YOLO+MP in Nansha and **{df_town:.2f}%** lower in Town; under motion blur, the reductions are **{mb_ns:.2f}%** and **{mb_town:.2f}%**, respectively.",
            f"- **Camera-angle changes:** when the camera shifts after YOLO lane-region calibration, S1 mean journey time is **{angle_ns:.2f}%** lower in Nansha and **{angle_town:.2f}%** lower in Town. Town mean waiting also falls by **{angle_wait:.2f}%**.",
            f"- **Dynamic shake:** S1 retains a mean-journey advantage of **{shake_ns:.2f}%** in Nansha and **{shake_town:.2f}%** in Town. Shake gains are smaller; blur and camera shifts show the more pronounced advantages.",
        ]),
        'Across both evaluated scenes and all four perturbations, S1 has lower mean waiting, queue length and journey time than YOLO+MP. The practical value is competitive clean-view control combined with reduced traffic-performance loss when visual input degrades. These are simulated input changes, not completed real-world adverse-weather validation.',
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
    for directory in ('docs', 'results'):
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
