import json
from pathlib import Path
from sumo_fork_probe import load_raw
NET = Path('out/s1-e0/d0/network/junction.net.xml')
TABLE_GREEN = {'ew_straight': 45.0, 'ew_left': 14.0, 'ns_straight': 45.0, 'ns_left': 14.0}

def make_raw(cond, seed):
    if cond in ('balanced', 'sustained-uneven', 'time-varying'):
        raw = load_raw(Path(f'configs/vlm-realtime-control/episode-{cond}.formal.json'), seed)
    elif cond == 'uneven125':
        raw = load_raw(Path('configs/vlm-realtime-control/ood-uneven125-6001.json'), seed)
    else:
        raw = load_raw(Path(f'configs/vlm-realtime-control/ood-varyshuf-{seed}.json'), seed)
    raw['formal_end'] = 98 + 120 + 180
    return raw
