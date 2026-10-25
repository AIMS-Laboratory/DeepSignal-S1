"""Video assembly checks use synthetic frames, not performance evidence."""

import json
import shutil

import cv2
import numpy as np
import pytest

from deepsignal_s1.data import write_json
from deepsignal_s1.video import render


@pytest.fixture(params=[5, 10])
def footage(tmp_path, request):
    fps = request.param
    for controller, frames in (("s1", 2), ("fixed", 3)):
        directory = tmp_path / controller
        report = {
            "controller": controller,
            "complete": True,
            "failure": None,
            "quality": "Epic",
            "scene": "synthetic-video-test",
            "regime": "east-west",
            "condition": "clean",
            "seed": 1,
            "realtime_verified": False,
            "metrics": {"mean_journey_s": 10 if controller == "s1" else 20},
        }
        write_json(directory / "report.json", report)
        write_json(directory / "plan.json", {"seed": 1})
        writer = cv2.VideoWriter(
            str(directory / "cameras.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
            fps, (160, 90)
        )
        timeline = []
        for index in range(frames):
            writer.write(np.full((90, 160, 3), 70 + 40 * index, np.uint8))
            timeline.append({
                "time": (index + 1) / fps, "phase": "test", "stage": "green",
                "green_total_s": 10, "countdown_s": None,
                "metrics": {"mean_journey_s": 10, "mean_queue_vehicles": 1,
                            "complete": True, "completed": 2, "vehicles": 2},
            })
        writer.release()
        (directory / "video-trace.jsonl").write_text(
            "\n".join(json.dumps(row) for row in timeline) + "\n"
        )
    return tmp_path


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required")
def test_comparison_encodes_both_sides_and_retains_finished_frame(footage):
    output = footage / "comparison"
    render(footage / "s1", footage / "fixed", output)
    capture = cv2.VideoCapture(str(output / "DeepSignal-S1-vs-fixed.mp4"))
    assert capture.get(cv2.CAP_PROP_FRAME_COUNT) == 3
    assert capture.get(cv2.CAP_PROP_FRAME_WIDTH) == 3840
    assert capture.get(cv2.CAP_PROP_FRAME_HEIGHT) == 2160
    source = cv2.VideoCapture(str(footage / "s1/cameras.mp4"))
    assert capture.get(cv2.CAP_PROP_FPS) == source.get(cv2.CAP_PROP_FPS)
    source.release()
    for _ in range(3):
        ok, frame = capture.read()
        assert ok and frame.std() > 10
        assert frame[800, 800].mean() > 40
        assert frame[800, 2800].mean() > 40
    capture.release()
    assert (output / "comparison-cover.jpg").is_file()


def test_mismatched_video_plans_are_rejected(footage):
    write_json(footage / "fixed/plan.json", {"seed": 2})
    with pytest.raises(ValueError, match="same arrival plan"):
        render(footage / "s1", footage / "fixed", footage / "comparison")
