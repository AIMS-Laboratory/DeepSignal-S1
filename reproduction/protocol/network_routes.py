import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path.cwd()
import os as _os

def _imports(cfg):
    _os.environ['DEEPSIGNAL_JUNCTION_PROFILE'] = str(ROOT / f"configs/junctions/nansha-{cfg['junction'].lower()}-v2.json")
    import importlib
    import deepsignal.junction_profile as jp
    import deepsignal.ue4_junction as uj
    import deepsignal.traffic_scenario as ts
    jp._cached_load.cache_clear()
    importlib.reload(uj)
    importlib.reload(ts)
    return ts.write_routes

def probe_links(cfg):
    t = ET.parse(cfg['net']).getroot()
    straight = {'0'}
    links = {p: [] for p in cfg['phases']}
    lane_kind = {}
    for c in t.findall('connection'):
        if c.get('tl') != cfg['tls']:
            continue
        (fr, fl, link) = (c.get('from'), int(c.get('fromLane')), int(c.get('linkIndex')))
        ap = next((a for (a, e) in cfg['approach_edges'].items() if fr == e), None)
        if ap is None:
            continue
        kind = 'SR' if c.get('dir') != 'l' else 'L'
        lane_kind[link] = (ap, kind)
    for c in t.findall('connection'):
        if c.get('tl') != cfg['tls']:
            continue
        link = int(c.get('linkIndex'))
        (ap, kind) = lane_kind[link]
        for p in cfg['phases']:
            if (ap, kind) in cfg['movements'][p] or (ap, 'SR' if kind == 'SR' else kind) in [(m[0], m[1]) for m in cfg['movements'][p]]:
                if (ap, kind) in cfg['movements'][p]:
                    links[p].append(link)
    return links

def state_str(links, n_links, mode, phase=None):
    s = ['r'] * n_links
    if mode == 'G' or mode == 'y':
        for l in links[phase]:
            s[l] = mode
    return ''.join(s)
