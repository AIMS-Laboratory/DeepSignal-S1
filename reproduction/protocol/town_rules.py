from signal_states import PHASES
R_MAX = 150.0
T_END = 518.0

def legal_b(cur, G, red_age):
    S = []
    for p in PHASES:
        if p == cur:
            continue
        if red_age[p] + 10.0 > R_MAX:
            continue
        rest = [q for q in PHASES if q not in (cur, p)]
        ok = True
        for a in (0, 1):
            (q1, q2) = (rest[a], rest[1 - a])
            if red_age[q1] + 21.0 <= R_MAX and red_age[q2] + 32.0 <= R_MAX:
                break
        else:
            ok = False
        if ok:
            S.append(p)
    delta = min(5.0, 60.0 - G)
    E = G < 60.0 and any((red_age[p] + delta + 10.0 <= R_MAX and _rest_ok(red_age, cur, p, delta) for p in PHASES if p != cur))
    return (S, E)

def _rest_ok(red_age, cur, p, h):
    rest = [q for q in PHASES if q not in (cur, p)]
    for a in (0, 1):
        (q1, q2) = (rest[a], rest[1 - a])
        if red_age[q1] + h + 21.0 <= R_MAX and red_age[q2] + h + 32.0 <= R_MAX:
            return True
    return False
