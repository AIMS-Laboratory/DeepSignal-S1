"""Record and validate the five-second green tail used by Town controllers."""


PROTOCOL = "green-tail5-v1"


class SignalTrace:
    def __init__(self):
        self.events = []
        self.switches = []

    def stage(self, t, phase, kind):
        self.events.append({"t": round(t, 3), "phase": phase, "stage": kind})

    def switch(self, t, phase, target, yellow=3.0, all_red=2.0):
        self.switches.append({
            "t": round(t, 3),
            "phase": phase,
            "target": target,
            "yellow_at": round(t + 5.0, 3),
            "all_red_at": round(t + 5.0 + yellow, 3),
            "green_at": round(t + 5.0 + yellow + all_red, 3),
        })

    def metadata(self, end_time):
        errors = []
        for switch in self.switches:
            expected_events = (
                ("yellow_at", switch["phase"], "y"),
                ("all_red_at", "all_red", "r"),
                ("green_at", switch["target"], "G"),
            )
            for key, phase, stage in expected_events:
                expected = switch[key]
                if expected > end_time + 0.01:
                    continue
                if not any(
                    event["phase"] == phase
                    and event["stage"] == stage
                    and abs(event["t"] - expected) <= 0.11
                    for event in self.events
                ):
                    errors.append({"switch_t": switch["t"], "missing_stage": stage,
                                   "expected_t": expected})
        return {"protocol": PROTOCOL, "end_time": round(end_time, 3),
                "switches": self.switches, "events": self.events, "errors": errors}
