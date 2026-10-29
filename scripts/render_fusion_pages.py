#!/usr/bin/env python3
"""Render public Markdown tables from results/fusion-2026-10-30.json."""

from __future__ import annotations

import argparse
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


def render(data: dict[str, Any], chinese: bool) -> str:
    if chinese:
        lines = [
            "### 正常视觉：三方比较",
            "",
            "| 场景 | n | S1 | 工程固定 | YOLO+MP | S1比固定改善 | MP比固定改善 | S1比MP改善 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    else:
        lines = [
            "### Clean views: three-way comparison",
            "",
            "| Scene | n | S1 | Fixed | YOLO+MP | S1 vs fixed | MP vs fixed | S1 vs MP |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    for row in data["normal"]:
        sums = row["sums"]
        mp_vs_fixed = 100.0 * (1.0 - sums["mp"] / sums["fixed"])
        lines.append(
            f"| {scene_label(row, chinese)} | {row['cases']} | {sums['s1']:.2f} | {sums['fixed']:.2f} | "
            f"{sums['mp']:.2f} | **{row['s1_vs_fixed_improvement_percent']:.2f}%** | "
            f"**{mp_vs_fixed:.2f}%** | **{row['s1_vs_mp_improvement_percent']:.2f}%** |"
        )
    if chinese:
        lines += [
            "",
            "### 特殊视觉：仅与YOLO+MP比较",
            "",
            "| 场景 | 条件 | n | S1 | YOLO+MP | S1改善 |",
            "|---|---|---:|---:|---:|---:|",
        ]
    else:
        lines += [
            "",
            "### Perturbed views: S1 vs. YOLO+MP only",
            "",
            "| Scene | Condition | n | S1 | YOLO+MP | S1 reduction |",
            "|---|---|---:|---:|---:|---:|",
        ]
    labels = {row["scene"]: row.get("scene_label", row["scene"]) for row in data["normal"]}
    for row in data["extreme"]:
        sums = row["sums"]
        display_scene = labels[row["scene"]] if chinese else ("Nansha" if row["scene"] == "nansha" else "Town10HD")
        lines.append(
            f"| {display_scene} | {condition_label(row['condition'], chinese)} | {row['cases']} | "
            f"{sums['s1']:.2f} | {sums['mp']:.2f} | **{row['improvement_percent']:.2f}%** |"
        )
    lines += ["", (
        "表内耗时是配对案例指标之和（秒），不是一辆车的平均耗时。南沙每案例使用1298秒时域的截断平均行程；Town每案例使用518秒时域的截断总行程。改善率按同场景、同条件的指标和计算。"
        if chinese else
        "Time entries are sums of matched-case metrics (seconds), not one vehicle's mean travel time. Nansha sums capped per-case means at H=1298 s; Town sums capped per-case totals at H=518 s. Reductions use matched metric sums within each scene and condition."
    )]
    return "\n".join(lines)


def render_highlights(data: dict[str, Any], chinese: bool) -> str:
    normal = {row["scene"]: row for row in data["normal"]}
    extreme = {(row["scene"], row["condition"]): row for row in data["extreme"]}
    latency = data["latency"]["all_calls"]
    if chinese:
        return "\n".join(
            [
                f"- **正常控制有效：** 相对冻结工程固定配时，南沙72案例改善 **{normal['nansha']['s1_vs_fixed_improvement_percent']:.2f}%**，Town五类车流改善 **{normal['town']['s1_vs_fixed_improvement_percent']:.2f}%**。",
                f"- **特殊视觉稳健：** 单独的固定机位偏移条件下，Town相对YOLO+MP改善 **{extreme[('town', 'angle15')]['improvement_percent']:.2f}%**；31像素运动模糊条件下，南沙改善 **{extreme[('nansha', 'mb31')]['improvement_percent']:.2f}%**。",
                f"- **三帧BF16决策：** RTX 5090共{latency['count']}次模型请求，平均 **{latency['mean_ms']:.0f}毫秒**，中位数{latency['median_ms']:.0f}毫秒。",
            ]
        )
    return "\n".join(
        [
            f"- **Effective clean control:** versus frozen engineering timing, S1 reduces the metric by **{normal['nansha']['s1_vs_fixed_improvement_percent']:.2f}%** across 72 Nansha cases and **{normal['town']['s1_vs_fixed_improvement_percent']:.2f}%** across five Town regimes.",
            f"- **Robust under visual disruption:** in the single fixed-camera-shift condition, Town improves **{extreme[('town', 'angle15')]['improvement_percent']:.2f}%** over YOLO+MP; under 31 px motion blur, Nansha improves **{extreme[('nansha', 'mb31')]['improvement_percent']:.2f}%**.",
            f"- **Three-frame BF16 decisions:** {latency['count']} RTX 5090 model calls average **{latency['mean_ms']:.0f} ms**, with a {latency['median_ms']:.0f} ms median.",
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
    validate(data)
    readme = ROOT / "README.md"
    readme_zh = ROOT / "README.zh-CN.md"
    replace_block(readme, "FUSION_HIGHLIGHTS", render_highlights(data, False))
    replace_block(readme, "FUSION_RESULTS", render(data, False))
    replace_block(readme, "FUSION_LATENCY", render_latency(data, False))
    replace_block(readme_zh, "FUSION_HIGHLIGHTS", render_highlights(data, True))
    replace_block(readme_zh, "FUSION_RESULTS", render(data, True))
    replace_block(readme_zh, "FUSION_LATENCY", render_latency(data, True))
    if args.model_card is not None:
        card = args.model_card.resolve()
        replace_block(card, "FUSION_HIGHLIGHTS", render_highlights(data, False))
        replace_block(card, "FUSION_RESULTS", render(data, False))
        replace_block(card, "FUSION_LATENCY", render_latency(data, False))
        local_card = (ROOT / ".local" / "HF_MODEL_CARD.md").resolve()
        if card == local_card:
            public_card = ROOT / ".local" / "hf-public" / "DeepSignal-S1" / "README.md"
            public_card.parent.mkdir(parents=True, exist_ok=True)
            public_card.write_text(card.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"rendered fusion pages from {args.results}")


if __name__ == "__main__":
    main()
