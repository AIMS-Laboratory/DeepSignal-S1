from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any
import xml.etree.ElementTree as ET
from .junction_profile import active_profile
from .sumo_network import align_target_lane_boundaries, apply_target_stop_offsets
_PROFILE = active_profile()
APPROACH_EDGES = _PROFILE.approach_edges
INSERTION_PATHS = _PROFILE.insertion_paths
TARGET_JUNCTION_ID = _PROFILE.junction_id
TARGET_TLS_ID = _PROFILE.tls_id
CANDIDATE_YELLOW = 3
CANDIDATE_ALL_RED = 2
COUNTDOWN_SECONDS = 5

@dataclass(frozen=True)
class GreenTable:
    major_green: int
    minor_green: int
    yellow: int
    default_all_reds: tuple[int, ...]
    applied_all_red: int

    @property
    def adjustments(self) -> tuple[str, ...]:
        return ('默认程序为单边轮放（lead-lag）结构，运行程序按四个放行组重建；绿灯时长直接采用默认 major/minor 原值', '默认 major 绿由 26+5 秒拆段构成（行人灯变化），聚并计为 31 秒', f"默认全红 {'/'.join((str(v) for v in self.default_all_reds))} 秒不等，统一为共同候选 {self.applied_all_red} 秒")

@dataclass(frozen=True)
class JunctionStage:
    name: str
    duration: int
    state: str
    group: str
    color: str
    indices: tuple[int, ...]
    countdown: bool

def _junction_connections(net_file: Path) -> tuple[ET.Element, list[ET.Element]]:
    root = ET.parse(net_file).getroot()
    connections = root.findall(f"connection[@tl='{TARGET_TLS_ID}']")
    if not connections:
        raise ValueError(f'路网缺少目标信号路口 {TARGET_TLS_ID} 的连接')
    return (root, connections)

def motor_links(net_file: Path) -> tuple[dict[int, ET.Element], list[int]]:
    (_, connections) = _junction_connections(net_file)
    motor: dict[int, ET.Element] = {}
    pedestrian: list[int] = []
    for c in connections:
        index = int(c.attrib['linkIndex'])
        if c.get('from', '').startswith(':'):
            pedestrian.append(index)
        else:
            motor[index] = c
    if set(motor) & set(pedestrian):
        raise ValueError('目标路口的机动车与行人连接索引重叠')
    return (motor, pedestrian)

def movement_groups(net_file: Path) -> dict[str, tuple[int, ...]]:
    (motor, _) = motor_links(net_file)
    profile = active_profile()
    edge_to_label = {edge: label for (label, edge) in APPROACH_EDGES.items()}
    served_by: dict[tuple[str, str], list[str]] = {}
    for phase in profile.phases:
        for movement in phase.movements:
            served_by.setdefault(movement, []).append(phase.key)
    groups: dict[str, list[int]] = {key: [] for key in profile.phase_keys}
    unmatched = []
    for (index, c) in sorted(motor.items()):
        label = edge_to_label.get(str(c.get('from')))
        if label is None:
            raise ValueError(f'连接 {dict(c.attrib)} 不属于档案受控进口')
        group = 'L' if c.get('dir') == 'l' else 'SR'
        keys = served_by.get((label, group))
        if not keys:
            unmatched.append((index, label, group, c.get('dir')))
            continue
        for key in keys:
            groups[key].append(index)
    if unmatched:
        raise ValueError(f'受控连接不属于任何相位服务组: {unmatched}')
    return {key: tuple(sorted(indices)) for (key, indices) in groups.items()}

def default_green_table(net_file: Path) -> GreenTable:
    (motor, _) = motor_links(net_file)
    (_, phases) = _junction_phases(net_file)
    greens: list[tuple[frozenset[int], int]] = []
    yellows: set[int] = set()
    all_reds: dict[int, None] = {}
    for phase in phases:
        state = str(phase.get('state', ''))
        duration = int(round(float(phase.get('duration', '0'))))
        colors = {index: state[index] for index in motor if index < len(state)}
        on = frozenset((i for (i, color) in colors.items() if color in 'Gg'))
        yellow_on = frozenset((i for (i, color) in colors.items() if color == 'y'))
        if yellow_on:
            yellows.add(duration)
        elif on:
            if greens and greens[-1][0] == on:
                (released, total) = greens[-1]
                greens[-1] = (released, total + duration)
            else:
                greens.append((on, duration))
        elif duration:
            all_reds[duration] = None
    if len(greens) != 4 or len({greens[0][1], greens[2][1]}) != 1 or len({greens[1][1], greens[3][1]}) != 1:
        raise ValueError(f'默认绿灯表不是两轴对称的四大放行段: {[duration for (_, duration) in greens]}')
    if len(yellows) != 1:
        raise ValueError(f'默认黄灯时长不统一: {sorted(yellows)}')
    return GreenTable(major_green=greens[0][1], minor_green=greens[1][1], yellow=next(iter(yellows)), default_all_reds=tuple(all_reds), applied_all_red=CANDIDATE_ALL_RED)

def _junction_phases(net_file: Path) -> tuple[ET.Element, list[ET.Element]]:
    root = _junction_connections(net_file)[0]
    for tl in root.findall(f"tlLogic[@id='{TARGET_TLS_ID}']"):
        phases = tl.findall('phase')
        if phases:
            return (tl, phases)
    raise ValueError(f'目标信号路口 {TARGET_TLS_ID} 没有可用信号程序')

def junction_program(net_file: Path, table: GreenTable, initial_red: int) -> tuple[JunctionStage, ...]:
    groups = movement_groups(net_file)
    (motor, pedestrian) = motor_links(net_file)
    order = ('ew_straight', 'ew_left', 'ns_straight', 'ns_left')

    def stage(name: str, duration: int, group: str, color: str, countdown: bool) -> JunctionStage:
        width = max([*motor, *pedestrian]) + 1
        state = ['r'] * width
        if group:
            for index in groups[group]:
                state[index] = color
        return JunctionStage(name=name, duration=duration, state=''.join(state), group=group, color=color if group else 'r', indices=groups.get(group, ()), countdown=countdown)
    stages = [stage('initial_red', initial_red, '', 'r', False)]
    for group in order:
        green = table.major_green if group.endswith('straight') else table.minor_green
        head = green - COUNTDOWN_SECONDS
        if head < 0:
            raise ValueError(f'{group} 绿灯 {green} 秒不足以包含 {COUNTDOWN_SECONDS} 秒倒计时')
        axis = group.removesuffix('_straight').removesuffix('_left')
        kind = 'straight' if group.endswith('straight') else 'left'
        stages.append(stage(f'{axis}_{kind}', head, group, 'G', False))
        stages.append(stage(f'{axis}_{kind}_countdown', COUNTDOWN_SECONDS, group, 'G', True))
        stages.append(stage(f'{axis}_{kind}_yellow', table.yellow, group, 'y', False))
        stages.append(stage('all_red', table.applied_all_red, '', 'r', False))
    return tuple(stages)

def build_junction_network(xodr: str, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    xodr_file = output / 'Town10HD_Opt.xodr'
    raw_file = output / 'imported.net.xml'
    input_file = output / 'left-only-input.net.xml'
    net_file = output / 'junction.net.xml'
    xodr_file.write_text(xodr, encoding='utf-8')
    with (output / 'netconvert.log').open('w') as log:
        subprocess.run(['netconvert', '--opendrive', str(xodr_file), '--output-file', str(raw_file), '--geometry.min-radius.fix', '--geometry.remove', '--opendrive.curve-resolution', '1', '--opendrive.import-all-lanes', '--output.original-names', '--tls.guess', 'true', '--tls.discard-simple', 'false', '--crossings.guess', 'true', '--crossings.guess.speed-threshold', '16.7'], check=True, stdout=log, stderr=subprocess.STDOUT)
        tree = ET.parse(raw_file)
        root = tree.getroot()
        removed = []
        for c in root.findall('connection'):
            if c.get('tl') == TARGET_TLS_ID and c.get('from') in set(APPROACH_EDGES.values()) and (c.get('fromLane') == '4') and (c.get('dir') == 's'):
                removed.append(dict(c.attrib))
                root.remove(c)
        if len(removed) != 4:
            raise ValueError(f'预期四个进口各一条内侧直行连接，实际删除 {len(removed)}: {removed}')
        tree.write(input_file, encoding='utf-8', xml_declaration=True)
        subprocess.run(['netconvert', '--sumo-net-file', str(input_file), '--output-file', str(net_file), '--tls.rebuild'], check=True, stdout=log, stderr=subprocess.STDOUT)
    align_target_lane_boundaries(net_file)
    apply_target_stop_offsets(net_file)
    movement_groups(net_file)
    return net_file

def approach_channels(net_file: Path) -> dict[str, dict[str, tuple[int, ...]]]:
    (motor, _) = motor_links(net_file)
    channels: dict[str, dict[str, list[int]]] = {}
    for (index, c) in sorted(motor.items()):
        approach = next((a for (a, e) in APPROACH_EDGES.items() if e == c.get('from')))
        direction = c.get('dir')
        kind = 'left' if direction == 'l' else 'straight'
        channels.setdefault(approach, {}).setdefault(kind, []).append(index)
    missing = {approach: sorted(kinds) for (approach, kinds) in channels.items() if set(kinds) != {'straight', 'left'}}
    if missing:
        raise ValueError(f'进口缺少直右或左转通道: {missing}')
    if set(channels) != set(APPROACH_EDGES):
        raise ValueError(f'通道没有覆盖全部进口: {sorted(channels)}')
    return {approach: {kind: tuple(sorted(indices)) for (kind, indices) in kinds.items()} for (approach, kinds) in channels.items()}

class JunctionSignalMirror:

    def __init__(self, channels: dict[str, tuple[Any, tuple[int, ...]]]) -> None:
        if not channels:
            raise ValueError('信号通道映射不能为空')
        actors: dict[int, str] = {}
        claimed: set[int] = set()
        for (name, (light, indices)) in channels.items():
            if not indices:
                raise ValueError(f'通道 {name} 没有关联 SUMO 连接')
            for index in indices:
                if index in claimed:
                    raise ValueError(f'连接 {index} 被多个通道重复认领')
                claimed.add(index)
            owner = actors.get(light.id)
            if owner is not None:
                raise ValueError(f'不同通道 {owner} 与 {name} 不能复用同一 CARLA 灯 actor')
            actors[light.id] = name
        self.channels = channels

    def _colors(self, sumo_state: str) -> dict[str, Any]:
        import carla
        colors = {'r': carla.TrafficLightState.Red, 'y': carla.TrafficLightState.Yellow, 'G': carla.TrafficLightState.Green, 'g': carla.TrafficLightState.Green}
        result = {}
        for (name, (_, indices)) in self.channels.items():
            found = {colors[sumo_state[index]] for index in indices}
            if len(found) != 1:
                raise ValueError(f'同一通道 {name} 的 SUMO 连接不能具有不同灯色')
            result[name] = found.pop()
        return result

    def write(self, sumo_state: str) -> None:
        for (name, color) in self._colors(sumo_state).items():
            self.channels[name][0].set_state(color)

    def read_back(self, sumo_state: str) -> dict[str, dict[str, Any]]:
        rows = {}
        for (name, expected) in self._colors(sumo_state).items():
            (light, indices) = self.channels[name]
            actual = light.get_state()
            rows[name] = {'actor_id': light.id, 'sumo_link_indices': indices, 'expected': str(expected), 'actual': str(actual), 'matches': actual == expected}
        if not all((row['matches'] for row in rows.values())):
            raise RuntimeError(f'CARLA 底层灯态与 SUMO 不一致: {rows}')
        return rows

def mount_junction_markings(world: Any, client: Any, session: Any, net_file: Path) -> list[int]:
    import math
    import carla
    import numpy as np
    from PIL import Image, ImageDraw
    from .crosswalks import ROAD_MARKING_MESH
    root = ET.parse(net_file).getroot()
    location = root.find('location')
    assert location is not None
    (offset_x, offset_y) = map(float, location.attrib['netOffset'].split(','))
    tile = 0.15
    left = [(-0.18, -1.8), (0.18, -1.8), (0.18, 1.18), (-0.7, 1.18), (-0.7, 1.65), (-1.4, 1), (-0.7, 0.35), (-0.7, 0.82), (-0.18, 0.82)]
    straight = [(-0.18, -1.8), (0.18, -1.8), (0.18, 1.2), (0.65, 1.2), (0, 2), (-0.65, 1.2), (-0.18, 1.2)]
    right = [(-x, y) for (x, y) in left]
    masks: dict[str, Any] = {}
    for (lane_kind, polygons) in (('4', [left]), ('3', [straight, right])):
        mask = Image.new('1', (21, 29))
        draw = ImageDraw.Draw(mask)
        for polygon in polygons:
            draw.polygon([(round(x / tile) + 10, round(y / tile) + 14) for (x, y) in polygon], fill=1)
        masks[lane_kind] = np.asarray(mask)
    blueprint = world.get_blueprint_library().find('static.prop.mesh')
    blueprint.set_attribute('mesh_path', ROAD_MARKING_MESH)
    blueprint.set_attribute('scale', str(tile))
    blueprint.set_attribute('role_name', 'ue4_junction_marking')
    commands = []
    for edge_id in APPROACH_EDGES.values():
        for (lane_index, mask_array) in masks.items():
            lane = root.find(f"edge[@id='{edge_id}']/lane[@index='{lane_index}']")
            assert lane is not None
            points = [tuple(map(float, p.split(',')[:2])) for p in lane.attrib['shape'].split()]
            (end_x, end_y) = (points[-1][0] - offset_x, offset_y - points[-1][1])
            (dx, dy) = (points[-1][0] - points[-2][0], points[-2][1] - points[-1][1])
            length = math.hypot(dx, dy)
            (forward_x, forward_y) = (dx / length, dy / length)
            (right_x, right_y) = (-forward_y, forward_x)
            for (row, column) in zip(*np.nonzero(mask_array)):
                (lateral, forward) = ((column - 10) * tile, (row - 14) * tile - 6)
                commands.append(carla.command.SpawnActor(blueprint, carla.Transform(carla.Location(x=end_x + forward_x * forward + right_x * lateral, y=end_y + forward_y * forward + right_y * lateral, z=0.025), carla.Rotation(yaw=math.degrees(math.atan2(forward_y, forward_x))))))
    responses = client.apply_batch_sync(commands, False)
    actor_ids = [r.actor_id for r in responses if not r.error]
    errors = [r.error for r in responses if r.error]

    def close() -> None:
        results = client.apply_batch_sync([carla.command.DestroyActor(i) for i in actor_ids], False)
        failures = [r.error for r in results if r.error]
        if failures:
            raise RuntimeError(f'四进口标线清理失败: {failures[0]}')
    session.register_cleanup(close)
    if errors:
        raise RuntimeError(f'四进口标线生成失败: {errors[0]}')
    return actor_ids
