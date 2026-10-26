from __future__ import annotations
from pathlib import Path
from .ue4_junction import default_green_table
GREEN_TABLES = ('default', 'neutral', 'webster')
WEBSTER_GREEN = {'ew_straight': 16.0, 'ew_left': 6.0, 'ns_straight': 16.0, 'ns_left': 6.0}

def green_table_greens(table: str, net_file: Path) -> dict[str, float]:
    if table == 'default':
        default = default_green_table(net_file)
        return {'ew_straight': float(default.major_green), 'ew_left': float(default.minor_green), 'ns_straight': float(default.major_green), 'ns_left': float(default.minor_green)}
    if table == 'neutral':
        default = default_green_table(net_file)
        even = float((default.major_green + default.minor_green) // 2)
        return {'ew_straight': even, 'ew_left': even, 'ns_straight': even, 'ns_left': even}
    if table == 'webster':
        return dict(WEBSTER_GREEN)
    raise ValueError(f'未知绿表 {table}，可选 {GREEN_TABLES}')
