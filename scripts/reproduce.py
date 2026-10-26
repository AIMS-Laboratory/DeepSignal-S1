"""Run one fixed-plan case from the archived paired-test matrix."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', choices=['nansha', 'town10hd'], required=True)
    parser.add_argument('--controller', choices=['fixed', 's1', 'visual-pressure'], required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--condition', choices=['clean', 'motion-blur-9', 'defocus-2.5', 'angle-8', 'angle-12', 'angle-16'], default='clean')
    parser.add_argument('--endpoint', default='http://127.0.0.1:18404')
    parser.add_argument('--detector-endpoint', default='http://127.0.0.1:8031/v1/detect2')
    parser.add_argument('--port', type=int, default=25020)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[1] / 'reproduction'
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    env['PYTHONPATH'] = os.pathsep.join(str(workspace / p) for p in ['src', 'protocol', 'scripts/carla'])
    env['CARLA_RPC_PORT'] = env['NS_UE5_PORT'] = str(args.port)
    if args.controller == 'fixed':
        cmd = [sys.executable, str(workspace / 'protocol/fixed_baseline.py'), '--scene', args.scene,
               '--tag', args.tag, '--output', str(output)]
        env['CUDA_VISIBLE_DEVICES'] = ''
    else:
        deg, param = {
            'clean': ('none', '0'), 'motion-blur-9': ('mb', '9'),
            'defocus-2.5': ('df', '2.5'), 'angle-8': ('j8', '8'),
            'angle-12': ('j8', '12'), 'angle-16': ('j8', '16'),
        }[args.condition]
        if args.scene == 'nansha':
            name = 'nansha_s1.py' if args.controller == 's1' else 'nansha_pressure.py'
            option = '--serve' if args.controller == 's1' else '--yolo'
            endpoint = args.endpoint if args.controller == 's1' else args.detector_endpoint
            cmd = [sys.executable, str(workspace / 'protocol' / name), args.tag, option, endpoint, '--out', str(output)]
            env.update(NS_DEG=deg, NS_DEGP=param)
        elif args.controller == 's1':
            cmd = [sys.executable, str(workspace / 'protocol/town_s1.py'), args.tag,
                   '--serve', args.endpoint, '--out', str(output), '--jitter', param if deg == 'j8' else '0',
                   '--degrade', 'none' if deg == 'j8' else deg, '--deg-param', param]
        else:
            script = 'town_pressure_degraded.py' if deg in ('mb', 'df') else 'town_pressure.py'
            cmd = [sys.executable, str(workspace / 'protocol' / script), args.tag]
            env.update(MP_JITTER=param if deg == 'j8' else '0', OUTD=str(output), YOLO_URL=args.detector_endpoint)
            env.update(DEG=deg, DEGP=param)
    return subprocess.call(cmd, cwd=workspace, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
