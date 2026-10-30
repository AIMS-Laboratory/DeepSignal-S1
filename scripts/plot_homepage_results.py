#!/usr/bin/env python3
"""Plot all three homepage traffic metrics from the table's published CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
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
    chinese_fonts = ["Noto Sans CJK SC", "Noto Sans CJK JP", "DejaVu Sans"]
    local_font = Path("/System/Library/Fonts/STHeiti Medium.ttc")
    if language == "zh" and local_font.exists():
        font_manager.fontManager.addfont(local_font)
        chinese_fonts.insert(0, font_manager.FontProperties(fname=local_font).get_name())
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": (chinese_fonts if language == "zh"
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
    return (("多路口场景" if language == "zh" else "Multi-intersection") if scene == "nansha"
            else ("标准仿真场景" if language == "zh" else "Standard simulation"))


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


def heading(fig: plt.Figure, title: str) -> None:
    fig.text(0.02, 0.975, title, fontsize=16, weight="bold", va="top")
    fig.add_artist(Line2D([0.02, 0.985], [0.885, 0.885], transform=fig.transFigure,
                          color=GRID, linewidth=1))


def legend(fig: plt.Figure, language: str, clean: bool) -> None:
    handles = [
        Line2D([], [], marker="o", linestyle="none", color=S1, markersize=8, label="S1"),
        Line2D([], [], marker="D", linestyle="none", markeredgecolor=MP,
               markerfacecolor="white", markersize=7, label="YOLO+MP"),
    ]
    if clean:
        handles = [Patch(facecolor=S1, label="S1"), Patch(facecolor=MP, label="YOLO+MP"),
                   Patch(facecolor=FIXED, label="固定配时方案" if language == "zh" else "Fixed-time plan")]
    fig.legend(handles=handles, loc="upper right", bbox_to_anchor=(0.99, 0.995),
               ncol=len(handles), frameon=False, handletextpad=0.4, columnspacing=1.3,
               fontsize=10)


def plot_clean(rows: dict, language: str) -> plt.Figure:
    chinese = language == "zh"
    fig, axes = plt.subplots(2, 3, figsize=(13.8, 4.2))
    fig.subplots_adjust(left=0.17, right=0.975, bottom=0.115, top=0.78,
                        hspace=0.48, wspace=0.28)
    heading(fig, "正常视觉 · 三种控制方法" if chinese else "Clean views · Three controllers")
    legend(fig, language, clean=True)
    controllers = ("s1", "mp", "fixed")
    labels = ["S1", "YOLO+MP", "固定配时方案" if chinese else "Fixed-time plan"]
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
            ax.set_ylim(-0.55, 2.55)
            ax.set_yticks([2, 1, 0], labels if col == 0 else ["", "", ""])
            if col == 0:
                ax.get_yticklabels()[0].set_color(S1)
                ax.get_yticklabels()[0].set_weight("bold")
                count = rows[(scene, "clean", "s1")]["cases"]
                name = scene_name(scene, language)
                fig.text(0.02, ax.get_position().y1 + 0.014,
                         f"{name}\n{count} {'案例' if chinese else 'cases'}",
                         fontsize=11, weight="bold", va="bottom", linespacing=1.25)
            if row == 0:
                ax.set_title(f"{mandarin if chinese else english} ({zh_unit if chinese else unit})",
                             loc="left", pad=10, fontsize=12, weight="bold")
            decorate_axis(ax)
    fig.text(0.02, 0.02, "三项指标均越低越好；数值与上表一致，无置信区间。" if chinese
             else "Lower is better. Same aggregate means as the table; no confidence intervals.",
             fontsize=9, color=MUTED)
    return fig


def reduction(s1: float, baseline: float) -> float:
    return 100 * (1 - s1 / baseline)


def plot_perturbed(rows: dict, language: str) -> plt.Figure:
    chinese = language == "zh"
    fig, axes = plt.subplots(2, 3, figsize=(13.8, 5.5))
    fig.subplots_adjust(left=0.195, right=0.93, bottom=0.105, top=0.78,
                        hspace=0.34, wspace=0.38)
    heading(fig, "特殊视觉 · S1 与 YOLO+MP" if chinese else "Perturbed views · S1 vs YOLO+MP")
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
            ax.set_ylim(-0.45, 3.45)
            ax.set_yticks([3, 2, 1, 0], condition_names(language) if col == 0 else ["", "", "", ""])
            if col == 0:
                count = rows[(scene, "df9", "s1")]["cases"]
                fig.text(0.02, ax.get_position().y1 + 0.014,
                         f"{scene_name(scene, language)}\n{count} {'案例/条件' if chinese else 'cases / condition'}",
                         fontsize=11, weight="bold", va="bottom", linespacing=1.25)
            if row == 0:
                ax.set_title(f"{mandarin if chinese else english} ({zh_unit if chinese else unit})",
                             loc="left", pad=10, fontsize=12, weight="bold")
                ax.text(1.04, 1.08, "降幅" if chinese else "Reduction", transform=ax.transAxes,
                        fontsize=9, color=MUTED, ha="left", va="bottom")
            decorate_axis(ax)
    fig.text(0.02, 0.02, "越靠左越好。降幅 = (YOLO+MP − S1) / YOLO+MP × 100%；每场景一个交通种子，无置信区间。" if chinese
             else "Further left is better. Reduction = (YOLO+MP − S1) / YOLO+MP × 100%; one traffic seed per scene, no confidence intervals.",
             fontsize=9, color=MUTED)
    return fig


def save(fig: plt.Figure, output_dir: Path, name: str, language: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg"):
        path = output_dir / f"{name}-{language}.{extension}"
        fig.savefig(path, facecolor="white")
        if extension == "svg":
            path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
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
