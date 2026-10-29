#!/usr/bin/env python3
"""Render GitHub-ready fusion result figures from the single public JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


GREEN = "#168A55"
GRAY = "#8B929A"
BLUE = "#2878B5"
GRID = "#D9DEE3"


def style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Noto Sans CJK SC", "DejaVu Sans"],
        "font.size": 10, "axes.titlesize": 13,
        "axes.labelsize": 10, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "legend.fontsize": 9, "axes.spines.top": False, "axes.spines.right": False,
        "figure.dpi": 150, "savefig.dpi": 220, "svg.fonttype": "none",
    })


def save(fig: plt.Figure, output_dir: Path, name: str, pdf: bool, language: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = name if language == "zh" else f"{name}-en"
    for suffix in ("png", "svg") + (("pdf",) if pdf else ()):
        fig.savefig(output_dir / f"{filename}.{suffix}", bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def plot_normal(data: dict, output_dir: Path, pdf: bool, language: str) -> None:
    rows = data["normal"]
    x = np.arange(len(rows)); width = 0.24
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    fixed_label = "工程固定" if language == "zh" else "Engineering fixed"
    for offset, key, label, color in ((-width, "s1", "S1", GREEN), (0, "fixed", fixed_label, GRAY), (width, "mp", "YOLO+MP", BLUE)):
        values = [row["fixed_normalized"][key] for row in rows]
        bars = ax.bar(x + offset, values, width, label=label, color=color)
        ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
    ax.axhline(100, color="#555B61", linewidth=1)
    scene_names = {"nansha": "南沙" if language == "zh" else "Nansha", "town": "Town10HD"}
    unit = "案例" if language == "zh" else "cases"
    ax.set_xticks(x, [f"{scene_names[row['scene']]}\n(n={row['cases']} {unit})" for row in rows])
    ax.set_ylabel("有限时域交通指标（工程固定 = 100，越低越好）" if language == "zh" else "Normalized finite-horizon metric\n(engineering fixed = 100; lower is better)")
    ax.legend(frameon=False, ncol=3, loc="upper center")
    ax.set_ylim(0, max(max(row["fixed_normalized"].values()) for row in rows) * 1.18)
    ax.yaxis.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True)
    save(fig, output_dir, "normal", pdf, language)


def plot_extreme(data: dict, output_dir: Path, pdf: bool, language: str) -> None:
    conditions = ["df9", "mb31", "angle15", "shake5"]
    labels = ["失焦 σ=9", "运动模糊 31 px", "固定偏角", "动态抖动"] if language == "zh" else ["Defocus σ=9", "Motion blur 31 px", "Static angle", "Dynamic shake"]
    x = np.arange(len(conditions)); width = 0.34
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    for offset, scene, color in ((-width / 2, "nansha", GREEN), (width / 2, "town", BLUE)):
        values = [next(row["improvement_percent"] for row in data["extreme"] if row["scene"] == scene and row["condition"] == condition) for condition in conditions]
        scene_label = {"nansha": ("南沙" if language == "zh" else "Nansha") + " (n=9)", "town": "Town10HD (n=5)"}[scene]
        bars = ax.bar(x + offset, values, width, label=scene_label, color=color)
        ax.bar_label(bars, fmt="%.1f%%", padding=3, fontsize=8)
    ax.axhline(0, color="#555B61", linewidth=1)
    ax.axhline(10, color="#C2473B", linewidth=1.2, linestyle="--", label="10% 开发目标" if language == "zh" else "10% development target")
    ax.set_xticks(x, labels); ax.set_ylabel("S1 相对 YOLO+MP 改善（%）" if language == "zh" else "S1 improvement over YOLO+MP (%)")
    ax.legend(frameon=False, ncol=1, loc="upper left")
    ax.yaxis.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True)
    save(fig, output_dir, "extreme", pdf, language)


def plot_degradation(data: dict, output_dir: Path, pdf: bool, language: str) -> None:
    conditions = ["df9", "mb31", "angle15", "shake5"]
    labels = ["失焦", "运动模糊", "固定偏角", "动态抖动"] if language == "zh" else ["Defocus", "Motion blur", "Static angle", "Dynamic shake"]
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.2), sharey=False)
    titles = ("南沙：严格配对 9 例", "Town10HD：严格配对 5 例") if language == "zh" else ("Nansha: 9 strictly paired cases", "Town10HD: 5 strictly paired cases")
    for ax, scene, title in zip(axes, ("nansha", "town"), titles):
        x = np.arange(len(conditions)); width = 0.34
        for offset, controller, color, label in ((-width / 2, "s1", GREEN, "S1"), (width / 2, "mp", BLUE, "YOLO+MP")):
            values = [next(row["degradation_percent"] for row in data["degradation"] if row["scene"] == scene and row["condition"] == condition and row["controller"] == controller) for condition in conditions]
            bars = ax.bar(x + offset, values, width, label=label, color=color)
            ax.bar_label(bars, labels=[f"{value:.1f}%" for value in values], padding=3, fontsize=8)
        ax.axhline(0, color="#555B61", linewidth=1)
        ax.set_xticks(x, labels, rotation=18, ha="right"); ax.set_title(title)
        ax.yaxis.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True)
    axes[0].set_ylabel("相对自身正常视觉的退化（%，负值表示改善）" if language == "zh" else "Change from each controller's clean condition (%)\n(negative indicates improvement)")
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, output_dir, "degradation", pdf, language)


def plot_latency(data: dict, output_dir: Path, pdf: bool, language: str) -> None:
    latency = data["latency"]; samples = np.asarray(latency["samples_ms"], dtype=float)
    fig, (ax, tail) = plt.subplots(1, 2, figsize=(10.0, 4.2), gridspec_kw={"width_ratios": [2.2, 1]})
    bins = np.linspace(0, max(samples), 55)
    ax.hist(samples, bins=bins, color=GREEN, alpha=0.88)
    ax.axvline(1000, color="#C2473B", linestyle="--", linewidth=1.2, label="1 秒" if language == "zh" else "1 second")
    ax.set_xlabel("单次模型决策请求（ms）" if language == "zh" else "Model decision request (ms)"); ax.set_ylabel("调用次数" if language == "zh" else "Calls")
    ax.set_title("全部真实 model call" if language == "zh" else "All recorded model calls"); ax.legend(frameon=False)
    ax.yaxis.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True)
    ordered = np.sort(samples); survival = 1 - np.arange(1, len(ordered) + 1) / len(ordered)
    tail.plot(ordered, survival * 100, color=GREEN, linewidth=1.6)
    tail.axvline(1000, color="#C2473B", linestyle="--", linewidth=1.2)
    tail.set_yscale("log"); tail.set_ylim(max(0.01, 100 / len(ordered)), 100)
    tail.set_xlabel("延迟（ms）" if language == "zh" else "Latency (ms)"); tail.set_ylabel("超过该延迟的调用（%）" if language == "zh" else "Calls exceeding latency (%)")
    tail.set_title("尾部分布（对数纵轴）" if language == "zh" else "Tail distribution (log y-axis)"); tail.grid(True, color=GRID, linewidth=0.7)
    stats = latency["all_calls"]
    fig.text(0.5, 0.99, f"median {stats['median_ms']:.0f} ms · P95 {stats['p95_ms']:.0f} ms · max {stats['max_ms']:.0f} ms", ha="center", va="top", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, output_dir, "latency", pdf, language)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/fusion-2026-10-30.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("assets/results-fusion"))
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--language", choices=("zh", "en"), default="zh")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    style()
    plot_normal(data, args.output_dir, args.pdf, args.language)
    plot_extreme(data, args.output_dir, args.pdf, args.language)
    plot_degradation(data, args.output_dir, args.pdf, args.language)
    plot_latency(data, args.output_dir, args.pdf, args.language)


if __name__ == "__main__":
    main()
