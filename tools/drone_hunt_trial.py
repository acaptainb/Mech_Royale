"""drone-hunt: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/drone_hunt_trial.py [--baseline <git revision>]

A closed-loop fight with one NPC drone. Our mech stands still; the world fires our gun when
the bot holds the trigger (252 m/s, 0.24 s, 12-round magazine, 2.4 s reload, 0.6 deg spread,
torso turning at the configured rates). The drone is passive until a bullet hits it; then it
closes to 30 m at its configured speed and shoots one 90 m/s bullet per cooldown (2.5 deg
spread) at our body, 25 damage each. 45 damage per hit; at 0 HP it drops its 2 cubes.
Reports drone kills, cubes dropped, HP we lost and the time of the kill. Standard library only.
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
from harness import BotProcess, export

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90
CONFIG = et.HELLO["config"]
MECH, GUN, NPC = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["npc"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT = 0.05
OPEN = next(b for b in range(0, 360, 5)
            if all(et.clear_from(et.HOME, b + d, r) for d in (-25, 0, 25) for r in (40, 60, 100, 150)))


def hits_body(origin, direction, length, centre, radius, height):
    cx, cy, cz = centre
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((cx - origin[0]) * dx + (cy - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - cx, py - cy) <= radius + BULLET_R and cz <= pz <= cz + height


class Local:
    """The candidate in-process, logging each decision's engagement reason for the trace."""

    def __init__(self):
        import mechfight as mf
        mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
        from bot import Bot
        self.bot, self.log = Bot(et.HELLO), []

    def act(self, obs):
        action = self.bot.act(copy.deepcopy(obs))
        decision = self.bot.engagement.decision
        drone = next((m for m in obs["mechs"] if m["kind"] == "npc"), None)
        self.log.append(dict(t=obs["t"], hp=obs["self"]["hp"], target=decision.get("target"),
                             reason=decision.get("reason"), fire=bool((action.get("fire") or [False])[0]),
                             drone_m=None if drone is None else round(math.dist(drone["pos"], obs["self"]["pos"]), 1),
                             drone_hp=None if drone is None else drone["hp"], cubes=len(obs["cubes"])))
        return action

    def close(self):
        pass


def fight(folder, origin, drone_at, mechs=(), seconds=15.0, seed=1, bot=None):
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
            obs["t"] = round(t, 2)
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


def at(origin, bearing, distance):
    a = math.radians(bearing)
    return (origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a))


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    home = list(et.HOME)
    origin_c, bearing_c, distance_c, _ = et.COVER_SPOT
    far_mech = et.mech(5, OPEN + 60, 180, aim_at_us=False)
    cases = [
        ("lone passive drone, 60 m", home, at(home, OPEN, 60), (), "activates"),
        ("lone passive drone, 85 m", home, at(home, OPEN, 85), (), "activates"),
        ("passive drone, 120 m (beyond 90 m)", home, at(home, OPEN, 120), (), "identical"),
        ("passive drone 60 m, a mech listed", home, at(home, OPEN, 60), (far_mech,), "identical"),
        ("passive drone behind cover", list(origin_c), at(origin_c, bearing_c, distance_c), (), "identical"),
    ]
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; 15 s each\n")
    print(f"{'case':40}{'drone kills':>13}{'cubes':>10}{'HP lost':>12}{'kill at s':>12}{'shots':>12}  check")
    print(f"{'':40}{'base | cand':>13}{'b | c':>10}{'base | cand':>12}{'base | cand':>12}{'base | cand':>12}")
    failures = []
    for k, (name, origin, drone_at, mechs, expect) in enumerate(cases):
        base = fight(folder, origin, drone_at, mechs, seed=500 + k)
        cand = fight(ROOT, origin, drone_at, mechs, seed=500 + k)
        if expect == "identical":
            ok, text = base == cand, "identical"
        else:
            ok = cand["killed_at"] is not None and base["killed_at"] is None
            text = "kills the drone the baseline ignores"
        kill = lambda r: "-" if r["killed_at"] is None else f"{r['killed_at']:.1f}"
        print(f"{name:40}{int(base['killed_at'] is not None):>6} | {int(cand['killed_at'] is not None):<5}"
              f"{base['cubes']:>5} | {cand['cubes']:<3}{base['hp_lost']:>6} | {cand['hp_lost']:<5}"
              f"{kill(base):>6} | {kill(cand):<5}{base['shots']:>6} | {cand['shots']:<5}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    name, origin, drone_at, mechs, _ = cases[0]
    local = Local()
    result = fight(ROOT, origin, drone_at, mechs, seed=500, bot=local)
    print(f"\ntrace ({name}, candidate in-process, same seed; kill at {result['killed_at']} s):")
    print(f"{'t':>5}{'drone m':>9}{'drone hp':>10}{'our hp':>8}  {'target':8}{'fire':6}reason")
    shown, last = 0, None
    for row in local.log:
        if row["reason"] != last or row["t"] in (0.0, 0.5, 1.0, 1.5) or (row["drone_hp"] is None and shown < 99):
            print(f"{row['t']:>5.1f}{str(row['drone_m']):>9}{str(row['drone_hp']):>10}{row['hp']:>8.0f}  "
                  f"{str(row['target']):8}{str(row['fire']):6}{row['reason']}" + (f"  (cubes listed {row['cubes']})"
                                                                                if row["cubes"] else ""))
            if row["drone_hp"] is None:
                shown = 99
        last = row["reason"]

    from bot import Bot
    local = Bot(et.HELLO)
    drones = 0
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
        drones += any(m.get("kind") == "npc" for m in obs["mechs"])
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(base_bot.act(copy.deepcopy(o)) != cand_bot.act(copy.deepcopy(o)) for o in et.STREAM)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: decisions listing a drone {drones}; drone-hunt decisions {local.engagement.drone_hunt};"
          f" decisions answered differently (debug included) {differ}")
    if differ:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
