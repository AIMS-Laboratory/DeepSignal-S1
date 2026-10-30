import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("homepage_plots", ROOT / "scripts/plot_homepage_results.py")
PLOTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLOTS)
PAGE_SPEC = importlib.util.spec_from_file_location("pages", ROOT / "scripts/render_fusion_pages.py")
PAGES = importlib.util.module_from_spec(PAGE_SPEC)
PAGE_SPEC.loader.exec_module(PAGES)


def rows():
    return PLOTS.load_rows(ROOT / "results/fusion-2026-10-30-traffic.csv")


def test_chart_source_matches_all_published_table_metrics():
    data = json.loads((ROOT / "results/fusion-2026-10-30.json").read_text())
    records = json.loads((ROOT / "results/fusion-2026-10-30-traffic.json").read_text())["records"]
    values = rows()
    assert len(values) == 22
    for key in ("normal", "extreme"):
        for group in data[key]:
            for controller in (("s1", "fixed", "mp") if key == "normal" else ("s1", "mp")):
                plotted = values[(group["scene"], group.get("condition", "clean"), controller)]
                stats = PAGES.traffic_stats(group, controller, records)
                assert plotted["cases"] == group["cases"]
                for metric, *_ in PLOTS.METRICS:
                    assert plotted[metric] == pytest.approx(stats[metric])


@pytest.mark.parametrize("language", ["en", "zh"])
def test_clean_bars_show_actual_means_on_shared_zero_based_axes(language):
    PLOTS.style(language)
    values = rows()
    fig = PLOTS.plot_clean(values, language)
    try:
        for index, ax in enumerate(fig.axes):
            scene = ("nansha", "town")[index // 3]
            metric = PLOTS.METRICS[index % 3][0]
            expected = [values[(scene, "clean", c)][metric] for c in ("s1", "mp", "fixed")]
            assert [patch.get_width() for patch in ax.patches] == pytest.approx(expected)
            assert [t.get_text() for t in ax.texts] == [f"{v:.2f}" for v in expected]
            assert ax.get_xlim()[0] == 0
            assert ax.get_xlim() == fig.axes[index % 3].get_xlim()
    finally:
        PLOTS.plt.close(fig)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_perturbed_points_and_reductions_use_only_the_two_controllers(language):
    PLOTS.style(language)
    values = rows()
    fig = PLOTS.plot_perturbed(values, language)
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        scene_header = next(t for t in fig.texts if "9 " in t.get_text())
        assert not scene_header.get_window_extent(renderer).overlaps(fig.axes[0]._left_title.get_window_extent(renderer))
        for index, ax in enumerate(fig.axes):
            scene = ("nansha", "town")[index // 3]
            metric = PLOTS.METRICS[index % 3][0]
            assert len(ax.collections) == 8
            for i, condition in enumerate(PLOTS.CONDITIONS):
                s1 = values[(scene, condition, "s1")][metric]
                mp = values[(scene, condition, "mp")][metric]
                assert ax.collections[2 * i].get_offsets()[0, 0] == pytest.approx(mp)
                assert ax.collections[2 * i + 1].get_offsets()[0, 0] == pytest.approx(s1)
                assert ax.texts[i].get_text() == f"{100 * (1 - s1 / mp):.1f}%"
            assert ax.get_xlim()[0] == 0
            assert ax.get_xlim() == fig.axes[index % 3].get_xlim()
    finally:
        PLOTS.plt.close(fig)


@pytest.mark.parametrize("language,filename", [("en", "README.md"), ("zh", "README.zh-CN.md")])
def test_each_table_is_followed_by_its_own_local_chart(language, filename):
    text = (ROOT / filename).read_text()
    results = text.split("<!-- FUSION_RESULTS:BEGIN -->")[1].split("<!-- FUSION_RESULTS:END -->")[0]
    after_tables = results.split("</table>")[1:]
    assert len(after_tables) == 2
    for after, name in zip(after_tables, ("clean-comparison", "perturbed-comparison")):
        path = f"assets/results-fusion/{name}-{language}.png"
        assert after.lstrip().startswith(f'<img width="1280" src="{path}"')
        assert text.count(f'src="{path}"') == 1
        assert (ROOT / path).is_file()
        assert (ROOT / path).with_suffix(".svg").is_file()


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("plot,height", [(PLOTS.plot_clean, 4.2), (PLOTS.plot_perturbed, 5.5)])
def test_compact_figures_preserve_readable_labels_without_clipping(language, plot, height):
    PLOTS.style(language)
    fig = plot(rows(), language)
    try:
        assert fig.get_size_inches() == pytest.approx([13.8, height])
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        texts = list(fig.texts)
        for ax in fig.axes:
            texts += list(ax.texts) + ax.get_yticklabels() + [ax._left_title]
            texts += [label for value, label in zip(ax.get_xticks(), ax.get_xticklabels())
                      if ax.get_xlim()[0] <= value <= ax.get_xlim()[1]]
        for text in texts:
            if not text.get_text():
                continue
            assert text.get_fontsize() >= 9
            bounds = text.get_window_extent(renderer)
            assert bounds.x0 >= 0 and bounds.y0 >= 0, text.get_text()
            assert bounds.x1 <= fig.bbox.x1 and bounds.y1 <= fig.bbox.y1, text.get_text()
        assert not fig.texts[0].get_window_extent(renderer).overlaps(fig.legends[0].get_window_extent(renderer))
    finally:
        PLOTS.plt.close(fig)
