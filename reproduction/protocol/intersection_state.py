import json
from pathlib import Path
ROOT = Path.cwd()
STATE_TASK = 'Adaptive traffic-signal control for one intersection. You see three camera frames of the same intersection, in chronological order (oldest first, latest last). The current phase is serving with a fixed 5-second green tail counted down at the end. Decide now: extend the current green by 5 more seconds when traffic still needs it, or switch the green to another phase when the current one is clearing and another direction has waiting traffic.'
_DESC_CACHE = {}

def phase_descs(raw_cfg):
    out = {}
    for p in raw_cfg['phases']:
        by_ap = {}
        for (ap, kind) in p['movements']:
            by_ap.setdefault(ap, []).append(kind)
        parts = []
        for ap in sorted(by_ap):
            kinds = set(by_ap[ap])
            if kinds == {'SR', 'L'}:
                parts.append(f'{ap} approach through, right and left turns')
            elif kinds == {'SR'}:
                parts.append(f'{ap} approach through and right turns')
            else:
                parts.append(f'{ap} approach left turns')
        y = p['transition']['yellow_s']
        r = p['transition']['all_red_s']
        out[p['key']] = f"{'; '.join(parts)} (yellow {y:g}s, all-red {r:g}s)"
    return out

def ns_layout(junction):
    if junction in _DESC_CACHE:
        return _DESC_CACHE[junction]
    raw = json.loads((ROOT / f'configs/junctions/nansha-{junction.lower()}-v2.json').read_text())
    descs = phase_descs(raw)
    aps = raw['approach_labels']
    ap_txt = f"Four approaches ({'/'.join(aps)})" if len(aps) == 4 else f"Three approaches ({'/'.join(aps)})"
    layout = {'phases': descs, 'approaches': f'{ap_txt}, each with through/right lanes and a left-turn lane (movements served vary by phase).', 'camera_view': f'Tiled 1600x900 frame from {len(aps)} cameras, one per approach' + (' (a direction without a camera renders as a black tile)' if len(aps) == 3 else '') + '.', 'transitions': {p['key']: {'yellow_s': p['transition']['yellow_s'], 'all_red_s': p['transition']['all_red_s']} for p in raw['phases']}}
    _DESC_CACHE[junction] = layout
    return layout

def build_ns_state(cfg, cur, G, e, red_age):
    from nansha_rules import legal_ns
    (S, E) = legal_ns(cur, G, red_age, cfg)
    legal = (['extend_5s'] if E else []) + [f'switch_to_{p}' for p in cfg['phases'] if p in S]
    if not legal:
        return None
    layout = ns_layout(cfg['junction'])
    return {'task': STATE_TASK, 'intersection_layout': layout, 'signal': {'current_phase': cur, 'green_elapsed_s': e, 'committed_total_green_s': G}, 'legal_actions': legal}
