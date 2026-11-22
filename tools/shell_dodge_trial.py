"""mortar-dodge: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/shell_dodge_trial.py [--baseline <git revision>]

1. Scripted decisions: a shell about to land on our route, a shell landing 25 m away, a shell
   landing on us while the zone return is urgent, a shell landing after the 2.5 s horizon.
2. Closed loop: our mech walks a 120 m route while a stationary mortar mech 60-200 m away lobs
   shells at where we will be (low or high arc, aim spread 1.5 m, one every 2.6 s). Positions,
   acceleration, boost energy, knock-back and energy drain follow the bot's own commands. A shell
   is shown to the bot only while it is visible: within 45 m, or within 200 m and 60 deg of our
   aim. It explodes on the terrain or on our body: 200 + 160 on a direct hit, else 160 falling to
   30% at 7 m from our centre.
3. Controls with identical starts, which must give identical commands on every decision: shells
   aimed 30 m wide, a gun shooter only, and shells landing on us while we are outside the zone.
4. The standard recording: how many decisions differ.

The world model has no buildings for shells and opponents stand still; it measures the dodge
decision and its first-order effect, not placement. Standard library only.
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
from dodge_trial import GRID, clear_heading, lead_aim, observation, walkable
from harness import BotProcess, export, plain

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90
CONFIG = et.HELLO["config"]
MECH = CONFIG["mech"]
GUN = CONFIG["weapons"]["gun"]
MORTAR = CONFIG["weapons"]["mortar"]
TUBE = MECH["height"] + 0.5
DT_TICK = 0.05


def launch(origin, target, arc):
    """Launch velocity from `origin` (tube) to land on `target`; arc "low" or "high". None if out of range."""
    v, g = MORTAR["speed"], MORTAR["gravity"]
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    d = math.hypot(dx, dy)
    dz = target[2] - origin[2]
    disc = v ** 4 - g * (g * d * d + 2 * dz * v * v)
    if disc < 0 or d < 1e-6:
        return None
    root = math.sqrt(disc)
    tan = (v * v - root) / (g * d) if arc == "low" else (v * v + root) / (g * d)
    pitch = math.atan(tan)
    flight = d / (v * math.cos(pitch))
    h = v * math.cos(pitch)
    return [h * dx / d, h * dy / d, v * math.sin(pitch)], flight


def shell_at(key, target, flight_left, arc="high", bearing_deg=0.0, distance=120.0):
    """A shell in mid-flight, `flight_left` seconds before it lands on `target`."""
    a = math.radians(bearing_deg)
    origin = [target[0] + distance * math.cos(a), target[1] + distance * math.sin(a), 0.0]
    origin[2] = et.ground(*origin[:2]) + TUBE
    goal = [target[0], target[1], et.ground(*target[:2])]
    vel, flight = launch(origin, goal, arc)
    t = flight - flight_left
    g = MORTAR["gravity"]
    pos = [origin[0] + vel[0] * t, origin[1] + vel[1] * t, origin[2] + vel[2] * t - 0.5 * g * t * t]
    return dict(id=key, kind="mortar", pos=pos, vel=[vel[0], vel[1], vel[2] - g * t])


# --- scripted decisions --------------------------------------------------------------------

def scripted():
    home = list(et.HOME)
    heading, ahead = clear_heading(home)
    h = math.radians(heading)
    walk = (MECH["walk_speed"] * math.cos(h), MECH["walk_speed"] * math.sin(h))
    where = lambda t: [home[0] + walk[0] * t, home[1] + walk[1] * t]
    cases = [
        ("shell landing on our route in 1.2 s", True,
         observation(0, home, walk, ahead, [shell_at(1, where(1.2), 1.2, bearing_deg=heading + 90)])),
        ("shell landing 25 m to the side", False,
         observation(0, home, walk, ahead, [shell_at(2, [where(1.2)[0] + 25 * math.cos(h + math.pi / 2),
                                                         where(1.2)[1] + 25 * math.sin(h + math.pi / 2)],
                                                     1.2, bearing_deg=heading + 90)])),
        ("shell landing on us, urgent zone return", False,
         observation(0, home, walk, ahead, [shell_at(3, where(1.2), 1.2, bearing_deg=heading + 90)],
                     zone=([home[0] - 80, home[1]], 50.0))),
        ("shell landing on us in 4 s (after the horizon)", False,
         observation(0, home, (0, 0), home, [shell_at(4, home, 4.0, bearing_deg=heading + 90)])),
    ]
    return cases, home


def run_scripted(folder):
    print(f"{'scripted decision':48}{'baseline move / boost':>26}{'candidate move / boost':>26}  check")
    failures, trace = [], None
    cases, home = scripted()
    for name, expect, obs in cases:
        base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
        a, b = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        base_bot.close()
        cand_bot.close()
        if expect:
            ok = plain(a) != plain(b) and b.get("boost") and a["move"] != b["move"]
            text = "steps away, boosting"
            trace = (obs, a, b)
        else:
            ok = plain(a) == plain(b)
            text = "identical to baseline"
        fmt = lambda act: f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}] / {str(act.get('boost', False)):5}"
        print(f"{name:48}{fmt(a):>26}{fmt(b):>26}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    return failures, trace


# --- closed loop ---------------------------------------------------------------------------

def visible(me, aim_yaw, point):
    d = math.dist(me[:2], point[:2])
    if d <= CONFIG["vision"].get("near_range", 45):
        return True
    if d > CONFIG["vision"].get("range", 200):
        return False
    bearing = math.atan2(point[1] - me[1], point[0] - me[0])
    off = (bearing - aim_yaw + math.pi) % math.tau - math.pi
    return abs(off) <= math.radians(CONFIG["vision"].get("fov_deg", 120) / 2)


def splash_damage(d):
    if d > MORTAR["splash_radius"]:
        return 0.0, 0.0
    falloff = 1 - (1 - MORTAR["splash_edge"]) * d / MORTAR["splash_radius"]
    return MORTAR["splash"] * falloff, falloff


def react(folder, ep):
    """One closed-loop episode; returns damage, arrival, energy and the command log."""
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(ep["seed"])
    x, y = ep["start"]
    vx = vy = 0.0
    energy, spent_at, spent = MECH["energy"], -10.0, 0.0
    hp, outside, reached = 1400.0, 0, None
    direct = splashed = 0
    splash_total = 0.0
    track, blasts = [], []
    shots, next_fire, next_id, events, log = [], ep.get("first", 0.3), 9000, [], []
    move, boost, aim_yaw = [0.0, 0.0], False, 0.0
    sx, sy = ep["shooter"]
    sz = et.ground(sx, sy)
    weapon = ep.get("weapon", "mortar")
    shooter = dict(id=5, kind="mech", pos=[sx, sy, sz], vel=[0, 0, 0], aim=[0, 0],
                   hp=1400, max_hp=1400, cubes=0, weapons=[weapon], charging=False)
    g = MORTAR["gravity"]
    for tick in range(int(30 / DT_TICK)):
        now = tick * DT_TICK
        z = et.ground(x, y)
        shooter["aim"] = [math.atan2(y - sy, x - sx), 0.0]
        if tick % 2 == 0:
            seen = [dict(id=s["id"], kind=weapon, pos=[round(v, 3) for v in s["pos"]],
                         vel=[round(v, 3) for v in s["vel"]])
                    for s in shots if visible((x, y), aim_yaw, s["pos"])]
            obs = observation(tick // 2, [x, y], (vx, vy), ep["goal"], seen, [shooter], ep["zone"],
                              events, hp=hp, energy=energy)
            obs["t"] = round(now, 2)
            if not obs["self"]["in_zone"]:
                outside += 1
            action = bot.act(obs)
            log.append(plain(action))
            track.append((round(now, 2), x, y, len(seen)))
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            if action.get("aim"):
                aim_yaw = action["aim"][0]
        # shooter
        if now >= next_fire - 1e-9:
            if weapon == "mortar":
                origin = [sx, sy, sz + TUBE]
                flight = 1.0
                for _ in range(4):  # lead: where we will be when the shell lands
                    tx, ty = x + vx * flight, y + vy * flight
                    a = rng.uniform(0, math.tau)
                    target = [tx + ep.get("wide", 0.0) * math.cos(a), ty + ep.get("wide", 0.0) * math.sin(a),
                              et.ground(tx, ty)]
                    solved = launch(origin, target, ep["arc"])
                    if solved is None:
                        break
                    vel, flight = solved
                spread = rng.gauss(0, 1.5), rng.gauss(0, 1.5)
                target = [target[0] + spread[0], target[1] + spread[1], target[2]]
                solved = launch(origin, target, ep["arc"])
                if solved is not None:
                    vel, _ = solved
                    shots.append(dict(id=next_id, pos=list(origin), vel=list(vel), age=0.0))
                    next_id += 1
                next_fire = now + MORTAR["cooldown"]
            else:
                if math.dist((x, y), (sx, sy)) <= GUN["range"]:
                    yaw = lead_aim((sx, sy), (x, y), (vx, vy), GUN["speed"]) + math.radians(rng.gauss(0, GUN["spread_deg"]))
                    z0 = sz + MECH["muzzle_height"]
                    shots.append(dict(id=next_id, pos=[sx + 3 * math.cos(yaw), sy + 3 * math.sin(yaw), z0],
                                      vel=[GUN["speed"] * math.cos(yaw), GUN["speed"] * math.sin(yaw), 0.0], age=0.0))
                    next_id += 1
                next_fire = now + 0.25
        # our movement (knock-back adds to the velocity and decays under ground acceleration)
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
        start = (x, y)
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * DT_TICK
            if walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        # shots
        alive = []
        for s in shots:
            p0 = list(s["pos"])
            if weapon == "mortar":
                p1 = [p0[0] + s["vel"][0] * DT_TICK, p0[1] + s["vel"][1] * DT_TICK,
                      p0[2] + s["vel"][2] * DT_TICK - 0.5 * g * DT_TICK ** 2]
                s["vel"][2] -= g * DT_TICK
            else:
                p1 = [p0[0] + s["vel"][0] * DT_TICK, p0[1] + s["vel"][1] * DT_TICK, p0[2]]
            # direct hit: closest approach of the segment to our body axis during this tick
            rx, ry = p0[0] - start[0], p0[1] - start[1]
            wx, wy = (p1[0] - p0[0]) - (x - start[0]), (p1[1] - p0[1]) - (y - start[1])
            w2 = wx * wx + wy * wy
            f = 0.0 if w2 < 1e-12 else max(0.0, min(1.0, -(rx * wx + ry * wy) / w2))
            zf = p0[2] + f * (p1[2] - p0[2])
            reach = MECH["radius"] + (CONFIG["projectile"]["gun_radius"] if weapon == "gun" else 0.0)
            body = math.hypot(rx + f * wx, ry + f * wy) <= reach and z <= zf <= z + MECH["height"]
            landed = weapon == "mortar" and p1[2] <= et.ground(p1[0], p1[1])
            if body or landed:
                if weapon == "gun":
                    hp -= GUN["damage"]
                    direct += 1
                    events.append(dict(type="damaged", amount=GUN["damage"], weapon="gun", by=5,
                                       bearing=math.atan2(sy - y, sx - x)))
                    continue
                blast = p0 if body else p1
                d = 0.0 if body else math.dist(blast[:2], (x, y))
                damage, falloff = splash_damage(d)
                if body:
                    damage += MORTAR["damage"]
                    direct += 1
                elif damage > 0:
                    splashed += 1
                blasts.append((round(now, 2), blast[0], blast[1], math.dist(blast[:2], (x, y)), damage))
                if damage > 0:
                    hp -= damage
                    splash_total += damage
                    away = math.atan2(y - blast[1], x - blast[0])
                    vx += MORTAR["knock"] * falloff * math.cos(away)
                    vy += MORTAR["knock"] * falloff * math.sin(away)
                    energy = max(0.0, energy - MORTAR["drain"] * falloff)
                    events.append(dict(type="damaged", amount=round(damage), weapon="mortar", by=5,
                                       bearing=math.atan2(blast[1] - y, blast[0] - x)))
                continue
            s["pos"] = p1
            s["age"] += DT_TICK
            if (weapon == "mortar" and s["age"] < MORTAR["ttl"]) or (
                    weapon == "gun" and math.dist(p1[:2], (sx, sy)) <= GUN["range"]):
                alive.append(s)
        shots = alive
        if reached is None and math.dist((x, y), ep["goal"]) <= 4:
            reached = round(now, 1)
            break
    times = list(bot.times)
    bot.close()
    return dict(damage=1400.0 - hp, direct=direct, splashed=splashed, spent=spent, outside=outside,
                reached=reached, log=log, fired=next_id - 9000, track=track, blasts=blasts, times=times)


def episodes():
    home = et.HOME
    start, goal = [home[0] - 60, home[1]], [home[0] + 60, home[1]]
    assert walkable(start) and walkable(goal)
    out = []
    for distance in (60, 100, 150, 200):
        for angle, label in ((90, "abeam"), (135, "oblique")):
            a = math.radians(angle)
            shooter = [home[0] + distance * math.cos(a), home[1] + distance * math.sin(a)]
            for arc in ("low", "high"):
                out.append(dict(name=f"{distance:>3} m {label}, {arc} arc", start=start, goal=goal,
                                shooter=shooter, zone=([home[0], home[1]], 400.0), arc=arc,
                                seed=distance * 10 + angle + (arc == "high")))
    return out


def heldout_episodes(seed=91217, count=16):
    """Fresh routes elsewhere on the map, random shooter range, bearing and arc."""
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
        distance, bearing = rng.uniform(60, 200), rng.uniform(0, math.tau)
        shooter = [mid[0] + distance * math.cos(bearing), mid[1] + distance * math.sin(bearing)]
        if not walkable(shooter):
            continue
        arc = rng.choice(("low", "high"))
        out.append(dict(name=f"{distance:>3.0f} m, route {len(out) + 1}, {arc} arc", start=start, goal=goal,
                        shooter=shooter, zone=(mid, 400.0), arc=arc, seed=seed + len(out)))
    return out


def controls():
    home = et.HOME
    start, goal = [home[0] - 60, home[1]], [home[0] + 60, home[1]]
    shooter = [home[0], home[1] + 100]
    return [
        ("shells aimed 30 m wide, high arc", dict(start=start, goal=goal, shooter=shooter, arc="high",
                                                  zone=([home[0], home[1]], 400.0), wide=30.0, seed=1)),
        ("shells aimed 30 m wide, low arc", dict(start=start, goal=goal, shooter=shooter, arc="low",
                                                 zone=([home[0], home[1]], 400.0), wide=30.0, seed=2)),
        ("gun shooter only, 100 m", dict(start=start, goal=goal, shooter=shooter, arc="low", weapon="gun",
                                         zone=([home[0], home[1]], 400.0), seed=3)),
        ("shells on us, outside the zone (urgent)", dict(start=start, goal=goal, shooter=shooter, arc="high",
                                                         zone=([home[0] + 300, home[1]], 120.0), seed=4)),
    ]


def run_loop(folder, eps, title):
    print(f"\n{title:30}{'damage taken':>15}{'direct hits':>13}{'splashed':>11}{'boost energy':>15}"
          f"{'outside':>11}{'arrival s':>13}")
    print(f"{'':30}{'base | cand':>15}{'base | cand':>13}{'base | cand':>11}{'base | cand':>15}"
          f"{'base | cand':>11}{'base | cand':>13}")
    totals = {k: dict(damage=0.0, direct=0, splashed=0, spent=0.0, outside=0, missed=0, arrival=0.0, fired=0,
                      times=[]) for k in ("base", "cand")}
    for ep in eps:
        base, cand = react(folder, ep), react(ROOT, ep)
        for key, row in (("base", base), ("cand", cand)):
            t = totals[key]
            for field in ("damage", "direct", "splashed", "spent", "outside", "fired"):
                t[field] += row[field]
            t["missed"] += row["reached"] is None
            t["times"] += row["times"]
            t["arrival"] += row["reached"] if row["reached"] is not None else 30.0
        arrive = lambda r: "-" if r["reached"] is None else f"{r['reached']:.1f}"
        print(f"{ep['name']:30}{base['damage']:>7.0f} | {cand['damage']:<6.0f}{base['direct']:>5} | {cand['direct']:<5}"
              f"{base['splashed']:>4} | {cand['splashed']:<4}{base['spent']:>7.0f} | {cand['spent']:<6.0f}"
              f"{base['outside']:>4} | {cand['outside']:<4}{arrive(base):>6} | {arrive(cand):<5}")
    b, c = totals["base"], totals["cand"]
    print(f"{'total':30}{b['damage']:>7.0f} | {c['damage']:<6.0f}{b['direct']:>5} | {c['direct']:<5}"
          f"{b['splashed']:>4} | {c['splashed']:<4}{b['spent']:>7.0f} | {c['spent']:<6.0f}"
          f"{b['outside']:>4} | {c['outside']:<4}  route time {b['arrival']:.1f} | {c['arrival']:.1f} s,"
          f" unreached {b['missed']} | {c['missed']}, shells fired {b['fired']} | {c['fired']}")
    for key in ("base", "cand"):
        ms = sorted(v * 1e3 for v in totals[key]["times"])
        print(f"  {key} decision round trip: p50 {ms[len(ms) // 2]:.1f} ms, p99 {ms[int(0.99 * len(ms))]:.1f} ms,"
              f" max {ms[-1]:.1f} ms over {len(ms)} decisions (this machine)")
    return totals


def run_controls(folder):
    print(f"\n{'control (identical starts)':44}{'decisions':>11}{'differing':>11}{'damage base | cand':>22}  check")
    failures = []
    for name, ep in controls():
        base, cand = react(folder, ep), react(ROOT, ep)
        differ = sum(a != b for a, b in zip(base["log"], cand["log"])) + abs(len(base["log"]) - len(cand["log"]))
        ok = differ == 0
        print(f"{name:44}{len(base['log']):>11}{differ:>11}{base['damage']:>11.0f} | {cand['damage']:<8.0f}"
              f"  {'ok  ' if ok else 'FAIL'} identical commands")
        if not ok:
            failures.append(name)
    return failures


def run_trace(folder):
    """The first two shells of the 100 m abeam low-arc episode, decision by decision."""
    ep = next(e for e in episodes() if e["name"].startswith("100 m abeam, low"))
    rows = {key: react(where, ep) for key, where in (("base", folder), ("cand", ROOT))}
    print(f"\ntrace, {ep['name']} (shells fired at 0.3 s and 2.9 s; route runs +x):")
    print(f"{'t s':>5}  {'baseline pos / move / boost':>36}  {'candidate pos / move / boost':>36}  shells seen")
    fmt = lambda pt, act: (f"({pt[1] - ep['start'][0]:5.1f},{pt[2] - ep['start'][1]:+5.1f}) "
                           f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}] / {str(act.get('boost', False)):5}")
    for k in range(0, 46):
        a, b = rows["base"]["log"][k], rows["cand"]["log"][k]
        pa, pb = rows["base"]["track"][k], rows["cand"]["track"][k]
        print(f"{k * 0.1:>5.1f}  {fmt(pa, a):>36}  {fmt(pb, b):>36}  {pa[3]} | {pb[3]}{'' if a == b else '  <- differs'}")
    for key in ("base", "cand"):
        for t, bx, by, d, damage in rows[key]["blasts"][:2]:
            print(f"  {key}: shell bursts at t={t:.2f} s, {d:4.1f} m from our centre, {damage:.0f} damage")


def run_recording(folder):
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    bot = Bot(et.HELLO)
    for obs in et.STREAM:
        bot.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(base_bot.act(copy.deepcopy(o)) != cand_bot.act(copy.deepcopy(o)) for o in et.STREAM)
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    shells = sum(1 for o in et.STREAM for p in o["projectiles"] if p["kind"] == "mortar")
    print(f"\nrecording: {shells} mortar shell sightings; shell-dodge decisions {bot.shell_dodge.decisions},"
          f" outcomes {dict(sorted(bot.shell_dodge.counts.items())) or 'none'};"
          f" {differ} of {len(et.STREAM)} answers differ from the baseline (debug included);"
          f" round trip p99 {p99:.1f} ms")
    return differ


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    failures, trace = run_scripted(folder)
    if trace:
        obs, a, b = trace
        print(f"\ntrace, shell landing on our route: we walk at {MECH['walk_speed']} m/s; the shell lands where we"
              f" would be in 1.2 s")
        print(f"  baseline:  move {[round(v, 2) for v in a['move']]}, boost {a.get('boost')}")
        print(f"  candidate: move {[round(v, 2) for v in b['move']]}, boost {b.get('boost')}")
    for eps, title in ((episodes(), "closed loop (tuning set)"), (heldout_episodes(), "closed loop (held-out)")):
        totals = run_loop(folder, eps, title)
        if totals["cand"]["damage"] >= totals["base"]["damage"]:
            failures.append(f"{title}: no less damage taken")
        if totals["cand"]["outside"] > totals["base"]["outside"]:
            failures.append(f"{title}: more decisions outside the zone")
        if totals["cand"]["missed"] > totals["base"]["missed"]:
            failures.append(f"{title}: routes left unfinished")
    failures += run_controls(folder)
    run_trace(folder)
    if run_recording(folder):
        failures.append("recording: answers differ with no shell listed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (scripted checks and controls; closed-loop numbers are measurements)")


if __name__ == "__main__":
    main()
