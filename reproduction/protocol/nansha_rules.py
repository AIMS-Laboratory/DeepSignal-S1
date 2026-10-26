import json
from pathlib import Path
ROOT = Path.cwd()
CFGS = ROOT / 'configs/junctions'
TAIL = 5.0
EXT = 5.0
G_MAX = 60.0
R_MAX = 400.0

def load_ns(junction):
    v2 = CFGS / f'nansha-{junction.lower()}-v2.json'
    cfg = json.loads((v2 if v2.exists() else CFGS / f'nansha-{junction.lower()}.json').read_text())
    phases = [p['key'] for p in cfg['phases']]
    mov = {p['key']: [tuple(m) for m in p['movements']] for p in cfg['phases']}
    all_red = {p['key']: float(p['transition']['all_red_s']) for p in cfg['phases']}
    yellow = {p['key']: float(p['transition']['yellow_s']) for p in cfg['phases']}
    tuned = {p['key']: float(p['fixed_green_s']) for p in cfg['phases']}
    return {'junction': junction, 'tls': cfg['tls_id'], 'approaches': cfg['approach_labels'], 'approach_edges': cfg['approach_edges'], 'phases': phases, 'movements': mov, 'all_red': all_red, 'yellow': yellow, 'tuned': tuned, 'g_min': float(cfg['green_range'][0]), 'g_max': float(cfg['green_range'][1]), 'net': cfg['default_network']}

def legal_ns(cur, G, red_age, cfg):
    P = cfg['phases']
    S = []
    for p in P:
        if p == cur:
            continue
        (y, r) = (cfg['yellow'][p], cfg['all_red'][p])
        if red_age[p] + TAIL + y + r + cfg['g_min'] > R_MAX + G:
            continue
        rest = [q for q in P if q not in (cur, p)]
        ok = False
        for a in (0, 1):
            (q1, q2) = (rest[a], rest[1 - a]) if len(rest) > 1 else (rest[0], rest[0])
            c1 = TAIL + cfg['yellow'][cur] + cfg['all_red'][cur] + cfg['g_min']
            c2 = c1 + TAIL + cfg['yellow'][q1] + cfg['all_red'][q1] + cfg['g_min']
            if red_age[q1] + c1 <= R_MAX + G and red_age[q2] + c2 <= R_MAX + G:
                ok = True
                break
        if ok:
            S.append(p)
    E = G < cfg['g_max'] and bool(S)
    return (S, E)
