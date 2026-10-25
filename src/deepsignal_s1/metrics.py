"""Vehicle-level accounting, including waiting outside the simulation network."""


class TripMetrics:
    def __init__(self, plan):
        self.planned = {
            v["vehicle_id"]: v["planned_depart"]
            for v in plan["vehicles"]
            if v["cohort"] == "formal"
        }
        self.arrivals = {}
        self.queue_vehicle_seconds = 0.0
        self.observed_seconds = 0.0
        self.start = plan["window"][0]

    def update(self, now, arrived, queued, step):
        for vehicle in arrived:
            if vehicle in self.planned:
                self.arrivals[vehicle] = now
        if now >= self.start:
            self.queue_vehicle_seconds += queued * step
            self.observed_seconds += step

    def report(self, now):
        n = len(self.planned)
        complete = len(self.arrivals) == n
        bounded = sum(
            self.arrivals.get(v, now) - t for v, t in self.planned.items() if t <= now
        )
        return {
            "vehicles": n,
            "completed": len(self.arrivals),
            "unfinished": n - len(self.arrivals),
            "complete": complete,
            "mean_journey_s": sum(self.arrivals[v] - t for v, t in self.planned.items())
            / n
            if complete
            else None,
            "accumulated_journey_s": bounded,
            "mean_queue_vehicles": self.queue_vehicle_seconds / self.observed_seconds
            if self.observed_seconds
            else 0.0,
        }
