from __future__ import annotations
from collections.abc import Mapping
from typing import Any, cast
import cv2
import numpy as np
from .cameras import CameraRigConfig, TILE_LABELS, covers_of, slot_offsets
from .control import Frame

def carla_image_to_bgr(image: Any) -> Frame:
    bgra = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)
    return bgra[:, :, :3].copy()

def compose_tiled_frame(direction_frames: Mapping[str, Frame], config: CameraRigConfig, *, draw_labels: bool=True) -> Frame:
    offsets = slot_offsets(config)
    columns = max((x // config.tile_width for (x, _) in offsets.values())) + 1
    rows = max((y // config.tile_height for (_, y) in offsets.values())) + 1
    canvas = np.zeros((rows * config.tile_height, columns * config.tile_width, 3), dtype=np.uint8)
    for (camera, (x, y)) in offsets.items():
        source = direction_frames.get(camera)
        tile: Frame
        if source is None:
            tile = cast(Frame, np.zeros((config.tile_height, config.tile_width, 3), dtype=np.uint8))
        else:
            tile = cast(Frame, cv2.resize(source, (config.tile_width, config.tile_height), interpolation=cv2.INTER_AREA))
        if draw_labels:
            label = '+'.join((TILE_LABELS[d] for d in covers_of(config, camera)))
            if source is None:
                label += ' | NO CAMERA'
            cv2.putText(tile, label, (16, min(44, config.tile_height - 8)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
        canvas[y:y + config.tile_height, x:x + config.tile_width] = tile
    return canvas
