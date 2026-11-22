"""v12 hold near cover: baseline and candidate as real bot processes from identical starts.

    py tools/hold_trial.py [--baseline <git revision>]

A closed-loop world moves the mech where it steers (ground acceleration, walk and boost
speed, boost energy), blocks it on the navigation grid, and runs a multi-phase zone: each
phase holds, then the circle shrinks linearly toward the next one, then a new next circle is
announced. Opponents and damage are injected at fixed times. Reports metres walked, seconds
outside the current circle (late arrivals), and for each release case the decision on which
the hold ended against the decision on which the condition changed. Standard library only.
"""
import copy
import math
import random
import sys
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


def walkable(point):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


class Zone:
    """circles[k] = (centre, radius); timing[k] = (hold_s, shrink_s) for the shrink from k to k+1."""

    def __init__(self, circles, timing):
        self.circles, self.phases, start = circles, [], 0.0
        for hold, shrink in timing:
            self.phases.append((start + hold, start + hold + shrink))
            start += hold + shrink

    def at(self, t):
        for k, (begin, end) in enumerate(self.phases):
            if t < end or k == len(self.phases) - 1:
                f = min(1.0, max(0.0, (t - begin) / (end - begin)))
                (c0, r0), (c1, r1) = self.circles[k], self.circles[k + 1]
                centre = [c0[0] + f * (c1[0] - c0[0]), c0[1] + f * (c1[1] - c0[1])]
                return dict(center=centre, radius=r0 + f * (r1 - r0), next_center=list(c1), next_radius=r1,
                            shrink_start=begin, shrink_end=end, dps=20)


def observation(tick, now, pos, vel, zone, mechs, events, hp, energy):
    obs = et.frame(tick, mechs, events, origin=pos[:2], hp=hp)
    obs["t"] = round(now, 2)
    obs["self"].update(pos=[pos[0], pos[1], et.ground(*pos[:2])], vel=[vel[0], vel[1], 0.0], energy=energy)
    obs["zone"] = zone
    obs["self"]["in_zone"] = math.dist(pos[:2], zone["center"]) <= zone["radius"]
    return obs


def simulate(act, ep):
    x, y = ep["start"]
    vx = vy = 0.0
    energy, spent_at, hp = MECH["energy"], -10.0, 1400.0
    walked, outside, moves = 0.0, 0, []
    move, boost, events = [0.0, 0.0], False, []
    zone = ep["zone"]
    for tick in range(int(ep["seconds"] / DT_TICK)):
        now = tick * DT_TICK
        state = zone.at(now)
        if tick % 2 == 0:
            if math.dist((x, y), state["center"]) > state["radius"]:
                outside += 1
            mechs = [m for t, m in ep.get("mechs", []) if now >= t - 1e-9]
            if any(abs(now - t) < 1e-9 for t in ep.get("hits", [])):
                events.append(dict(type="damaged", amount=45, weapon="gun", by=9, bearing=1.0))
                hp -= 45
            obs = observation(tick // 2, now, (x, y), (vx, vy), state, mechs, events, hp, energy)
            action = act(obs)
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            moves.append(list(move))
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
        before = (x, y)
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * DT_TICK
            if walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        walked += math.dist(before, (x, y))
    return dict(walked=round(walked, 1), late_s=round(outside * 0.1, 1), moves=moves)


# --- geometry ------------------------------------------------------------------------------

def covered(point):
    from cover import Cover
    from hold import Hold
    global _HOLD
    if "_HOLD" not in globals():
        _HOLD = Hold(Cover())
    return _HOLD.near_cover(point)


def clear_goal(start, distance, rng=None):
    bearings = list(range(0, 360, 10))
    if rng:
        rng.shuffle(bearings)
    for bearing in bearings:
        a = math.radians(bearing)
        goal = [start[0] + distance * math.cos(a), start[1] + distance * math.sin(a)]
        if walkable(goal) and GRID.clear_segment(start, goal):
            return a, goal
    return None


def find_start(want_cover, rng=None, distance=110):
    cells = [i for i, v in enumerate(GRID.free) if v]
    order = range(0, len(cells), 13) if rng is None else (rng.randrange(len(cells)) for _ in range(20000))
    for index in order:
        start = list(GRID.point(cells[index]))
        if covered(start) != want_cover:
            continue
        found = clear_goal(start, distance, rng)
        if found:
            return start, found
    raise RuntimeError("no start")


def single_phase(start, goal, seconds=45.0):
    """Start well inside a large next circle centred on `goal`; the shrink ends after `seconds`."""
    zone = Zone([(goal, 400.0), (goal, 160.0), (goal, 80.0)], [(30.0, 20.0), (20.0, 20.0)])
    return zone


def episodes():
    (cs, (ca, cgoal)) = find_start(True)
    (es, (ea, egoal)) = find_start(False)
    out = []
    out.append(dict(name="quiet covered start", start=cs, zone=single_phase(cs, cgoal), seconds=45.0,
                    expect="hold"))
    out.append(dict(name="exposed start", start=es, zone=single_phase(es, egoal), seconds=45.0,
                    expect="identical"))
    opponent = et.mech(5, math.degrees(ca) + 90, 120, origin=cs)
    out.append(dict(name="opponent appears at t=5.0", start=cs, zone=single_phase(cs, cgoal), seconds=20.0,
                    mechs=[(5.0, opponent)], expect="release", change=5.0))
    out.append(dict(name="unseen attacker hits at t=5.0", start=cs, zone=single_phase(cs, cgoal), seconds=20.0,
                    hits=[5.0], expect="release", change=5.0))
    # Phase 1 next circle is centred 20 m from the start toward the goal; at t=15 the zone
    # announces a 40 m next circle centred on the goal, 110 m away.
    c1 = [cs[0] + 20 * math.cos(ca), cs[1] + 20 * math.sin(ca)]
    moving = Zone([(c1, 400.0), (c1, 160.0), (cgoal, 40.0), (cgoal, 20.0)], [(5.0, 10.0), (10.0, 15.0), (20.0, 20.0)])
    out.append(dict(name="next circle moves away at t=15.0", start=cs, zone=moving, seconds=45.0,
                    expect="release", change=15.0))
    return out


def random_episodes(seed, count=20):
    """Starts inside a three-phase zone; each next circle is a random circle inside the last."""
    rng = random.Random(seed)
    out = []
    while len(out) < count:
        want = len(out) % 2 == 0
        start, (a, goal) = find_start(want, rng, distance=rng.uniform(60, 140))
        r1 = rng.uniform(140, 220)
        if math.dist(start, goal) + 30 > r1:
            continue
        r2 = rng.uniform(40, 80)
        off = rng.uniform(0, r1 - r2 - 5)
        b = rng.uniform(0, math.tau)
        c2 = [goal[0] + off * math.cos(b), goal[1] + off * math.sin(b)]
        if not walkable(c2):
            continue
        zone = Zone([(goal, 400.0), (goal, r1), (c2, r2), (c2, r2 * 0.4)],
                    [(rng.uniform(5, 15), 15.0), (rng.uniform(10, 20), 15.0), (15.0, 15.0)])
        out.append(dict(name=f"seed {seed} #{len(out) + 1:>2} ({'covered' if want else 'exposed'})",
                        start=start, zone=zone, seconds=60.0, expect="measure"))
    return out


def held(moves, k):
    return k < len(moves) and math.hypot(*moves[k]) == 0


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    print(f"{'episode':36}{'metres walked':>16}{'late s':>12}{'holds':>7}{'hold decisions':>16}  check")
    print(f"{'':36}{'base | v12':>16}{'base | v12':>12}")
    failures, traces = [], {}
    totals = {}
    plan = [(ep, None) for ep in episodes()]
    for seed, title in ((5150, "randomized starts, seed 5150 (tuning)"), (8086, "randomized starts, seed 8086 (held out)")):
        plan += [(ep, title if k == 0 else None) for k, ep in enumerate(random_episodes(seed))]
    for ep, title in plan:
        if title:
            print(f"\n{title}:")
        rows = {}
        for key, path in (("base", folder), ("cand", ROOT)):
            bot = BotProcess(path, et.HELLO)
            rows[key] = simulate(bot.act, ep)
            bot.close()
        local = Bot(et.HELLO)
        simulate(local.act, ep)
        hold = local.hold
        base, cand = rows["base"], rows["cand"]
        expect = ep["expect"]
        if expect == "hold":
            ok = hold.started > 0 and cand["walked"] < base["walked"] - 20 and cand["late_s"] <= base["late_s"]
            text = "holds; walks far less; no later than the baseline"
        elif expect == "identical":
            ok = hold.started == 0 and base["moves"] == cand["moves"]
            text = "no hold; identical moves"
        elif expect == "release":
            k = round(ep["change"] / 0.1)
            ok = held(cand["moves"], k - 1) and not held(cand["moves"], k) and cand["late_s"] <= base["late_s"]
            text = f"held at decision {k - 1}, moving at decision {k} (the change); no later than the baseline"
        else:
            key = "covered" if "covered" in ep["name"] else "exposed"
            seed = ep["name"].split()[1]
            agg = totals.setdefault(seed, dict(base_walk=0.0, cand_walk=0.0, base_late=0.0, cand_late=0.0,
                                               holds=0, episodes_held=0, exposed_holds=0))
            agg["base_walk"] += base["walked"]
            agg["cand_walk"] += cand["walked"]
            agg["base_late"] += base["late_s"]
            agg["cand_late"] += cand["late_s"]
            agg["holds"] += hold.started
            agg["episodes_held"] += hold.started > 0
            ok = cand["late_s"] <= base["late_s"]
            text = "no later than the baseline"
        print(f"{ep['name']:36}{base['walked']:>7.1f} | {cand['walked']:<7.1f}{base['late_s']:>5.1f} | {cand['late_s']:<5.1f}"
              f"{hold.started:>5}{hold.decisions:>12}      {'ok  ' if ok else 'FAIL'} {text}")
        traces[ep["name"]] = (base, cand)
        if not ok:
            failures.append(ep["name"])
    for seed, agg in totals.items():
        print(f"\nseed {seed}: metres walked {agg['base_walk']:.0f} -> {agg['cand_walk']:.0f};"
              f" late seconds {agg['base_late']:.1f} -> {agg['cand_late']:.1f};"
              f" episodes with a hold {agg['episodes_held']} of 20 ({agg['holds']} holds)")
    base, cand = traces["opponent appears at t=5.0"]
    print("\ntrace, opponent appears at t=5.0 (move per decision):")
    for k in (0, 10, 48, 49, 50, 51, 60):
        print(f"  t={k * 0.1:4.1f}  baseline {[round(v, 2) for v in base['moves'][k]]}   v12 {[round(v, 2) for v in cand['moves'][k]]}")
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o))) for o in et.STREAM)
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: holds {local.hold.started}, hold decisions {local.hold.decisions};"
          f" {differ} of {len(et.STREAM)} decisions answered differently from the baseline; round trip p99 {p99:.1f} ms")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
