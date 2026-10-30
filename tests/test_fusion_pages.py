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
def test_gallery_shows_both_scenes_without_collapsed_content(chinese, language):
    body = PAGES.render_gallery(chinese)
    assert '<details' not in body
    assert body.count('.gif') == 8
    assert body.count('/town-') == 4
    assert body.count('/nansha-') == 4
    assert f'/fusion-1.0/v4/{language}/town-angle15.gif' in body
    assert '<video' not in body
    assert body.count('https://github.com/user-attachments/assets/') == 2


@pytest.mark.parametrize('chinese', [False, True])
def test_comparison_groups_share_three_cells_without_merging_controller_metrics(chinese):
    data = json.loads((ROOT / 'results/fusion-2026-10-30.json').read_text())
    records = json.loads((ROOT / 'results/fusion-2026-10-30-traffic.json').read_text())['records']
    tables = ET.fromstring('<root>' + PAGES.render(data, chinese, records) + '</root>').findall('table')
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
    assert body.count('<table>') == 4
    assert 'System One（端到端快思考）' in body and 'System One（系统一）' not in body
    assert 'Lane regions are calibrated' in body and 'YOLO车道画线' in body
    assert 'https://github.com/AIMS-Laboratory/DeepSignal-S1/blob/main/docs/reproduction.md' in body
    assert f'[English]({homepage})' in body and '[简体中文](#简体中文)' in body
    assert '/blob/main/README.zh-CN.md' not in body
    assert '### 结果解读' in body and '### What the Results Show' in body


@pytest.mark.parametrize('chinese', [False, True])
def test_discussion_uses_current_comparisons_and_keeps_clean_town_tied(chinese):
    data = json.loads((ROOT / 'results/fusion-2026-10-30.json').read_text())
    records = json.loads((ROOT / 'results/fusion-2026-10-30-traffic.json').read_text())['records']
    body = PAGES.render_discussion(data, chinese, records)
    for percentage in ('18.17', '33.77', '1.36', '2.28', '15.79', '59.29', '30.14',
                       '70.16', '16.40', '82.93', '90.63', '6.80', '6.72'):
        assert f'**{percentage}%**' in body
    assert ('基本持平' if chinese else 'essentially tied') in body
    assert ('真实恶劣天气验证' if chinese else 'real-world adverse-weather validation') in body
    assert '**485' in body and '**477' in body and '**99.08%**' in body
    highlights = PAGES.render_highlights(data, chinese, records)
    assert '**1.36%**' in highlights
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


def test_large_gallery_does_not_reduce_shake_to_a_narrow_preview():
    body = PAGES.render_gallery(True)
    assert body.count('<img width="1280"') == 8
    assert body.count('https://github.com/user-attachments/assets/') == 2
    assert '/fusion-1.0/v4/zh/town-shake5.gif' in body
    assert '备用播放' not in body
    assert 'Large-screen / alternate player' not in body


@pytest.mark.parametrize('chinese', [False, True])
def test_github_video_uses_native_autoembed_not_html_or_navigation(chinese):
    body = PAGES.video_tag('nansha', 'clean', chinese)
    assert body.startswith('https://github.com/user-attachments/assets/')
    assert len(body.splitlines()) == 1
    assert '<video' not in body
    assert '[' not in body
    assert '/blob/' not in body


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
