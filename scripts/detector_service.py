"""Optional visual-baseline detector. Run independently from the simulator."""

import argparse
import base64
import time


def main():
    import cv2
    import numpy as np
    import uvicorn
    from fastapi import FastAPI
    from ultralytics import YOLO

    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", required=True)
    parser.add_argument("--port", type=int, default=8032)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--ns-calibration", type=float, default=1.62)
    args = parser.parse_args()
    model = YOLO(args.weights)
    app = FastAPI()

    @app.post("/v1/detect2")
    def detect(payload: dict):
        started = time.perf_counter()
        pixels = cv2.imdecode(
            np.frombuffer(base64.b64decode(payload["image"]), np.uint8),
            cv2.IMREAD_COLOR,
        )
        counts = {}
        for approach, (x, y) in payload["tiles"].items():
            tile = pixels[y : y + payload["tile_h"], x : x + payload["tile_w"]]
            result = model.predict(
                tile, conf=0.25, classes=[2, 7], device=args.device, verbose=False
            )[0]
            centers = (
                result.boxes.xywh[:, :2].cpu().numpy()
                if result.boxes is not None
                else []
            )
            for kind in ("SR", "L"):
                spec = payload["guides"].get(approach, {}).get(kind, {})
                polygon = np.asarray(spec.get("polygon", []), dtype=np.float32)
                counts[f"{approach}-{kind}"] = (
                    sum(
                        cv2.pointPolygonTest(polygon, (float(cx), float(cy)), False)
                        >= 0
                        for cx, cy in centers
                    )
                    if len(polygon) >= 3
                    else 0
                )
        calibrated = {
            key: value * (args.ns_calibration if key[0] in "NS" else 1)
            for key, value in counts.items()
        }
        return {
            "movement_calib": calibrated,
            "infer_ms": 1000 * (time.perf_counter() - started),
        }

    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
