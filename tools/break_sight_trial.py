"""break-sight: crossing-fire (c120041, official 2.94) and candidate as real bot processes.

    py tools/break_sight_trial.py [--baseline <git revision>]

A closed-loop gunfight near buildings, 40 s. One or two scripted gun mechs (1400 HP, the
same gun as ours: 252 m/s, 45 damage, 0.24 s cooldown, 12-round magazine, 2.4 s reload,
0.6 deg spread) lead their shots at us whenever their eye has a clear line to our body by
cover.py. "hold" shooters stand still; "hunt" shooters always know where we are (the worst
case for hiding) and walk the navigation grid toward us until they can see us. Bullets stop
at solid matter. Hits from outside our torso's front arc deal x1.5. Every mech regenerates
45 HP/s after 5 s without dealing or taking damage. Our gun fires where the bot aims (the
torso turns at the configured rate); the bot lists a shooter it can see (45 m all round, or
200 m inside the 120 deg wedge, clear line) and keeps it listed 5 s after losing sight, as
the server does. Our movement: ground acceleration, walk/boost speed, boost energy, the
navigation grid. Reports HP over time, damage taken and dealt, kills and time of death.
Controls: HP above 55% with one attacker, no attacker, an urgent zone return. Also checks
that the v8 dodge keeps the final say, and activation on the standard recording.
Standard library only.
"""
import copy
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from cover import Cover
from harness import BotProcess, export, plain
from navigation import Navigator

BASELINE = "c1200411b37163ea2496aefbb861a496d2bcea12"  # crossing-fire, official 2.94
CONFIG = et.HELLO["config"]
MECH, GUN = CONFIG["mech"], CONFIG["weapons"]["gun"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
COVER = Cover()
GRID = dt.GRID
DT = 0.05
VISION_M, NEAR_M, FOV = 200.0, 45.0, math.radians(120)


def eye(p):
    return (p[0], p[1], et.ground(*p[:2]) + MECH["eye_height"])


def body(p):
    return (p[0], p[1], et.ground(*p[:2]) + 4.5)


def sees(a, b):
    return COVER.clear(eye(a), body(b), skip_start=3.0, skip_end=2.5)


def blocked_at(origin, d, length):
    """Distance along the bullet's step to the first solid sample, or None."""
    s = 0.0
    while s <= length:
        if COVER.solid(origin[0] + s * d[0], origin[1] + s * d[1], origin[2] + s * d[2]):
            return s
        s += 1.0
    return None


def body_param(origin, d, length, centre):
    """Distance along the step where it passes through a mech body at `centre`, or None."""
    tx, ty, tz = centre[0], centre[1], et.ground(*centre[:2])
    flat2 = d[0] * d[0] + d[1] * d[1]
    s = max(0.0, min(length, ((tx - origin[0]) * d[0] + (ty - origin[1]) * d[1]) / flat2))
    px, py, pz = origin[0] + s * d[0], origin[1] + s * d[1], origin[2] + s * d[2]
    if math.hypot(px - tx, py - ty) <= MECH["radius"] + BULLET_R and tz <= pz <= tz + MECH["height"]:
        return s
    return None


def hidden_near(start, shooters, radii=(3.0, 5.0, 7.0, 10.0, 14.0, 18.0, 24.0)):
    out = []
    for r in radii:
        for k in range(16):
            a = k * math.tau / 16
            q = (start[0] + r * math.cos(a), start[1] + r * math.sin(a))
            if GRID.clear_segment(start, q) and not any(sees(s, q) for s in shooters):
                out.append(r)
    return out


def find_spot(distances, spread_deg):
    """A walkable point away from the map edge, exposed to shooters at `distances` m on
    bearings `spread_deg` apart (all on walkable ground), with at least three points hidden from
    all of them 5-24 m away (none closer than 5 m, the nearest within 12 m)."""
    for index in range(0, len(GRID.free), 7):
        if not GRID.free[index]:
            continue
        i, j = index % GRID.width, index // GRID.width
        if not (15 <= i < GRID.width - 15 and 15 <= j < GRID.height - 15):
            continue
        p = GRID.point(index)
        for bearing in range(0, 360, 20):
            shooters = []
            for n, d in enumerate(distances):
                a = math.radians(bearing + n * spread_deg)
                s = (p[0] + d * math.cos(a), p[1] + d * math.sin(a))
                if not dt.walkable(s) or not sees(s, p) or not sees(p, s):
                    break
                shooters.append(s)
            if len(shooters) != len(distances):
                continue
            near = hidden_near(p, shooters)
            if len(near) >= 3 and 5.0 <= min(near) <= 12.0 and goal_for(p, bearing) != list(p):
                return list(p), shooters, bearing
    raise RuntimeError(f"no spot for {distances}")


def goal_for(start, bearing):
    """A walkable zone goal 80-150 m away, across the line to the first shooter if possible."""
    for distance in (120, 100, 150, 80):
        for side in (90, -90, 120, -120, 150, -150, 180, 60, -60):
            a = math.radians(bearing + side)
            g = [start[0] + distance * math.cos(a), start[1] + distance * math.sin(a)]
            if dt.walkable(g):
                return g
    return list(start)


def fight(folder, start, shooter_starts, goal, hp0=1400.0, seconds=40.0, mode="hold", seed=1,
          zone=None, next_radius=250.0):
    bot = BotProcess(folder, et.HELLO)
    rng_us, rng_them = random.Random(seed), random.Random(seed + 1000)
    x, y = start
    vx = vy = 0.0
    energy, spent_at = MECH["energy"], -10.0
    hp, last_combat = hp0, -10.0
    aim = [math.atan2(goal[1] - y, goal[0] - x), 0.0]
    commanded = list(aim)
    gun = et.gun()
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    shooters = []
    for n, s in enumerate(shooter_starts):
        shooters.append(dict(id=5 + n, pos=list(s), hp=1400.0, ammo=GUN["mag"], cooldown=0.3 * n, reload=0.0,
                             last_combat=-10.0, listed_until=-1.0, alive=True, nav=Navigator()))
    zone = zone or (list(start), 400.0)
    bullets, events, actions, samples = [], [], [], {}
    move, boost, fire = [0.0, 0.0], False, [False, False]
    taken = dealt = kills = 0
    died = None
    positions = []
    for tick in range(int(seconds / DT) + 1):
        now = round(tick * DT, 2)
        for mark in (10, 20, 30, 40):
            if abs(now - mark) < 1e-6:
                samples[mark] = round(hp)
        if tick == int(seconds / DT):
            break
        # shooters move (hunt) and fire
        for s in shooters:
            if not s["alive"]:
                continue
            sx, sy = s["pos"]
            visible = math.dist((sx, sy), (x, y)) <= VISION_M and sees((sx, sy), (x, y))
            if mode == "hunt" and not visible:
                w = s["nav"].waypoint([sx, sy, et.ground(sx, sy)], [x, y])
                dx, dy = w[0] - sx, w[1] - sy
                L = math.hypot(dx, dy)
                if L > 0.5:
                    step = MECH["walk_speed"] * DT
                    nx, ny = sx + dx / L * min(step, L), sy + dy / L * min(step, L)
                    if dt.walkable((nx, ny)):
                        s["pos"] = [nx, ny]
            s["cooldown"] = max(0.0, s["cooldown"] - DT)
            if s["reload"] > 0:
                s["reload"] = max(0.0, s["reload"] - DT)
                if s["reload"] == 0:
                    s["ammo"] = GUN["mag"]
            elif visible and s["cooldown"] == 0 and s["ammo"] > 0 and math.dist(s["pos"], (x, y)) <= GUN["range"]:
                yaw = dt.lead_aim(tuple(s["pos"]), (x, y), (vx, vy), GUN["speed"]) + math.radians(rng_them.gauss(0, GUN["spread_deg"]))
                d = (math.cos(yaw), math.sin(yaw), 0.0)
                z0 = et.ground(*s["pos"]) + MECH["muzzle_height"]
                # aim down to our body height over the distance
                dist = math.dist(s["pos"], (x, y))
                dz = ((et.ground(x, y) + 4.5) - z0) / max(dist, 1.0)
                norm = math.sqrt(1 + dz * dz)
                d = (d[0] / norm, d[1] / norm, dz / norm)
                bullets.append(dict(owner=s["id"], pos=[s["pos"][0] + 3 * d[0], s["pos"][1] + 3 * d[1], z0 + 3 * d[2]],
                                    dir=d, travelled=3.0, origin=tuple(s["pos"])))
                s["ammo"] -= 1
                s["cooldown"] = GUN["cooldown"]
                if s["ammo"] == 0:
                    s["reload"] = GUN["reload"]
        # decision
        if tick % 2 == 0:
            listed = []
            for s in shooters:
                if not s["alive"]:
                    continue
                d = math.dist(s["pos"], (x, y))
                bearing = math.atan2(s["pos"][1] - y, s["pos"][0] - x)
                in_wedge = abs((bearing - aim[0] + math.pi) % math.tau - math.pi) <= FOV / 2
                if (d <= NEAR_M or (d <= VISION_M and in_wedge)) and sees((x, y), s["pos"]):
                    s["listed_until"] = now + 5.0
                if now <= s["listed_until"] + 1e-9:
                    toward = math.atan2(y - s["pos"][1], x - s["pos"][0])
                    listed.append(dict(id=s["id"], kind="mech", pos=[s["pos"][0], s["pos"][1], et.ground(*s["pos"])],
                                       vel=[0, 0, 0], aim=[toward, 0.0], hp=round(s["hp"]), max_hp=1400, cubes=0,
                                       weapons=["gun"], charging=False))
            visible_bullets = [dict(id=1000 + k, kind="gun", pos=list(b["pos"]), vel=[GUN["speed"] * c for c in b["dir"]])
                               for k, b in enumerate(bullets) if b["owner"] != 0]
            obs = dt.observation(tick // 2, [x, y], (vx, vy), goal, visible_bullets, listed, zone, events,
                                 hp=round(hp, 1), energy=energy)
            obs["t"] = now
            obs["zone"]["next_radius"] = next_radius
            obs["self"]["aim"] = list(aim)
            obs["self"]["weapons"] = [copy.deepcopy(gun), None]
            obs["alive"] = 1 + sum(s["alive"] for s in shooters)
            action = bot.act(obs)
            actions.append(plain(action))
            positions.append((now, round(x, 1), round(y, 1), round(hp), len(listed)))
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
        # torso
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        # our gun
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng_us.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng_us.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            z0 = et.ground(x, y) + MECH["muzzle_height"]
            bullets.append(dict(owner=0, pos=[x + 3 * d[0], y + 3 * d[1], z0 + 3 * d[2]], dir=d, travelled=3.0,
                                origin=(x, y)))
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # our movement
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        speed = MECH["walk_speed"]
        if boost and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            energy = max(0.0, energy - MECH["boost_drain"] * DT)
            spent_at = now
        elif now - spent_at >= MECH["energy_regen_delay"]:
            energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT)
        dvx, dvy = mx * speed - vx, my * speed - vy
        dv = math.hypot(dvx, dvy)
        limit = MECH["ground_accel"] * DT
        if dv > limit:
            dvx, dvy = dvx * limit / dv, dvy * limit / dv
        vx, vy = vx + dvx, vy + dvy
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * DT
            if dt.walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        # bullets
        alive = []
        step = GUN["speed"] * DT
        for b in bullets:
            wall = blocked_at(b["pos"], b["dir"], step)
            if b["owner"] == 0:
                hit = None
                for s in shooters:
                    if s["alive"]:
                        at = body_param(b["pos"], b["dir"], step, s["pos"])
                        if at is not None and (wall is None or at < wall) and (hit is None or at < hit[0]):
                            hit = (at, s)
                if hit:
                    s = hit[1]
                    s["hp"] -= GUN["damage"]
                    s["last_combat"] = last_combat = now
                    dealt += GUN["damage"]
                    events.append(dict(type="hit", target=s["id"], amount=GUN["damage"], weapon="gun"))
                    if s["hp"] <= 0:
                        s["alive"] = False
                        kills += 1
                        events.append(dict(type="kill", target=s["id"]))
                    continue
            else:
                at = body_param(b["pos"], b["dir"], step, (x, y))
                if at is not None and (wall is None or at < wall):
                    came_from = math.atan2(-b["dir"][1], -b["dir"][0])
                    rear = abs((came_from - aim[0] + math.pi) % math.tau - math.pi) > math.radians(MECH["front_arc_deg"] / 2)
                    amount = GUN["damage"] * (MECH["rear_mult"] if rear else 1.0)
                    hp -= amount
                    taken += amount
                    last_combat = now
                    for s in shooters:
                        if s["id"] == b["owner"]:
                            s["last_combat"] = now
                    events.append(dict(type="damaged", amount=amount, weapon="gun", by=b["owner"], rear=rear,
                                       bearing=math.atan2(b["origin"][1] - y, b["origin"][0] - x)))
                    continue
            if wall is not None:
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        bullets = alive
        # regeneration
        if now - last_combat >= MECH["regen_delay"] and hp > 0:
            hp = min(1400.0, hp + MECH["regen_per_s"] * DT)
        for s in shooters:
            if s["alive"] and now - s["last_combat"] >= MECH["regen_delay"]:
                s["hp"] = min(1400.0, s["hp"] + MECH["regen_per_s"] * DT)
        if hp <= 0:
            died = now
            break
    bot.close()
    for mark in (10, 20, 30, 40):
        samples.setdefault(mark, 0 if died is not None else round(hp))
    return dict(hp=samples, taken=round(taken), dealt=round(dealt), kills=kills, died=died, actions=actions,
                positions=positions, final=round(max(hp, 0)))


def first_below(result, frac=0.55):
    for k, (_, _, _, hp, _) in enumerate(result["positions"]):
        if hp < frac * 1400:
            return k
    return len(result["positions"])


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    one, b1 = None, None
    spots = {}
    for key, distances, spread in (("one-100", (100,), 0), ("one-60", (60,), 0), ("one-150", (150,), 0),
                                   ("two", (80, 120), 35)):
        spots[key] = find_spot(distances, spread)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; 40 s closed-loop gunfights\n")
    cases = [
        ("1 shooter 100 m, hold, our HP 50%", "one-100", "hold", 700.0, "activates"),
        ("1 shooter 100 m, hunts us, our HP 50%", "one-100", "hunt", 700.0, "activates"),
        ("1 shooter 60 m, hold, our HP 50%", "one-60", "hold", 700.0, "activates"),
        ("1 shooter 150 m, hold, our HP 50%", "one-150", "hold", 700.0, "activates"),
        ("2 shooters 80/120 m, hold, full HP", "two", "hold", 1400.0, "activates"),
        ("2 shooters 80/120 m, hunt us, full HP", "two", "hunt", 1400.0, "activates"),
        ("1 shooter 100 m, hold, full HP (control)", "one-100", "hold", 1400.0, "control-hp"),
        ("1 shooter 100 m, hunts us, full HP (control)", "one-100", "hunt", 1400.0, "control-hp"),
    ]
    print(f"{'case':44}{'HP at 10/20/30/40 s':>34}{'taken':>13}{'dealt':>13}{'kills':>9}{'died at s':>14}  check")
    print(f"{'':44}{'base | cand':>34}{'base | cand':>13}{'base | cand':>13}{'b | c':>9}{'base | cand':>14}")
    failures, trace = [], None
    totals = {"base": [0, 0, 0, 0], "cand": [0, 0, 0, 0]}
    for n, (name, key, mode, hp0, expect) in enumerate(cases):
        start, shooter_starts, bearing = spots[key]
        goal = goal_for(start, bearing)
        b = fight(folder, start, shooter_starts, goal, hp0=hp0, mode=mode, seed=500 + n)
        c = fight(ROOT, start, shooter_starts, goal, hp0=hp0, mode=mode, seed=500 + n)
        hpstr = lambda r: "/".join(str(r["hp"][m]) for m in (10, 20, 30, 40))
        died = lambda r: "-" if r["died"] is None else f"{r['died']:.1f}"
        if expect == "control-hp":
            kb, kc = first_below(b), first_below(c)
            k = min(kb, kc)
            ok = b["actions"][:k] == c["actions"][:k] and kb == kc
            text = f"identical for the {k} decisions while HP >= 55%"
        else:
            for tag, r in (("base", b), ("cand", c)):
                totals[tag][0] += r["taken"]
                totals[tag][1] += r["dealt"]
                totals[tag][2] += r["kills"]
                totals[tag][3] += r["died"] is not None
            ok = b["actions"] != c["actions"]
            text = "rule fires (measurement)"
            if trace is None and mode == "hold" and hp0 < 1400:
                trace = (name, b, c)
        print(f"{name:44}{hpstr(b):>18} | {hpstr(c):<15}{b['taken']:>6} | {c['taken']:<6}{b['dealt']:>6} | {c['dealt']:<6}"
              f"{b['kills']:>4} | {c['kills']:<3}{died(b):>7} | {died(c):<6}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    tb, tc = totals["base"], totals["cand"]
    print(f"{'activating cases, total':44}{'':34}{tb[0]:>6} | {tc[0]:<6}{tb[1]:>6} | {tc[1]:<6}{tb[2]:>4} | {tc[2]:<3}"
          f"{tb[3]:>7} | {tc[3]:<6}  (deaths)")

    # controls: no attacker; urgent zone return while losing
    start, shooter_starts, bearing = spots["one-100"]
    goal = goal_for(start, bearing)
    b = fight(folder, start, [], goal, hp0=700.0, seconds=12.0, seed=9)
    c = fight(ROOT, start, [], goal, hp0=700.0, seconds=12.0, seed=9)
    ok = b["actions"] == c["actions"]
    print(f"{'no attacker, our HP 50% (control)':44}{'':34}{'':13}{'':13}{'':9}{'':14}  {'ok  ' if ok else 'FAIL'} identical on all {len(c['actions'])} decisions")
    if not ok:
        failures.append("no attacker")
    far = [start[0] + 150 * math.cos(math.radians(bearing + 180)), start[1] + 150 * math.sin(math.radians(bearing + 180))]
    b = fight(folder, start, shooter_starts, far, hp0=700.0, seconds=6.0, seed=10, zone=(far, 40.0), next_radius=30.0)
    c = fight(ROOT, start, shooter_starts, far, hp0=700.0, seconds=6.0, seed=10, zone=(far, 40.0), next_radius=30.0)
    ok = b["actions"] == c["actions"]
    print(f"{'urgent zone return, HP 50%, shot at (control)':44}{'':34}{'':13}{'':13}{'':9}{'':14}  {'ok  ' if ok else 'FAIL'} identical on all {len(c['actions'])} decisions")
    if not ok:
        failures.append("urgent zone return")

    # the v8 dodge keeps the final say: while the rule steers (hit at 43% HP every decision),
    # a bullet on course arrives; both builds must answer it with the same dodge.
    me, sh, bearing = spots["one-100"]
    shooter = sh[0]
    goal = goal_for(me, bearing)
    mech = dict(id=5, kind="mech", pos=[shooter[0], shooter[1], et.ground(*shooter)], vel=[0, 0, 0],
                aim=[math.atan2(me[1] - shooter[1], me[0] - shooter[0]), 0.0], hp=1400, max_hp=1400, cubes=0,
                weapons=["gun"], charging=False)
    hit = dict(type="damaged", amount=45, weapon="gun", by=5, bearing=math.atan2(shooter[1] - me[1], shooter[0] - me[0]))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    steered = False
    for k in range(4):
        o = dt.observation(k, list(me), (0.0, 0.0), goal, (), [mech], events=[hit], hp=600)
        o["zone"]["next_radius"] = 250.0
        a, c = base_bot.act(copy.deepcopy(o)), cand_bot.act(copy.deepcopy(o))
        steered = steered or a["move"] != c["move"]
        rule_move = c["move"]
    o = dt.observation(4, list(me), (0.0, 0.0), goal, [dt.bullet_at(1, me, (0, 0), 150, 200)], [mech], events=[hit], hp=600)
    o["zone"]["next_radius"] = 250.0
    a, c = base_bot.act(copy.deepcopy(o)), cand_bot.act(copy.deepcopy(o))
    base_bot.close()
    cand_bot.close()
    ok = steered and a["move"] == c["move"] and math.hypot(*c["move"]) > 0.9
    print(f"{'bullet on course while the rule steers':44}{'':34}{'':13}{'':13}{'':9}{'':14}  {'ok  ' if ok else 'FAIL'}"
          f" rule steered {[round(v, 2) for v in rule_move]}; then the dodge: base {[round(v, 2) for v in a['move']]},"
          f" cand {[round(v, 2) for v in c['move']]}")
    if not ok:
        failures.append("dodge override")

    if trace:
        name, b, c = trace
        print(f"\ntrace, {name} (t, position, HP, mechs listed | move, boost, fire):")
        for k in (0, 5, 10, 15, 20, 30, 40, 60, 80, 100, 150, 200, 250, 300, 399):
            row = []
            for r in (b, c):
                if k < len(r["positions"]):
                    t, px, py, hp, n = r["positions"][k]
                    act = r["actions"][k]
                    row.append(f"({px:7.1f},{py:7.1f}) {hp:5d} {n} | [{act['move'][0]:+.2f},{act['move'][1]:+.2f}] "
                               f"{'B' if act.get('boost') else '-'} {'F' if (act.get('fire') or [0])[0] else '-'}")
                else:
                    row.append("dead".ljust(44))
            print(f"  t={k * 0.1:5.1f}  crossing-fire {row[0]:44}  break-sight {row[1]}")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    for o in et.STREAM:
        local.act(copy.deepcopy(o))
    counts = local.break_sight.counts
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    moved = other = 0
    for o in et.STREAM:
        a, c = base_bot.act(copy.deepcopy(o)), cand_bot.act(copy.deepcopy(o))
        moved += a.get("move") != c.get("move") or a.get("boost") != c.get("boost") or a.get("jump") != c.get("jump")
        rest = lambda x: {k: v for k, v in x.items() if k not in ("move", "boost", "jump", "tick", "debug")}
        other += rest(a) != rest(c)
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    worst = max(cand_bot.times) * 1e3
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: rule outcomes {dict(sorted(counts.items()))}; move/boost/jump differs on {moved},"
          f" any other command on {other} of {len(et.STREAM)}; round trip p99 {p99:.1f} ms, max {worst:.1f} ms")
    if other:
        failures.append("recording: a command other than move/boost/jump changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (HP and kills are from the simplified duel world, not placements)")


if __name__ == "__main__":
    main()
