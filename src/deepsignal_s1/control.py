"""Signal execution rules shared by the tested controllers."""

from __future__ import annotations


class SignalController:
    def __init__(self, scene, *, fixed=False):
        self.scene = scene
        self.phases = {p["key"]: p for p in scene["phases"]}
        self.order = list(self.phases)
        self.fixed = fixed
        self.phase = self.order[0]
        self.stage = "red"
        self.green_start = 0.0
        self.green_total = 0.0
        self.last_green_end = {p: 0.0 for p in self.order}
        self.next_time = 0.2
        self.next_kind = "green"
        self.target = self.phase
        self.waiting = False
        self.decision_at = None
        self.last_choice = None
        self.tail_end = None

    def _open(self, now, target):
        initial = self.green_total == 0
        self.phase = target
        self.stage = "green"
        self.green_start = now
        self.green_total = (
            self.phases[target]["fixed_green_s"]
            if self.fixed
            else max(self.scene["green_min_s"], 9 if initial else 0)
        )
        self.tail_end = None
        self.next_time = now + self.green_total - (0 if self.fixed else 5)
        self.next_kind = "yellow" if self.fixed else "decide"
        self.target = self.order[(self.order.index(target) + 1) % len(self.order)]

    def observation_time(self):
        """Predict the next observation endpoint, including phase transitions."""
        if self.fixed:
            return None
        if self.waiting:
            return self.decision_at
        if self.next_kind == "decide":
            return self.next_time
        initial_green = max(self.scene["green_min_s"], 9 if self.green_total == 0 else 0)
        at = self.next_time
        if self.next_kind == "yellow":
            at += self.phases[self.phase]["yellow_s"]
        if self.next_kind in ("yellow", "red"):
            at += self.phases[self.target]["all_red_s"]
        return at + initial_green - 5

    def advance(self, now):
        if self.waiting or now + 1e-7 < self.next_time:
            return False
        at, kind = self.next_time, self.next_kind
        if kind == "green":
            self._open(at, self.target)
        elif kind == "decide":
            self.waiting = True
            self.decision_at = at
            return True
        elif kind == "yellow":
            self.last_green_end[self.phase] = at
            self.stage = "yellow"
            self.next_time = at + self.phases[self.phase]["yellow_s"]
            self.next_kind = "red"
        elif kind == "red":
            self.stage = "red"
            self.next_time = at + self.phases[self.target]["all_red_s"]
            self.next_kind = "green"
        return False

    def legal_actions(self, now):
        if not self.waiting:
            raise ValueError("No decision is currently due")
        red = {
            p: (0 if p == self.phase else now - self.last_green_end[p])
            for p in self.order
        }
        switches = []
        limit = self.scene["max_red_s"] + self.green_total
        for target in self.order:
            if target == self.phase:
                continue
            phase = self.phases[target]
            if (
                red[target]
                + 5
                + phase["yellow_s"]
                + phase["all_red_s"]
                + self.scene["green_min_s"]
                > limit
            ):
                continue
            rest = [p for p in self.order if p not in (target, self.phase)]
            feasible = not rest
            for first in rest:
                c1 = (
                    5
                    + self.phases[self.phase]["yellow_s"]
                    + self.phases[self.phase]["all_red_s"]
                    + self.scene["green_min_s"]
                )
                c2 = (
                    c1
                    + 5
                    + self.phases[first]["yellow_s"]
                    + self.phases[first]["all_red_s"]
                    + self.scene["green_min_s"]
                )
                if red[first] + c1 <= limit and all(
                    red[p] + c2 <= limit for p in rest if p != first
                ):
                    feasible = True
            if feasible:
                switches.append(target)
        actions = (
            ["extend_5s"]
            if self.green_total < self.scene["green_max_s"] and switches
            else []
        )
        return actions + [f"switch_to_{p}" for p in switches]

    def interlock(self, now):
        candidates = [
            a.removeprefix("switch_to_")
            for a in self.legal_actions(now)
            if a.startswith("switch_to_")
        ]
        for target in sorted(candidates, key=lambda p: self.last_green_end[p]):
            phase = self.phases[target]
            red = now - self.last_green_end[target]
            if (
                red
                + 50
                + phase["yellow_s"]
                + phase["all_red_s"]
                + self.scene["green_min_s"]
                > self.scene["max_red_s"] + self.green_total
            ):
                return f"switch_to_{target}"
        return None

    def context(self, now):
        return {
            "intersection": {
                "id": self.scene["id"],
                "approaches": list(self.scene["approach_edges"]),
                "phases": list(self.phases.values()),
            },
            "signal": {
                "current_phase": self.phase,
                "green_elapsed_s": round(now - self.green_start, 1),
                "committed_total_green_s": self.green_total,
            },
            "legal_actions": self.legal_actions(now),
        }

    def accept(self, choice):
        if choice not in self.legal_actions(self.decision_at):
            raise ValueError(f"Invalid controller action: {choice}")
        self.last_choice = choice
        self.waiting = False
        if choice == "extend_5s":
            self.green_total += min(5, self.scene["green_max_s"] - self.green_total)
            self.next_time = self.green_start + self.green_total - 5
            self.next_kind = "decide"
        else:
            self.target = choice.removeprefix("switch_to_")
            self.tail_end = self.decision_at + 5
            self.next_time = self.tail_end
            self.next_kind = "yellow"

    def state_string(self, links, width):
        state = ["r"] * width
        if self.stage != "red":
            for index in links[self.phase]:
                state[index] = "G" if self.stage == "green" else "y"
        return "".join(state)

    def snapshot(self, now):
        return {
            "phase": self.phase,
            "stage": self.stage,
            "green_total_s": self.green_total,
            "countdown_s": max(0, self.tail_end - now)
            if self.tail_end and self.stage == "green"
            else None,
            "last_action": self.last_choice,
        }
