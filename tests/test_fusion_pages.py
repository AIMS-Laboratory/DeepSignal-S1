import importlib.util
from pathlib import Path

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
    assert body.count('/town-') == 8
    assert body.count('/nansha-') == 8
    assert f'/fusion-1.0/v4/{language}/town-angle15.gif' in body
    assert '<video controls=' in body
    assert body.count('https://github.com/user-attachments/assets/') == 2


def test_hf_gallery_uses_its_own_public_videos():
    body = PAGES.render_gallery(True, github=False)
    assert 'github.com/user-attachments' not in body
    assert '/zh/town-clean.mp4' in PAGES.video_tag('town', 'clean', True, github=False)
    assert body.count('.mp4"') == 2


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
    assert body.count('<video controls="controls" width="1280"') == 2
    assert '/fusion-1.0/v4/zh/town-shake5.gif' in body
    assert '备用播放' in body


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
