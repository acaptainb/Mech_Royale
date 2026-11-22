"""farm-power: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/farm_trial.py [--baseline <git revision>]

Three closed loops, from the drone-hunt and crate-shoot trials plus a cube walk (vision is not
modelled: everything placed is listed, so the bot's own range, cover and timing checks decide):
- drones: a passive NPC drone (350 HP) that fights back once hit; our mech stands still and the
  world fires our gun (252 m/s, 0.24 s, 12 rounds, 2.4 s reload, 0.6 deg spread);
- crates: 300 HP crates hit by our gun; a destroyed crate lists its cube (and, half the time,
  a weapon pickup);
- cubes: our mech walks on the ground grid (walk speed, ground acceleration) toward whatever
  the bot commands; a cube within the pickup radius is collected.
Farming applies only before 180 s of match time, with no game mech listed and no mech hitting
us; the controls (beyond range, behind cover, a mech listed, a recent hit, after 180 s, an
urgent zone return) must match dodge-tuned exactly. Also reports the standard recording.
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
from harness import BotProcess, export

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
CONFIG = et.HELLO["config"]
MECH, GUN, CRATE, NPC = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["crates"], CONFIG["npc"]
CHANCE = CONFIG["loot"]["crate_weapon_chance"]
PICKUP_R = CONFIG["cubes"].get("pickup_radius", 3.5)
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT = 0.05
OPEN = next(b for b in range(0, 360, 5)
            if all(et.clear_from(et.HOME, b + d, r) for d in (-25, 0, 25) for r in (40, 60, 100, 120, 150, 170)))


def calm(obs):
    """A zone that does not shrink during the trial, so only the farming rules can differ."""
    obs["zone"].update(shrink_start=1000.0, shrink_end=1050.0)


def at3(origin, bearing, distance):
    a = math.radians(bearing)
    x, y = origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)
    return [round(x, 2), round(y, 2), round(et.ground(x, y), 2)]


def at2(origin, bearing, distance):
    return tuple(at3(origin, bearing, distance)[:2])


def hits_body(origin, direction, length, base, radius, height):
    cx, cy, cz = base
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((cx - origin[0]) * dx + (cy - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - cx, py - cy) <= radius + BULLET_R and cz <= pz <= cz + height


def crate_run(folder, origin, crate_spots, mechs=(), events0=(), seconds=12.0, seed=1, weapons=None, bot=None, t0=0.0):
    bot = bot or BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    z0 = et.ground(*origin)
    crates = [dict(id=1001 + i, pos=list(p), hp=float(CRATE["hp"])) for i, p in enumerate(crate_spots)]
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    slots = weapons or [None, None]
    aim, commanded, fire = [0.0, 0.0], [0.0, 0.0], [False, False]
    ours, events, cubes, pickups = [], list(events0), [], []
    shots, hits, destroyed, slot1_held = 0, 0, [], 0
    for tick in range(int(seconds / DT)):
        t = tick * DT
        if tick % 2 == 0:
            obs = et.frame(tick // 2, list(mechs), events, origin=origin,
                           weapons=[copy.deepcopy(gun), copy.deepcopy(slots[1])])
            obs["t"] = round(t0 + t, 2)
            calm(obs)
            obs["self"]["aim"] = list(aim)
            obs["crates"] = [dict(id=c["id"], pos=list(c["pos"]), hp=round(c["hp"])) for c in crates]
            obs["cubes"] = copy.deepcopy(cubes)
            obs["pickups"] = copy.deepcopy(pickups)
            action = bot.act(obs)
            events = []
            fire = list(action.get("fire") or [False, False])
            slot1_held += bool(fire[1:] and fire[1])
            commanded = list(action.get("aim") or commanded)
            if tick == 0:
                aim = list(commanded)
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
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            ours.append(dict(pos=[origin[0] + 3 * d[0], origin[1] + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]],
                             dir=d, travelled=3.0))
            shots += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
            gun["reload"] = GUN["reload"]
        alive = []
        for b in ours:
            step = GUN["speed"] * DT
            struck = next((c for c in crates if hits_body(b["pos"], b["dir"], step, c["pos"], CRATE["radius"],
                                                          CRATE["height"])), None)
            if struck is not None:
                hits += 1
                struck["hp"] -= GUN["damage"]
                events.append(dict(type="hit", target=struck["id"], amount=GUN["damage"], weapon="gun"))
                if struck["hp"] <= 0:
                    crates.remove(struck)
                    destroyed.append((struck["id"], round(t, 1)))
                    x, y, z = struck["pos"]
                    cubes.append(dict(id=5001 + len(cubes), pos=[x, y, z]))
                    if rng.random() < CHANCE:
                        pickups.append(dict(id=8001 + len(pickups), kind="laser", pos=[x + 1, y, z]))
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        ours = alive
    bot.close()
    return dict(shots=shots, hits=hits, destroyed=destroyed, cubes=len(cubes), pickups=len(pickups),
                slot1=slot1_held)


def drone_fight(folder, origin, drone_at, mechs=(), seconds=15.0, seed=1, bot=None, t0=0.0):
    bot = bot or BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    z0 = et.ground(*origin)
    drone = dict(id=104, kind="npc", pos=[drone_at[0], drone_at[1], et.ground(*drone_at)], vel=[0.0, 0.0, 0.0],
                 aim=[0.0, 0.0], hp=float(NPC["hp"]), max_hp=NPC["hp"])
    aggro, drone_cd, alive = False, 0.0, True
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    aim, commanded, fire = [0.0, 0.0], [0.0, 0.0], [False, False]
    ours, theirs, events, cubes = [], [], [], []
    hp, shots, hits, killed_at, decisions_firing = 1400.0, 0, 0, None, 0
    for tick in range(int(seconds / DT)):
        t = tick * DT
        if tick % 2 == 0:
            listed = ([dict(copy.deepcopy(drone), hp=round(drone["hp"]))] if alive else []) + list(mechs)
            obs = et.frame(tick // 2, listed, events, origin=origin, hp=hp, weapons=[copy.deepcopy(gun), None])
            obs["t"] = round(t0 + t, 2)
            calm(obs)
            obs["self"]["aim"] = list(aim)
            obs["cubes"] = copy.deepcopy(cubes)
            obs["projectiles"] = [dict(id=9000 + i, kind="npc", pos=list(b["pos"]), vel=[b["dir"][0] * NPC["projectile_speed"],
                                  b["dir"][1] * NPC["projectile_speed"], b["dir"][2] * NPC["projectile_speed"]])
                                  for i, b in enumerate(theirs)]
            action = bot.act(obs)
            events = []
            fire = list(action.get("fire") or [False, False])
            decisions_firing += bool(fire[0])
            commanded = list(action.get("aim") or commanded)
            if tick == 0:
                aim = list(commanded)
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
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            ours.append(dict(pos=[origin[0] + 3 * d[0], origin[1] + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]],
                             dir=d, travelled=3.0))
            shots += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # the drone
        if alive and aggro:
            dx, dy = origin[0] - drone["pos"][0], origin[1] - drone["pos"][1]
            dist = math.hypot(dx, dy)
            if dist > 30:
                step = NPC["speed"] * DT
                drone["pos"][0] += dx / dist * step
                drone["pos"][1] += dy / dist * step
                drone["pos"][2] = et.ground(drone["pos"][0], drone["pos"][1])
                drone["vel"] = [dx / dist * NPC["speed"], dy / dist * NPC["speed"], 0.0]
            else:
                drone["vel"] = [0.0, 0.0, 0.0]
            drone["aim"] = [math.atan2(dy, dx), 0.0]
            drone_cd = max(0.0, drone_cd - DT)
            if drone_cd == 0:
                yaw = math.atan2(dy, dx) + math.radians(rng.gauss(0, NPC["spread_deg"]))
                start = [drone["pos"][0], drone["pos"][1], drone["pos"][2] + NPC["height"] / 2]
                target_z = z0 + MECH["height"] / 2
                pitch = math.atan2(target_z - start[2], dist) + math.radians(rng.gauss(0, NPC["spread_deg"]))
                theirs.append(dict(pos=start, dir=(math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw),
                                                   math.sin(pitch)), travelled=0.0))
                drone_cd = NPC["cooldown"]
        # bullets
        alive_ours = []
        for b in ours:
            step = GUN["speed"] * DT
            if alive and hits_body(b["pos"], b["dir"], step, drone["pos"], NPC["radius"], NPC["height"]):
                hits += 1
                drone["hp"] -= GUN["damage"]
                aggro = True
                events.append(dict(type="hit", target=104, amount=GUN["damage"], weapon="gun"))
                if drone["hp"] <= 0:
                    alive = False
                    killed_at = round(t, 1)
                    cubes = [dict(id=5001 + i, pos=[drone["pos"][0] + i, drone["pos"][1], drone["pos"][2]])
                             for i in range(NPC["cubes"])]
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive_ours.append(b)
        ours = alive_ours
        alive_theirs = []
        for b in theirs:
            step = NPC["projectile_speed"] * DT
            if hits_body(b["pos"], b["dir"], step, [origin[0], origin[1], z0], MECH["radius"], MECH["height"]):
                hp -= NPC["damage"]
                events.append(dict(type="damaged", amount=NPC["damage"], weapon="npc", by=104,
                                   bearing=math.atan2(drone["pos"][1] - origin[1], drone["pos"][0] - origin[0])))
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= 200:
                alive_theirs.append(b)
        theirs = alive_theirs
    bot.close()
    return dict(shots=shots, hits=hits, killed_at=killed_at, cubes=len(cubes), hp_lost=round(1400 - hp))



def cube_walk(folder, origin, cube_spots, mechs=(), events0=(), seconds=20.0, t0=0.0, urgent=False):
    """Our mech walks where the bot commands on the ground grid; cubes within the pickup radius
    are collected. The zone goal is our start, so dodge-tuned stands still unless it farms."""
    bot = BotProcess(folder, et.HELLO)
    x, y = origin
    vx = vy = 0.0
    cubes = [dict(id=5001 + i, pos=list(p)) for i, p in enumerate(cube_spots)]
    collected, events = [], list(events0)
    closest = min((math.dist(p[:2], origin) for p in cube_spots), default=0.0)
    move = [0.0, 0.0]
    for tick in range(int(seconds / DT)):
        t = tick * DT
        if tick % 2 == 0:
            obs = et.frame(tick // 2, list(mechs), events, origin=(x, y))
            obs["t"] = round(t0 + t, 2)
            calm(obs)
            obs["self"]["vel"] = [vx, vy, 0.0]
            obs["cubes"] = copy.deepcopy(cubes)
            if urgent:
                obs["zone"].update(center=[origin[0], origin[1]], radius=400.0,
                                   next_center=[origin[0] + 200.0, origin[1]], next_radius=40.0,
                                   shrink_start=round(t0 + 10.0, 2), shrink_end=round(t0 + 40.0, 2))
            else:
                obs["zone"].update(next_center=[origin[0], origin[1]])
            action = bot.act(obs)
            events = []
            move = action.get("move", move)
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        dvx, dvy = mx * MECH["walk_speed"] - vx, my * MECH["walk_speed"] - vy
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
        for cube in list(cubes):
            closest = min(closest, math.dist(cube["pos"][:2], (x, y)))
            if math.dist(cube["pos"][:2], (x, y)) <= PICKUP_R:
                cubes.remove(cube)
                collected.append((cube["id"], round(t, 1)))
    bot.close()
    return dict(collected=collected, closest=round(closest, 1), end=(round(x, 1), round(y, 1)))


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    home = list(et.HOME)
    origin_c, bearing_c, distance_c, _ = et.COVER_SPOT
    far_mech = et.mech(5, OPEN + 60, 180, aim_at_us=False)
    mortar_hit = [dict(type="damaged", amount=160, weapon="mortar", by=7, bearing=None)]
    failures = []
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; open bearing {OPEN} deg\n")
    totals = {"drone kills": [0, 0], "crates destroyed": [0, 0], "cubes collected": [0, 0]}

    print(f"{'drone case (15 s)':44}{'kills':>9}{'cubes':>9}{'HP lost':>13}{'kill at s':>13}{'shots':>11}  check")
    drone_cases = [
        ("passive drone, 60 m", home, at2(home, OPEN, 60), (), 0.0, "activates"),
        ("passive drone, 120 m", home, at2(home, OPEN, 120), (), 0.0, "activates"),
        ("passive drone, 145 m", home, at2(home, OPEN, 145), (), 0.0, "measure"),
        ("passive drone, 170 m (beyond 150 m)", home, at2(home, OPEN, 170), (), 0.0, "identical"),
        ("passive drone 60 m, after 180 s", home, at2(home, OPEN, 60), (), 190.0, "identical"),
        ("passive drone 60 m, a mech listed", home, at2(home, OPEN, 60), (far_mech,), 0.0, "identical"),
        ("passive drone behind cover", list(origin_c), at2(origin_c, bearing_c, distance_c), (), 0.0, "identical"),
    ]
    for k, (name, origin, spot, mechs, t0, expect) in enumerate(drone_cases):
        b = drone_fight(folder, origin, spot, mechs, seed=500 + k, t0=t0)
        c = drone_fight(ROOT, origin, spot, mechs, seed=500 + k, t0=t0)
        kb, kc = int(b["killed_at"] is not None), int(c["killed_at"] is not None)
        totals["drone kills"][0] += kb
        totals["drone kills"][1] += kc
        ok = (b == c) if expect == "identical" else (kc > kb) if expect == "activates" else True
        text = {"identical": "identical", "activates": "kills it; dodge-tuned does not", "measure": "measurement"}[expect]
        print(f"{name:44}{kb:>4} | {kc:<3}{b['cubes']:>4} | {c['cubes']:<3}{b['hp_lost']:>6} | {c['hp_lost']:<5}"
              f"{str(b['killed_at']):>6} | {str(c['killed_at']):<5}{b['shots']:>5} | {c['shots']:<4}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    print(f"\n{'crate case (12 s)':44}{'destroyed':>11}{'cubes':>9}{'pickups':>10}{'shots':>11}  check")
    crate_cases = [
        ("crate at 60 m", home, [at3(home, OPEN, 60)], (), (), 0.0, "activates"),
        ("crate at 120 m", home, [at3(home, OPEN, 120)], (), (), 0.0, "activates"),
        ("crate at 145 m", home, [at3(home, OPEN, 145)], (), (), 0.0, "measure"),
        ("crate at 170 m (beyond 150 m)", home, [at3(home, OPEN, 170)], (), (), 0.0, "identical"),
        ("crate at 60 m, after 180 s", home, [at3(home, OPEN, 60)], (), (), 190.0, "identical"),
        ("crate at 60 m, a mech listed", home, [at3(home, OPEN, 60)], (far_mech,), (), 0.0, "identical"),
        ("crate at 60 m, unseen mech shelled us", home, [at3(home, OPEN, 60)], (), mortar_hit, 0.0, "identical"),
        ("crate behind cover", list(origin_c), [at3(origin_c, bearing_c, distance_c)], (), (), 0.0, "identical"),
    ]
    for k, (name, origin, spots, mechs, ev, t0, expect) in enumerate(crate_cases):
        seconds = 4.8 if ev else 12.0
        b = crate_run(folder, origin, spots, mechs, ev, seconds=seconds, seed=700 + k, t0=t0)
        c = crate_run(ROOT, origin, spots, mechs, ev, seconds=seconds, seed=700 + k, t0=t0)
        db, dc = len(b["destroyed"]), len(c["destroyed"])
        totals["crates destroyed"][0] += db
        totals["crates destroyed"][1] += dc
        ok = (b == c) if expect == "identical" else (dc > db) if expect == "activates" else True
        text = {"identical": "identical", "activates": "destroys it; dodge-tuned does not", "measure": "measurement"}[expect]
        print(f"{name:44}{db:>5} | {dc:<4}{b['cubes']:>4} | {c['cubes']:<3}{b['pickups']:>4} | {c['pickups']:<4}"
              f"{b['shots']:>5} | {c['shots']:<4}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    print(f"\n{'cube case (20 s, zone goal = start)':44}{'collected':>15}{'closest m':>15}  check")
    cube_cases = [
        ("cube at 50 m", home, [at3(home, OPEN, 50)], (), 0.0, False, "activates"),
        ("cube at 110 m", home, [at3(home, OPEN, 110)], (), 0.0, False, "activates"),
        ("cube at 140 m (beyond 120 m)", home, [at3(home, OPEN, 140)], (), 0.0, False, "identical"),
        ("cube at 50 m, after 180 s", home, [at3(home, OPEN, 50)], (), 190.0, False, "identical"),
        ("cube at 50 m, a mech listed", home, [at3(home, OPEN, 50)], (far_mech,), 0.0, False, "identical"),
        ("cube at 50 m, urgent zone return", home, [at3(home, OPEN, 50)], (), 0.0, True, "identical"),
    ]
    for name, origin, spots, mechs, t0, urgent, expect in cube_cases:
        b = cube_walk(folder, origin, spots, mechs, t0=t0, urgent=urgent)
        c = cube_walk(ROOT, origin, spots, mechs, t0=t0, urgent=urgent)
        nb, nc = len(b["collected"]), len(c["collected"])
        totals["cubes collected"][0] += nb
        totals["cubes collected"][1] += nc
        ok = (b == c) if expect == "identical" else (nc > nb)
        text = "identical" if expect == "identical" else "walks over and collects it"
        when = lambda r: (str(r["collected"][0][1]) + " s") if r["collected"] else "-"
        print(f"{name:44}{when(b):>8} | {when(c):<7}{b['closest']:>7} | {c['closest']:<6}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    print("\ntotals (dodge-tuned | farm-power): " + ", ".join(f"{k} {v[0]} | {v[1]}" for k, v in totals.items()))

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = 0
    for obs in et.STREAM:
        a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        strip = lambda x: {k: v for k, v in x.items() if k not in ("tick", "debug")}
        differ += strip(a) != strip(c)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: {differ} of {len(et.STREAM)} answers differ; farm decisions: drone hunt"
          f" {local.engagement.drone_hunt}, crate shoot {local.engagement.crate_shots}, cube walk {local.farm.walks}")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
