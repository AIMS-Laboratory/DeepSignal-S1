#!/usr/bin/env python3
"""Render public Markdown tables from results/fusion-2026-10-30.json."""

from __future__ import annotations

import argparse
import csv
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


def render(data: dict[str, Any], chinese: bool, records: list[dict[str, Any]]) -> str:
    lines = []
    for key, title in (('normal', '正常视觉：三方比较' if chinese else 'Clean views: three controllers'),
                       ('extreme', '特殊视觉：S1与YOLO+MP' if chinese else 'Perturbed views: S1 vs YOLO+MP')):
        lines += [f'### {title}', '']
        if chinese:
            lines += ['| 场景 | 条件 | 案例数 | 控制方法 | 平均等待（秒/车） | 平均排队长度（辆） | 平均行程（秒/车） |',
                      '|---|---|---:|---|---:|---:|---:|']
        else:
            lines += ['| Scene | Condition | Cases | Controller | Mean wait (s/veh) | Mean queue (veh) | Mean journey (s/veh) |',
                      '|---|---|---:|---|---:|---:|---:|']
        for group in data[key]:
            controllers = ('s1', 'fixed', 'mp') if key == 'normal' else ('s1', 'mp')
            condition = ('正常' if chinese else 'Clean') if key == 'normal' else condition_label(group['condition'], chinese)
            for controller in controllers:
                values = traffic_stats(group, controller, records)
                label = {'s1': '**S1**', 'fixed': '工程固定' if chinese else 'Engineering fixed', 'mp': 'YOLO+MP'}[controller]
                cells = [f"{values[name]:.2f}" if values[name] is not None else ('未记录' if chinese else 'Not recorded')
                         for name in ('mean_wait_s_per_vehicle', 'mean_queue_vehicles', 'mean_journey_s_per_vehicle')]
                lines.append(f"| {scene_label(group,chinese)} | {condition} | {group['cases']} | {label} | {' | '.join(cells)} |")
        lines.append('')
    supplemented = sum(row.get('evaluation_batch') == 'nansha-mp-metrics-20261030' and row['status'] == 'complete' for row in records) == 72
    if chinese:
        lines += ['**指标定义：** 平均等待包括正式评测车辆的停车等待和拥堵造成的入网等待；平均排队长度是共同发车窗口98—398秒内，受控进口车道停车车辆总数的时间平均，单位为辆，不是米；平均行程从计划出发计时。行程与等待按车辆数加权，排队按相同窗口的案例均值汇总。',
                  '',
                  '南沙评估截止1298秒，Town截止518秒，未完成车辆的已耗时也计入，不能删除拥堵车辆后只报告已完成者。原始记录不变；等待和排队由原动作/灯态的SUMO重放补算，逐案例行程已核对。',
                  '',
                  ('南沙正常视觉YOLO+MP已独立补跑同一组72案例，等待、排队、行程整行采用该补跑批次；S1与工程固定记录不变。原先缺日志的历史YOLO+MP成绩保留，不与新统计混拼。' if supplemented else '南沙正常视觉YOLO+MP的72回合正在补跑完整日志；完成前这两项仍显示“未记录”，不推测或拿录像单例替代整批统计。')]
    else:
        lines += ['**Definitions:** mean wait includes stopped waiting and insertion waiting for formal evaluation vehicles. Mean queue is the time-averaged total halted vehicles on controlled incoming lanes during the common 98–398 s demand window, in vehicles rather than metres. Journey time starts at planned departure. Wait and journey means are vehicle-weighted; queues average equal-window case means.',
                  '',
                  'Evaluation ends at 1298 s in Nansha and 518 s in Town. Unfinished vehicles contribute their elapsed time at the cutoff. Original records are unchanged; waiting and queue statistics come from recorded-action/signal SUMO replay checked against each original journey score.',
                  '',
                  ('Clean Nansha YOLO+MP was rerun on the same 72 cases with full logs. Its entire waiting/queue/journey row comes from that supplementary batch; S1 and engineering-fixed records are unchanged. The original unlogged MP results remain archived, not spliced into the new row.' if supplemented else 'The 72 clean Nansha YOLO+MP cases are being rerun with full logs. Until completion, waiting and queue remain "Not recorded", not inferred or replaced with selected recording cases.')]
    return '\n'.join(lines)


def render_highlights(data: dict[str, Any], chinese: bool) -> str:
    normal = {row["scene"]: traffic_means(row) for row in data["normal"]}
    extreme = {(row["scene"], row["condition"]): traffic_means(row) for row in data["extreme"]}
    latency = data["latency"]["all_calls"]
    if chinese:
        return "\n".join(
            [
                f"- **正常控制有效：** 相对冻结工程固定配时，平均行程时间在南沙72案例降低 **{100*(1-normal['nansha']['s1']/normal['nansha']['fixed']):.2f}%**，在Town五类车流降低 **{100*(1-normal['town']['s1']/normal['town']['fixed']):.2f}%**。",
                f"- **特殊视觉稳健：** 固定机位偏移下，Town平均行程比YOLO+MP降低 **{100*(1-extreme[('town', 'angle15')]['s1']/extreme[('town', 'angle15')]['mp']):.2f}%**；31像素运动模糊下，南沙降低 **{100*(1-extreme[('nansha', 'mb31')]['s1']/extreme[('nansha', 'mb31')]['mp']):.2f}%**。",
                f"- **未量化本地推理：** RTX 5090共{latency['count']}次模型请求，平均 **{latency['mean_ms']:.0f}毫秒**，中位数{latency['median_ms']:.0f}毫秒。",
            ]
        )
    return "\n".join(
        [
            f"- **Effective clean control:** versus frozen engineering timing, S1 reduces vehicle-weighted mean journey time by **{100*(1-normal['nansha']['s1']/normal['nansha']['fixed']):.2f}%** across 72 Nansha cases and **{100*(1-normal['town']['s1']/normal['town']['fixed']):.2f}%** across five Town regimes.",
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


def video_tag(scene: str, condition: str, chinese: bool, github: bool = True) -> str:
    language = 'zh' if chinese else 'en'
    key = f'{language}/{scene}-{condition}.mp4'
    if github:
        source = json.loads((ROOT / 'results/fusion-2026-10-30-github-videos.json').read_text())['videos'][key]
    else:
        source = f'https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/{key}'
    mirror = f'https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v4/{key}'
    label = '大屏 / 备用播放' if chinese else 'Large-screen / alternate player'
    return f'<video controls="controls" width="1280" playsinline="playsinline" src="{source}"></video>\n\n[{label}]({mirror})'


def render_gallery(chinese: bool, github: bool = True) -> str:
    language = 'zh' if chinese else 'en'
    base = f'https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/resolve/main/media/fusion-1.0/v4/{language}'
    lines = []
    for scene, label in (('town', 'Town10HD'), ('nansha', '南沙' if chinese else 'Nansha')):
        lines += [f'### {label}', '']
        for condition in ('angle15', 'df9', 'mb31', 'shake5'):
            title = f'{label} · {condition_label(condition, chinese)}'
            preview = f'{base}/{scene}-{condition}.gif'
            if (scene, condition) in (('town', 'angle15'), ('nansha', 'mb31')):
                movie = video_tag(scene, condition, chinese, github)
            else:
                mirror = f'https://huggingface.co/datasets/AIMS2025/DeepSignal-S1-Media/blob/main/media/fusion-1.0/v4/{language}/{scene}-{condition}.mp4'
                movie = f"[{'大屏 / 备用播放' if chinese else 'Large-screen / alternate player'}]({mirror})"
            lines += [f'#### {title}', '', f'<img width="1280" src="{preview}" alt="{title}">', '',
                      movie, '']
    return '\n'.join(lines).rstrip()


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
        writer = csv.DictWriter(stream, fieldnames=['scene', 'condition', 'cases', 'vehicles', 'controller', 'mean_journey_s_per_vehicle', 'mean_wait_s_per_vehicle', 'mean_queue_vehicles', 'complete_cases'])
        writer.writeheader()
        for group in [*data['normal'], *data['extreme']]:
            for controller, mean in traffic_means(group).items():
                writer.writerow(dict(scene=group['scene'], condition=group.get('condition', 'clean'),
                                     cases=group['cases'], vehicles=sum(r['source_records']['s1']['vehicles'] for r in group['case_results']),
                                     controller=controller, **traffic_stats(group, controller, traffic_records)))
    readme = ROOT / "README.md"
    readme_zh = ROOT / "README.zh-CN.md"
    replace_block(readme, "FUSION_HIGHLIGHTS", render_highlights(data, False))
    replace_block(readme, "FUSION_RESULTS", render(data, False, traffic_records))
    replace_block(readme, "FUSION_LATENCY", render_latency(data, False))
    replace_block(readme, 'FUSION_GALLERY', render_gallery(False))
    replace_block(readme_zh, "FUSION_HIGHLIGHTS", render_highlights(data, True))
    replace_block(readme_zh, "FUSION_RESULTS", render(data, True, traffic_records))
    replace_block(readme_zh, "FUSION_LATENCY", render_latency(data, True))
    replace_block(readme_zh, 'FUSION_GALLERY', render_gallery(True))
    for path, chinese in ((readme, False), (readme_zh, True)):
        replace_block(path, 'FUSION_CLEAN_VIDEOS', '\n\n'.join(
            f"### {('正常视觉：南沙三方对比' if scene == 'nansha' else '正常视觉：Town10HD三方对比') if chinese else ('Clean Nansha: Three Controllers' if scene == 'nansha' else 'Clean Town10HD: Three Controllers')}\n\n{video_tag(scene, 'clean', chinese)}"
            for scene in ('nansha', 'town')))
    if args.model_card is not None:
        card = args.model_card.resolve()
        replace_block(card, "FUSION_HIGHLIGHTS", render_highlights(data, False))
        replace_block(card, "FUSION_RESULTS", render(data, False, traffic_records))
        replace_block(card, "FUSION_LATENCY", render_latency(data, False))
        replace_block(card, 'FUSION_GALLERY', render_gallery(False, github=False))
        local_card = (ROOT / ".local" / "HF_MODEL_CARD.md").resolve()
        if card == local_card:
            public_card = ROOT / ".local" / "hf-public" / "DeepSignal-S1" / "README.md"
            public_card.parent.mkdir(parents=True, exist_ok=True)
            public_card.write_text(card.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"rendered fusion pages from {args.results}")


if __name__ == "__main__":
    main()
