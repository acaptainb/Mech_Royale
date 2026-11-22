"""v9 zone-return recovery: baseline and candidate as real bot processes from matched starts.

    py tools/zone_return_trial.py [--baseline <git revision>]

Each episode starts outside the zone, so both bots are in zone-return mode from the first
decision. A closed-loop world moves the mech where it steers (ground acceleration, walk and
boost speed, boost energy), blocks it on the navigation grid and on obstacles the bot's map
does not contain, and applies zone damage outside the circle. Reports seconds outside the
zone, whether and when the mech reached safety (inside the current circle), and how many
recovery attempts the candidate made. Jumps are not modelled, so an obstacle can only be
walked around. Standard library only.
"""
import copy
import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
from harness import BASELINE, BotProcess, export, plain
from navigation import Navigator

CONFIG = et.HELLO["config"]
MECH = CONFIG["mech"]
GRID = Navigator()
DT_TICK = 0.05
CAP_S = 30.0


def walkable(point, obstacles=()):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    if not (0 <= i < GRID.width and 0 <= j < GRID.height and GRID.free[j * GRID.width + i]):
        return False
    for kind, data in obstacles:
        if kind == "disc" and math.dist(point, data[:2]) < data[2]:
            return False
        if kind == "wall":
            (ax, ay), (bx, by), half = data
            sx, sy = bx - ax, by - ay
            f = max(0.0, min(1.0, ((point[0] - ax) * sx + (point[1] - ay) * sy) / (sx * sx + sy * sy)))
            if math.hypot(ax + f * sx - point[0], ay + f * sy - point[1]) < half:
                return False
    return True


def observation(tick, pos, vel, ep, hp, energy, events):
    obs = et.frame(tick, [], events, origin=pos[:2], hp=hp)
    obs["self"].update(pos=[pos[0], pos[1], et.ground(*pos[:2])], vel=[vel[0], vel[1], 0.0], energy=energy)
    centre, radius = ep["zone"]
    obs["zone"] = dict(center=list(centre), radius=radius, next_center=list(centre), next_radius=radius * 0.6,
                       shrink_start=1000.0, shrink_end=1050.0, dps=20)
    obs["self"]["in_zone"] = math.dist(pos[:2], centre) <= radius
    return obs


def simulate(act, ep):
    """Run one episode with `act(obs) -> action`; return the measurements."""
    x, y = ep["start"]
    vx = vy = 0.0
    energy, spent_at, hp = MECH["energy"], -10.0, 1400.0
    outside = 0
    reached = None
    move, boost, events, actions = [0.0, 0.0], False, [], []
    centre, radius = ep["zone"]
    for tick in range(int(CAP_S / DT_TICK)):
        now = tick * DT_TICK
        inside = math.dist((x, y), centre) <= radius
        if tick % 2 == 0:
            if not inside:
                outside += 1
            obs = observation(tick // 2, (x, y), (vx, vy), ep, hp, energy, events)
            obs["t"] = round(now, 2)
            action = act(obs)
            actions.append(plain(action))
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
        if inside and reached is None:
            reached = round(now, 1)
            break
        if not inside:
            hp -= 20 * DT_TICK
            if tick % 2 == 1:
                events = [dict(type="damaged", amount=2.0, weapon="zone", by=None, bearing=None)]
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        speed = MECH["walk_speed"]
        if boost and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            energy = max(0.0, energy - MECH["boost_drain"] * DT_TICK)
            spent_at = now
        elif now - spent_at >= MECH["energy_regen_delay"]:
            energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT_TICK)
        dvx, dvy = mx * speed - vx, my * speed - vy
        dv = math.hypot(dvx, dvy)
        limit = MECH["ground_accel"] * DT_TICK
        if dv > limit:
            dvx, dvy = dvx * limit / dv, dvy * limit / dv
        vx, vy = vx + dvx, vy + dvy
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * DT_TICK
            if walkable(candidate, ep["obstacles"]):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
    return dict(outside_s=round(outside * 0.1, 1), reached=reached, actions=actions)


# --- episodes -----------------------------------------------------------------------------

def clear_route(origin, distance):
    for bearing in range(0, 360, 5):
        a = math.radians(bearing)
        goal = [origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)]
        if GRID.clear_segment(origin, goal) and walkable(goal):
            return a, goal
    raise RuntimeError("no clear route")


def path_length(a, b, limit=20000):
    start, goal = GRID.snap(a), GRID.snap(b)
    seen, queue = {start: 0}, deque([start])
    while queue and len(seen) < limit:
        i = queue.popleft()
        if i == goal:
            return seen[i] * GRID.step
        for j in (i - 1, i + 1, i - GRID.width, i + GRID.width):
            if GRID.free[j] and j not in seen:
                seen[j] = seen[i] + 1
                queue.append(j)
    return math.inf


def corner_episode():
    """A start whose straight line to the zone centre is blocked by a mapped building, with a
    walkable way round that is at most 60% longer."""
    for index in range(0, len(GRID.free), 11):
        if not GRID.free[index]:
            continue
        start = list(GRID.point(index))
        for bearing in range(0, 360, 20):
            a = math.radians(bearing)
            centre = [start[0] + 90 * math.cos(a), start[1] + 90 * math.sin(a)]
            if not walkable(centre) or GRID.clear_segment(start, centre):
                continue
            length = path_length(start, centre)
            if 99 <= length <= 1.6 * 90:
                # A small circle: the mech has to walk the whole way round the building.
                return dict(name="slow turn round a mapped corner", start=start, zone=(centre, 12.0),
                            obstacles=[], expect="no retry")
    raise RuntimeError("no corner episode")


def episodes():
    home = list(et.HOME)
    a, goal = clear_route(home, 110)
    ux, uy = math.cos(a), math.sin(a)
    across = (-uy, ux)

    def wall(at, half_length):
        cx, cy = home[0] + ux * at, home[1] + uy * at
        return ("wall", ((cx - across[0] * half_length, cy - across[1] * half_length),
                         (cx + across[0] * half_length, cy + across[1] * half_length), 1.5))

    return [
        # The jam from the v5 pickup trial ("deadline closes mid-route", instance 4): the mech
        # stood pressed against an obstacle the grid does not know, centred at (469.9, -74.4),
        # pushing toward the zone at (303, -50) from (475.7, -75.8), and stayed outside.
        dict(name="known case: v5-trial jam", start=[476.0, -75.9], zone=([303.0, -50.0], 150.0),
             obstacles=[("disc", (469.85, -74.45, 6.0))], expect="recover"),
        dict(name="unmapped wall across the route", start=home, zone=(goal, 60.0),
             obstacles=[wall(15, 8)], expect="recover"),
        dict(name="wide unmapped wall", start=home, zone=(goal, 60.0),
             obstacles=[wall(15, 22)], expect="recover"),
        dict(name="clear return route", start=home, zone=(goal, 60.0), obstacles=[], expect="no retry"),
        corner_episode(),
    ]


def heldout_episodes(seed=31337, count=24):
    """Fresh starts elsewhere on the map. Half have an unmapped wall or disc across a clear
    route (random distance and size); the rest are controls: a clear route, or a route that
    must turn round a mapped building."""
    import random
    rng = random.Random(seed)
    free = [i for i, v in enumerate(GRID.free) if v]
    out = []
    while len(out) < count:
        start = list(GRID.point(rng.choice(free)))
        a = rng.uniform(0, math.tau)
        centre = [start[0] + 100 * math.cos(a), start[1] + 100 * math.sin(a)]
        if not walkable(centre):
            continue
        clear = GRID.clear_segment(start, centre)
        kind = ("obstacle", "clear", "corner")[len(out) % 3 if len(out) % 2 else 0]
        if kind in ("obstacle", "clear") and not clear:
            continue
        if kind == "corner" and (clear or path_length(start, centre) > 160):
            continue
        obstacles = []
        if kind == "obstacle":
            at, half = rng.uniform(10, 25), rng.uniform(4, 22)
            cx, cy = start[0] + at * math.cos(a), start[1] + at * math.sin(a)
            if rng.random() < 0.5:
                obstacles = [("disc", (cx, cy, max(4.0, half / 2)))]
            else:
                px, py = -math.sin(a), math.cos(a)
                obstacles = [("wall", ((cx - px * half, cy - py * half), (cx + px * half, cy + py * half), 1.5))]
        radius = 30.0 if kind != "corner" else 12.0
        out.append(dict(name=f"held-out {len(out) + 1:>2}: {kind}", start=start, zone=(centre, radius),
                        obstacles=obstacles, expect="recover" if obstacles else "no retry"))
    return out


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; every episode starts"
          f" outside the zone (cap {CAP_S:.0f} s)\n")
    print(f"{'episode':36}{'seconds outside':>18}{'reached safety at':>20}{'retries':>9}  check")
    print(f"{'':36}{'base | v9':>18}{'base | v9':>20}")
    failures, traces = [], {}
    # Seeds 31337, 90210 and 4711 each exposed a failure that shaped a rule (movement gate,
    # rejecting a follow-the-slide rule, the 1.5 s step), so they count as tuning sets. Seed 2718
    # was generated only after every constant and rule was fixed.
    seeds = [(31337, "tuning set, seed 31337 (its slide case led to the movement gate)"),
             (90210, "tuning set, seed 90210 (it rejected a follow-the-slide rule)"),
             (4711, "tuning set, seed 4711 (with the others, chose the 1.5 s step)"),
             (2718, "fresh held-out set, seed 2718 (generated after all rules were fixed)")]
    plan = [(ep, None) for ep in episodes()]
    for seed, title in seeds:
        plan += [(dict(ep, name=ep["name"].replace("held-out", f"seed {seed}")), title if k == 0 else None)
                 for k, ep in enumerate(heldout_episodes(seed))]
    unsolved = []
    for number, (ep, title) in enumerate(plan):
        if title:
            print(f"\n{title}:")
        rows = {}
        for key, folder_ in (("base", folder), ("cand", ROOT)):
            bot = BotProcess(folder_, et.HELLO)
            rows[key] = simulate(bot.act, ep)
            bot.close()
        local = Bot(et.HELLO)  # the same deterministic run in-process, to read the retry count
        simulate(local.act, ep)
        recovery = getattr(local, "recovery", None)
        retries = recovery.counts.get("retry", 0) if recovery else 0
        base, cand = rows["base"], rows["cand"]
        if ep["expect"] == "no retry":
            ok = retries == 0 and base["actions"] == cand["actions"] and cand["reached"] is not None
            text = "no retry; identical actions; reaches safety"
        elif base["reached"] is not None:
            # The baseline got round on its own (the wall slid it clear): v9 must not be worse.
            ok = cand["reached"] is not None and cand["outside_s"] <= base["outside_s"] + 0.1
            text = "baseline got round unaided; v9 no slower"
        elif cand["reached"] is None and number >= len(episodes()):
            # Random geometry can wall off every way round that one sideways step can reach.
            ok = cand["outside_s"] <= base["outside_s"]
            unsolved.append(ep["name"])
            text = "UNSOLVED by both (no worse than the baseline)"
        else:
            ok = cand["reached"] is not None and cand["outside_s"] < base["outside_s"]
            text = "reaches safety sooner than the baseline"
        reach = lambda r: "never" if r["reached"] is None else f"{r['reached']:.1f} s"
        print(f"{ep['name']:36}{base['outside_s']:>8.1f} | {cand['outside_s']:<7.1f}{reach(base):>9} | {reach(cand):<8}"
              f"{retries:>5}    {'ok  ' if ok else 'FAIL'} {text}")
        traces[ep["name"]] = (base, cand)
        if not ok:
            failures.append(ep["name"])
    print(f"\nunsolved by both bots: {len(unsolved)} {unsolved or ''}")
    base, cand = traces["known case: v5-trial jam"]
    print("\ntrace, known case (decision: move / jump):")
    for k in range(0, min(len(base["actions"]), len(cand["actions"]), 60), 6):
        b, c = base["actions"][k], cand["actions"][k]
        fmt = lambda a: f"[{a['move'][0]:+.2f},{a['move'][1]:+.2f}] {'jump' if a.get('jump') else '    '}"
        print(f"  t={k * 0.1:4.1f}   baseline {fmt(b)}   v9 {fmt(c)}")
    # The standard recording: never in zone-return trouble, so nothing may change.
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o))) for o in et.STREAM)
    base_bot.close()
    cand_bot.close()
    recovery = getattr(local, "recovery", None)
    print(f"\nrecording: retries {recovery.counts.get('retry', 0) if recovery else 0};"
          f" {differ} of {len(et.STREAM)} decisions answered differently from the baseline")
    if differ:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
