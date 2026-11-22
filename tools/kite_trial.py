"""kite-distance: mortar-dodge + crossing-fire (4f4596e, official 3.04) and candidate as real bot processes.

    py tools/kite_trial.py [--baseline <git revision>]

A closed-loop fight on the open lawn. Our mech walks a 120 m route inside a large zone while
one house mech starts 90 m away and walks at us (11.7 m/s) until its standoff distance,
shooting with one weapon:
  gun        252 m/s led bullets, 0.24 s, 12-round magazine, 2.4 s reload, 0.6 deg spread
  lightning  60 damage every 0.25 s within 45 m (its aim is always on us, the lawn is open)
  mortar     72 m/s shell lobbed at where we stand when it fires, 200 direct + 160 splash
             falling to 30% at 7 m, every 2.6 s
Our gun fires when the bot holds the trigger, from our moving position along the torso's actual
aim (turn rates from the config), with seeded spread (the same draws for both bots). Movement,
acceleration, boost energy, walls (ground grid), regeneration after 5 s without damage, and
both mechs' HP follow the commands. Controls: an attacker holding at 100 m, a passive mech
passing 50 m to the side, and an urgent zone return. Also compares the standard recording:
only move, boost and jump may differ. Standard library only.
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
from harness import BotProcess, export, plain
from navigation import Navigator

BASELINE = "4f4596e12bf916fe76039a7e75652cf4036d35f4"  # mortar-dodge + crossing-fire, official 3.04
CONFIG = et.HELLO["config"]
MECH, GUN = CONFIG["mech"], CONFIG["weapons"]["gun"]
LIGHTNING, MORTAR = CONFIG["weapons"]["lightning"], CONFIG["weapons"]["mortar"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
GRID = Navigator()
DT = 0.05
SECONDS = 25.0
HOME = list(et.HOME)


def walkable(point):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


def route():
    """A heading from HOME whose 120 m route is clear on the ground grid."""
    for bearing in range(0, 360, 5):
        a = math.radians(bearing)
        goal = [HOME[0] + 120 * math.cos(a), HOME[1] + 120 * math.sin(a)]
        if GRID.clear_segment(HOME, goal) and walkable(goal):
            return bearing, goal
    raise RuntimeError("no clear route")


HEADING, GOAL = route()


def lead_yaw(origin, target, vel, speed):
    rx, ry = target[0] - origin[0], target[1] - origin[1]
    a = vel[0] ** 2 + vel[1] ** 2 - speed ** 2
    b = 2 * (rx * vel[0] + ry * vel[1])
    c = rx * rx + ry * ry
    disc = b * b - 4 * a * c
    t = 0.0
    if disc >= 0 and abs(a) > 1e-9:
        roots = [r for r in ((-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)) if r > 0]
        t = min(roots) if roots else 0.0
    return math.atan2(ry + vel[1] * t, rx + vel[0] * t)


def body_hit(origin, direction, length, centre, radius):
    """Does the flat segment from origin along direction for length pass within radius of centre?"""
    dx, dy = direction
    s = max(0.0, min(length, (centre[0] - origin[0]) * dx + (centre[1] - origin[1]) * dy))
    return math.hypot(origin[0] + s * dx - centre[0], origin[1] + s * dy - centre[1]) <= radius


# name, weapon, start bearing relative to the route (deg), start distance, standoff, passive, urgent
CASES = [
    ("gun attacker, ahead", "gun", 0, 90, 30, False, False, "activates"),
    ("gun attacker, abeam", "gun", 90, 90, 30, False, False, "activates"),
    ("gun attacker, behind (measurement)", "gun", 180, 90, 30, False, False, "measure"),
    ("lightning attacker, abeam", "lightning", 90, 90, 20, False, False, "activates"),
    ("lightning attacker, ahead", "lightning", 0, 90, 20, False, False, "activates"),
    ("mortar attacker, abeam", "mortar", 90, 90, 60, False, False, "activates"),
    ("gun attacker holding at 100 m (control)", "gun", 90, 110, 100, False, False, "identical"),
    ("passive mech passing 50 m to the side (control)", None, None, None, None, True, False, "identical"),
    ("gun attacker 50 m, urgent zone return (control)", "gun", 90, 50, 30, False, True, "identical"),
]


def fight(folder, case, seed, log=None):
    name, weapon, rel, start_d, standoff, passive, urgent, _ = case
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    x, y = HOME
    vx = vy = 0.0
    energy, spent_at = MECH["energy"], -10.0
    hp, quiet_since = float(MECH["hp"]), 0.0
    aim, commanded = [math.radians(HEADING), 0.0], [math.radians(HEADING), 0.0]
    h = math.radians(HEADING)
    along, across = (math.cos(h), math.sin(h)), (-math.sin(h), math.cos(h))
    if passive:
        # walks the opposite way along a line 50 m to the side, starting 120 m ahead
        ox, oy = HOME[0] + 120 * along[0] + 50 * across[0], HOME[1] + 120 * along[1] + 50 * across[1]
    else:
        a = h + math.radians(rel)
        ox, oy = HOME[0] + start_d * math.cos(a), HOME[1] + start_d * math.sin(a)
    o_hp, ovx, ovy = 1400.0, 0.0, 0.0
    if urgent:
        # far enough that we stay outside the circle for the whole fight: the return stays urgent
        far = [HOME[0] + 700 * along[0], HOME[1] + 700 * along[1]]
        zone = dict(center=far, radius=150.0, next_center=list(far), next_radius=100.0)
    else:
        zone = dict(center=list(HOME), radius=400.0, next_center=list(GOAL), next_radius=250.0)
    zone.update(shrink_start=1000.0, shrink_end=1050.0, dps=20)
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    o_gun = dict(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    o_next = 0.5  # the opponent opens fire half a second in
    ours, theirs, shells, events = [], [], [], []
    hits_dealt = hits_taken = 0
    damage_taken, closest, outside = 0.0, math.inf, 0
    fire, move, boost = [False, False], [0.0, 0.0], False
    killed = died = None
    next_id = 9000
    for tick in range(int(SECONDS / DT)):
        now = tick * DT
        # the opponent walks at us until its standoff, or along its passing line
        if passive:
            ovx, ovy = -MECH["walk_speed"] * along[0], -MECH["walk_speed"] * along[1]
        else:
            d = math.dist((ox, oy), (x, y))
            if d > standoff + 0.5:
                ovx, ovy = MECH["walk_speed"] * (x - ox) / d, MECH["walk_speed"] * (y - oy) / d
            else:
                ovx = ovy = 0.0
        ox, oy = ox + ovx * DT, oy + ovy * DT
        toward_us = math.atan2(y - oy, x - ox)
        o_aim = toward_us + (math.pi / 2 if passive else 0.0)
        distance = math.dist((ox, oy), (x, y))
        closest = min(closest, distance)
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [], events, origin=[x, y], hp=round(hp))
            obs["t"] = round(now, 2)
            obs["self"].update(pos=[x, y, et.ground(x, y)], vel=[vx, vy, 0.0], energy=energy,
                               aim=list(aim), weapons=[copy.deepcopy(gun), None])
            obs["zone"] = copy.deepcopy(zone)
            obs["self"]["in_zone"] = math.dist((x, y), zone["center"]) <= zone["radius"]
            obs["mechs"] = [dict(id=5, kind="mech", pos=[ox, oy, et.ground(ox, oy)], vel=[ovx, ovy, 0.0],
                                 aim=[o_aim, 0.0], hp=round(o_hp), max_hp=1400, cubes=0,
                                 weapons=[weapon or "gun"], charging=False)]
            obs["projectiles"] = [dict(id=b["id"], kind="gun", pos=list(b["pos"]), vel=list(b["vel"]))
                                  for b in theirs]
            if not obs["self"]["in_zone"]:
                outside += 1
            action = bot.act(obs)
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if log is not None and tick % 20 == 0:
                log.append((round(now, 1), round(distance), [round(v, 2) for v in move], boost, any(fire), round(hp)))
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
        # --- the opponent shoots
        if not passive and now >= o_next - 1e-9:
            if weapon == "gun" and distance <= GUN["range"]:
                if o_gun["reload"] <= 0 and o_gun["ammo"] > 0:
                    yaw = lead_yaw((ox, oy), (x, y), (vx, vy), GUN["speed"]) + math.radians(rng.gauss(0, GUN["spread_deg"]))
                    theirs.append(dict(id=next_id, pos=[ox + 3 * math.cos(yaw), oy + 3 * math.sin(yaw), et.ground(ox, oy) + 7],
                                       vel=[GUN["speed"] * math.cos(yaw), GUN["speed"] * math.sin(yaw), 0.0],
                                       origin=(ox, oy)))
                    next_id += 1
                    o_gun["ammo"] -= 1
                    if o_gun["ammo"] == 0:
                        o_gun["reload"] = GUN["reload"]
                    o_next = now + GUN["cooldown"]
            elif weapon == "lightning" and distance <= LIGHTNING["range"]:
                damage_taken += LIGHTNING["damage"]
                hp -= LIGHTNING["damage"]
                hits_taken += 1
                quiet_since = now
                events.append(dict(type="damaged", amount=LIGHTNING["damage"], weapon="lightning", by=5,
                                   bearing=math.atan2(oy - y, ox - x)))
                o_next = now + LIGHTNING["cooldown"]
            elif weapon == "mortar" and distance <= MORTAR["speed"] ** 2 / MORTAR["gravity"] - 1:
                ratio = min(1.0, distance * MORTAR["gravity"] / MORTAR["speed"] ** 2)
                pitch = 0.5 * math.asin(ratio)
                flight = 2 * MORTAR["speed"] * math.sin(pitch) / MORTAR["gravity"]
                shells.append(dict(at=(x, y), land=now + flight))
                o_next = now + MORTAR["cooldown"]
        if o_gun["reload"] > 0:
            o_gun["reload"] = max(0.0, o_gun["reload"] - DT)
            if o_gun["reload"] == 0:
                o_gun["ammo"] = GUN["mag"]
        # --- our movement
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
            if walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        # --- our torso and gun
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            ours.append(dict(pos=[x + 3 * math.cos(yaw), y + 3 * math.sin(yaw)], dir=(math.cos(yaw), math.sin(yaw)),
                             travelled=3.0))
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # --- bullets fly (flat: both mechs stand on the same lawn)
        step = GUN["speed"] * DT
        alive = []
        for b in ours:
            if body_hit(b["pos"], b["dir"], step, (ox, oy), MECH["radius"] + BULLET_R):
                hits_dealt += 1
                o_hp -= GUN["damage"]
                quiet_since = now
                events.append(dict(type="hit", target=5, amount=GUN["damage"], weapon="gun"))
                continue
            b["pos"] = [b["pos"][0] + b["dir"][0] * step, b["pos"][1] + b["dir"][1] * step]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        ours = alive
        alive = []
        for b in theirs:
            d = (b["vel"][0] / GUN["speed"], b["vel"][1] / GUN["speed"])
            if body_hit(b["pos"], d, step, (x, y), MECH["radius"] + BULLET_R):
                hits_taken += 1
                damage_taken += GUN["damage"]
                hp -= GUN["damage"]
                quiet_since = now
                events.append(dict(type="damaged", amount=GUN["damage"], weapon="gun", by=5,
                                   bearing=math.atan2(b["origin"][1] - y, b["origin"][0] - x)))
                continue
            b["pos"] = [b["pos"][0] + d[0] * step, b["pos"][1] + d[1] * step, b["pos"][2]]
            if math.dist(b["pos"][:2], b["origin"]) <= GUN["range"]:
                alive.append(b)
        theirs = alive
        landed = [s for s in shells if s["land"] <= now + 1e-9]
        shells = [s for s in shells if s["land"] > now + 1e-9]
        for s in landed:
            d = math.dist(s["at"], (x, y))
            amount = MORTAR["damage"] if d <= MECH["radius"] else 0.0
            if d <= MORTAR["splash_radius"] + MECH["radius"]:
                edge = max(0.0, d - MECH["radius"]) / MORTAR["splash_radius"]
                amount += MORTAR["splash"] * (1 - (1 - MORTAR["splash_edge"]) * min(1.0, edge))
            if amount:
                hits_taken += 1
                damage_taken += amount
                hp -= amount
                quiet_since = now
                events.append(dict(type="damaged", amount=round(amount), weapon="mortar", by=5, bearing=None))
        # --- regeneration after 5 s without dealing or taking damage
        if now - quiet_since >= MECH["regen_delay"] and hp < MECH["hp"]:
            hp = min(float(MECH["hp"]), hp + MECH["regen_per_s"] * DT)
        if o_hp <= 0 and killed is None:
            killed = round(now, 1)
            break
        if hp <= 0 and died is None:
            died = round(now, 1)
            break
    bot.close()
    return dict(closest=round(closest, 1), taken=round(damage_taken), hits_taken=hits_taken, hits=hits_dealt,
                killed=killed, died=died, hp=round(hp), outside=outside,
                left=round(math.dist((x, y), zone["next_center"]), 1))


def recording(folder):
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    kited = []
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
        if getattr(local, "kite", None) is not None and local.kite.active:
            kited.append(obs["t"])
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    moved = other = 0
    trace = []
    for obs in et.STREAM:
        a, c = plain(base_bot.act(copy.deepcopy(obs))), plain(cand_bot.act(copy.deepcopy(obs)))
        keep = lambda x: {k: v for k, v in x.items() if k not in ("move", "boost", "jump")}
        moved += a != c
        other += keep(a) != keep(c)
        if a != c and len(trace) < 4:
            m = obs["mechs"][0] if obs["mechs"] else None
            d = round(math.dist(m["pos"][:2], obs["self"]["pos"][:2])) if m else None
            trace.append((obs["t"], d, a.get("move"), c.get("move"), a.get("boost"), c.get("boost")))
    base_bot.close()
    cand_bot.close()
    return kited, moved, other, trace, dict(sorted(getattr(local, "kite").counts.items())) if hasattr(local, "kite") else {}


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; route heading {HEADING} deg,"
          f" {SECONDS:.0f} s per fight, opponent 1400 HP\n")
    head = (f"{'case':48}{'closest m':>13}{'damage taken':>15}{'our hits':>11}{'kill s':>11}"
            f"{'HP left':>13}{'outside':>9}{'to goal m':>13}  check")
    print(head)
    print(f"{'':48}{'base | kite':>13}{'base | kite':>15}{'base|kite':>11}{'base|kite':>11}"
          f"{'base | kite':>13}{'b | k':>9}{'base | kite':>13}")
    failures, sums = [], {"base": [0, 0, 0], "cand": [0, 0, 0]}
    results = []
    for k, case in enumerate(CASES):
        base, cand = fight(folder, case, 500 + k), fight(ROOT, case, 500 + k)
        results.append((case, base, cand))
        expect = case[-1]
        if expect == "identical":
            ok, text = base == cand, "identical"
        elif expect == "measure":
            ok, text = cand["outside"] <= base["outside"], "measurement, no extra zone exits"
        else:
            ok = cand["closest"] > base["closest"] and cand["outside"] <= base["outside"]
            text = "keeps more distance, no extra zone exits"
            for key, row in (("base", base), ("cand", cand)):
                sums[key][0] += row["taken"]
                sums[key][1] += row["hits"]
                sums[key][2] += row["killed"] is not None
        kill = lambda r: "-" if r["killed"] is None else f"{r['killed']:.0f}"
        hp = lambda r: f"dead {r['died']:.0f}s" if r["died"] is not None else str(r["hp"])
        print(f"{case[0]:48}{base['closest']:>6.0f} | {cand['closest']:<5.0f}{base['taken']:>7} | {cand['taken']:<6}"
              f"{base['hits']:>5}|{cand['hits']:<5}{kill(base):>5}|{kill(cand):<5}{hp(base):>6} | {hp(cand):<6}"
              f"{base['outside']:>4}|{cand['outside']:<4}{base['left']:>6.0f} | {cand['left']:<6.0f}"
              f"{'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(case[0])
    b, c = sums["base"], sums["cand"]
    print(f"{'activating cases, total':48}{'':13}{b[0]:>7} | {c[0]:<6}{b[1]:>5}|{c[1]:<5}{b[2]:>5}|{c[2]:<5}")

    case = next(c for c in CASES if c[0].startswith("lightning attacker, abeam"))
    k = CASES.index(case)
    base_log, cand_log = [], []
    fight(folder, case, 500 + k, base_log)
    fight(ROOT, case, 500 + k, cand_log)
    print(f"\ntrace, {case[0]} (every 1 s): distance m, move, boost, firing, our HP")
    for (t, d, m, b, f, h), (_, d2, m2, b2, f2, h2) in zip(base_log, cand_log):
        print(f"  t={t:4.1f}  baseline      {d:>3} m move {m} boost {b!s:5} fire {f!s:5} HP {h:<5}"
              f"  kite {d2:>3} m move {m2} boost {b2!s:5} fire {f2!s:5} HP {h2}")

    kited, moved, other, trace, counts = recording(folder)
    print(f"\nrecording: kite rule set the move on {len(kited)} of {len(et.STREAM)} decisions"
          f" (t = {', '.join(f'{t:.1f}' for t in kited)}); outcomes {counts}")
    print(f"  any command differs from the baseline on {moved}; anything other than move, boost, jump on {other}")
    for t, d, a, c, ba, bc in trace:
        fmt = lambda m: "[" + ",".join(f"{v:+.2f}" for v in m) + "]" if m else str(m)
        print(f"  t={t:4.1f}  mech {d} m: baseline move {fmt(a)} boost {ba}; kite move {fmt(c)} boost {bc}")
    if other:
        failures.append("recording: a command other than move, boost or jump changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (damage, hits and kill times are measurements)")


if __name__ == "__main__":
    main()
