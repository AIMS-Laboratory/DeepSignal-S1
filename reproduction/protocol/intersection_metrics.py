"""Evaluation-only intersection metrics; never used as controller observations."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET


def trip_metrics(path, planned, horizon):
    eligible = {vehicle: depart for vehicle, depart in planned.items() if depart < horizon}
    records = {node.get("id"): node.attrib for node in ET.parse(path).getroot().findall("tripinfo")
               if node.get("id") in eligible and float(node.get("depart")) >= 0}
    waiting = sum(float(row["waitingTime"]) for row in records.values())
    stops = sum(int(row["waitingCount"]) for row in records.values())
    loss = sum(float(row["timeLoss"]) for row in records.values())
    arrived = sum(0 <= float(row["arrival"]) <= horizon for row in records.values())
    missing = len(eligible) - len(records)
    delay = sum(float(records[vehicle]["depart"]) - depart if vehicle in records
                else horizon - depart for vehicle, depart in eligible.items())
    count = len(eligible)
    return {
        "planned_vehicles": count,
        "inserted_vehicles": len(records),
        "arrived_vehicles": arrived,
        "unfinished_inserted_vehicles": len(records) - arrived,
        "not_inserted_vehicles": missing,
        "sum_observed_stopped_time_s": waiting,
        "sum_observed_stop_count": stops,
        "sum_observed_time_loss_s": loss,
        "mean_stopped_time_s": waiting / count if count and not missing else None,
        "mean_stop_count": stops / count if count and not missing else None,
        "mean_time_loss_s": loss / count if count and not missing else None,
        "mean_insertion_wait_s": delay / count if count else None,
        "all_formal_journeys_complete": arrived == count,
        "waiting_scope": "SUMO waitingTime and waitingCount for formal vehicles through the observed end; "
                         "unfinished journeys are included. Means are unavailable if vehicles never entered.",
    }


class IntersectionMetrics:
    def __init__(self, connection, tls_id, start=98.0, end=518.0):
        self.connection = connection
        self.lanes = tuple(lane for lane in dict.fromkeys(
            connection.trafficlight.getControlledLanes(str(tls_id))) if not lane.startswith(":"))
        self.start, self.end = start, end
        self.last_time = 0.0
        self.observed_seconds = 0.0
        self.queue_vehicle_seconds = {lane: 0.0 for lane in self.lanes}
        self.max_queue_vehicles = 0

    def update(self, now):
        duration = max(0.0, min(now, self.end) - max(self.last_time, self.start))
        self.last_time = now
        if not duration:
            return
        counts = {lane: self.connection.lane.getLastStepHaltingNumber(lane) for lane in self.lanes}
        for lane, value in counts.items():
            self.queue_vehicle_seconds[lane] += value * duration
        self.max_queue_vehicles = max(self.max_queue_vehicles, sum(counts.values()))
        self.observed_seconds += duration

    def write(self, destination, tripinfo, planned, failed=False):
        duration = self.observed_seconds
        value = {
            "tag": Path(destination).name.removesuffix("-metrics.json"),
            "failed": bool(failed),
            "window_s": [self.start, min(self.last_time, self.end)],
            "observed_seconds": duration,
            "fixed_horizon_covered": self.last_time >= self.end - 1e-6,
            "incoming_lanes": list(self.lanes),
            "mean_queue_vehicles": sum(self.queue_vehicle_seconds.values()) / duration if duration else None,
            "max_queue_vehicles": self.max_queue_vehicles,
            "queue_vehicle_seconds": sum(self.queue_vehicle_seconds.values()),
            "mean_queue_vehicles_by_lane": {
                lane: value / duration if duration else None
                for lane, value in self.queue_vehicle_seconds.items()},
            "queue_scope": "All vehicles on unique signal-controlled incoming lanes; time-averaged "
                           "SUMO halting counts (speed < 0.1 m/s). Unit: vehicles, not metres.",
            "evaluation_only": True,
            **trip_metrics(tripinfo, planned, min(self.last_time, self.end)),
        }
        Path(destination).write_text(json.dumps(value, indent=2) + "\n")
        return value
