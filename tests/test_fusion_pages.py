import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pages', ROOT / 'scripts/render_fusion_pages.py')
PAGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PAGES)


def test_mean_journey_is_vehicle_weighted_not_mean_of_case_means():
    group = {'scene': 'nansha', 'case_results': [
        {'s1': 10, 'mp': 20, 'source_records': {'s1': {'vehicles': 1}}},
        {'s1': 30, 'mp': 40, 'source_records': {'s1': {'vehicles': 3}}},
    ]}
    assert PAGES.traffic_means(group) == {'s1': 25, 'mp': 35}
    group['scene'] = 'town'
    assert PAGES.traffic_means(group) == {'s1': 10, 'mp': 15}


@pytest.mark.parametrize('chinese,language', [(True, 'zh'), (False, 'en')])
def test_gallery_groups_remaining_cases_and_keeps_public_fallbacks(chinese, language):
    body = PAGES.render_gallery(chinese)
    assert body.count('<details>') == body.count('</details>') == 4
    assert body.count('.gif') == 6
    assert body.count('.jpg') == 6
    featured = PAGES.render_featured(chinese)
    assert featured.count('.gif') == 2
    assert f'assets/previews/{language}/town-angle15.gif' in featured
    assert '<video' not in body
    assert body.count('https://github.com/user-attachments/assets/') == 6


@pytest.mark.parametrize('filename,language', [('README.md', 'en'), ('README.zh-CN.md', 'zh')])
def test_featured_demos_are_not_duplicated_in_the_gallery(filename, language):
    body = (ROOT / filename).read_text()
    gallery = body.split('<!-- FUSION_GALLERY:BEGIN -->')[1].split('<!-- FUSION_GALLERY:END -->')[0]
    featured = body.split('<!-- FUSION_FEATURED:BEGIN -->')[1].split('<!-- FUSION_FEATURED:END -->')[0]
    for name in ('town-angle15', 'nansha-mb31'):
        image = f'assets/previews/{language}/{name}.gif'
        assert body.count(image) == featured.count(image) == 1
        assert image not in gallery
    assert '## Town10HD: Decisions After Camera Repositioning' not in body
    assert '## Town10HD：机位改变后仍直接决策' not in body


@pytest.mark.parametrize('filename,heading', [
    ('README.md', '## Eight Perturbation Views'),
    ('README.zh-CN.md', '## 八组特殊视觉'),
])
def test_real_junction_overviews_precede_the_gallery_in_both_languages(filename, heading):
    body = (ROOT / filename).read_text()
    gallery_start = body.index(heading)
    for name in ('nansha-j03-aerial.jpg', 'town10hd-189-aerial.jpg'):
        path = f'assets/junctions/{name}'
        assert (ROOT / path).is_file()
        assert body.count(f'src="{path}"') == 1
        assert body.index(f'src="{path}"') < gallery_start
    introduction = body[:gallery_start]
    assert all(junction not in introduction for junction in ('J03', 'J08', 'J05', 'J07'))
    media_notes = (ROOT / 'docs/media-delivery.md').read_text()
    assert all(junction in media_notes for junction in ('J03', 'J08', 'J05', 'J07'))


@pytest.mark.parametrize('chinese,filename', [(True, 'README.zh-CN.md'), (False, 'README.md')])
def test_town_demand_table_matches_configs_and_current_evaluation_seed(chinese, filename):
    body = PAGES.render_town_demand(chinese)
    table = ET.fromstring('<root>' + body + '</root>').find('table')
    cells = [row.findall('td') for row in table.findall('./tbody/tr')]
    assert len(cells) == 5 and all(len(row) == 4 for row in cells)
    assert all(cell.get('nowrap') is not None for row in cells for cell in row)
    rows = [[' '.join(cell.itertext()) for cell in row] for row in cells]
    prefix = 'https://github.com/AIMS-Laboratory/DeepSignal-S1/blob/main/'
    paths = [link.get('href').removeprefix(prefix) for link in table.findall('.//a')]
    assert len(paths) == 5
    configs = [json.loads((ROOT / path).read_text()) for path in paths]
    for row, config in zip(rows, configs):
        params = config['regime_params']
        if config['regime'] == 'balanced':
            assert f"{params['balanced_rate_vph']:g}" in row[1]
        elif config['regime'] == 'asymmetric':
            assert f"{params['asymmetric_heavy_vph']:g}" in row[1]
            assert f"{params['asymmetric_light_vph']:g}" in row[1]
            assert params['asymmetric_heavy_vph'] / params['asymmetric_light_vph'] == 5
        else:
            assert ' → '.join(f'{rate:g}' for _, rate in params['time_varying_rates_vph']) in row[1]
            assert '0-60' in row[2] and '60-120' in row[2] and '120' in row[2]
        assert params['turn_split'] == {'s': 0.7, 'r': 0.15, 'l': 0.15}
    assert paths[-1].endswith('ood-varyshuf-18040.json')
    assert '200 → 700 → 200' in rows[3][1]
    assert '200 → 200 → 700' in rows[4][1]
    assert '25%' in rows[2][3]
    readme = (ROOT / filename).read_text()
    assert readme.split('<!-- TOWN_DEMAND:BEGIN -->\n')[1].split('\n<!-- TOWN_DEMAND:END -->')[0] == body


@pytest.mark.parametrize('chinese', [False, True])
def test_comparison_groups_share_three_cells_without_merging_controller_metrics(chinese):
    data = json.loads((ROOT / 'results/fusion-2026-10-30.json').read_text())
    records = json.loads((ROOT / 'results/fusion-2026-10-30-traffic.json').read_text())['records']
    tables = ET.fromstring('<root>' + PAGES.render(data, chinese, records) + '</root>').findall('.//table')
    assert len(tables) == 2
    for table, key, controllers in zip(tables, ('normal', 'extreme'), (('s1', 'fixed', 'mp'), ('s1', 'mp'))):
        assert len(table.findall('./thead/tr/th')) == 7
        rows = table.findall('./tbody/tr')
        assert len(rows) == len(data[key]) * len(controllers)
        for group_index, group in enumerate(data[key]):
            for controller_index, controller in enumerate(controllers):
                cells = rows[group_index * len(controllers) + controller_index].findall('td')
                if controller_index == 0:
                    assert len(cells) == 7
                    assert [cell.get('rowspan') for cell in cells[:3]] == [str(len(controllers))] * 3
                    assert cells[0].text == PAGES.scene_label(group, chinese)
                    assert cells[2].text == str(group['cases'])
                    expected_condition = ('正常' if chinese else 'Clean') if key == 'normal' else PAGES.condition_label(group['condition'], chinese)
                    assert cells[1].text == expected_condition
                else:
                    assert len(cells) == 4
                    assert all(cell.get('rowspan') is None for cell in cells)
                stats = PAGES.traffic_stats(group, controller, records)
                expected_label = {'s1': 'S1', 'fixed': '固定配时方案' if chinese else 'Fixed-time plan', 'mp': 'YOLO+MP'}[controller]
                assert ''.join(cells[-4].itertext()) == expected_label
                assert [cell.text for cell in cells[-3:]] == [f'{stats[name]:.2f}' for name in
                    ('mean_wait_s_per_vehicle', 'mean_queue_vehicles', 'mean_journey_s_per_vehicle')]


def test_hf_card_retains_public_bilingual_results_without_embedded_media():
    homepage = 'https://huggingface.co/AIMS2025/DeepSignal-S1'
    body = PAGES.render_hf_card((ROOT / 'README.md').read_text(), (ROOT / 'README.zh-CN.md').read_text(), homepage)
    assert '<video' not in body and '<img' not in body
    assert '.gif' not in body and 'github.com/user-attachments/' not in body
    assert 'FUSION_RESULTS:BEGIN' in body and 'FUSION_LATENCY:BEGIN' in body
    assert 'FUSION_GALLERY' not in body and 'FUSION_CLEAN_VIDEOS' not in body
    assert '## 评测结果' in body and '## Results' in body
    assert body.count('<table>') == 6
    assert 'System One' in body and '## 工作原理' in body
    assert 'Lane regions are calibrated' in body and 'YOLO车道画线' in body
    assert 'https://github.com/AIMS-Laboratory/DeepSignal-S1/blob/main/docs/reproduction.md' in body
    assert f'[English]({homepage})' in body and '[简体中文](#简体中文)' in body
    assert '/blob/main/README.zh-CN.md' not in body
    assert '### 结果解读' in body and '### What the Results Show' in body
    assert 'https://github.com/AIMS-Laboratory/DeepSignal-S1/blob/main/docs/visual-robustness.md' in body
    assert '## Five traffic demand scenarios' in body and '## 5类交通需求场景' in body
    assert body.count('200 → 200 → 700') == 2
    assert 'https://github.com/AIMS-Laboratory/DeepSignal-S1/blob/main/reproduction/configs/vlm-realtime-control/ood-varyshuf-18040.json' in body


@pytest.mark.parametrize('chinese', [False, True])
def test_discussion_uses_current_comparisons_and_keeps_clean_town_tied(chinese):
    data = json.loads((ROOT / 'results/fusion-2026-10-30.json').read_text())
    records = json.loads((ROOT / 'results/fusion-2026-10-30-traffic.json').read_text())['records']
    body = PAGES.render_discussion(data, chinese, records)
    summary = PAGES.render_summary(data, chinese, records)
    for scene in ('nansha', 'town'):
        group = next(row for row in data['normal'] if row['scene'] == scene)
        percentage = PAGES.improvement_percent(group, 'fixed', records)
        assert f'**{percentage:.2f}%**' in summary
    assert ('基本持平' if chinese else 'essentially tied') in body
    assert ('真实恶劣天气验证' if chinese else 'real-world adverse-weather validation') in body
    assert '**485' in body and '**477' in body and '**99.08%**' in body
    if chinese:
        for condition in ('失焦', '运动模糊', '固定角度偏移', '动态抖动'):
            assert f'- **{condition}：' in body
        for cause in ('自动对焦', '更长曝光', '检修', '阵风', '重型车辆'):
            assert cause in body
        assert '调整后保持不动的固定偏角不同' in body
    else:
        for condition in ('Defocus', 'Motion blur', 'Fixed camera-angle shifts', 'Dynamic shake'):
            assert f'- **{condition}:' in body
        for cause in ('autofocus', 'longer exposures', 'maintenance', 'Wind gusts', 'heavy vehicles'):
            assert cause in body
        assert 'Unlike a fixed angle shift' in body
    assert '(docs/visual-robustness.md)' in body
    highlights = PAGES.render_highlights(data, chinese, records)
    assert '**99.08%**' in highlights
    assert '1.36%' in summary
    for group in data['extreme']:
        s1 = PAGES.traffic_stats(group, 's1', records)
        mp = PAGES.traffic_stats(group, 'mp', records)
        for metric in ('mean_wait_s_per_vehicle', 'mean_queue_vehicles', 'mean_journey_s_per_vehicle'):
            assert s1[metric] < mp[metric]


def test_missing_control_history_is_not_silently_replaced_with_partial_mean():
    group = {'scene': 'nansha', 'cases': 1, 'case_results': [
        {'s1': 10, 'mp': 20, 'source_records': {'s1': {'vehicles': 2}}}]}
    row = {'scene': 'nansha', 'condition': 'clean', 'controller': 'mp', 'status': 'missing_control_history'}
    stats = PAGES.traffic_stats(group, 'mp', [row])
    assert stats['mean_journey_s_per_vehicle'] == 20
    assert stats['mean_wait_s_per_vehicle'] is None
    assert stats['mean_queue_vehicles'] is None


def test_wait_includes_measured_insertion_wait_not_only_inserted_vehicles():
    group = {'scene': 'town', 'cases': 1, 'case_results': [
        {'s1': 60, 'mp': 100, 'source_records': {'s1': {'vehicles': 2}}}]}
    record = dict(scene='town', condition='clean', controller='s1', status='complete',
                  vehicles=2, sum_observed_stopped_time_s=20, mean_insertion_wait_s=5,
                  mean_queue_vehicles=3)
    assert PAGES.traffic_stats(group, 's1', [record]) == {
        'mean_journey_s_per_vehicle': 30, 'mean_wait_s_per_vehicle': 15,
        'mean_queue_vehicles': 3, 'complete_cases': 1}


def test_public_previews_preserve_animation_and_have_traceable_sources():
    import hashlib
    from PIL import Image
    manifest = json.loads((ROOT / 'assets/previews/manifest.json').read_text())['files']
    source = json.loads((ROOT / 'results/fusion-2026-10-30-github-videos.json').read_text())['videos']
    assert set(manifest) == set(source)
    assert len([r for r in manifest.values() if 'preview' in r]) == 16
    for key, row in manifest.items():
        assert row['source'] == source[key]
        assert (ROOT / row['poster']).is_file()
        if 'preview' in row:
            path = ROOT / row['preview']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
            assert path.stat().st_size < 4_800_000
            with Image.open(path) as im:
                assert im.n_frames > 1
                assert list(im.size) == row['size']
                assert row['duration_ms'] >= (4700 if 'shake5' in key else 11900)


@pytest.mark.parametrize('chinese', [False, True])
def test_github_video_uses_native_autoembed_not_html_or_navigation(chinese):
    body = PAGES.video_tag('nansha', 'clean', chinese)
    assert body.startswith('https://github.com/user-attachments/assets/')
    assert len(body.splitlines()) == 1
    assert '<video' not in body
    assert '[' not in body
    assert '/blob/' not in body


@pytest.mark.parametrize('chinese', [False, True])
@pytest.mark.parametrize('scene,condition', [
    ('town', 'angle15'), ('nansha', 'mb31'), ('nansha', 'clean'), ('town', 'clean'),
])
def test_video_starts_collapsed_with_valid_public_media(chinese, scene, condition):
    body = PAGES.render_video(scene, condition, chinese)
    details = ET.fromstring(body)
    assert details.tag == 'details' and 'open' not in details.attrib
    summary = details.find('summary')
    assert summary.text.startswith('视频：' if chinese else 'Video: ')
    if condition == 'clean':
        import hashlib
        language = 'zh' if chinese else 'en'
        manifest = json.loads((ROOT / 'assets/videos/manifest.json').read_text())['files']
        row = manifest[f'{language}/{scene}-clean.mp4']
        assert details.find('img').get('src') == row['preview']
        assert (ROOT / row['preview']).is_file()
        assert row['video'] in body and 'nansha' not in body and 'town' not in body.lower()
        assert hashlib.sha256((ROOT / row['video']).read_bytes()).hexdigest() == row['sha256']
        assert details.find('.//video') is None
        return
    assert summary.tail.strip() == PAGES.video_tag(scene, condition, chinese)
    assert '\n\n' + PAGES.video_tag(scene, condition, chinese) + '\n\n' in body
    assert details.find('.//img') is None and details.find('.//video') is None


@pytest.mark.parametrize('filename', ['README.md', 'README.zh-CN.md'])
def test_readmes_keep_details_balanced_and_featured_previews_visible(filename):
    body = (ROOT / filename).read_text()
    assert body.count('<details>') == body.count('</details>')
    featured = body.split('<!-- FUSION_FEATURED:BEGIN -->')[1].split('<!-- FUSION_FEATURED:END -->')[0]
    assert '<details' not in featured and featured.count('.gif') == 2
    assert '<details open' not in body


def test_fresh_mp_row_uses_all_three_metrics_from_the_same_supplement():
    group = {'scene': 'nansha', 'cases': 1, 'case_results': [
        {'s1': 10, 'mp': 20, 'source_records': {'s1': {'vehicles': 2}}}]}
    fresh = dict(scene='nansha', condition='clean', controller='mp', status='complete',
                 vehicles=2, sum_observed_stopped_time_s=12, mean_insertion_wait_s=1,
                 mean_queue_vehicles=3, mean_journey_s=25,
                 evaluation_batch='nansha-mp-metrics-20261030')
    stats = PAGES.traffic_stats(group, 'mp', [fresh])
    assert stats['mean_journey_s_per_vehicle'] == 25
    assert stats['mean_wait_s_per_vehicle'] == 7
    assert stats['mean_queue_vehicles'] == 3
    assert PAGES.improvement_percent(group, 'mp', [fresh]) == pytest.approx(60)
