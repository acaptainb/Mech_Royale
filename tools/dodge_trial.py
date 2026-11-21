"""v8 bullet dodge: baseline and candidate as real bot processes from identical conditions.

    py tools/dodge_trial.py [--baseline <git revision>]

1. Scripted decisions: a direct incoming bullet, a near miss, a bullet moving away, a mortar
   shell, a wall on one side, walls on both sides, an urgent zone return, the zone edge.
2. Reactive trial: our mech walks a route while a stationary mech 60-150 m away fires leading
   gun bullets at it (252 m/s, one every 0.25 s, 0.6 deg spread). Positions, acceleration, boost
   energy and hits follow the bot's own commands. Counts hits taken, boost energy spent and
   decisions outside the zone.
3. The standard recording: how often the rule activates, and how many decisions differ.

The world model is simple (no walls for bullets, opponents stand still); it measures the
dodge decision and its first-order effect, not placement. Standard library only.
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
GUN = CONFIG["weapons"]["gun"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
GRID = Navigator()
DT_TICK = 0.05


def walkable(point):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


def observation(tick, pos, vel, goal, projectiles=(), mechs=(), zone=None, events=(), hp=1400, energy=100):
    obs = et.frame(tick, mechs, events, origin=pos[:2], hp=hp)
    obs["self"].update(pos=[pos[0], pos[1], et.ground(*pos[:2])], vel=[vel[0], vel[1], 0.0], energy=energy)
    centre, radius = zone if zone else (list(pos[:2]), 400.0)
    obs["zone"] = dict(center=list(centre), radius=radius, next_center=list(goal), next_radius=10.0,
                       shrink_start=1000.0, shrink_end=1050.0, dps=20)
    obs["self"]["in_zone"] = math.dist(pos[:2], centre) <= radius
    obs["projectiles"] = copy.deepcopy(list(projectiles))
    return obs


def bullet_at(key, target, target_vel, distance, bearing_deg, lead=True, offset=0.0, kind="gun"):
    """A bullet `distance` m from target along `bearing_deg`, flying to hit it (or to miss by `offset` m)."""
    a = math.radians(bearing_deg)
    flight = distance / GUN["speed"]
    aim = [target[0] + (target_vel[0] * flight if lead else 0), target[1] + (target_vel[1] * flight if lead else 0)]
    start = [aim[0] + distance * math.cos(a), aim[1] + distance * math.sin(a)]
    side = (-math.sin(a), math.cos(a))
    aim = [aim[0] + side[0] * offset, aim[1] + side[1] * offset]
    dx, dy = aim[0] - start[0], aim[1] - start[1]
    norm = math.hypot(dx, dy)
    z = et.ground(*target[:2]) + 4.5
    return dict(id=key, kind=kind, pos=[start[0], start[1], z], vel=[GUN["speed"] * dx / norm, GUN["speed"] * dy / norm, 0.0])


# --- scripted decisions --------------------------------------------------------------------

def find_wall_spot(both):
    """A walkable point where a 4 m step is blocked on one side (or both) of some axis."""
    for index in range(0, len(GRID.free), 3):
        if not GRID.free[index]:
            continue
        p = GRID.point(index)
        for angle in range(0, 180, 15):
            a = math.radians(angle)
            side = (math.cos(a), math.sin(a))
            plus = GRID.clear_segment(p, (p[0] + 4 * side[0], p[1] + 4 * side[1]))
            minus = GRID.clear_segment(p, (p[0] - 4 * side[0], p[1] - 4 * side[1]))
            if both and not plus and not minus:
                return p, side
            if not both and not plus and minus:
                return p, side
    raise RuntimeError("no wall spot")


def clear_heading(origin, distance=100):
    """A heading whose straight route is clear on the ground grid, so the planner walks it at once."""
    for bearing in range(0, 360, 5):
        a = math.radians(bearing)
        goal = [origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)]
        if GRID.clear_segment(origin, goal):
            return bearing, goal
    raise RuntimeError("no clear heading")


def scripted():
    home = list(et.HOME)
    heading, ahead = clear_heading(home)
    h = math.radians(heading)
    walk = (MECH["walk_speed"] * math.cos(h), MECH["walk_speed"] * math.sin(h))
    across = heading + 90  # bullets come from our left, across the route
    cases = []
    cases.append(("direct incoming bullet (150 m)", True,
                  observation(0, home, walk, ahead, [bullet_at(1, home, walk, 150, across)])))
    cases.append(("harmless near miss (8 m wide)", False,
                  observation(0, home, walk, ahead, [bullet_at(2, home, walk, 150, across, offset=8.0)])))
    away_dir = (math.cos(math.radians(across)), math.sin(math.radians(across)))
    away = dict(id=3, kind="gun", pos=[home[0] - 20 * away_dir[0], home[1] - 20 * away_dir[1], et.ground(*home) + 4.5],
                vel=[-GUN["speed"] * away_dir[0], -GUN["speed"] * away_dir[1], 0.0])
    cases.append(("bullet moving away", False, observation(0, home, walk, ahead, [away])))
    cases.append(("mortar shell on course", False,
                  observation(0, home, walk, ahead, [bullet_at(4, home, walk, 150, across, kind="mortar")])))
    cases.append(("direct bullet, too close to clear (40 m)", False,
                  observation(0, home, walk, ahead, [bullet_at(9, home, walk, 40, across)])))
    spot, side = find_wall_spot(both=False)
    bearing = math.degrees(math.atan2(side[1], side[0])) + 90  # bullet travels across the wall axis
    cases.append(("wall on one side", "open side",
                  observation(0, list(spot), (0, 0), list(spot), [bullet_at(5, spot, (0, 0), 150, bearing)]), side))
    spot2, side2 = find_wall_spot(both=True)
    bearing2 = math.degrees(math.atan2(side2[1], side2[0])) + 90
    cases.append(("walls on both sides", False,
                  observation(0, list(spot2), (0, 0), list(spot2), [bullet_at(6, spot2, (0, 0), 150, bearing2)])))
    outside = observation(0, home, walk, ahead, [bullet_at(7, home, walk, 150, across)],
                          zone=([home[0] - 80, home[1]], 50.0))
    cases.append(("urgent zone return (outside the zone)", False, outside))
    # 2 m inside the north edge of a large circle, bullet flying along x: the outward step exits.
    edge_zone = ([home[0], home[1] - 398.0], 400.0)
    cases.append(("zone edge 2 m away", "inward",
                  observation(0, home, (0, 0), home, [bullet_at(8, home, (0, 0), 150, 0)], zone=edge_zone)))
    return cases


def run_scripted(folder):
    print(f"{'scripted decision':40}{'baseline move / boost':>28}{'v8 move / boost':>28}  check")
    failures, trace = [], None
    for case in scripted():
        name, expect, obs = case[:3]
        base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
        a, b = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        base_bot.close()
        cand_bot.close()
        bullet = obs["projectiles"][0]
        bv = bullet["vel"][:2]
        bn = math.hypot(*bv)
        across = abs((b["move"][0] * bv[0] + b["move"][1] * bv[1]) / bn) < 0.01 if b.get("move") else False
        if expect is False:
            ok = plain(a) == plain(b)
            text = "identical to baseline"
        elif expect is True:
            ok = plain(a) != plain(b) and across and b["boost"]
            text = "sideways to the bullet, boosting"
            trace = (obs, a, b)
        elif expect == "open side":
            side = case[3]
            ok = across and (b["move"][0] * side[0] + b["move"][1] * side[1]) < -0.99
            text = "steps to the open side, not into the wall"
        else:  # inward
            ok = across and b["move"][1] < -0.99
            text = "steps inward, never out of the zone"
        fmt = lambda act: f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}] / {str(act.get('boost', False)):5}"
        print(f"{name:40}{fmt(a):>28}{fmt(b):>28}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    return failures, trace


# --- reactive trial ------------------------------------------------------------------------

def episodes():
    home = et.HOME
    start, goal = [home[0] - 60, home[1]], [home[0] + 60, home[1]]
    assert walkable(start) and walkable(goal)
    out = []
    for distance in (60, 100, 150):
        for angle, label in ((90, "abeam"), (135, "oblique")):
            mid = [home[0], home[1]]
            a = math.radians(angle)
            shooter = [mid[0] + distance * math.cos(a), mid[1] + distance * math.sin(a)]
            for edge in (False, True):
                zone = ([home[0], home[1] - 392.0], 400.0) if edge else ([home[0], home[1]], 400.0)
                out.append(dict(name=f"{distance:>3} m {label}{', zone edge' if edge else ''}",
                                start=start, goal=goal, shooter=shooter, zone=zone,
                                seed=distance * 10 + angle + edge))
    return out


def heldout_episodes(seed=70411, count=16):
    """Fresh routes elsewhere on the map, random shooter range and bearing, random zone edge."""
    rng = random.Random(seed)
    free = [i for i, v in enumerate(GRID.free) if v]
    out = []
    while len(out) < count:
        start = list(GRID.point(rng.choice(free)))
        a = rng.uniform(0, math.tau)
        goal = [start[0] + 120 * math.cos(a), start[1] + 120 * math.sin(a)]
        if not (walkable(goal) and GRID.clear_segment(start, goal)):
            continue
        mid = [(start[0] + goal[0]) / 2, (start[1] + goal[1]) / 2]
        distance, bearing = rng.uniform(50, 180), rng.uniform(0, math.tau)
        shooter = [mid[0] + distance * math.cos(bearing), mid[1] + distance * math.sin(bearing)]
        if not walkable(shooter):
            continue
        edge = rng.random() < 0.5
        if edge:
            side = rng.choice((-1, 1))
            normal = (-math.sin(a) * side, math.cos(a) * side)
            zone = ([mid[0] - normal[0] * 394.0, mid[1] - normal[1] * 394.0], 400.0)
        else:
            zone = (mid, 400.0)
        out.append(dict(name=f"{distance:>3.0f} m, route {len(out) + 1}{', zone edge' if edge else ''}",
                        start=start, goal=goal, shooter=shooter, zone=zone, seed=seed + len(out)))
    return out


def lead_aim(origin, target, vel, speed):
    """Direction to hit a target moving at constant velocity (falls back to direct aim)."""
    rx, ry = target[0] - origin[0], target[1] - origin[1]
    a = vel[0] ** 2 + vel[1] ** 2 - speed ** 2
    b = 2 * (rx * vel[0] + ry * vel[1])
    c = rx * rx + ry * ry
    disc = b * b - 4 * a * c
    t = 0.0
    if disc >= 0 and abs(a) > 1e-9:
        roots = [(-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)]
        positive = [r for r in roots if r > 0]
        t = min(positive) if positive else 0.0
    return math.atan2(ry + vel[1] * t, rx + vel[0] * t)


def react(folder, ep):
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(ep["seed"])
    x, y = ep["start"]
    vx = vy = 0.0
    energy, spent_at, spent = MECH["energy"], -10.0, 0.0
    hp, hits, outside, reached = 1400.0, 0, 0, None
    bullets, next_fire, next_id, events = [], 0.0, 9000, []
    move, boost = [0.0, 0.0], False
    sx, sy = ep["shooter"]
    shooter = dict(id=5, kind="mech", pos=[sx, sy, et.ground(sx, sy)], vel=[0, 0, 0], aim=[0, 0],
                   hp=1400, max_hp=1400, cubes=0, weapons=["gun"], charging=False)
    for tick in range(int(30 / DT_TICK)):
        now = tick * DT_TICK
        shooter["aim"] = [math.atan2(y - sy, x - sx), 0.0]
        if tick % 2 == 0:
            visible = [dict(id=b["id"], kind="gun", pos=list(b["pos"]), vel=list(b["vel"])) for b in bullets]
            obs = observation(tick // 2, [x, y], (vx, vy), ep["goal"], visible, [shooter], ep["zone"],
                              events, hp=hp, energy=energy)
            obs["t"] = round(now, 2)
            if not obs["self"]["in_zone"]:
                outside += 1
            action = bot.act(obs)
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
        # shooter
        if now >= next_fire - 1e-9 and math.dist((x, y), (sx, sy)) <= GUN["range"]:
            yaw = lead_aim((sx, sy), (x, y), (vx, vy), GUN["speed"]) + math.radians(rng.gauss(0, GUN["spread_deg"]))
            z0 = et.ground(sx, sy) + MECH["muzzle_height"]
            bullets.append(dict(id=next_id, pos=[sx + 3 * math.cos(yaw), sy + 3 * math.sin(yaw), z0],
                                vel=[GUN["speed"] * math.cos(yaw), GUN["speed"] * math.sin(yaw), 0.0],
                                origin=(sx, sy)))
            next_id += 1
            next_fire = now + 0.25
        # our movement
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        speed = MECH["walk_speed"]
        if boost and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            drain = MECH["boost_drain"] * DT_TICK
            energy = max(0.0, energy - drain)
            spent += drain
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
            if walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        # bullets
        alive = []
        for b in bullets:
            bx, by = b["pos"][0], b["pos"][1]
            ex, ey = bx + b["vel"][0] * DT_TICK, by + b["vel"][1] * DT_TICK
            sxv, syv = ex - bx, ey - by
            f = max(0.0, min(1.0, ((x - bx) * sxv + (y - by) * syv) / (sxv * sxv + syv * syv)))
            if math.hypot(bx + f * sxv - x, by + f * syv - y) <= MECH["radius"] + BULLET_R:
                hits += 1
                hp -= GUN["damage"]
                events.append(dict(type="damaged", amount=GUN["damage"], weapon="gun", by=5,
                                   bearing=math.atan2(sy - y, sx - x)))
                continue
            b["pos"] = [ex, ey, b["pos"][2]]
            if math.dist((ex, ey), b["origin"]) <= GUN["range"]:
                alive.append(b)
        bullets = alive
        if reached is None and math.dist((x, y), ep["goal"]) <= 4:
            reached = round(now, 1)
            break
    bot.close()
    return dict(hits=hits, spent=spent, outside=outside, reached=reached)


def run_reactive(folder, eps, title):
    print(f"\n{title:28}{'hits taken':>13}{'boost energy':>15}{'decisions outside':>20}{'arrival s':>13}")
    print(f"{'':28}{'base | v8':>13}{'base | v8':>15}{'base | v8':>20}{'base | v8':>13}")
    totals = {"base": dict(hits=0, spent=0.0, outside=0, missed=0), "cand": dict(hits=0, spent=0.0, outside=0, missed=0)}
    for ep in eps:
        base, cand = react(folder, ep), react(ROOT, ep)
        for key, row in (("base", base), ("cand", cand)):
            totals[key]["hits"] += row["hits"]
            totals[key]["spent"] += row["spent"]
            totals[key]["outside"] += row["outside"]
            totals[key]["missed"] += row["reached"] is None
        arrive = lambda r: "-" if r["reached"] is None else f"{r['reached']:.1f}"
        print(f"{ep['name']:28}{base['hits']:>6} | {cand['hits']:<5}{base['spent']:>7.0f} | {cand['spent']:<6.0f}"
              f"{base['outside']:>11} | {cand['outside']:<7}{arrive(base):>6} | {arrive(cand):<5}")
    b, c = totals["base"], totals["cand"]
    print(f"{'total':28}{b['hits']:>6} | {c['hits']:<5}{b['spent']:>7.0f} | {c['spent']:<6.0f}"
          f"{b['outside']:>11} | {c['outside']:<7}   unreached {b['missed']} | {c['missed']}")
    return totals


def run_recording(folder):
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    bot = Bot(et.HELLO)
    for obs in et.STREAM:
        bot.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o))) for o in et.STREAM)
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    bullets = sum(len(o["projectiles"]) for o in et.STREAM)
    print(f"\nrecording: {bullets} bullet sightings in {sum(1 for o in et.STREAM if o['projectiles'])} decisions;"
          f" rule outcomes {dict(sorted(bot.dodge.counts.items())) or 'none'};"
          f" {differ} of {len(et.STREAM)} decisions answered differently from the baseline;"
          f" round trip p99 {p99:.1f} ms")
    return bot.dodge.counts


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    failures, trace = run_scripted(folder)
    if trace:
        obs, a, b = trace
        bullet = obs["projectiles"][0]
        print(f"\ntrace, direct incoming bullet: we walk at {MECH['walk_speed']} m/s; a bullet 150 m to our left flies"
              f" at {GUN['speed']} m/s, led onto our path")
        print(f"  baseline: move {a['move']}, boost {a.get('boost')}, aim {[round(v, 2) for v in a['aim']]}, fire {a.get('fire')}")
        print(f"  v8:       move {b['move']}, boost {b.get('boost')}, aim {[round(v, 2) for v in b['aim']]}, fire {b.get('fire')}")
    for eps, title in ((episodes(), "reactive (tuning set)"), (heldout_episodes(), "reactive (held-out)")):
        totals = run_reactive(folder, eps, title)
        if totals["cand"]["outside"] > totals["base"]["outside"]:
            failures.append(f"{title}: more decisions outside the zone")
        if totals["cand"]["missed"] > totals["base"]["missed"]:
            failures.append(f"{title}: routes left unfinished")
    run_recording(folder)
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (scripted checks; reactive and recording numbers are measurements)")


if __name__ == "__main__":
    main()
