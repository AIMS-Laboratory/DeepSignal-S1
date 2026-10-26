from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
EPS = 1e-09

class Action(str, Enum):
    EXTEND = 'EXTEND'
    END = 'END'

class Stage(str, Enum):
    INITIAL_RED = 'initial_red'
    GREEN = 'green'
    COUNTDOWN = 'countdown'
    YELLOW = 'yellow'
    ALL_RED = 'all_red'

@dataclass(frozen=True)
class GreenBounds:
    min_green: float
    max_green: float

    def validate(self) -> None:
        if self.max_green < self.min_green:
            raise ValueError(f'最大绿 {self.max_green} 小于最小绿 {self.min_green}')

@dataclass
class LoopConfig:
    step: float
    observation_window: float
    reservation: float
    extension_step: float
    countdown: float
    yellow: float
    all_red: float
    min_green: float
    max_green: float
    per_phase_bounds: Mapping[str, GreenBounds] = field(default_factory=dict)
    fixed_green_by_phase: Mapping[str, float] = field(default_factory=dict)
    post_handover_green_by_phase: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.step <= 0:
            raise ValueError('仿真步长必须为正')
        if self.observation_window <= 0:
            raise ValueError('观察窗长度必须为正')
        if self.reservation <= 0:
            raise ValueError('决策预留时间必须为正')
        if self.extension_step <= 0:
            raise ValueError(f'延长步长必须为正，得到 {self.extension_step}')
        if self.countdown <= 0:
            raise ValueError('末端倒计时时长必须为正')
        if self.yellow <= 0 or self.all_red <= 0:
            raise ValueError('黄灯与全红时长必须为正')
        default = GreenBounds(self.min_green, self.max_green)
        default.validate()
        if self.min_green < self.countdown:
            raise ValueError(f'最小绿 {self.min_green} 不足以包含 {self.countdown} 秒倒计时')
        for (phase, bounds) in self.per_phase_bounds.items():
            bounds.validate()
            if bounds.min_green < self.countdown:
                raise ValueError(f'{phase} 最小绿 {bounds.min_green} 不足以包含倒计时')
        for (phase, green) in self.fixed_green_by_phase.items():
            if green < self.countdown:
                raise ValueError(f'{phase} 固定绿灯 {green} 不足以包含倒计时')
        for (phase, green) in self.post_handover_green_by_phase.items():
            if green < self.countdown:
                raise ValueError(f'{phase} 交接后固定绿灯 {green} 不足以包含倒计时')

    def bounds_for(self, phase: str) -> GreenBounds:
        return self.per_phase_bounds.get(phase, GreenBounds(self.min_green, self.max_green))

@dataclass(frozen=True)
class FinalAnswer:
    action: Action | None
    raw_output: str
    complete: bool
    wall_seconds: float

@dataclass(frozen=True)
class DecisionRequest:
    request_id: str
    phase: str
    issued_at: float
    window_start: float
    window_end: float
    state_time: float
    deadline: float
    legal_actions: tuple[Action, ...]
    frame_times: tuple[float, ...]
    green_elapsed_at_state: float
    red_elapsed: dict[str, float]
    signal_history: tuple[tuple[float, str], ...]

@dataclass(frozen=True)
class DecisionRecord:
    request: DecisionRequest
    outcome_kind: str
    action: Action | None
    executed_action: Action | None
    executed_at: float
    raw_output: str | None
    wall_seconds: float | None
    green_total_seconds: float | None

@dataclass(frozen=True)
class IssueRequest:
    request: DecisionRequest

@dataclass(frozen=True)
class Outcome:
    time: float
    record: DecisionRecord

@dataclass(frozen=True)
class SignalUpdate:
    time: float
    stage: str
    group: str
    color: str
    state: str
    countdown_remaining: float | None

@dataclass(frozen=True)
class PhaseChange:
    time: float
    from_phase: str | None
    to_phase: str

class SignalController:

    def __init__(self, config: LoopConfig, phases: tuple[str, ...], groups: Mapping[str, tuple[int, ...]], link_count: int, initial_red: float, handover_at: float | None=None) -> None:
        if len(phases) < 2:
            raise ValueError('相位序列至少两个相位')
        missing = [phase for phase in phases if phase not in groups]
        if missing:
            raise ValueError(f'放行组映射缺少相位: {missing}')
        unknown = set(groups) - set(phases)
        if unknown:
            raise ValueError(f'放行组映射含未知相位: {sorted(unknown)}')
        claimed = [i for indices in groups.values() for i in indices]
        if len(claimed) != len(set(claimed)):
            raise ValueError('不同放行组不能重复认领同一连接索引')
        if max(claimed, default=-1) >= link_count:
            raise ValueError('连接索引超出状态字符串宽度')
        if handover_at is not None:
            if handover_at < initial_red - EPS:
                raise ValueError(f'交接边界 {handover_at} 不能早于首个绿灯起点 {initial_red}')
            without_fixed = [phase for phase in phases if phase not in config.fixed_green_by_phase]
            if without_fixed:
                raise ValueError(f'共同预热需要全部相位的固定配时，缺少: {without_fixed}')
        if config.post_handover_green_by_phase:
            if handover_at is None:
                raise ValueError('交接后固定表需要交接边界（共同预热交接）')
            missing_post = [phase for phase in phases if phase not in config.post_handover_green_by_phase]
            if missing_post:
                raise ValueError(f'交接后固定表必须覆盖全部相位，缺少: {missing_post}')
        self.config = config
        self.phases = phases
        self.groups = {phase: tuple(groups[phase]) for phase in phases}
        self.link_count = link_count
        self.initial_red = initial_red
        self._handover_at = handover_at
        self.last_tick = 0.0
        self._stage = Stage.INITIAL_RED
        self._stage_start = 0.0
        self._phase_index = 0
        self._green_start = 0.0
        self._red_since = {phase: 0.0 for phase in phases}
        self._pending: DecisionRequest | None = None
        self._early_result: FinalAnswer | None = None
        self._next_issue_time: float | None = None
        self._request_counter = 0
        self._records: list[DecisionRecord] = []
        self._settled_ids: set[str] = set()
        self._signal_log: list[tuple[float, str]] = [(0.0, 'initial_red')]
        self._fixed_boundary: float | None = None

    @property
    def pending(self) -> DecisionRequest | None:
        return self._pending

    @property
    def records(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._records)

    @property
    def handover_at(self) -> float | None:
        return self._handover_at

    @property
    def current_phase(self) -> str:
        return self.phases[self._phase_index]

    def _phase(self, offset: int=0) -> str:
        return self.phases[(self._phase_index + offset) % len(self.phases)]

    def _bounds(self, phase: str) -> GreenBounds:
        return self.config.bounds_for(phase)

    def _boundary(self, phase: str, green_start: float) -> float:
        return green_start + self._bounds(phase).max_green - self.config.countdown

    def _state_str(self, group: str, color: str) -> str:
        state = ['r'] * self.link_count
        if color != 'r':
            for index in self.groups[group]:
                state[index] = color
        return ''.join(state)

    def _stage_name(self) -> str:
        phase = self.current_phase
        if self._stage is Stage.INITIAL_RED:
            return 'initial_red'
        if self._stage is Stage.GREEN:
            return phase
        if self._stage is Stage.COUNTDOWN:
            return f'{phase}_countdown'
        if self._stage is Stage.YELLOW:
            return f'{phase}_yellow'
        return 'all_red'

    def _log_signal(self, t: float, label: str) -> None:
        if not self._signal_log or self._signal_log[-1][1] != label:
            self._signal_log.append((t, label))

    def _signal_history_since(self, window_start: float) -> tuple[tuple[float, str], ...]:
        return tuple(((time, label) for (time, label) in self._signal_log if time >= window_start - EPS))

    def _settle(self, t: float, status: FinalAnswer | None) -> Outcome:
        assert self._pending is not None
        request = self._pending
        result = self._early_result if self._early_result is not None else status
        if result is None or not result.complete:
            (kind, action, executed) = ('timeout', None, Action.EXTEND)
            (raw, wall) = (result.raw_output if result else None, None)
        elif result.action not in request.legal_actions:
            (kind, action, executed) = ('invalid', None, Action.EXTEND)
            (raw, wall) = (result.raw_output, result.wall_seconds)
        else:
            kind = 'model'
            (action, executed) = (result.action, result.action)
            (raw, wall) = (result.raw_output, result.wall_seconds)
        executed_at = request.deadline
        green_total: float | None = None
        self._pending = None
        self._early_result = None
        if executed is Action.END:
            green_total = executed_at - self._green_start + self.config.countdown
            minimum = self._bounds(request.phase).min_green
            if green_total < minimum - EPS:
                raise RuntimeError(f'结束动作使绿灯总长 {green_total} 低于最小绿 {minimum}')
            self._enter_countdown(executed_at, forced=False)
        else:
            next_deadline = max(executed_at + self.config.extension_step, t + self.config.reservation)
            boundary = self._boundary(request.phase, self._green_start)
            if next_deadline < boundary - EPS:
                self._next_issue_time = max(next_deadline - self.config.reservation, t)
            else:
                self._next_issue_time = None
        record = DecisionRecord(request=request, outcome_kind=kind, action=action, executed_action=executed, executed_at=executed_at, raw_output=raw, wall_seconds=wall, green_total_seconds=green_total)
        self._records.append(record)
        self._settled_ids.add(request.request_id)
        return Outcome(time=executed_at, record=record)

    def _enter_countdown(self, t: float, forced: bool) -> Outcome | None:
        if self._pending is not None:
            raise RuntimeError('存在未决请求时不能启动倒计时')
        phase = self.current_phase
        boundary = self._boundary(phase, self._green_start)
        if t > boundary + self.config.countdown + EPS:
            raise RuntimeError('倒计时启动越过最大绿边界')
        self._stage = Stage.COUNTDOWN
        self._stage_start = t
        self._log_signal(t, f'{phase}_countdown')
        if forced:
            request = DecisionRequest(request_id=f'forced-{self._request_counter:04d}', phase=phase, issued_at=t, window_start=t - self.config.observation_window, window_end=t, state_time=t, deadline=t, legal_actions=(), frame_times=(), green_elapsed_at_state=t - self._green_start, red_elapsed=dict(self._red_elapsed(t)), signal_history=())
            self._request_counter += 1
            record = DecisionRecord(request=request, outcome_kind='forced', action=None, executed_action=Action.END, executed_at=t, raw_output=None, wall_seconds=None, green_total_seconds=t - self._green_start + self.config.countdown)
            self._records.append(record)
            self._settled_ids.add(request.request_id)
            return Outcome(time=t, record=record)
        return None

    def _begin_green(self, start: float, events: list[Any], *, advance: bool) -> None:
        (self._stage, self._stage_start) = (Stage.GREEN, start)
        if advance:
            self._phase_index = (self._phase_index + 1) % len(self.phases)
        self._green_start = start
        self._log_signal(start, self.current_phase)
        events.append(PhaseChange(time=start, from_phase=None, to_phase=self.current_phase))
        in_warmup = self._handover_at is None or start < self._handover_at - EPS
        if in_warmup:
            fixed = self.config.fixed_green_by_phase.get(self.current_phase)
        elif self.config.post_handover_green_by_phase:
            fixed = self.config.post_handover_green_by_phase.get(self.current_phase)
        else:
            fixed = None
        if fixed is not None:
            self._next_issue_time = None
            self._fixed_boundary = fixed - self.config.countdown
        else:
            self._fixed_boundary = None
            self._next_issue_time = max(start + self._bounds(self.current_phase).min_green - self.config.countdown - self.config.reservation, start)

    def _advance_stage(self, t: float, events: list[Any]) -> None:
        while True:
            if self._stage is Stage.INITIAL_RED:
                end = self._stage_start + self.initial_red
                if t + EPS < end:
                    break
                self._begin_green(end, events, advance=False)
            elif self._stage is Stage.COUNTDOWN:
                end = self._stage_start + self.config.countdown
                if t + EPS < end:
                    break
                (self._stage, self._stage_start) = (Stage.YELLOW, end)
                self._log_signal(end, f'{self.current_phase}_yellow')
            elif self._stage is Stage.YELLOW:
                end = self._stage_start + self.config.yellow
                if t + EPS < end:
                    break
                (self._stage, self._stage_start) = (Stage.ALL_RED, end)
                self._log_signal(end, 'all_red')
                self._red_since[self.current_phase] = end
            elif self._stage is Stage.ALL_RED:
                end = self._stage_start + self.config.all_red
                if t + EPS < end:
                    break
                self._begin_green(end, events, advance=True)
            else:
                break

    def _red_elapsed(self, t: float) -> dict[str, float]:
        return {phase: t - since for (phase, since) in self._red_since.items() if phase != self.current_phase}

    def _try_issue(self, t: float, window: Mapping[str, Any] | None, events: list[Any]) -> None:
        if self._stage is not Stage.GREEN or self._pending is not None:
            return
        if self._fixed_boundary is not None:
            return
        if self._next_issue_time is None or t + EPS < self._next_issue_time:
            return
        if window is None:
            return
        deadline = max(t + self.config.reservation, self._next_issue_time + self.config.reservation)
        boundary = self._boundary(self.current_phase, self._green_start)
        if deadline >= boundary - EPS:
            self._next_issue_time = None
            return
        self._request_counter += 1
        frame_times = tuple((float(v) for v in window['frame_times']))
        history = tuple(((float(time), str(label)) for (time, label) in window['signal_history']))
        request = DecisionRequest(request_id=f'req-{self._request_counter:04d}', phase=self.current_phase, issued_at=t, window_start=t - self.config.observation_window, window_end=t, state_time=t, deadline=deadline, legal_actions=(Action.EXTEND, Action.END), frame_times=frame_times, green_elapsed_at_state=t - self._green_start, red_elapsed=self._red_elapsed(t), signal_history=history)
        self._pending = request
        self._early_result = None
        self._next_issue_time = None
        events.append(IssueRequest(request=request))

    def tick(self, t: float, *, status: FinalAnswer | None, window: Mapping[str, Any] | None) -> tuple[Any, ...]:
        if t <= self.last_tick + EPS:
            raise ValueError(f'tick 时间 {t} 必须严格递增（上一步 {self.last_tick}）')
        self.last_tick = t
        events: list[Any] = []
        if self._pending is not None:
            request = self._pending
            if t + EPS >= request.deadline:
                events.append(self._settle(t, status))
            elif status is not None and status.complete:
                if self._early_result is None:
                    self._early_result = status
            elif status is not None and (not status.complete):
                pass
        self._advance_stage(t, events)
        if self._stage is Stage.GREEN and self._fixed_boundary is not None:
            forced_at = self._green_start + float(self._fixed_boundary)
            if t + EPS >= forced_at and self._pending is None:
                forced_event = self._enter_countdown(forced_at, forced=True)
                if forced_event is not None:
                    events.append(forced_event)
                self._fixed_boundary = None
        elif self._stage is Stage.GREEN:
            boundary = self._boundary(self.current_phase, self._green_start)
            if t + EPS >= boundary and self._pending is None and (self._next_issue_time is None):
                forced_event = self._enter_countdown(boundary, forced=True)
                if forced_event is not None:
                    events.append(forced_event)
        self._try_issue(t, window, events)
        update = self.current_update(t)
        events.append(update)
        return tuple(events)

    def current_update(self, t: float) -> SignalUpdate:
        phase = self.current_phase
        if self._stage is Stage.INITIAL_RED:
            (name, group, color, remaining) = ('initial_red', '', 'r', None)
        elif self._stage is Stage.GREEN:
            (name, group, color, remaining) = (phase, phase, 'G', None)
        elif self._stage is Stage.COUNTDOWN:
            name = f'{phase}_countdown'
            (group, color) = (phase, 'G')
            remaining = self.config.countdown - (t - self._stage_start)
        elif self._stage is Stage.YELLOW:
            (name, group, color, remaining) = (f'{phase}_yellow', phase, 'y', None)
        else:
            (name, group, color, remaining) = ('all_red', '', 'r', None)
        return SignalUpdate(time=t, stage=name, group=group, color=color, state=self._state_str(group, color) if group else 'r' * self.link_count, countdown_remaining=remaining)

    def note_late_final(self, request_id: str, final: FinalAnswer) -> Outcome | None:
        if request_id not in self._settled_ids:
            return None
        request = next((r.request for r in self._records if r.request.request_id == request_id), None)
        if request is None:
            return None
        record = DecisionRecord(request=request, outcome_kind='late', action=None, executed_action=None, executed_at=self.last_tick, raw_output=final.raw_output, wall_seconds=final.wall_seconds, green_total_seconds=None)
        self._records.append(record)
        return Outcome(time=self.last_tick, record=record)
