"""YOLO+MP movement-pressure baseline using the same camera samples."""

import base64
import json
import urllib.request


class VisualPressureClient:
    def __init__(self, endpoint, scene, guides):
        if not endpoint:
            raise ValueError("Visual pressure requires --detector-endpoint")
        self.endpoint = endpoint.rstrip("/") + "/v1/detect2"
        self.scene, self.guides = scene, guides

    def decide(self, context, frames):
        width, height = self.scene["tile_size"]
        tiles = {
            a: [(i % 2) * width, (i // 2) * height]
            for i, a in enumerate(("E", "W", "S", "N"))
            if a in self.scene["approach_edges"]
        }
        observations = []
        for frame in frames:
            payload = {
                "image": base64.b64encode(frame).decode("ascii"),
                "tiles": tiles,
                "tile_w": width,
                "tile_h": height,
                "guides": self.guides,
            }
            request = urllib.request.Request(
                self.endpoint,
                json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                observations.append(json.load(response)["movement_calib"])
        score = {}
        for phase in self.scene["phases"]:
            score[phase["key"]] = sum(
                weight * observation.get(f"{a}-{kind}", 0)
                for weight, observation in zip((0.25, 0.25, 0.5), observations)
                for a, kind in phase["movements"]
            )
        current = context["signal"]["current_phase"]
        red_age = context["signal"]["red_age_s"]
        order = [p["key"] for p in self.scene["phases"]]

        def value(action):
            phase = (
                current if action == "extend_5s" else action.removeprefix("switch_to_")
            )
            return (
                score[phase] + (1 if phase == current else 0),
                red_age[phase],
                -order.index(phase),
            )

        return {
            "choice": max(context["legal_actions"], key=value),
            "model_version": "yolo-mp-v1",
        }
