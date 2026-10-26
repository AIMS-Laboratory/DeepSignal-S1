"""Run fixed-plan visual cases sequentially on a dedicated scene server."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', choices=['nansha', 'town10hd'], required=True)
    parser.add_argument('--controller', choices=['s1', 'visual-pressure'], required=True)
    parser.add_argument('--condition', choices=['clean', 'motion-blur-9', 'defocus-2.5', 'angle-8', 'angle-12', 'angle-16'], required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:18404')
    parser.add_argument('--detector-endpoint', default='http://127.0.0.1:8031/v1/detect2')
    parser.add_argument('--port', type=int, default=25020)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    matrix = json.loads((root / 'reproduction/matrix.json').read_text())
    cases = [c for c in matrix['cases'] if c['scene'] == args.scene]
    output = args.output.resolve() / args.condition / args.controller
    output.mkdir(parents=True, exist_ok=True)
    config = dict(vars(args), output=str(output), runtime='UE5/CARLA-0.10.0', metric=matrix['metrics'][args.scene])
    if args.controller == 's1':
        with urllib.request.urlopen(args.endpoint + '/health', timeout=10) as response:
            config['model_version'] = json.loads(response.read())['model_version']
    (output / 'run-config.json').write_text(json.dumps(config, indent=2) + '\n')
    failures = []
    for index, case in enumerate(cases):
        target = output / (case['tag'] + '.json')
        if not target.exists():
            command = [sys.executable, str(root / 'scripts/reproduce.py'), '--scene', args.scene,
                       '--controller', args.controller, '--tag', case['tag'], '--condition', args.condition,
                       '--endpoint', args.endpoint, '--detector-endpoint', args.detector_endpoint,
                       '--port', str(args.port), '--output', str(output)]
            with (output / (case['tag'] + '.log')).open('w') as log:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'Test process failed: {case["tag"]}; see its log')
        record = json.loads(target.read_text())
        if record.get('fail'):
            failures.append({'tag': case['tag'], 'fail': record['fail']})
        status = {'scene': args.scene, 'controller': args.controller, 'condition': args.condition,
                  'completed': index + 1, 'expected': len(cases), 'failures': failures}
        (output / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
        print(json.dumps(status), flush=True)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
