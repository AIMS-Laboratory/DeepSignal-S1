"""Run the finite DeepSignal-S1-1.0 fusion-weight reproduction matrix."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


def main():
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / 'reproduction/fusion-release-matrix.json'
    manifest = json.loads(manifest_path.read_text())
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=sorted(manifest['suites']), required=True)
    parser.add_argument('--controller', choices=['fixed', 's1', 'visual-pressure'], required=True)
    parser.add_argument('--condition', choices=['clean', 'df9', 'mb31', 'angle15', 'shake5'], required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:18404')
    parser.add_argument('--detector-endpoint', default='http://127.0.0.1:8031/v1/detect2')
    parser.add_argument('--port', type=int, default=25020)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.controller == 'fixed' and args.condition != 'clean':
        parser.error('Frozen engineering fixed timing is compared only under clean visual conditions.')

    suite = manifest['suites'][args.suite]
    allowed_conditions = suite.get('allowed_conditions', manifest['conditions'])
    if args.condition not in allowed_conditions:
        parser.error(f'{args.suite} only supports conditions: {", ".join(allowed_conditions)}')
    if 'tags_from' in suite:
        source = suite['tags_from']
        source_manifest = json.loads((manifest_path.parent / source['manifest']).read_text())
        tags = source_manifest['suites'][source['suite']]['conditions'][source['condition']]
    else:
        tags = suite['tags']
    if args.controller == 's1':
        with urllib.request.urlopen(args.endpoint + '/health', timeout=10) as response:
            actual_version = json.loads(response.read())['model_version']
        if actual_version != suite['model_version']:
            raise RuntimeError(f'This suite requires {suite["model_version"]}, not {actual_version}')

    output = args.output.resolve() / args.suite / args.condition / args.controller
    output.mkdir(parents=True, exist_ok=True)
    config_path = output / 'run-config.json'
    run_config = {
        'manifest': str(manifest_path.relative_to(root)),
        'release': manifest['release'],
        'suite': args.suite,
        'scene': suite['scene'],
        'condition': args.condition,
        'condition_profile': manifest['conditions'][args.condition],
        'controller': args.controller,
        'expected_model_version': suite['model_version'],
        'runtime': suite['runtime'],
        'quality': suite['quality'],
        'protocol': manifest['protocol'],
        'comparison_policy': manifest['comparison_policy'],
    }
    if config_path.exists():
        if json.loads(config_path.read_text()) != run_config:
            raise RuntimeError(f'Existing run manifest does not match this invocation: {config_path}')
    else:
        config_path.write_text(json.dumps(run_config, indent=2) + '\n')

    failures = []
    for index, tag in enumerate(tags):
        target = output / (tag + '.json')
        if not target.exists():
            case_output = output / tag if args.controller == 'fixed' else output
            command = [sys.executable, str(root / 'scripts/reproduce.py'),
                       '--scene', suite['scene'], '--controller', args.controller,
                       '--condition', args.condition, '--tag', tag,
                       '--endpoint', args.endpoint, '--detector-endpoint', args.detector_endpoint,
                       '--port', str(args.port), '--output', str(case_output)]
            with (output / (tag + '.log')).open('w') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            produced = case_output / 'result.json' if args.controller == 'fixed' else target
            if result.returncode or not produced.exists():
                raise RuntimeError(f'Case process failed: {tag}; see its log')
            record = json.loads(produced.read_text())
            record.update(scene=args.suite, condition=args.condition, controller=args.controller,
                          runtime=suite['runtime'], quality=suite['quality'])
            if args.controller == 's1':
                record['model_version'] = suite['model_version']
            target.write_text(json.dumps(record, indent=2) + '\n')
        record = json.loads(target.read_text())
        if record.get('fail'):
            failures.append({'tag': tag, 'fail': record['fail']})
        status = {'completed': index + 1, 'expected': len(tags), 'failures': failures}
        (output / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
        print(json.dumps(status), flush=True)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
