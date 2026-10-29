"""Compose synchronized comparison footage from newly recorded test runs."""

import json
from pathlib import Path
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .data import read_json


def render(model_run, fixed_run, output):
    directories = [Path(model_run), Path(fixed_run)]
    reports = [read_json(d / "report.json") for d in directories]
    if [r["controller"] for r in reports] != ["s1", "fixed"]:
        raise ValueError("Select a model run on the left and fixed timing on the right")
    if reports[1].get("baseline") != "engineering-fixed" or any(r["condition"] != "clean" for r in reports):
        raise ValueError("Current comparison footage requires clean views and identified engineering fixed timing")
    if any(
        not r["complete"] or r.get("failure") or r["quality"] != "Epic" for r in reports
    ):
        raise ValueError(
            "Comparison footage requires complete Epic-quality paired runs"
        )
    if read_json(directories[0] / "plan.json") != read_json(
        directories[1] / "plan.json"
    ):
        raise ValueError("The two videos must share the same arrival plan")
    for field in ("scene", "condition", "regime", "seed"):
        if reports[0][field] != reports[1][field]:
            raise ValueError(f"The two videos differ in {field}")
    captures = [cv2.VideoCapture(str(d / "cameras.mp4")) for d in directories]
    fps = captures[0].get(cv2.CAP_PROP_FPS)
    if fps <= 0 or any(abs(c.get(cv2.CAP_PROP_FPS) - fps) > 0.01 for c in captures):
        for capture in captures:
            capture.release()
        raise ValueError("The paired recordings must have the same frame rate")
    timelines = [
        [
            json.loads(line)
            for line in (d / "video-trace.jsonl").read_text().splitlines()
        ]
        for d in directories
    ]
    for capture, timeline in zip(captures, timelines):
        if not capture.isOpened() or int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) != len(
            timeline
        ):
            raise ValueError("A source video or its synchronized trace is incomplete")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    fonts = {size: ImageFont.truetype(font_path, size) for size in (28, 32, 40, 56, 72)}
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "3840x2160",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output / "DeepSignal-S1-vs-fixed.mp4"),
    ]
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE)
    last = [None, None]
    preview_index = min(round(250 * fps), max(len(t) for t in timelines) - 1)
    journey = [r["metrics"]["mean_journey_s"] for r in reports]
    full_episode = (
        f"Full-episode mean journey: DeepSignal-S1 {journey[0]:.2f}s"
        f"   |   Engineering fixed {journey[1]:.2f}s"
    )
    if journey[0] < journey[1]:
        full_episode += f"   |   {100 * (1 - journey[0] / journey[1]):.1f}% shorter"
    try:
        for index in range(max(len(t) for t in timelines)):
            image = Image.new("RGB", (3840, 2160), (20, 22, 25))
            draw = ImageDraw.Draw(image)
            draw.text(
                (64, 40),
                "DeepSignal-S1  |  Visual Traffic Signal Control",
                font=fonts[56],
                fill="white",
            )
            live = all(r["realtime_verified"] for r in reports)
            draw.text(
                (64, 130),
                f"{reports[0]['scene']}   |   {reports[0]['condition']}   |   "
                + (
                    "Recorded live closed loop"
                    if live
                    else "Recorded online simulation"
                ),
                font=fonts[32],
                fill=(190, 195, 200),
            )
            for side, (capture, timeline) in enumerate(zip(captures, timelines)):
                if index < len(timeline):
                    ok, frame = capture.read()
                    if not ok:
                        raise RuntimeError("Source video decoding failed")
                    last[side] = frame
                state = timeline[min(index, len(timeline) - 1)]
                x = 64 + side * 1920
                color = (89, 218, 159) if side == 0 else (225, 226, 230)
                title = "DeepSignal-S1" if side == 0 else "Engineering Fixed Timing"
                draw.text((x, 240), title, font=fonts[56], fill=color)
                frame = cv2.cvtColor(
                    cv2.resize(last[side], (1792, 1008)), cv2.COLOR_BGR2RGB
                )
                image.paste(Image.fromarray(frame), (x, 340))
                for i, direction in enumerate(("E", "W", "S", "N")):
                    px, py = x + (i % 2) * 896 + 12, 350 + (i // 2) * 504
                    draw.rectangle((px, py, px + 64, py + 48), fill=(20, 22, 25))
                    draw.text(
                        (px + 10, py + 4), direction, font=fonts[32], fill="white"
                    )
                draw.text(
                    (x, 1390),
                    f"Time {state['time']:.1f}s   |   {state['phase']}   |   {state['stage']}",
                    font=fonts[32],
                    fill=color,
                )
                action = state.get("last_action") or (
                    "Fixed phase cycle" if side else "Waiting for first decision"
                )
                draw.text(
                    (x, 1460), action.replace("_", " "), font=fonts[32], fill="white"
                )
                light_color = {
                    "green": (89, 218, 159),
                    "yellow": (245, 207, 97),
                    "red": (245, 111, 108),
                }[state["stage"]]
                draw.ellipse((x + 1720, 1398, x + 1752, 1430), fill=light_color)
                commitment = f"Committed green: {state['green_total_s']:g} s"
                if state["countdown_s"] is not None:
                    commitment += f"   |   Green tail: {state['countdown_s']:.1f} s"
                draw.text((x, 1530), commitment, font=fonts[32], fill=(190, 195, 200))
                m = state["metrics"]
                journey = f"{m['mean_journey_s']:.2f} s" if m["complete"] else "--"
                for label, value, offset in (
                    ("Mean Journey Time", journey, 0),
                    ("Mean Queue", f"{m['mean_queue_vehicles']:.2f} veh", 620),
                    ("Completed", f"{m['completed']} / {m['vehicles']}", 1240),
                ):
                    draw.text(
                        (x + offset, 1640), label, font=fonts[28], fill=(190, 195, 200)
                    )
                    draw.text((x + offset, 1710), value, font=fonts[56], fill=color)
                if index >= len(timeline):
                    draw.text(
                        (x, 1850),
                        "Journey complete; final frame retained",
                        font=fonts[28],
                        fill=(190, 195, 200),
                    )
                elif not m["complete"]:
                    draw.text(
                        (x, 1850),
                        "Journey mean is finalized after all formal vehicles arrive",
                        font=fonts[28],
                        fill=(190, 195, 200),
                    )
            draw.text(
                (64, 1950),
                full_episode,
                font=fonts[40],
                fill=(89, 218, 159),
            )
            draw.text(
                (64, 2040),
                "Selected simulation scenario  |  Same arrivals, routes, camera conditions and traffic rules",
                font=fonts[32],
                fill=(190, 195, 200),
            )
            encoder.stdin.write(image.tobytes())
            if index == preview_index:
                image.save(output / "comparison-cover.jpg", quality=95)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("Comparison video encoding failed")
    finally:
        for capture in captures:
            capture.release()
        if encoder.poll() is None:
            encoder.terminate()
            encoder.wait()
