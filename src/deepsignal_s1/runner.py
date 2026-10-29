"""Run genuine closed-loop tests or a CPU-only fixed-timing reference."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections import deque
from contextlib import nullcontext
import json
from pathlib import Path
import time

from .baselines import VisualPressureClient
from .client import ModelClient
from .control import SignalController
from .data import read_json, signal_links, write_json, write_routes
from .metrics import TripMetrics


def run_episode(
    scene,
    plan,
    output,
    *,
    controller="fixed",
    endpoint=None,
    detector_endpoint=None,
    assets=None,
    host="127.0.0.1",
    port=25020,
    cpu=False,
    record=False,
    condition="clean",
    realtime=False,
    deadline=1.0,
):
    import traci

    if controller == "fixed" and condition != "clean":
        raise ValueError("Frozen engineering fixed timing is compared only under clean visual conditions")
    if cpu and controller != "fixed":
        raise ValueError("Camera-based controllers cannot run in CPU-only mode")
    if cpu and record:
        raise ValueError("Recording requires the UE5 scene")
    if scene["id"] != plan["scene"]:
        raise ValueError("The arrival plan belongs to another scene")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plan.json", plan)
    routes = write_routes(plan, output)
    links, width = signal_links(scene)
    signal = SignalController(scene, fixed=controller == "fixed")
    metrics = TripMetrics(plan)
    backend = None
    if controller == "s1":
        backend = ModelClient(endpoint, timeout=max(10, deadline))
    elif controller == "visual-pressure":
        backend = VisualPressureClient(
            detector_endpoint,
            scene,
            read_json(Path(scene["network_path"]).parent / "lane-guides.json"),
        )
    elif controller != "fixed":
        raise ValueError(f"Unknown controller: {controller}")
    if cpu:
        rendering = nullcontext(None)
    else:
        from .scene import CameraScene

        rendering = CameraScene(
            scene,
            assets,
            output,
            host=host,
            port=port,
            record=record,
            condition=condition,
        )
    label = f"s1-{controller}-{time.monotonic_ns()}"
    command = [
        "sumo",
        "--net-file",
        scene["network_path"],
        "--route-files",
        str(routes),
        "--step-length",
        "0.1",
        "--time-to-teleport",
        "-1",
        "--no-step-log",
        "true",
        "--seed",
        str(plan["seed"]),
        "--tripinfo-output",
        str(output / "tripinfo.xml"),
        "--tripinfo-output.write-unfinished",
        "true",
        "--log",
        str(output / "sumo.log"),
    ]
    now = 0.0
    failure = None
    version = None
    decisions = []
    pending = None
    pending_since = None
    buffer = deque(maxlen=80)
    started = time.perf_counter()
    conn = None
    deadline_misses = 0
    simulation_wall_seconds = 0.0
    max_clock_lag_s = 0.0
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        with (
            rendering as view,
            (output / "trace.jsonl").open("w", encoding="utf-8") as trace,
        ):
            traci.start(command, label=label, stdout=None)
            conn = traci.getConnection(label)
            conn.trafficlight.setRedYellowGreenState(scene["tls_id"], "r" * width)
            sim_started = time.perf_counter()
            for tick in range(1, round(scene["horizon_s"] * 10) + 1):
                now = tick / 10
                if realtime:
                    time.sleep(max(0, sim_started + now - time.perf_counter()))
                conn.simulationStep(now)
                if (
                    conn.simulation.getStartingTeleportNumber()
                    or conn.simulation.getCollidingVehiclesNumber()
                ):
                    raise RuntimeError("Simulation contains a collision or teleport")
                active = conn.vehicle.getIDList()
                queued = sum(
                    conn.vehicle.getSpeed(v) < 0.1
                    for v in active
                    if v in metrics.planned
                )
                metrics.update(now, conn.simulation.getArrivedIDList(), queued, 0.1)
                due = signal.advance(now)
                state = signal.state_string(links, width)
                conn.trafficlight.setRedYellowGreenState(scene["tls_id"], state)
                if view:
                    observation_at = signal.observation_time()
                    should_capture = (tick % 2 == 0) if record else (
                        not signal.fixed
                        and (
                            signal.waiting
                            or any(
                                abs(now - (observation_at - dt)) < 0.01
                                for dt in (4, 2, 0)
                            )
                        )
                    )
                    if should_capture:
                        frame = view.capture(conn, plan, state)
                        buffer.append((now, frame))
                if due:
                    forced = signal.interlock(now)
                    if forced:
                        signal.accept(forced)
                        decisions.append(
                            {
                                "time": now,
                                "choice": forced,
                                "source": "signal-interlock",
                            }
                        )
                    else:
                        samples = []
                        for offset in (4, 2, 0):
                            found = next(
                                (
                                    f
                                    for t, f in reversed(buffer)
                                    if abs(t - (now - offset)) < 0.01
                                ),
                                None,
                            )
                            if found is None:
                                raise RuntimeError(
                                    f"Missing camera sample at simulation time {now - offset:.1f}"
                                )
                            samples.append(found)
                        context = signal.context(now)
                        if controller == "visual-pressure":
                            context["signal"]["red_age_s"] = {
                                p: 0 if p == signal.phase else now - ended
                                for p, ended in signal.last_green_end.items()
                            }
                        if not context["legal_actions"]:
                            raise RuntimeError("No legal signal action remains")
                        if controller == "s1":
                            samples = [view.encode_model_input(f) for f in samples]
                        pending_since = now
                        pending = executor.submit(backend.decide, context, samples)
                if pending is not None:
                    if not realtime:
                        result = pending.result()
                    elif pending.done():
                        result = pending.result()
                    elif now - pending_since >= deadline - 1e-7:
                        deadline_misses += 1
                        raise RuntimeError(
                            "The model missed its live decision deadline"
                        )
                    else:
                        result = None
                    if result is not None:
                        if version is not None and version != result["model_version"]:
                            raise RuntimeError(
                                "The serving model changed during an episode"
                            )
                        version = result["model_version"]
                        signal.accept(result["choice"])
                        decisions.append(
                            {
                                "time": pending_since,
                                "received_at": now,
                                "source": controller,
                                **result,
                            }
                        )
                        pending = None
                snapshot = {
                    "time": now,
                    **signal.snapshot(now),
                    "metrics": metrics.report(now),
                }
                trace.write(json.dumps(snapshot) + "\n")
                if view and record and should_capture:
                    view.write_trace(snapshot)
                simulation_wall_seconds = time.perf_counter() - sim_started
                if realtime:
                    max_clock_lag_s = max(
                        max_clock_lag_s, simulation_wall_seconds - now
                    )
                if now >= plan["window"][1] and metrics.report(now)["complete"]:
                    if not record or should_capture:
                        break
            if not metrics.report(now)["complete"]:
                raise RuntimeError(
                    "Not all planned formal vehicles completed their journeys"
                )
    except KeyboardInterrupt:
        failure = "Interrupted by operator"
        raise
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
    finally:
        if conn is not None:
            conn.close()
        executor.shutdown(wait=True, cancel_futures=True)
        elapsed = time.perf_counter() - started
        report = {
            "scene": scene["id"],
            "regime": plan["regime"],
            "seed": plan["seed"],
            "condition": condition,
            "controller": controller,
            "baseline": "engineering-fixed" if controller == "fixed" else None,
            "fixed_green_s": ({p["key"]: p["fixed_green_s"] for p in scene["phases"]}
                              if controller == "fixed" else None),
            "model_version": version,
            "quality": None if cpu else "Epic",
            "engine": "SUMO" if cpu else "UE5",
            "capture_profile": None if cpu else (
                "recording-tile-resolution" if record else "observation-configured-resolution"
            ),
            "recording_fps": 5 if record else None,
            "metrics": metrics.report(now),
            "decisions": len(decisions),
            "failure": failure,
            "simulation_seconds": now,
            "wall_seconds": elapsed,
            "simulation_wall_seconds": simulation_wall_seconds,
            "max_clock_lag_s": max_clock_lag_s,
            "deadline_misses": deadline_misses,
            "realtime_verified": realtime
            and failure is None
            and deadline_misses == 0
            and max_clock_lag_s <= deadline,
            "complete": failure is None and metrics.report(now)["complete"],
        }
        write_json(output / "decisions.json", decisions)
        write_json(output / "report.json", report)
        write_json(
            output / "vehicle-records.json",
            {
                v: {"planned_depart": d, "arrived_at": metrics.arrivals.get(v)}
                for v, d in metrics.planned.items()
            },
        )
    if failure:
        raise RuntimeError(f"{failure}; partial records retained in {output}")
    return report
