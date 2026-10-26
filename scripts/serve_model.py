"""Start the inference runtime distributed with the approved model download."""

import argparse
import importlib.util
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18404)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    path = args.model.resolve() / "deepsignal_runtime.py"
    spec = importlib.util.spec_from_file_location("deepsignal_release", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Missing model inference runtime: {path}")
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    runtime.serve(args.model, host=args.host, port=args.port, device=args.device)


if __name__ == "__main__":
    main()
