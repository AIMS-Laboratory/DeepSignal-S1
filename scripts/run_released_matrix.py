"""Run only the cases and frozen model version associated with a published table."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=['nansha', 'town10hd-archive'], required=True)
    parser.add_argument('--controller', choices=['fixed', 's1', 'visual-pressure'], required=True)
    parser.add_argument('--condition', choices=['clean', 'angle-8', 'defocus-2.5'], required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:18404')
    parser.add_argument('--detector-endpoint', default='http://127.0.0.1:8031/v1/detect2')
    parser.add_argument('--port', type=int, default=25020)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.controller == 'fixed' and args.condition != 'clean':
        parser.error('Frozen engineering fixed timing is compared only under clean visual conditions.')
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'reproduction/release-matrix.json').read_text())
    suite = manifest['suites'][args.suite]
    if args.condition not in suite['conditions']:
        parser.error('This condition is not part of the published suite; use the supplementary protocol instead.')
    if args.controller == 's1':
        with urllib.request.urlopen(args.endpoint + '/health', timeout=10) as response:
            actual_version = json.loads(response.read())['model_version']
        if actual_version != suite['model_version']:
            raise RuntimeError(f'This table requires {suite["model_version"]}, not {actual_version}')
    output = args.output.resolve() / args.suite / args.condition / args.controller
    output.mkdir(parents=True, exist_ok=True)
    (output / 'run-config.json').write_text(json.dumps({
        'suite': args.suite, 'condition': args.condition, 'controller': args.controller,
        'release': manifest['release'], 'expected_model_version': suite['model_version'],
        'runtime': suite['runtime'], 'quality': suite['quality'],
    }, indent=2) + '\n')
    failures = []
    for index, tag in enumerate(suite['conditions'][args.condition]):
        target = output / (tag + '.json')
        if not target.exists():
            case_output = output / tag if args.controller == 'fixed' else output
            if args.suite == 'town10hd-archive':
                command = [sys.executable, str(root / 'scripts/reproduce_archive.py')]
            else:
                command = [sys.executable, str(root / 'scripts/reproduce.py'), '--scene', 'nansha']
            command += ['--controller', args.controller, '--condition', args.condition, '--tag', tag,
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
        if args.controller == 's1' and record.get('model_version') != suite['model_version']:
            raise RuntimeError(f'Existing result uses a different or unspecified model version: {tag}')
        if record.get('fail'):
            failures.append({'tag': tag, 'fail': record['fail']})
        status = {'completed': index + 1, 'expected': len(suite['conditions'][args.condition]), 'failures': failures}
        (output / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
        print(json.dumps(status), flush=True)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
