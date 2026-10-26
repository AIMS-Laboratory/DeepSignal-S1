import argparse
import base64
import time
import numpy as np
MODEL = None

def main():
    global MODEL
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--port', type=int, default=8030)
    ap.add_argument('--conf', type=float, default=0.25)
    ap.add_argument('--ns-calib', type=float, default=1.62, help='NS 轴计数校准因子（balanced dev 25 帧：EW 均值 4.80 vs NS 2.96，E 相机 lateral_offset=7 视角差所致；MP 判据仅比轴向故只做轴向校准）')
    args = ap.parse_args()
    import cv2
    import uvicorn
    from fastapi import FastAPI
    from pydantic import BaseModel
    from ultralytics import YOLO
    MODEL = YOLO(args.model)
    MODEL.predict(np.zeros((360, 640, 3), dtype=np.uint8), conf=args.conf, classes=[2, 7], verbose=False)

    class DetectReq(BaseModel):
        image: str
        tiles: dict
        tile_w: int = 640
        tile_h: int = 360

    class Detect2Req(DetectReq):
        guides: dict = {}
    app = FastAPI()

    @app.post('/v1/detect')
    def detect(req: DetectReq):
        t0 = time.monotonic()
        img = cv2.imdecode(np.frombuffer(base64.b64decode(req.image), np.uint8), cv2.IMREAD_COLOR)
        counts = {}
        for (direction, (x, y)) in req.tiles.items():
            tile = img[y:y + req.tile_h, x:x + req.tile_w]
            r = MODEL.predict(tile, conf=args.conf, classes=[2, 7], verbose=False)
            boxes = r[0].boxes
            if boxes is not None and len(boxes):
                cy = boxes.xywh[:, 1] + boxes.xywh[:, 3] / 2
                counts[direction] = int((cy < req.tile_h * 0.5).sum())
            else:
                counts[direction] = 0
        return {'counts': counts, 'counts_calib': {d: round(n * args.ns_calib, 2) if d in ('N', 'S') else n for (d, n) in counts.items()}, 'infer_ms': round((time.monotonic() - t0) * 1000, 1)}

    @app.post('/v1/detect2')
    def detect2(req: Detect2Req):
        t0 = time.monotonic()
        img = cv2.imdecode(np.frombuffer(base64.b64decode(req.image), np.uint8), cv2.IMREAD_COLOR)
        movement = {}
        for (direction, (x, y)) in req.tiles.items():
            polys = {}
            for (lane_name, spec) in req.guides.get(direction, {}).items():
                pts = np.array(spec['polygon'] if isinstance(spec, dict) else spec, dtype=np.float32)
                if len(pts) >= 3:
                    polys[lane_name] = pts
            tile = img[y:y + req.tile_h, x:x + req.tile_w]
            r = MODEL.predict(tile, conf=args.conf, classes=[2, 7], verbose=False)
            boxes = r[0].boxes
            for lane_name in ('SR', 'L'):
                movement[f'{direction}-{lane_name}'] = 0
            if boxes is None or not len(boxes):
                continue
            cx = boxes.xywh[:, 0].cpu().numpy()
            cy = boxes.xywh[:, 1].cpu().numpy()
            for (lane_name, pts) in polys.items():
                inside = np.array([cv2.pointPolygonTest(pts, (float(px), float(py)), False) >= 0 for (px, py) in zip(cx, cy)])
                movement[f'{direction}-{lane_name}'] = int(inside.sum())
        calib = {k: round(n * args.ns_calib, 2) if k[0] in ('N', 'S') else n for (k, n) in movement.items()}
        return {'movement': movement, 'movement_calib': calib, 'infer_ms': round((time.monotonic() - t0) * 1000, 1)}
    uvicorn.run(app, host='0.0.0.0', port=args.port)
if __name__ == '__main__':
    main()
