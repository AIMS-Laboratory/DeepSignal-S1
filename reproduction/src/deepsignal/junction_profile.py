from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Mapping
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / 'configs/junctions/town10hd-189.json'
PROFILE_ENV = 'DEEPSIGNAL_JUNCTION_PROFILE'
_APPROACHES = ('E', 'W', 'S', 'N')

@dataclass(frozen=True)
class TransitionSpec:
    yellow_s: float
    all_red_s: float = 0.0
    keep_permitted_right: bool = False

@dataclass(frozen=True)
class PhaseSpec:
    key: str
    movements: tuple[tuple[str, str], ...]
    fixed_green_s: float
    transition: TransitionSpec = field(default_factory=lambda : TransitionSpec(3.0, 2.0))
    permitted: tuple[int, ...] = ()
    unlinked: tuple[int, ...] = ()

@dataclass(frozen=True)
class ApproachLaneSpec:
    straight_lanes: tuple[str, ...] = ()
    left_lanes: tuple[str, ...] = ()
    shared_sl_lanes: tuple[str, ...] = ()
    controlled_right: bool = True

def _default_phases() -> tuple[PhaseSpec, ...]:
    transition = TransitionSpec(3.0, 2.0)
    return (PhaseSpec('ew_straight', (('E', 'SR'), ('W', 'SR')), 31.0, transition), PhaseSpec('ew_left', (('E', 'L'), ('W', 'L')), 6.0, transition), PhaseSpec('ns_straight', (('S', 'SR'), ('N', 'SR')), 31.0, transition), PhaseSpec('ns_left', (('S', 'L'), ('N', 'L')), 6.0, transition))
STUB_APPROACH_EDGE_M = 6.0

def observation_edge_chain(profile: 'JunctionProfile', approach: str) -> tuple[str, ...]:
    path = tuple(profile.insertion_paths.get(approach, ()))
    if not path or path[-1] != profile.approach_edges[approach]:
        return (profile.approach_edges[approach],)
    return tuple(reversed(path))

@dataclass(frozen=True)
class JunctionProfile:
    name: str
    map_name: str
    junction_id: int
    tls_id: str
    tls_link_count: int
    approach_edges: dict[str, str]
    upstream_approach_edges: dict[str, str]
    straight_light_odr: dict[str, str]
    left_light_odr: dict[str, str]
    straight_lane: str
    left_lane: str
    default_network: str
    junction_code: str = ''
    approach_labels: tuple[str, ...] = _APPROACHES
    insertion_paths: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    green_range: tuple[int, int] = (6, 60)
    phases: tuple[PhaseSpec, ...] = ()
    approach_lanes: dict[str, ApproachLaneSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        labels = set(self.approach_labels)
        if set(self.approach_edges) != labels:
            raise ValueError(f'路口档案进口边必须覆盖进口标签集 {sorted(labels)}')
        for field_name in ('upstream_approach_edges', 'straight_light_odr', 'left_light_odr'):
            if set(getattr(self, field_name)) != labels:
                raise ValueError(f'档案字段 {field_name} 必须覆盖进口标签集 {sorted(labels)}')
        if not self.insertion_paths:
            object.__setattr__(self, 'insertion_paths', {a: (e,) for (a, e) in self.approach_edges.items()})
        for (approach, path) in self.insertion_paths.items():
            if not path or path[-1] != self.approach_edges[approach]:
                raise ValueError(f'进口 {approach} 插入链必须以进口边结尾: {path}')
        if not self.phases:
            object.__setattr__(self, 'phases', _default_phases())
        if not self.junction_code:
            object.__setattr__(self, 'junction_code', str(self.junction_id))

    @property
    def phase_keys(self) -> tuple[str, ...]:
        return tuple((p.key for p in self.phases))

    @property
    def fixed_greens(self) -> dict[str, float]:
        return {p.key: int(p.fixed_green_s) if float(p.fixed_green_s).is_integer() else p.fixed_green_s for p in self.phases}

    def lanes_for(self, approach: str) -> ApproachLaneSpec:
        spec = self.approach_lanes.get(approach)
        if spec is not None:
            return spec
        return ApproachLaneSpec(straight_lanes=(self.straight_lane,), left_lanes=(self.left_lane,))

def _phase_from_json(raw: dict) -> PhaseSpec:
    return PhaseSpec(key=raw['key'], movements=tuple(((m[0], m[1]) for m in raw.get('movements', ()))), fixed_green_s=float(raw.get('fixed_green_s', 31.0)), transition=TransitionSpec(yellow_s=float(raw.get('transition', {}).get('yellow_s', 3.0)), all_red_s=float(raw.get('transition', {}).get('all_red_s', 2.0)), keep_permitted_right=bool(raw.get('transition', {}).get('keep_permitted_right', False))), permitted=tuple((int(i) for i in raw.get('permitted', ()))), unlinked=tuple((int(i) for i in raw.get('unlinked', ()))))

def load_profile(path: Path | str | None=None) -> JunctionProfile:
    data = json.loads(Path(path or os.environ.get(PROFILE_ENV) or DEFAULT_PROFILE).read_text())
    lanes_raw = data.get('approach_lanes') or {}
    approach_lanes = {approach: ApproachLaneSpec(straight_lanes=tuple(v.get('straight_lanes', ())), left_lanes=tuple(v.get('left_lanes', ())), shared_sl_lanes=tuple(v.get('shared_sl_lanes', ())), controlled_right=bool(v.get('controlled_right', True))) for (approach, v) in lanes_raw.items()}
    return JunctionProfile(name=data['name'], map_name=data['map_name'], junction_id=int(data['junction_id']), tls_id=str(data['tls_id']), tls_link_count=int(data['tls_link_count']), approach_edges=data['approach_edges'], upstream_approach_edges=data['upstream_approach_edges'], straight_light_odr=data['straight_light_odr'], left_light_odr=data['left_light_odr'], straight_lane=str(data['straight_lane']), left_lane=str(data['left_lane']), default_network=data['default_network'], junction_code=str(data.get('junction_code', '')), approach_labels=tuple(data.get('approach_labels', _APPROACHES)), insertion_paths={a: tuple(p) for (a, p) in (data.get('insertion_paths') or {}).items()}, green_range=(int(data.get('green_range', (6, 60))[0]), int(data.get('green_range', (6, 60))[1])), phases=tuple((_phase_from_json(p) for p in data.get('phases', ()))), approach_lanes=approach_lanes)

@lru_cache(maxsize=8)
def _cached_load(path: str) -> JunctionProfile:
    return load_profile(Path(path))

def active_profile() -> JunctionProfile:
    return _cached_load(os.environ.get(PROFILE_ENV) or str(DEFAULT_PROFILE))
