from deepsignal.ue4_junction import movement_groups, motor_links
from episode_settings import NET
PHASES = ('ew_straight', 'ew_left', 'ns_straight', 'ns_left')
STATES = {}

def harvest(u):
    if u.group:
        STATES.setdefault((u.group, u.color), u.state)
    else:
        STATES.setdefault(('all_red', 'r'), u.state)

def warm_states():
    (motor, other) = motor_links(NET)
    width = max([*motor, *other]) + 1
    STATES['all_red', 'r'] = 'r' * width
    for (phase, links) in movement_groups(NET).items():
        for color in ('G', 'y'):
            state = ['r'] * width
            for index in links:
                state[index] = color
            STATES[phase, color] = ''.join(state)
