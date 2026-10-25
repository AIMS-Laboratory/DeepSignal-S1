"""Portable scenario inputs and deterministic arrival plans."""

from __future__ import annotations

import json
import random
import xml.etree.ElementTree as ET
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_scene(path):
    path = Path(path).resolve()
    scene = read_json(path)
    scene["network_path"] = str((path.parent / scene["network"]).resolve())
    return scene


def build_plan(scene, regime, seed, duration=300.0):
    if regime not in ("east-west", "north-south", "time-varying"):
        raise ValueError(f"Unknown traffic regime: {regime}")
    if duration <= 0:
        raise ValueError("Duration must be positive")
    rng = random.Random(seed)
    warmup = 98.0
    end = warmup + duration
    vehicles = []
    rates = scene["demand"]
    for approach, turns in sorted(scene["routes"].items()):
        t = 0.0
        index = 0
        while t < end:
            if regime == "time-varying":
                cuts = [
                    0.0,
                    warmup,
                    warmup + duration / 3,
                    warmup + duration * 2 / 3,
                    end,
                ]
                segment = next(i for i in range(4) if cuts[i] <= t < cuts[i + 1])
                rate = [
                    rates["light_vph"],
                    rates["light_vph"],
                    rates["heavy_vph"],
                    rates["light_vph"],
                ][segment]
                boundary = cuts[segment + 1]
            else:
                heavy = approach in (
                    ("E", "W") if regime == "east-west" else ("N", "S")
                )
                rate = rates["heavy_vph"] if heavy else rates["light_vph"]
                boundary = end
            if rate <= 0:
                t = boundary
                continue
            arrival = t + rng.expovariate(rate / 3600.0)
            if arrival >= boundary:
                t = boundary
                continue
            t = arrival
            weights = [rates["turn_split"].get(turn, 0.0) for turn in turns]
            turn = rng.choices(list(turns), weights=weights, k=1)[0]
            index += 1
            vehicles.append(
                {
                    "vehicle_id": f"{approach}-{turn}-{index:04d}",
                    "planned_depart": round(t, 2),
                    "approach": approach,
                    "turn": turn,
                    "route_edges": turns[turn]["edges"],
                    "depart_lane": turns[turn]["depart_lane"],
                    "cohort": "formal" if t >= warmup else "warmup",
                }
            )
    vehicles.sort(key=lambda v: (v["planned_depart"], v["vehicle_id"]))
    if not any(v["cohort"] == "formal" for v in vehicles):
        raise ValueError("The arrival plan contains no formal vehicles")
    return {
        "scene": scene["id"],
        "regime": regime,
        "seed": seed,
        "window": [warmup, end],
        "vehicles": vehicles,
    }


def write_routes(plan, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    root = ET.Element("routes")
    ET.SubElement(
        root,
        "vType",
        id="passenger",
        vClass="passenger",
        length="4.5",
        maxSpeed="8",
        sigma="0",
    )
    for vehicle in plan["vehicles"]:
        element = ET.SubElement(
            root,
            "vehicle",
            id=vehicle["vehicle_id"],
            type="passenger",
            depart=f"{vehicle['planned_depart']:.2f}",
            departLane=str(vehicle["depart_lane"]),
            departPos="0",
            departSpeed="0",
        )
        ET.SubElement(element, "route", edges=" ".join(vehicle["route_edges"]))
    path = directory / "routes.rou.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def signal_links(scene):
    root = ET.parse(scene["network_path"]).getroot()
    tls = scene["tls_id"]
    logic = next(t for t in root.findall("tlLogic") if t.get("id") == tls)
    width = len(logic.find("phase").get("state"))
    links = {p["key"]: [] for p in scene["phases"]}
    for connection in root.findall("connection"):
        if connection.get("tl") != tls:
            continue
        approach = next(
            (
                a
                for a, edge in scene["approach_edges"].items()
                if edge == connection.get("from")
            ),
            None,
        )
        kind = "L" if connection.get("dir") == "l" else "SR"
        for phase in scene["phases"]:
            if [approach, kind] in phase["movements"]:
                links[phase["key"]].append(int(connection.get("linkIndex")))
    if any(not value for value in links.values()):
        raise ValueError("A configured signal phase has no controlled movements")
    return links, width
