"""Deterministic paired visual perturbations driven by simulation time."""

import math
import os
import random

PROFILES = {
    "clean": {},
    "df9": {"defocus_sigma": 9.0},
    "mb31": {"motion_kernel_px": 31},
    "angle15": {"fixed_magnitudes_deg": (15.0, 8.0, 0.0)},
    "shake5": {"shake_amplitudes_deg": (5.0, 5.0, 2.5)},
}


class VisualPerturbation:
    def __init__(self, condition, seed):
        if condition not in PROFILES:
            raise ValueError(f"Unsupported visual condition: {condition}")
        self.condition = condition
        self.profile = PROFILES[condition]
        self.seed = int(seed)
        self.cameras = {}
        self.bases = {}
        self.parameters = {}
        self.current_time = 0.0

    @classmethod
    def from_env(cls, seed):
        return cls(os.environ.get("DS_VISUAL_CONDITION", "clean"), seed)

    def bind(self, cameras):
        self.cameras = cameras
        rng = random.Random(self.seed)
        for name in sorted(cameras):
            rotation = cameras[name].get_transform().rotation
            self.bases[name] = (rotation.yaw, rotation.pitch, rotation.roll)
            if self.condition == "angle15":
                self.parameters[name] = tuple(
                    magnitude * rng.choice((-1, 1)) if magnitude else 0.0
                    for magnitude in self.profile["fixed_magnitudes_deg"]
                )
            elif self.condition == "shake5":
                self.parameters[name] = tuple(rng.uniform(0, 2 * math.pi) for _ in range(6))
        self.move(0.0)

    def offsets(self, name, sim_time):
        if self.condition == "angle15":
            return self.parameters[name]
        if self.condition == "shake5":
            phases = self.parameters[name]
            return tuple(
                amplitude
                * (
                    0.7 * math.sin(2 * math.pi * 0.37 * sim_time + phases[2 * index])
                    + 0.3 * math.sin(2 * math.pi * 0.61 * sim_time + phases[2 * index + 1])
                )
                for index, amplitude in enumerate(self.profile["shake_amplitudes_deg"])
            )
        return (0.0, 0.0, 0.0)

    def move(self, sim_time):
        self.current_time = float(sim_time)
        if self.condition not in ("angle15", "shake5"):
            return
        for name, camera in self.cameras.items():
            transform = camera.get_transform()
            yaw, pitch, roll = self.bases[name]
            dyaw, dpitch, droll = self.offsets(name, self.current_time)
            transform.rotation.yaw = yaw + dyaw
            transform.rotation.pitch = pitch + dpitch
            transform.rotation.roll = roll + droll
            camera.set_transform(transform)

    def image(self, image):
        import cv2
        import numpy as np

        if "motion_kernel_px" in self.profile:
            width = self.profile["motion_kernel_px"]
            kernel = np.ones((1, width), dtype=np.float32) / width
            return cv2.filter2D(image, -1, kernel)
        if "defocus_sigma" in self.profile:
            return cv2.GaussianBlur(image, (0, 0), self.profile["defocus_sigma"])
        return image

    def metadata(self):
        return {
            "condition": self.condition,
            "seed": self.seed,
            "profile": self.profile,
            "clock": "SUMO simulation seconds",
            "camera_parameters": self.parameters,
            "base_rotations_deg": self.bases,
        }
