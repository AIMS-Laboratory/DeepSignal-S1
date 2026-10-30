#!/usr/bin/env python3
"""Plot all three homepage traffic metrics from the table's published CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator


ROOT = Path(__file__).resolve().parents[1]
S1 = "#147D78"
MP = "#708CAA"
FIXED = "#AFB7C1"
INK = "#252C34"
MUTED = "#687480"
GRID = "#E8EDEF"
LINK = "#CCDAD9"
METRICS = (
    ("mean_wait_s_per_vehicle", "Mean waiting time", "平均等待", "s/veh", "秒/车"),
    ("mean_queue_vehicles", "Mean queue length", "平均排队长度", "veh", "辆"),
    ("mean_journey_s_per_vehicle", "Mean journey time", "平均行程", "s/veh", "秒/车"),
)
CONDITIONS = ("df9", "mb31", "angle15", "shake5")


def style(language: str = "en") -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": (["Noto Sans CJK SC", "Noto Sans CJK JP", "DejaVu Sans"] if language == "zh"
                            else ["Inter", "DejaVu Sans"]),
        "font.size": 11,
        "font.weight": "normal",
        "text.color": INK,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.edgecolor": GRID,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "figure.dpi": 120,
        "savefig.dpi": 220,
    })


def load_rows(path: Path) -> dict:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return {
        (row["scene"], row["condition"], row["controller"]): {
            **{metric[0]: float(row[metric[0]]) for metric in METRICS},
            "cases": int(row["cases"]),
        }
        for row in rows
    }


def scene_name(scene: str, language: str) -> str:
    return ("南沙" if language == "zh" else "Nansha") if scene == "nansha" else "Town10HD"


def condition_names(language: str) -> list[str]:
    if language == "zh":
        return ["失焦\nσ = 9", "运动模糊\n31 像素", "固定偏角\n水平 ±15° / 俯仰 ±8°", "动态抖动\n峰值 5°"]
    return ["Defocus\nσ = 9", "Motion blur\n31 px", "Camera shift\nyaw ±15° / pitch ±8°", "Dynamic shake\npeak 5°"]


def decorate_axis(ax: plt.Axes) -> None:
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.tick_params(axis="both", length=0, pad=7, labelsize=10)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
    ax.spines["bottom"].set_visible(False)


def heading(fig: plt.Figure, title: str, subtitle: str) -> None:
    fig.text(0.035, 0.965, "DeepSignal-S1", fontsize=10, color=S1, weight="bold", va="top")
    fig.text(0.035, 0.920, title, fontsize=23, weight="bold", va="top")
    fig.text(0.035, 0.862, subtitle, fontsize=11, color=MUTED, va="top")
    fig.add_artist(Line2D([0.035, 0.975], [0.805, 0.805], transform=fig.transFigure,
                          color=GRID, linewidth=1))


def legend(fig: plt.Figure, language: str, clean: bool) -> None:
    handles = [
        Line2D([], [], marker="o", linestyle="none", color=S1, markersize=8, label="S1"),
        Line2D([], [], marker="D", linestyle="none", markeredgecolor=MP,
               markerfacecolor="white", markersize=7, label="YOLO+MP"),
    ]
    if clean:
        handles = [Patch(facecolor=S1, label="S1"), Patch(facecolor=MP, label="YOLO+MP"),
                   Patch(facecolor=FIXED, label="冻结工程固定配时" if language == "zh" else "Engineering fixed")]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.98, 0.985),
               ncol=len(handles), frameon=False, handletextpad=0.4, columnspacing=1.3,
               fontsize=10)


def plot_clean(rows: dict, language: str) -> plt.Figure:
    chinese = language == "zh"
    fig, axes = plt.subplots(2, 3, figsize=(13.8, 7.7))
    fig.subplots_adjust(left=0.17, right=0.965, bottom=0.14, top=0.70,
                        hspace=1.05, wspace=0.32)
    heading(fig, "正常视觉 · 三种控制方法" if chinese else "Clean views · Three controllers",
            "三项指标均越低越好；条形末端为实际均值。" if chinese
            else "Three traffic metrics. Lower is better; labels show the measured means.")
    legend(fig, language, clean=True)
    controllers = ("s1", "mp", "fixed")
    labels = ["S1", "YOLO+MP", "冻结工程固定配时" if chinese else "Engineering fixed"]
    for col, (metric, english, mandarin, unit, zh_unit) in enumerate(METRICS):
        limit = max(rows[(scene, "clean", c)][metric]
                    for scene in ("nansha", "town") for c in controllers) * 1.26
        for row, scene in enumerate(("nansha", "town")):
            ax = axes[row, col]
            values = [rows[(scene, "clean", c)][metric] for c in controllers]
            bars = ax.barh([2, 1, 0], values, height=0.52,
                           color=[S1, MP, FIXED], zorder=3)
            for bar, value, color in zip(bars, values, (S1, INK, MUTED)):
                ax.annotate(f"{value:.2f}", (value, bar.get_y() + bar.get_height() / 2),
                            xytext=(6, 0), textcoords="offset points", va="center",
                            fontsize=11, color=color, weight="bold" if color == S1 else "normal")
            ax.set_xlim(0, limit)
            ax.set_ylim(-0.65, 2.65)
            ax.set_yticks([2, 1, 0], labels if col == 0 else ["", "", ""])
            if col == 0:
                ax.get_yticklabels()[0].set_color(S1)
                ax.get_yticklabels()[0].set_weight("bold")
                count = rows[(scene, "clean", "s1")]["cases"]
                name = scene_name(scene, language)
                fig.text(0.035, 0.747 if row == 0 else 0.418,
                         f"{name}  /  {count} {'案例' if chinese else 'cases'}",
                         fontsize=12, weight="bold")
            ax.set_xlabel(zh_unit if chinese else unit, fontsize=10, labelpad=8)
            if row == 0:
                ax.set_title(mandarin if chinese else english, loc="left", pad=33,
                             fontsize=13, weight="bold")
            decorate_axis(ax)
    fig.text(0.035, 0.045, "与上表采用相同汇总口径；不显示置信区间。固定方案保持冻结。" if chinese
             else "Same aggregate means as the table; no confidence intervals shown. The engineering plan is held fixed.",
             fontsize=9, color=MUTED)
    return fig


def reduction(s1: float, baseline: float) -> float:
    return 100 * (1 - s1 / baseline)


def plot_perturbed(rows: dict, language: str) -> plt.Figure:
    chinese = language == "zh"
    fig, axes = plt.subplots(2, 3, figsize=(13.8, 9.7))
    fig.subplots_adjust(left=0.195, right=0.925, bottom=0.135, top=0.705,
                        hspace=0.65, wspace=0.50)
    heading(fig, "特殊视觉 · 扰动下的控制效果" if chinese else "Perturbed views · Control under disruption",
            "点位越靠左，交通表现越好；右侧百分比为 S1 相对 YOLO+MP 的降幅。" if chinese
            else "Further left is better. Percentages show S1 reductions relative to YOLO+MP.")
    legend(fig, language, clean=False)
    for col, (metric, english, mandarin, unit, zh_unit) in enumerate(METRICS):
        limit = max(rows[(scene, condition, controller)][metric]
                    for scene in ("nansha", "town") for condition in CONDITIONS
                    for controller in ("s1", "mp")) * 1.12
        for row, scene in enumerate(("nansha", "town")):
            ax = axes[row, col]
            for index, condition in enumerate(CONDITIONS):
                y = 3 - index
                s1 = rows[(scene, condition, "s1")][metric]
                mp = rows[(scene, condition, "mp")][metric]
                ax.axhspan(y - 0.39, y + 0.39, color="#F5F8F8", zorder=0)
                ax.plot([s1, mp], [y, y], color=LINK, linewidth=3, solid_capstyle="round", zorder=2)
                ax.scatter(mp, y, marker="D", s=48, facecolors="white", edgecolors=MP,
                           linewidths=1.6, zorder=3)
                ax.scatter(s1, y, marker="o", s=70, facecolors=S1, edgecolors="white",
                           linewidths=1, zorder=4)
                gain = reduction(s1, mp)
                ax.text(1.04, y, f"{gain:.1f}%", transform=ax.get_yaxis_transform(),
                        ha="left", va="center", fontsize=11, weight="bold",
                        color=S1 if gain >= 0 else "#B54747")
            ax.set_xlim(0, limit)
            ax.set_ylim(-0.55, 3.65)
            ax.set_yticks([3, 2, 1, 0], condition_names(language) if col == 0 else ["", "", "", ""])
            if col == 0:
                count = rows[(scene, "df9", "s1")]["cases"]
                fig.text(0.035, 0.782 if row == 0 else 0.435,
                         f"{scene_name(scene, language)}  /  {count} {'案例/条件' if chinese else 'cases per condition'}",
                         fontsize=12, weight="bold")
            ax.set_xlabel(zh_unit if chinese else unit, fontsize=10, labelpad=8)
            if row == 0:
                ax.set_title(mandarin if chinese else english, loc="left", pad=29,
                             fontsize=13, weight="bold")
                ax.text(1.04, 1.08, "降幅" if chinese else "Reduction", transform=ax.transAxes,
                        fontsize=9, color=MUTED, ha="left", va="bottom")
            decorate_axis(ax)
    fig.text(0.035, 0.051, "降幅 = (YOLO+MP − S1) / YOLO+MP × 100%；每个场景使用一个交通种子，无置信区间。" if chinese
             else "Reduction = (YOLO+MP − S1) / YOLO+MP × 100%. One traffic seed per scene; no confidence intervals shown.",
             fontsize=9, color=MUTED)
    return fig


def save(fig: plt.Figure, output_dir: Path, name: str, language: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        fig.savefig(output_dir / f"{name}-{language}.{extension}", facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "results/fusion-2026-10-30-traffic.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets/results-fusion")
    parser.add_argument("--language", choices=("en", "zh"), default="en")
    args = parser.parse_args()
    rows = load_rows(args.input)
    style(args.language)
    save(plot_clean(rows, args.language), args.output_dir, "clean-comparison", args.language)
    save(plot_perturbed(rows, args.language), args.output_dir, "perturbed-comparison", args.language)


if __name__ == "__main__":
    main()
