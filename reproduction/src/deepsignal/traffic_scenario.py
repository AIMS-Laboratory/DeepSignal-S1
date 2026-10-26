import xml.etree.ElementTree as ET
from .demand_plan import DemandParams, build_regime_plan
from .junction_profile import active_profile
from .ue4_junction import APPROACH_EDGES, TARGET_TLS_ID

def vehicle_turns(net_file):
    profile = active_profile()
    root = ET.parse(net_file).getroot()
    lane_to_group = {}
    for approach in profile.approach_labels:
        spec = profile.lanes_for(approach)
        for lane in (*spec.straight_lanes, *spec.shared_sl_lanes):
            lane_to_group[approach, lane] = 'SR'
        for lane in spec.left_lanes:
            lane_to_group[approach, lane] = 'L'
    phase_of = {}
    for phase in profile.phases:
        for (approach, group) in phase.movements:
            phase_of.setdefault((approach, group), phase.key)
    turns = {}
    for c in root.findall(f"connection[@tl='{TARGET_TLS_ID}']"):
        approach = next((a for (a, e) in APPROACH_EDGES.items() if e == c.get('from')), None)
        group = lane_to_group.get((approach, c.get('fromLane')))
        if approach is None or group is None:
            continue
        turn = c.attrib['dir']
        served = phase_of.get((approach, group))
        if served is None:
            raise ValueError(f'{approach} 的 {group} 组不在任何档案相位中')
        turns.setdefault(approach, {})[turn] = (c.attrib['to'], c.attrib['fromLane'], served)
    for (approach, moves) in turns.items():
        if not {'s', 'l'} & set(moves):
            raise ValueError(f'{approach}: 无直行/左转路线')
    if set(turns) != set(profile.approach_labels):
        missing = set(profile.approach_labels) - set(turns)
        raise ValueError(f'路线未覆盖全部进口: 缺 {missing}')
    return turns

def base_demand_params(duration: float) -> DemandParams:
    return DemandParams(360, 600, 120, ((0, 200), (duration / 3, 700), (duration * 2 / 3, 200)), {'s': 0.7, 'r': 0.15, 'l': 0.15}, 8.0)

def build_plan(net, regime, seed, duration, *, params: DemandParams | None=None, demand_case: str=''):
    demand = params if params is not None else base_demand_params(duration)
    return build_regime_plan(regime, params=demand, turns=vehicle_turns(net), window_start=0, window_end=98 + duration, seed=seed, time_varying_origin=98 if regime == 'time_varying' else None, demand_case=demand_case).with_cohorts(98)

def write_routes(net, output, vehicles):
    turns = vehicle_turns(net)
    root = ET.Element('routes')
    ET.SubElement(root, 'vType', id='probe', vClass='passenger', length='4.5', maxSpeed='8', sigma='0')
    for v in sorted(vehicles, key=lambda x: (x.planned_depart, x.vehicle_id)):
        element = ET.SubElement(root, 'vehicle', id=v.vehicle_id, type='probe', depart=f'{v.planned_depart:.2f}', departLane=turns[v.approach][v.turn][1], departPos='0', departSpeed='0')
        ET.SubElement(element, 'route', edges=' '.join(v.route_edges))
    path = output / 'routes.rou.xml'
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    return path
