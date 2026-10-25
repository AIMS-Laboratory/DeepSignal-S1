"""Command-line entry points for the public simulation tests."""

import argparse
import json
import os
from pathlib import Path
import sys

from .data import build_plan, load_scene, read_json, write_json


def parser():
    p = argparse.ArgumentParser(prog="deepsignal-s1")
    commands = p.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Build a deterministic arrival plan")
    prepare.add_argument("--scene", required=True, type=Path)
    prepare.add_argument(
        "--regime",
        choices=("east-west", "north-south", "time-varying"),
        default="east-west",
    )
    prepare.add_argument("--seed", type=int, default=99001)
    prepare.add_argument("--duration", type=float, default=300)
    prepare.add_argument("--output", required=True, type=Path)
    for name in ("run", "run-suite"):
        run = commands.add_parser(name)
        run.add_argument(
            "--controller", choices=("fixed", "s1", "visual-pressure"), default="fixed"
        )
        run.add_argument("--endpoint", default=os.environ.get("DEEPSIGNAL_ENDPOINT"))
        run.add_argument(
            "--detector-endpoint", default=os.environ.get("DETECTOR_ENDPOINT")
        )
        run.add_argument("--assets", type=Path, default=Path("assets/runtime"))
        run.add_argument("--host", default="127.0.0.1")
        run.add_argument("--port", type=int, default=25020)
        run.add_argument("--cpu", action="store_true")
        run.add_argument("--record", action="store_true")
        run.add_argument("--realtime", action="store_true")
        run.add_argument("--decision-deadline", type=float, default=1.0)
        run.add_argument("--output", required=True, type=Path)
        if name == "run":
            run.add_argument("--scene", required=True, type=Path)
            run.add_argument("--plan", required=True, type=Path)
            run.add_argument(
                "--condition",
                choices=("clean", "motion-blur", "defocus"),
                default="clean",
            )
        else:
            run.add_argument("--suite", required=True, type=Path)
    summary = commands.add_parser("summarize")
    summary.add_argument("--suite", required=True, type=Path)
    summary.add_argument("--runs", required=True, type=Path)
    summary.add_argument(
        "--controllers", nargs="+", default=["s1", "fixed", "visual-pressure"]
    )
    installer = commands.add_parser("install-assets")
    installer.add_argument("--archive", required=True, type=Path)
    installer.add_argument("--target", type=Path, default=Path("assets/runtime"))
    server = commands.add_parser("launch-scene")
    server.add_argument("--scene", required=True, type=Path)
    server.add_argument("--assets", type=Path, default=Path("assets/runtime"))
    server.add_argument("--port", type=int, default=25020)
    server.add_argument("--adapter", type=int, default=0)
    video = commands.add_parser("make-video")
    video.add_argument("--model-run", required=True, type=Path)
    video.add_argument("--fixed-run", required=True, type=Path)
    video.add_argument("--output", required=True, type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = build_plan(
                load_scene(args.scene), args.regime, args.seed, args.duration
            )
            write_json(args.output, result)
            print(f"Prepared {len(result['vehicles'])} vehicle arrivals: {args.output}")
        elif args.command in ("run", "run-suite"):
            from .runner import run_episode

            options = {
                "controller": args.controller,
                "endpoint": args.endpoint,
                "detector_endpoint": args.detector_endpoint,
                "assets": args.assets,
                "host": args.host,
                "port": args.port,
                "cpu": args.cpu,
                "record": args.record,
                "realtime": args.realtime,
                "deadline": args.decision_deadline,
            }
            if args.command == "run":
                result = run_episode(
                    load_scene(args.scene),
                    read_json(args.plan),
                    args.output,
                    condition=args.condition,
                    **options,
                )
                print(json.dumps(result, indent=2))
            else:
                suite = read_json(args.suite)
                for case in suite["cases"]:
                    scene = load_scene(args.suite.resolve().parent / case["scene_file"])
                    for seed in suite["seeds"]:
                        plan = build_plan(
                            scene, case["regime"], seed, suite["duration_s"]
                        )
                        name = f"{case['scene']}-{case['regime']}-{case['condition']}-{seed}"
                        target = args.output / name / args.controller
                        result = run_episode(
                            scene, plan, target, condition=case["condition"], **options
                        )
                        print(name, json.dumps(result["metrics"]))
        elif args.command == "summarize":
            from .summary import summarize

            result = summarize(args.runs, args.suite, args.controllers)
            print(json.dumps(result["rows"], indent=2))
        elif args.command == "install-assets":
            from .assets import install

            print(json.dumps(install(args.archive, args.target), indent=2))
        elif args.command == "launch-scene":
            from .assets import launch

            return launch(
                args.assets,
                load_scene(args.scene),
                port=args.port,
                adapter=args.adapter,
            )
        elif args.command == "make-video":
            from .video import render

            render(args.model_run, args.fixed_run, args.output)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
