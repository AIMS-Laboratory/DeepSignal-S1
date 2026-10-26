from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Mapping, Sequence
from .ue4_junction import APPROACH_EDGES, INSERTION_PATHS
REGIMES = ('balanced', 'asymmetric', 'time_varying', 'surge', 'direction_switch')

@dataclass(frozen=True)
class PlannedVehicle:
    vehicle_id: str
    planned_depart: float
    approach: str
    turn: str
    route_edges: tuple[str, ...]
    cohort: str = 'formal'

@dataclass(frozen=True)
class DemandParams:
    balanced_rate_vph: float
    asymmetric_heavy_vph: float
    asymmetric_light_vph: float
    time_varying_rates_vph: tuple[tuple[float, float], ...]
    turn_split: Mapping[str, float]
    max_speed: float
    surge_base_vph: float = 200.0
    surge_intensity_vph: float = 500.0
    surge_duration_s: float = 30.0
    surge_rate_per_second: float = 1.0 / 90.0
    asymmetric_heavy_approaches: tuple[str, ...] = ('E', 'W')
    time_varying_approaches: tuple[str, ...] = ()

@dataclass(frozen=True)
class PlannedArrivals:
    regime: str
    seed: int
    window: tuple[float, float]
    params_digest: str
    vehicles: tuple[PlannedVehicle, ...]
    time_varying_origin: float | None = None
    demand_case: str = ''

    @classmethod
    def load(cls, path: Path) -> 'PlannedArrivals':
        raw = json.loads(path.read_text(encoding='utf-8'))
        try:
            vehicles = tuple((PlannedVehicle(**{**v, 'route_edges': tuple(v['route_edges'])}) for v in raw['vehicles']))
        except (TypeError, KeyError) as error:
            raise ValueError(f'计划名单结构损坏: {path} ({error})') from error
        plan = cls(regime=raw['regime'], seed=raw['seed'], window=tuple(raw['window']), params_digest=raw['params_digest'], vehicles=vehicles, time_varying_origin=raw.get('time_varying_origin'), demand_case=raw.get('demand_case', ''))
        return plan

    def with_cohorts(self, formal_start: float) -> 'PlannedArrivals':
        marked = tuple((PlannedVehicle(**{**v.__dict__, 'cohort': 'warmup' if v.planned_depart < formal_start else 'formal'}) for v in self.vehicles))
        return PlannedArrivals(regime=self.regime, seed=self.seed, window=self.window, params_digest=self.params_digest, vehicles=marked, time_varying_origin=self.time_varying_origin, demand_case=self.demand_case)

def _surge_segments(bursts: list[tuple[float, float]], start: float, end: float, base_vph: float, intensity_vph: float) -> list[tuple[float, float, float]]:
    breakpoints = sorted({round(t, 6) for burst in bursts for t in burst if start < t < end})
    edges = [start, *breakpoints, end]
    segments: list[tuple[float, float, float]] = []
    for (seg_start, seg_end) in zip(edges, edges[1:]):
        if seg_end <= seg_start:
            continue
        overlap = sum((1 for (b_start, b_end) in bursts if b_start <= seg_start and b_end > seg_start))
        segments.append((seg_start, seg_end, base_vph + overlap * intensity_vph))
    return segments

def _rate_segments(regime: str, params: DemandParams, window: tuple[float, float], time_varying_origin: float | None=None, seed: int | None=None) -> dict[str, list[tuple[float, float, float]]]:
    (start, end) = window
    if regime == 'balanced':
        return {a: [(start, end, params.balanced_rate_vph)] for a in APPROACH_EDGES}
    if regime == 'asymmetric':
        heavy = params.asymmetric_heavy_approaches
        return {a: [(start, end, params.asymmetric_heavy_vph if a in heavy else params.asymmetric_light_vph)] for a in APPROACH_EDGES}
    if regime == 'direction_switch':
        middle = (start + end) / 2
        segments: dict[str, list[tuple[float, float, float]]] = {}
        for a in APPROACH_EDGES:
            heavy_first = a in 'EW'
            (heavy, light) = (params.asymmetric_heavy_vph, params.asymmetric_light_vph)
            segments[a] = [(start, middle, heavy if heavy_first else light), (middle, end, light if heavy_first else heavy)]
        return segments
    if regime == 'surge':
        if seed is None:
            raise ValueError('激增制式需要名单种子驱动迸发抽样')
        segments: dict[str, list[tuple[float, float, float]]] = {}
        for (index, approach) in enumerate(sorted(APPROACH_EDGES)):
            rng = random.Random(seed * 7919 + index)
            bursts: list[tuple[float, float]] = []
            clock = start
            while True:
                clock += rng.expovariate(params.surge_rate_per_second)
                if clock >= end:
                    break
                bursts.append((clock, min(clock + params.surge_duration_s, end)))
            segments[approach] = _surge_segments(bursts, start, end, params.surge_base_vph, params.surge_intensity_vph)
        return segments
    if regime == 'time_varying':
        origin = start if time_varying_origin is None else time_varying_origin
        if not start - 1e-09 <= origin < end - 1e-09:
            raise ValueError(f'时变分段原点 {time_varying_origin} 必须落在窗口 [{start}, {end}) 内')
        segments_all: list[tuple[float, float, float]] = []
        changes = sorted(params.time_varying_rates_vph)
        if not changes or changes[0][0] > 0:
            raise ValueError('时变体制的速率分段必须覆盖分段原点')
        if origin > start + 1e-09:
            segments_all.append((start, origin, changes[0][1]))
        for (index, (offset, rate)) in enumerate(changes):
            seg_start = origin + offset
            seg_end = origin + changes[index + 1][0] if index + 1 < len(changes) else end
            if seg_start < end:
                segments_all.append((seg_start, min(seg_end, end), rate))
        if params.time_varying_approaches:
            flat = [(start, end, changes[0][1])]
            return {a: list(segments_all) if a in params.time_varying_approaches else flat for a in APPROACH_EDGES}
        return {a: list(segments_all) for a in APPROACH_EDGES}
    raise ValueError(f'未知需求体制 {regime}，可选 {REGIMES}')

def build_regime_plan(regime: str, *, params: DemandParams, turns: Mapping[str, Mapping[str, tuple[str, str, str]]], window_start: float, window_end: float, seed: int, cohort: str='formal', time_varying_origin: float | None=None, demand_case: str='') -> PlannedArrivals:
    if regime not in REGIMES:
        raise ValueError(f'未知需求体制 {regime}，可选 {REGIMES}')
    if window_end <= window_start:
        raise ValueError('窗口结束必须晚于开始')
    rng = random.Random(seed)
    vehicles: list[PlannedVehicle] = []
    counters: dict[tuple[str, str], int] = {}
    for approach in APPROACH_EDGES:
        turns_by_dir = turns[approach]
        segments = _rate_segments(regime, params, (window_start, window_end), time_varying_origin, seed)[approach]
        for (seg_start, seg_end, rate) in segments:
            clock = seg_start
            while True:
                clock += rng.expovariate(rate / 3600.0)
                if clock >= seg_end:
                    break
                turn = rng.choices(list(turns_by_dir), weights=[params.turn_split.get(d, params.turn_split['s']) for d in turns_by_dir], k=1)[0]
                key = (approach, turn)
                counters[key] = counters.get(key, 0) + 1
                exit_edge = turns_by_dir[turn][0]
                vehicles.append(PlannedVehicle(vehicle_id=f'{approach}-{turn}-{counters[key]:03d}', planned_depart=round(clock, 2), approach=approach, turn=turn, route_edges=(*INSERTION_PATHS[approach], exit_edge), cohort=cohort))
    vehicles.sort(key=lambda v: (v.planned_depart, v.vehicle_id))
    return PlannedArrivals(regime=regime, seed=seed, window=(window_start, window_end), params_digest='', vehicles=tuple(vehicles), demand_case=demand_case, time_varying_origin=time_varying_origin if regime == 'time_varying' else None)
