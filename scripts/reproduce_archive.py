"""Run a published Town archive case with its original CARLA client/runtime."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--controller', choices=['fixed', 's1', 'visual-pressure'], required=True)
    parser.add_argument('--condition', choices=['clean', 'defocus-2.5'], required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:18404')
    parser.add_argument('--detector-endpoint', default='http://127.0.0.1:8031/v1/detect2')
    parser.add_argument('--port', type=int, default=25020)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[1] / 'reproduction'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    env['PYTHONPATH'] = os.pathsep.join(str(workspace / p) for p in
                                      ['legacy-town', 'src', 'protocol', 'scripts/carla'])
    env['CARLA_RPC_PORT'] = str(args.port)
    if args.controller == 'fixed':
        command = [sys.executable, str(workspace / 'protocol/fixed_baseline.py'), '--scene', 'town10hd',
                   '--tag', args.tag, '--output', str(output)]
        env['CUDA_VISIBLE_DEVICES'] = ''
    elif args.controller == 's1':
        command = [sys.executable, str(workspace / 'legacy-town/town_s1.py'), args.tag,
                   '--serve', args.endpoint, '--out', str(output), '--jitter', '0',
                   '--degrade', 'df' if args.condition == 'defocus-2.5' else 'none', '--deg-param', '2.5']
    else:
        name = 'town_pressure_degraded.py' if args.condition == 'defocus-2.5' else 'town_pressure.py'
        command = [sys.executable, str(workspace / 'legacy-town' / name), args.tag]
        env.update(MP_JITTER='0', OUTD=str(output), YOLO_URL=args.detector_endpoint,
                   DEG='df' if args.condition == 'defocus-2.5' else 'none', DEGP='2.5')
    return subprocess.call(command, cwd=workspace, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
