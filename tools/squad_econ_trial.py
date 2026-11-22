"""squad-econ: farm-power (8064167, official 3.25) and this tree as real bot processes.

    py tools/squad_econ_trial.py [--baseline <git revision>] [--quick]

Closed loops in a small world model: our mech walks where the bot steers it on the ground grid
(walk and boost speed, ground acceleration, boost energy), its torso turns at the turn rate, the gun
fires bullets with spread, crates (300 HP) drop a cube when destroyed, drones (350 HP) are passive
until hit, then close to 30 m and fire back, and cubes within the pickup radius are collected.
Vision follows the protocol: 45 m all round, 200 m inside the 120 degree wedge of the actual torso
yaw, lines checked on the cover raster; drones stay listed 5 s after leaving view. The bot's
debug label names its practice-mode plan, which is how activation is read back.

Cases:
- economy after 180 s (farm-power has stopped farming): a crate at 100 m, a drone at 120 m, a cube
  at 90 m; no crate or drone farming at 45 % HP or under danger; hysteresis; give-up and ban;
- zone: camping at the goal on the inner circle and standing still; zone must over loot;
- idle aim: the spin while standing, the sweep while moving, the turn to a recent hit;
- stuck: the recovery fires on time, jumps once, and is deterministic;
- mode: before 20 s, after a death we did not cause and on the standard recording, identical to
  farm-power on every decision; our own kill keeps the mode on.
Then decision timing (process round trip and in-process act()) and a fuzz pass. Standard library.
"""
import copy
import math
import random
import statistics
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from harness import BotProcess, export, plain

BASELINE = "8064167d11936561991186bf35261946ffbec33d"  # farm-power, official 3.25
CONFIG = et.HELLO["config"]
MECH, GUN, CRATE, NPC = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["crates"], CONFIG["npc"]
VISION = CONFIG["vision"]
PICKUP_R = CONFIG["cubes"].get("pickup_radius", 3.5)
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT = 0.05
HOME = list(et.HOME)


def wrap(a):
    return (a + math.pi) % math.tau - math.pi


def at3(origin, bearing, distance):
    a = math.radians(bearing)
    x, y = origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)
    return [round(x, 2), round(y, 2), round(et.ground(x, y), 2)]


def walkable_line(a, b, step=2.0):
    n = max(1, int(math.dist(a[:2], b[:2]) / step))
    return all(dt.walkable((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)) for k in range(n + 1))


def eye_clear(origin, point, lift=1.5):
    z0 = et.ground(*origin[:2]) + MECH["eye_height"]
    return et.COVER.clear([origin[0], origin[1], z0], [point[0], point[1], point[2] + lift], skip_start=0.5, skip_end=0.5)


# An open bearing from HOME: walkable and clear out to 130 m, with room on both sides.
OPEN = next(b for b in range(0, 360, 5)
            if all(walkable_line(HOME, at3(HOME, b + d, 130)) and eye_clear(HOME, at3(HOME, b + d, r))
                   for d in (-20, 0, 20) for r in (40, 90, 130)))


def calm_zone(origin=HOME):
    return dict(center=list(origin[:2]), radius=400.0, next_center=list(origin[:2]), next_radius=250.0,
                shrink_start=1000.0, shrink_end=1050.0, dps=20)


def hits_body(origin, direction, length, base, radius, height):
    cx, cy, cz = base
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((cx - origin[0]) * dx + (cy - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - cx, py - cy) <= radius + BULLET_R and cz <= pz <= cz + height


def visible(me, yaw, point, lift):
    d = math.dist(me[:2], point[:2])
    if d > VISION["range"]:
        return False
    if d > VISION["near_range"]:
        off = abs(wrap(math.atan2(point[1] - me[1], point[0] - me[0]) - yaw))
        if off > math.radians(VISION["fov_deg"]) / 2:
            return False
    return eye_clear(me, point, lift)


def world(folder, origin=HOME, t0=190.0, seconds=30.0, hp=1400.0, cubes=(), crates=(), drones=(), mechs=(),
          events=None, zone=None, alive=None, walls=(), frozen=False, spawn=None, seed=1, bot=None):
    """One closed-loop run. events: {decision index: [events]}; alive: f(t) -> (alive, [events]);
    zone: dict or f(t) -> dict; walls: [(centre, radius)] our mech cannot enter; frozen: our mech
    never moves; spawn: f(decision, world) -> [cube positions] added on that decision."""
    bot = bot or BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    x, y = origin[:2]
    vx = vy = 0.0
    energy, spent_at = MECH["energy"], -10.0
    max_hp = 1400.0
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    aim, commanded, fire, move, boost = [0.0, 0.0], [0.0, 0.0], [False, False], [0.0, 0.0], False
    cube_list = [dict(id=5001 + i, pos=list(p)) for i, p in enumerate(cubes)]
    crate_list = [dict(id=1001 + i, pos=list(p), hp=float(CRATE["hp"])) for i, p in enumerate(crates)]
    drone_list = [dict(id=104 + i, pos=list(p), home=list(p), hp=float(NPC["hp"]), aggro=False, cd=0.0,
                       seen=-99.0, vel=[0.0, 0.0, 0.0]) for i, p in enumerate(drones)]
    pickups, ours, theirs, pending = [], [], [], []
    out = dict(shots=0, hits=0, crates=[], drones=[], collected=[], jumps=0, labels=[], actions=[], aims=[],
               moves=[], track=[], hp_lost=0.0)
    next_cube = 5001 + len(cube_list)
    decision = -1
    for tick in range(int(seconds / DT)):
        t = round(t0 + tick * DT, 3)
        if tick % 2 == 0:
            decision += 1
            me = [x, y, et.ground(x, y)]
            if spawn:
                for p in spawn(decision, dict(pos=me)) or ():
                    cube_list.append(dict(id=next_cube, pos=list(p)))
                    next_cube += 1
            obs = et.frame(decision, list(mechs), (events or {}).get(decision, []) + pending, origin=(x, y), hp=hp,
                           weapons=[copy.deepcopy(gun), None])
            pending = []
            obs["tick"] = int(round(t * 20))
            obs["t"] = round(t, 2)
            obs["zone"] = copy.deepcopy(zone(t) if callable(zone) else (zone or calm_zone(origin)))
            zc, zr = obs["zone"]["center"], obs["zone"]["radius"]
            obs["self"].update(vel=[vx, vy, 0.0], aim=list(aim), energy=round(energy, 1), max_hp=max_hp,
                               cubes=len(out["collected"]), in_zone=math.dist((x, y), zc) <= zr)
            if alive:
                obs["alive"], extra = alive(t)
                obs["events"] += extra
            listed = []
            for d in drone_list:
                if d["hp"] <= 0:
                    continue
                if visible(me, aim[0], d["pos"], NPC["height"] / 2):
                    d["seen"] = t
                if t - d["seen"] <= VISION.get("memory_s", 5.0):
                    listed.append(dict(id=d["id"], kind="npc", pos=[round(v, 2) for v in d["pos"]],
                                       vel=list(d["vel"]), aim=[0.0, 0.0], hp=round(d["hp"]), max_hp=NPC["hp"]))
            obs["mechs"] = listed + copy.deepcopy(list(mechs))
            obs["crates"] = [dict(id=c["id"], pos=list(c["pos"]), hp=round(c["hp"])) for c in crate_list
                             if visible(me, aim[0], c["pos"], CRATE["height"] / 2)]
            obs["cubes"] = [copy.deepcopy(c) for c in cube_list if visible(me, aim[0], c["pos"], 0.5)]
            obs["pickups"] = [copy.deepcopy(p) for p in pickups if visible(me, aim[0], p["pos"], 0.5)]
            obs["projectiles"] = [dict(id=9000 + i, kind="npc", pos=list(b["pos"]),
                                       vel=[v * NPC["projectile_speed"] for v in b["dir"]]) for i, b in enumerate(theirs)]
            action = bot.act(obs)
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            move = list(action.get("move", move))
            boost = bool(action.get("boost"))
            out["jumps"] += bool(action.get("jump"))
            out["labels"].append((obs["t"], (action.get("debug") or {}).get("label", "")))
            out["actions"].append(plain(action))
            out["aims"].append((obs["t"], list(aim), list(commanded)))
            out["moves"].append((obs["t"], list(move)))
            out["track"].append((obs["t"], round(x, 2), round(y, 2)))
            if tick == 0:
                aim = list(commanded)
        # torso
        turn = wrap(commanded[0] - aim[0])
        aim[0] = wrap(aim[0] + max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn)))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        # legs
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        speed = MECH["walk_speed"]
        if boost and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            energy = max(0.0, energy - MECH["boost_drain"] * DT)
            spent_at = t
        elif t - spent_at >= MECH["energy_regen_delay"]:
            energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT)
        if frozen:
            vx = vy = 0.0
        else:
            dvx, dvy = mx * speed - vx, my * speed - vy
            dv = math.hypot(dvx, dvy)
            limit = MECH["ground_accel"] * DT
            if dv > limit:
                dvx, dvy = dvx * limit / dv, dvy * limit / dv
            vx, vy = vx + dvx, vy + dvy
            for axis in (0, 1):
                candidate = [x, y]
                candidate[axis] += (vx, vy)[axis] * DT
                if dt.walkable(candidate) and not any(math.dist(candidate, w[0][:2]) < w[1] for w in walls):
                    x, y = candidate
                elif axis == 0:
                    vx = 0.0
                else:
                    vy = 0.0
        z0 = et.ground(x, y)
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
            ours.append(dict(pos=[x + 3 * d[0], y + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]], dir=d, travelled=3.0))
            out["shots"] += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # drones
        for dr in drone_list:
            if dr["hp"] <= 0 or not dr["aggro"]:
                continue
            dx, dy = x - dr["pos"][0], y - dr["pos"][1]
            dist = math.hypot(dx, dy)
            if dist > 30:
                dr["pos"][0] += dx / dist * NPC["speed"] * DT
                dr["pos"][1] += dy / dist * NPC["speed"] * DT
                dr["pos"][2] = et.ground(dr["pos"][0], dr["pos"][1])
                dr["vel"] = [dx / dist * NPC["speed"], dy / dist * NPC["speed"], 0.0]
            else:
                dr["vel"] = [0.0, 0.0, 0.0]
            dr["cd"] = max(0.0, dr["cd"] - DT)
            if dr["cd"] == 0 and dist <= 90:
                yaw = math.atan2(dy, dx) + math.radians(rng.gauss(0, NPC["spread_deg"]))
                start = [dr["pos"][0], dr["pos"][1], dr["pos"][2] + NPC["height"] / 2]
                pitch = math.atan2(z0 + MECH["height"] / 2 - start[2], dist) + math.radians(rng.gauss(0, NPC["spread_deg"]))
                theirs.append(dict(pos=start, by=dr["id"], dir=(math.cos(pitch) * math.cos(yaw),
                                                                math.cos(pitch) * math.sin(yaw), math.sin(pitch)), travelled=0.0))
                dr["cd"] = NPC["cooldown"]
        # bullets
        alive_ours = []
        for b in ours:
            step = GUN["speed"] * DT
            struck = next((c for c in crate_list if hits_body(b["pos"], b["dir"], step, c["pos"], CRATE["radius"], CRATE["height"])), None)
            if struck is not None:
                out["hits"] += 1
                struck["hp"] -= GUN["damage"]
                pending.append(dict(type="hit", target=struck["id"], amount=GUN["damage"], weapon="gun"))
                if struck["hp"] <= 0:
                    crate_list.remove(struck)
                    out["crates"].append((struck["id"], round(t - t0, 1)))
                    cube_list.append(dict(id=next_cube, pos=list(struck["pos"])))
                    next_cube += 1
                continue
            drone = next((d for d in drone_list if d["hp"] > 0 and hits_body(b["pos"], b["dir"], step, d["pos"], NPC["radius"], NPC["height"])), None)
            if drone is not None:
                out["hits"] += 1
                drone["hp"] -= GUN["damage"]
                drone["aggro"] = True
                pending.append(dict(type="hit", target=drone["id"], amount=GUN["damage"], weapon="gun"))
                if drone["hp"] <= 0:
                    out["drones"].append((drone["id"], round(t - t0, 1)))
                    for k in range(NPC["cubes"]):
                        cube_list.append(dict(id=next_cube, pos=[drone["pos"][0] + k, drone["pos"][1], drone["pos"][2]]))
                        next_cube += 1
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive_ours.append(b)
        ours = alive_ours
        alive_theirs = []
        for b in theirs:
            step = NPC["projectile_speed"] * DT
            if hits_body(b["pos"], b["dir"], step, [x, y, z0], MECH["radius"], MECH["height"]):
                hp -= NPC["damage"]
                out["hp_lost"] += NPC["damage"]
                src = next(d for d in drone_list if d["id"] == b["by"])
                pending.append(dict(type="damaged", amount=NPC["damage"], weapon="npc", by=b["by"],
                                    bearing=math.atan2(src["pos"][1] - y, src["pos"][0] - x)))
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= 200:
                alive_theirs.append(b)
        theirs = alive_theirs
        # cubes
        for cube in list(cube_list):
            if math.dist(cube["pos"][:2], (x, y)) <= PICKUP_R:
                cube_list.remove(cube)
                out["collected"].append((cube["id"], round(t - t0, 1)))
                max_hp = 1400.0 * (1 + 0.04 * min(len(out["collected"]), 10))
                pending.append(dict(type="pickup", cubes=len(out["collected"])))
    bot.close()
    out["end"] = (round(x, 1), round(y, 1))
    out["times"] = list(bot.times)
    return out


def same(a, b):
    return a["actions"] == b["actions"] and a["end"] == b["end"] and a["collected"] == b["collected"]


def practice_labels(run):
    return [(t, label) for t, label in run["labels"] if label.startswith("squad")]


def first_time(run, word):
    return next((t for t, label in run["labels"] if word in label), None)


def fmt(run):
    when = lambda pairs: ",".join(f"{p[1]}" for p in pairs) or "-"
    return (f"crates {len(run['crates'])} ({when(run['crates'])} s), drones {len(run['drones'])} ({when(run['drones'])} s), "
            f"cubes {len(run['collected'])} ({when(run['collected'])} s), shots {run['shots']}, HP lost {run['hp_lost']:.0f}")


# --- scenarios ----------------------------------------------------------------------------------

def economy_cases(base, cand, report):
    crate = at3(HOME, OPEN, 100)
    drone = at3(HOME, OPEN + 15, 120)
    cube = at3(HOME, OPEN - 15, 90)
    engaged_mech = et.mech(5, OPEN + 180, 150, aim_at_us=True)
    unseen_hit = {0: [dict(type="damaged", amount=45, weapon="gun", by=9, bearing=math.radians(OPEN + 180))]}
    rows = [
        ("crate at 100 m", dict(crates=[crate], seconds=25), lambda b, c: len(c["crates"]) == 1 and not b["crates"]),
        ("drone at 120 m", dict(drones=[drone], seconds=30), lambda b, c: len(c["drones"]) == 1 and not b["drones"]),
        ("cube at 90 m", dict(cubes=[cube], seconds=20), lambda b, c: len(c["collected"]) == 1 and not b["collected"]),
        ("crate 100 m + drone 120 m, HP 45%", dict(crates=[crate], drones=[drone], hp=630.0, seconds=20),
         lambda b, c: c["shots"] == 0 and not c["crates"] and not c["drones"]),
        ("cube at 90 m, HP 45% (cubes have no HP rule)", dict(cubes=[cube], hp=630.0, seconds=20),
         lambda b, c: len(c["collected"]) == 1),
        ("crate + drone, an engaged mech listed", dict(crates=[crate], drones=[drone], mechs=[engaged_mech], seconds=20),
         lambda b, c: not c["crates"] and not c["drones"] and first_time(c, "loot") is None),
        ("crate, unseen mech hit at 0 s", dict(crates=[crate], events=unseen_hit, seconds=25),
         lambda b, c: len(c["crates"]) == 1 and (first_time(c, "loot") or 0) >= 190.0 + 4.0),
    ]
    print(f"{'economy after 180 s':44}  farm-power | squad-econ")
    for name, kw, check in rows:
        b, c = world(base, **kw), world(cand, **kw)
        ok = check(b, c)
        report(name, ok)
        extra = f"; first loot decision at {first_time(c, 'loot'):.1f} s" if "unseen" in name and first_time(c, "loot") else ""
        print(f"  {'ok  ' if ok else 'FAIL'} {name}\n        farm-power: {fmt(b)}\n        squad-econ: {fmt(c)}{extra}")


def hysteresis_cases(cand, report):
    """Cube A ahead; after 2 s cube B appears beside us. B's plain utility beats A's, but not A's
    x1.35 (keep A); in the control B beats even that (switch)."""
    a_spot = at3(HOME, OPEN, 60)
    for name, factor, expect_first in (("hysteresis keeps the current cube", math.sqrt(1.35), 5001),
                                       ("control: a decisively better cube wins", 1.8, 5002)):
        chosen = {}

        def spawn(decision, w, factor=factor, chosen=chosen):
            if decision != 20:
                return []
            me = w["pos"]
            u_a = 75.0 / (math.dist(me[:2], a_spot[:2]) + 18)
            d_b = 75.0 / (factor * u_a) - 18
            for turn in (110, -110, 140, -140, 90, -90):
                spot = at3(me, OPEN + turn, d_b)
                if walkable_line(me, spot) and eye_clear(me, spot):
                    chosen.update(d_a=math.dist(me[:2], a_spot[:2]), d_b=d_b, u_a=u_a, u_b=75.0 / (d_b + 18))
                    return [spot]
            return []

        c = world(cand, cubes=[a_spot], seconds=20, spawn=spawn)
        order = [key for key, _ in c["collected"]]
        ok = bool(order) and order[0] == expect_first and len(order) == 2
        report(name, ok)
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: at 2 s A is {chosen.get('d_a', 0):.1f} m away (utility "
              f"{chosen.get('u_a', 0):.2f}, x1.35 = {1.35 * chosen.get('u_a', 0):.2f}), B appears {chosen.get('d_b', 0):.1f} m away "
              f"(utility {chosen.get('u_b', 0):.2f}); collected {c['collected']}")


def give_up_case(cand, report):
    """A cube behind an invisible ring we cannot cross: followed for 30 s, banned for 60 s, then
    chosen again."""
    spot = at3(HOME, OPEN, 60)
    c = world(cand, cubes=[spot], walls=[(spot, 9.0)], seconds=100)
    loot = [t for t, label in c["labels"] if label.startswith("squad loot cube 5001")]
    gaps = [k for k in range(1, len(loot)) if loot[k] - loot[k - 1] > 5]
    first = loot[0] if loot else None
    stop = loot[gaps[0] - 1] if gaps else None
    again = loot[gaps[0]] if gaps else None
    ok = (first is not None and stop is not None and abs((stop - first) - 30.0) <= 0.6
          and abs((again - stop) - 60.0) <= 0.6 and not c["collected"])
    report("give-up after 30 s, banned for 60 s", ok)
    recoveries = sum(1 for k, (t, l) in enumerate(c["labels"])
                     if l == "squad unstuck" and (k == 0 or c["labels"][k - 1][1] != "squad unstuck"))
    print(f"  {'ok  ' if ok else 'FAIL'} give-up (a ring we cannot cross around the cube): followed from {first} s,"
          f" last at {stop} s ({(stop or 0) - (first or 0):.1f} s), chosen again at {again} s"
          f" ({(again or 0) - (stop or 0):.1f} s later); {recoveries} stuck recoveries meanwhile")


def zone_cases(base, cand, report):
    centre = at3(HOME, OPEN, 110)
    camp_zone = dict(center=list(HOME[:2]), radius=400.0, next_center=centre[:2], next_radius=100.0,
                     shrink_start=1000.0, shrink_end=1050.0, dps=20)
    inner = 100.0 - 30.0 - 5.0
    b, c = world(base, zone=camp_zone, seconds=20), world(cand, zone=camp_zone, seconds=20)
    end_d = math.dist(c["end"], centre[:2])
    still = [m for t, m in c["moves"][-50:]]
    standing = all(m == [0.0, 0.0] or m == [0, 0] for m in still)
    ok = abs(end_d - inner) <= 3.5 and standing and math.dist(b["end"], centre[:2]) < 5
    report("camps on the inner circle and stands still", ok)
    print(f"  {'ok  ' if ok else 'FAIL'} camp: next circle r=100 at 110 m (inner circle r={inner:.0f}); farm-power ends "
          f"{math.dist(b['end'], centre[:2]):.1f} m from the centre, squad-econ {end_d:.1f} m, standing still for the "
          f"last 5 s: {standing}")
    # Zone must over loot: 10 m outside a next circle that the shrink reaches within 4 s; a cube
    # inside the next circle 78 m away off to one side.
    cube = None
    for side in (45, -45, 60, -60):
        a = math.radians(OPEN + 180 + side)
        spot = [centre[0] + 85 * math.cos(a), centre[1] + 85 * math.sin(a)]
        spot = [round(spot[0], 2), round(spot[1], 2), round(et.ground(*spot), 2)]
        if walkable_line(HOME, spot) and dt.walkable(spot) and math.dist(spot[:2], HOME[:2]) <= 100:
            cube = spot
            break
    goal_bearing = math.atan2(centre[1] - HOME[1], centre[0] - HOME[0])

    def pressed(t, start=190.0 + 1.0):
        return dict(center=centre[:2], radius=125.0 if t <= start else max(100.0, 125.0 - 2.5 * (t - start)),
                    next_center=centre[:2], next_radius=100.0, shrink_start=start, shrink_end=start + 10.0, dps=20)

    relaxed = dict(center=centre[:2], radius=125.0, next_center=centre[:2], next_radius=100.0,
                   shrink_start=400.0, shrink_end=450.0, dps=20)
    for name, zone in (("zone must outranks loot", pressed), ("control: relaxed zone, same cube", relaxed)):
        r = world(cand, cubes=[cube], zone=zone, seconds=20)
        first_label = r["labels"][0][1]
        must = [k for k, (t, label) in enumerate(r["labels"]) if label.startswith("squad zone must")]
        loot = [k for k, (t, label) in enumerate(r["labels"]) if label.startswith("squad loot")]
        # Every zone-must decision steers toward the goal, not toward the cube.
        goal = [centre[0] + (HOME[0] - centre[0]) * inner / 110.0, centre[1] + (HOME[1] - centre[1]) * inner / 110.0]
        off = [abs(wrap(math.atan2(r["moves"][k][1][1], r["moves"][k][1][0])
                        - math.atan2(goal[1] - r["track"][k][2], goal[0] - r["track"][k][1]))) for k in must]
        first_loot = loot[0] if loot else None
        depth = (math.dist(r["track"][first_loot][1:], centre[:2]) if first_loot is not None else None)
        got = r["collected"][0][1] + 190.0 if r["collected"] else None
        if zone is pressed:
            # Loot resumes only once our own deadline is gone: 8 m inside the next circle.
            ok = (first_label.startswith("squad zone must") and off and max(off) < math.radians(15)
                  and first_loot is not None and first_loot > must[-1] and depth <= 100.0 - 8.0 + 0.5
                  and got is not None)
            print(f"  {'ok  ' if ok else 'FAIL'} {name}: {len(must)} zone-must decisions first (all within"
                  f" {math.degrees(max(off or [0])):.0f} deg of the goal, boost {sum(1 for k in must if r['actions'][k].get('boost'))});"
                  f" loot starts at {r['labels'][first_loot][0] if first_loot is not None else None} s, {depth and round(depth, 1)} m"
                  f" from the centre (safe from 92 m); cube collected at {got} s")
        else:
            ok = first_label.startswith("squad loot cube") and not must and got is not None
            print(f"  {'ok  ' if ok else 'FAIL'} {name}: first plan '{first_label}', no zone-must decisions,"
                  f" cube collected at {got} s")
        report(name, ok)


def idle_cases(cand, report):
    # Standing still: inside the inner circle with nothing around.
    r = world(cand, seconds=6)
    spins = [(t, a, c) for (t, a, c), (_, label) in zip(r["aims"], r["labels"]) if label == "squad camp"]
    exact = all(abs(wrap(c[0] - (a[0] + 0.35))) < 1e-6 and c[1] == 0.0 for t, a, c in spins)
    turned, full_turn = 0.0, None
    for (t0, a0, _), (t1, a1, _) in zip(r["aims"], r["aims"][1:]):
        turned += abs(wrap(a1[0] - a0[0]))
        if full_turn is None and turned >= math.tau:
            full_turn = round(t1 - r["aims"][0][0], 1)
    ok = len(spins) >= 55 and exact and full_turn is not None and full_turn <= 2.0
    report("spins while standing still", ok)
    print(f"  {'ok  ' if ok else 'FAIL'} standing: {len(spins)} decisions commanded actual yaw + 0.35 rad, pitch 0;"
          f" first full turn of the torso after {full_turn} s")
    # Moving: walking to a zone goal 120 m away with nothing to shoot.
    centre = at3(HOME, OPEN, 160)
    zone = dict(center=list(HOME[:2]), radius=400.0, next_center=centre[:2], next_radius=40.0,
                shrink_start=1000.0, shrink_end=1050.0, dps=20)
    r = world(cand, zone=zone, seconds=6)
    sweeps = []
    for (t, a, c), (_, m), (_, label) in zip(r["aims"], r["moves"], r["labels"]):
        if label == "squad camp walk" and math.hypot(*m) > 0.1:
            want = math.atan2(m[1], m[0]) + 1.15 * math.sin(1.3 * t)
            sweeps.append(abs(wrap(c[0] - want)) < 1e-6 and c[1] == 0.0)
    ok = len(sweeps) >= 55 and all(sweeps)
    report("sweeps while moving", ok)
    print(f"  {'ok  ' if ok else 'FAIL'} moving: {sum(sweeps)} of {len(sweeps)} walking decisions aimed at heading"
          f" + 1.15 sin(1.3 t), pitch 0")
    # A recent hit: a mortar blast from an unseen shooter (the engagement does not turn for it).
    bearing = math.radians(OPEN + 100)
    hit = {5: [dict(type="damaged", amount=120, weapon="mortar", by=9, bearing=bearing)]}
    r = world(cand, seconds=4.5, events=hit)
    facing = [abs(wrap(c[0] - bearing)) < 1e-6 for t, a, c in r["aims"][5:30]]
    after = r["aims"][31][2][0]
    ok = all(facing) and abs(wrap(after - bearing)) > 1e-3
    report("faces a hit from the last 2.5 s", ok)
    print(f"  {'ok  ' if ok else 'FAIL'} last hit: faced the blast bearing on {sum(facing)} of 25 decisions"
          f" (2.5 s), then resumed the idle aim")


def stuck_cases(cand, report):
    centre = at3(HOME, OPEN, 150)
    zone = dict(center=list(HOME[:2]), radius=400.0, next_center=centre[:2], next_radius=40.0,
                shrink_start=1000.0, shrink_end=1050.0, dps=20)
    runs = [world(cand, zone=zone, seconds=5, frozen=True) for _ in range(2)]
    r = runs[0]
    labels = [label for _, label in r["labels"]]
    starts = [k for k, label in enumerate(labels) if label == "squad unstuck" and (k == 0 or labels[k - 1] != "squad unstuck")]
    jumps = [k for k, a in enumerate(r["actions"]) if a.get("jump")]
    goal_heading = math.atan2(centre[1] - HOME[1], centre[0] - HOME[0])
    turned = [abs(wrap(math.atan2(r["actions"][k]["move"][1], r["actions"][k]["move"][0]) - goal_heading)) for k in starts]
    lengths = [sum(1 for label in labels[k:k + 6] if label == "squad unstuck") for k in starts if k + 6 <= len(labels)]
    ok = (bool(starts) and starts[0] == 8 and jumps == starts and all(n == 5 for n in lengths)
          and runs[0]["actions"] == runs[1]["actions"])
    report("stuck rule fires, jumps once, deterministic", ok)
    print(f"  {'ok  ' if ok else 'FAIL'} stuck (our mech cannot move): recoveries start on decisions {starts}"
          f" (0.1 s each), last {lengths} decisions, jump on {jumps}; random directions"
          f" {[round(math.degrees(a)) for a in turned]} deg off the route; two runs identical:"
          f" {runs[0]['actions'] == runs[1]['actions']}")


def mode_cases(base, cand, report):
    loot = dict(crates=[at3(HOME, OPEN, 100)], drones=[at3(HOME, OPEN + 15, 120)], cubes=[at3(HOME, OPEN - 15, 90)])
    rows = []
    b, c = world(base, t0=0.0, seconds=19.5, **loot), world(cand, t0=0.0, seconds=19.5, **loot)
    rows.append(("first 19.5 s of a match", same(b, c) and not practice_labels(c), b, c))
    outside = lambda t: (16 if t < 10.0 else 15, [])
    b, c = world(base, t0=0.0, seconds=60, alive=outside, **loot), world(cand, t0=0.0, seconds=60, alive=outside, **loot)
    rows.append(("a death we did not cause at 10 s, 60 s run", same(b, c) and not practice_labels(c), b, c))

    def own(t):
        return (16 if t < 25.0 else 15, [dict(type="kill", target=7)] if abs(t - 25.1) < 1e-6 else [])
    c = world(cand, t0=0.0, seconds=40, alive=own, **loot)
    late = [label for t, label in c["labels"] if t > 20.05]
    rows.append(("our own kill at 25 s (event a decision late)", all(l.startswith("squad") for l in late) and bool(late), None, c))
    flip = lambda t: (16 if t < 30.0 else 15, [])
    c = world(cand, t0=0.0, seconds=40, alive=flip, **loot)
    on = [t for t, label in c["labels"] if label.startswith("squad")]
    rows.append(("a death we did not cause at 30 s", bool(on) and min(on) > 20.0 and max(on) < 30.35, None, c))
    for name, ok, b, c in rows:
        report(name, ok)
        on = practice_labels(c)
        detail = (f"identical on all {len(c['actions'])} decisions" if b is not None and same(b, c)
                  else f"practice plan on {len(on)} decisions" + (f" ({on[0][0]}-{on[-1][0]} s)" if on else ""))
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {detail}")
    base_bot, cand_bot = BotProcess(base, et.HELLO), BotProcess(cand, et.HELLO)
    differ = 0
    for obs in et.STREAM:
        differ += plain(base_bot.act(copy.deepcopy(obs))) != plain(cand_bot.act(copy.deepcopy(obs)))
    base_bot.close()
    cand_bot.close()
    ok = differ == 0
    report("standard recording (a death we did not cause at 18 s)", ok)
    print(f"  {'ok  ' if ok else 'FAIL'} standard recording: {differ} of {len(et.STREAM)} answers differ")


# --- timing and fuzz -----------------------------------------------------------------------------

def busy_obs(rng, k, t):
    obs = et.frame(k)
    obs["t"] = round(t, 2)
    obs["tick"] = int(t * 20)
    me = obs["self"]["pos"]
    obs["self"]["vel"] = [rng.uniform(-12, 12), rng.uniform(-12, 12), 0.0]
    obs["self"]["aim"] = [rng.uniform(-math.pi, math.pi), 0.0]
    obs["mechs"] = [et.npc(100 + i, rng.uniform(0, 360), rng.uniform(20, 200)) for i in range(rng.randint(0, 12))]
    if rng.random() < 0.3:
        obs["mechs"] += [et.mech(i, rng.uniform(0, 360), rng.uniform(30, 240), aim_at_us=rng.random() < 0.5,
                                 vel=(rng.uniform(-12, 12), rng.uniform(-12, 12))) for i in range(rng.randint(1, 6))]
    obs["crates"] = [dict(id=1000 + i, pos=at3(me, rng.uniform(0, 360), rng.uniform(5, 200)), hp=300) for i in range(rng.randint(0, 20))]
    obs["cubes"] = [dict(id=5000 + i, pos=at3(me, rng.uniform(0, 360), rng.uniform(2, 150))) for i in range(rng.randint(0, 25))]
    obs["pickups"] = [dict(id=8000 + i, kind=rng.choice(["laser", "lightning", "mortar"]),
                           pos=at3(me, rng.uniform(0, 360), rng.uniform(3, 70))) for i in range(rng.randint(0, 4))]
    obs["projectiles"] = [dict(id=9000 + i, kind=rng.choice(["gun", "npc", "mortar"]),
                               pos=at3(me, rng.uniform(0, 360), rng.uniform(5, 80)),
                               vel=[rng.uniform(-250, 250), rng.uniform(-250, 250), rng.uniform(-20, 20)])
                          for i in range(rng.randint(0, 6))]
    if rng.random() < 0.2:
        obs["events"] = [dict(type="damaged", amount=45, weapon=rng.choice(["gun", "npc", "mortar", "zone"]),
                              by=rng.choice([None, 3, 104]), bearing=rng.choice([None, rng.uniform(-3, 3)]))]
    centre = at3(me, rng.uniform(0, 360), rng.uniform(0, 300))
    nr = rng.choice([380, 240, 140, 70, 25, 0])
    obs["zone"].update(center=centre[:2], radius=nr + rng.uniform(0, 200), next_center=centre[:2], next_radius=nr,
                       shrink_start=t + rng.uniform(-30, 30), shrink_end=t + rng.uniform(30, 60))
    return obs


def timing_and_fuzz(cand_times):
    import mechfight as mf
    mf.draw.label = mf.draw.line = mf.draw.point = mf.draw.text = lambda *args, **kw: None
    from bot import Bot
    rng = random.Random(4242)
    bot, times = Bot(et.HELLO), []
    for k in range(1500):
        obs = busy_obs(rng, k, 25 + 0.1 * k)
        start = time.perf_counter()
        bot.act(obs)
        times.append(time.perf_counter() - start)
    times.sort()
    cand_times = sorted(cand_times)
    pct = lambda xs, q: xs[min(len(xs) - 1, int(q * len(xs)))] * 1e3
    print(f"  process round trip over every squad-econ decision above ({len(cand_times)}): median "
          f"{pct(cand_times, 0.5):.2f} ms, p99 {pct(cand_times, 0.99):.2f} ms, max {cand_times[-1] * 1e3:.2f} ms")
    print(f"  in-process act() on 1,500 busy practice decisions (up to 12 drones, 6 mechs, 20 crates, 25 cubes,"
          f" 4 pickups, 6 projectiles): median {pct(times, 0.5):.2f} ms, p99 {pct(times, 0.99):.2f} ms, max {times[-1] * 1e3:.2f} ms")
    # Fuzz: random and malformed-but-legal observations, practice on and off, one long match.
    errors = []
    rng = random.Random(99)
    for match in range(6):
        bot = Bot(et.HELLO)
        alive = 16
        for k in range(700):
            t = 0.1 * k
            obs = busy_obs(rng, k, t)
            if rng.random() < 0.01:
                alive -= 1
                if rng.random() < 0.5:
                    obs["events"] = list(obs.get("events") or []) + [dict(type="kill", target=rng.randint(0, 15))]
            obs["alive"] = max(1, alive)
            if rng.random() < 0.05:
                obs["self"]["hp"] = rng.uniform(1, 1400)
            if rng.random() < 0.05:
                obs["self"]["weapons"] = [None, None]
            if rng.random() < 0.05:
                obs["self"]["grounded"] = False
            if rng.random() < 0.03:
                obs["zone"]["shrink_end"] = obs["zone"]["shrink_start"]
            if rng.random() < 0.02:
                obs["self"]["pos"] = [rng.uniform(-600, 600), rng.uniform(-400, 400), rng.uniform(-10, 60)]
            try:
                action = bot.act(obs)
                import json
                json.dumps(action)
                for key in ("move", "aim"):
                    if key in action and not all(math.isfinite(v) for v in action[key]):
                        raise ValueError(f"non-finite {key}: {action[key]}")
            except Exception:
                errors.append((match, k, traceback.format_exc(limit=3)))
    print(f"  fuzz: 6 matches x 700 random decisions (t 0-70 s, deaths with and without our kill events),"
          f" {len(errors)} exceptions or non-finite outputs")
    for e in errors[:3]:
        print("   ", e)
    return pct(times, 0.99), times[-1] * 1e3, not errors


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    base = export(revision)
    failures, table = [], []

    def report(name, ok):
        table.append((name, ok))
        if not ok:
            failures.append(name)

    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; open bearing {OPEN} deg\n")
    economy_cases(base, ROOT, report)
    print("\nhysteresis and give-up (squad-econ only; farm-power does not farm after 180 s)")
    hysteresis_cases(ROOT, report)
    give_up_case(ROOT, report)
    print("\nzone")
    zone_cases(base, ROOT, report)
    print("\nidle aim")
    idle_cases(ROOT, report)
    print("\nstuck")
    stuck_cases(ROOT, report)
    print("\nmode")
    mode_cases(base, ROOT, report)
    print("\ntiming and fuzz")
    p99, worst, clean = timing_and_fuzz(TIMES)
    report("in-process p99 under 8 ms", p99 < 8.0)
    report("fuzz: no exceptions", clean)
    print("\nsummary")
    for name, ok in table:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


TIMES = []
_world = world


def world(folder, *args, **kw):  # noqa: F811 - wraps the closed loop to collect candidate timings
    out = _world(folder, *args, **kw)
    if Path(folder) == ROOT:
        TIMES.extend(out["times"])
    return out


if __name__ == "__main__":
    main()
