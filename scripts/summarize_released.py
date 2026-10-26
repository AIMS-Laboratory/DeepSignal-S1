"""Recompute the published, version-bound finite-horizon comparison tables."""

import argparse
import json
from pathlib import Path


def load_fixed(path):
    path = Path(path)
    if path.is_file():
        return json.loads(path.read_text())['records']
    records = {}
    for source in path.rglob('*.json'):
        record = json.loads(source.read_text())
        if record.get('baseline') == 'engineering-fixed':
            if not record.get('scene'):
                record['scene'] = next((p for p in source.parts if p in {'nansha', 'town10hd', 'town10hd-archive'}), None)
            if record['scene'] is None:
                continue
            if record.get('scene') == 'town10hd-archive':
                record['scene'] = 'town10hd'
            records[record['scene'], record['tag']] = record
    return list(records.values())


def build_report(manifest, reference, fixed_records):
    reference = Path(reference)
    fixed = {(r['scene'], r['tag']): r for r in fixed_records}
    blocks = []
    for suite_name, suite in manifest['suites'].items():
        metric = suite['metric']
        for condition, tags in suite['conditions'].items():
            arms = {}
            for controller in ['s1', 'visual-pressure']:
                records = {}
                for tag in tags:
                    path = reference / suite_name / condition / controller / (tag + '.json')
                    if not path.exists():
                        raise ValueError(f'Missing published case: {path}')
                    record = json.loads(path.read_text())
                    if controller == 's1' and record.get('model_version') != suite['model_version']:
                        raise ValueError(f'Model version mismatch: {path}')
                    if record.get('fail') is None and not isinstance(record.get(metric), (int, float)):
                        raise ValueError(f'Successful case has no metric: {path}')
                    records[tag] = record
                arms[controller] = records
            paired = [t for t in tags if all(arms[a][t].get('fail') is None for a in arms)]
            sums = {a: sum(arms[a][t][metric] for t in paired) for a in arms}
            block = {'suite': suite_name, 'condition': condition,
                     'model_version': suite['model_version'], 'runtime': suite['runtime'],
                     'metric': metric, 'horizon_s': suite['horizon_s'],
                     'expected_pairs': len(tags), 'successful_pairs': len(paired), 'paired_tags': paired,
                     'failures': {a: [{'tag': t, 'fail': r['fail']} for t, r in records.items() if r.get('fail')]
                                  for a, records in arms.items()},
                     'paired_metric_sum': sums,
                     'improvement_vs_yolo_pct': 100 * (1 - sums['s1'] / sums['visual-pressure']),
                     's1_paired_wins': sum(arms['s1'][t][metric] < arms['visual-pressure'][t][metric] for t in paired)}
            if condition == 'clean':
                fixed_scene = 'town10hd' if suite_name == 'town10hd-archive' else suite_name
                fixed_sum = sum(fixed[(fixed_scene, t)][metric] for t in paired)
                block.update(engineering_fixed_sum=fixed_sum,
                             improvement_vs_engineering_fixed_pct=100 * (1 - sums['s1'] / fixed_sum))
                if suite_name == 'nansha':
                    junctions = []
                    for junction in sorted({t.split('-')[0] for t in paired}):
                        selected = [t for t in paired if t.startswith(junction + '-')]
                        values = {a: sum(arms[a][t][metric] for t in selected) for a in arms}
                        junctions.append({'junction': junction, 'case_count': len(selected),
                                          'metric_sum': values,
                                          's1_relative_difference_pct': 100 * (values['s1'] / values['visual-pressure'] - 1)})
                    block['junctions'] = junctions
                    block['junctions_within_5pct'] = sum(abs(j['s1_relative_difference_pct']) <= 5 for j in junctions)
            blocks.append(block)
    return {'release': manifest['release'], 'source': 'completed archived measurements; no supplementary results',
            'formula': '100 * (1 - sum(S1) / sum(baseline)) over explicitly matched successful cases',
            'blocks': blocks}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, default=root / 'reproduction/reference-results')
    parser.add_argument('--fixed', type=Path, default=root / 'results/engineering-fixed-2026-10-26.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    manifest = json.loads((root / 'reproduction/release-matrix.json').read_text())
    fixed = load_fixed(args.fixed)
    report = build_report(manifest, args.reference, fixed)
    text = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
