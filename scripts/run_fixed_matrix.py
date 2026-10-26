"""Run the fixed baseline with bounded concurrency and CPU-load backpressure."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def cpu_sample():
    values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--scene', choices=['all', 'nansha', 'town10hd'], default='all')
    args = parser.parse_args()
    if not 1 <= args.jobs <= max(1, (os.cpu_count() or 1) // 2):
        parser.error('--jobs must use at most half the logical CPUs')
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / 'reproduction/matrix.json').read_text())['cases']
    cases = [c for c in cases if args.scene == 'all' or c['scene'] == args.scene]
    pending = [c for c in cases if not (args.output / c['scene'] / c['tag'] / 'result.json').exists()]
    active, failures = [], []
    previous, paused, peak = cpu_sample(), False, 0.0
    try:
        while pending or active:
            current = cpu_sample()
            total, idle = current[0] - previous[0], current[1] - previous[1]
            load = 100 * (1 - idle / total) if total else 0
            previous = current
            peak = max(peak, load)
            should_pause = load >= 65 or (paused and load >= 60)
            if should_pause != paused:
                for process, _, _ in active:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGSTOP if should_pause else signal.SIGCONT)
                paused = should_pause
            for item in active[:]:
                process, case, handle = item
                code = process.poll()
                if code is not None:
                    handle.close()
                    active.remove(item)
                    if code:
                        failures.append(case)
                    print(f'{case["scene"]} {case["tag"]}: exit={code}; CPU={load:.1f}%', flush=True)
            while pending and len(active) < args.jobs and not paused and load < 60:
                case = pending.pop(0)
                target = (args.output / case['scene'] / case['tag']).resolve()
                target.mkdir(parents=True, exist_ok=True)
                handle = (target / 'run.log').open('w')
                command = [sys.executable, str(root / 'scripts/reproduce.py'), '--scene', case['scene'],
                           '--tag', case['tag'], '--controller', 'fixed', '--output', str(target)]
                process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
                active.append((process, case, handle))
            time.sleep(1)
    finally:
        for process, _, handle in active:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGCONT)
                os.killpg(process.pid, signal.SIGTERM)
                process.wait()
            handle.close()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'batch.json').write_text(json.dumps({'cases': len(cases), 'failures': failures,
        'peak_sampled_system_cpu_percent': peak, 'jobs': args.jobs}, indent=2) + '\n')
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
