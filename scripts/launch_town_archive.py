"""Launch the archived Town10HD CARLA image with NVIDIA CDI graphics access."""

import argparse
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gpu', required=True, help='NVIDIA GPU UUID from nvidia-smi')
    parser.add_argument('--port', type=int, default=25020)
    args = parser.parse_args()
    return subprocess.call([
        'docker', 'run', '--rm', '--name', f'deepsignal-s1-town-archive-{args.port}',
        '--device', f'nvidia.com/gpu={args.gpu}', '--network=host', '--cpus=12',
        '--env', 'OMP_NUM_THREADS=2', 'carlasim/carla:0.9.16',
        '/bin/bash', 'CarlaUE4.sh', '-RenderOffScreen', '-nosound', '-quality-level=Epic',
        f'-carla-rpc-port={args.port}', f'-carla-streaming-port={args.port + 1}',
    ])


if __name__ == '__main__':
    raise SystemExit(main())
