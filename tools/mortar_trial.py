"""mortar-arc: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/mortar_trial.py [--baseline <git revision>]

A closed-loop fight with a gun and a mortar. Our mech stands still; one opponent aims at us
(so v6 shoots) and stands or walks across. The world fires what the bot's triggers ask for:
gun bullets as in tools/lead_trial.py, and mortar shells launched from the tube (height
+ 0.5) 3 m out along the torso's actual aim at 72 m/s, falling at 22 m/s^2, bursting on the
opponent's body (200 direct), on the ground, on a building (cover.i16) or after 7 s. Splash
is 160 falling to 30% at 7 m; our own splash hurts us at half. Reports shells fired, direct
hits, mortar damage, gun hits and self-damage. Standard library only.
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
MECH, GUN, MORTAR = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["weapons"]["mortar"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT, SUB = 0.05, 5
COVER = et.COVER


def clear(origin, bearing, distance):
    return et.clear_from(origin, bearing, distance)


HOME = tuple(et.HOME)
OPEN = next(b for b in range(0, 360, 5)
            if all(clear(HOME, b + d, r) for d in (-25, -12, 0, 12, 25) for r in (12, 40, 80, 120, 180)))


def path(origin, bearing, distance, speed):
    """Opponent at `distance` m on `bearing`, walking across our line at `speed` m/s."""
    b = math.radians(bearing)
    start = (origin[0] + distance * math.cos(b), origin[1] + distance * math.sin(b))
    across = (-math.sin(b), math.cos(b))
    return lambda t: ((start[0] + across[0] * speed * t, start[1] + across[1] * speed * t),
                      (across[0] * speed, across[1] * speed))


def opponent(origin, pos, vel):
    toward = math.atan2(origin[1] - pos[1], origin[0] - pos[0])
    return dict(id=5, kind="mech", pos=[pos[0], pos[1], et.ground(*pos)], vel=[vel[0], vel[1], 0.0],
                aim=[toward, 0.0], hp=1400, max_hp=1400, cubes=0, weapons=["gun", "laser"], charging=False)


def splash_to(blast, body_pos, scale=1.0):
    """Splash damage from a burst at `blast` to a mech standing at `body_pos`."""
    x, y, z = body_pos
    horizontal = max(0.0, math.dist(blast[:2], (x, y)) - MECH["radius"] * scale)
    top = z + MECH["height"] * scale
    vertical = 0.0 if z <= blast[2] <= top else min(abs(blast[2] - z), abs(blast[2] - top))
    d = math.hypot(horizontal, vertical)
    if d > MORTAR["splash_radius"]:
        return 0.0
    return MORTAR["splash"] * (1 - (1 - MORTAR["splash_edge"]) * d / MORTAR["splash_radius"])


def fight(folder, origin, motion, seconds=8.0, seed=1, mortar=True):
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    tube = dict(kind="mortar", cooldown=0.0, stats=copy.deepcopy(MORTAR)) if mortar else None
    z0 = et.ground(*origin)
    me_body = (origin[0], origin[1], z0)
    aim, commanded, fire = [0.0, 0.0], [0.0, 0.0], [False, False]
    bullets, shells = [], []
    out = dict(shells=0, direct=0, mortar_dmg=0.0, shots=0, hits=0, self_dmg=0.0)
    for tick in range(int(seconds / DT)):
        t = tick * DT
        pos, vel = motion(t)
        target = opponent(origin, pos, vel)
        if tick == 0:
            aim = [math.atan2(pos[1] - origin[1], pos[0] - origin[0]), 0.0]
            commanded = list(aim)
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [target], origin=origin, weapons=[copy.deepcopy(gun), copy.deepcopy(tube)])
            obs["t"] = round(t, 2)
            obs["self"]["aim"] = list(aim)
            action = bot.act(obs)
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        aim[1] = max(MECH["min_pitch"], min(MECH["max_pitch"], aim[1]))
        d = (math.cos(aim[1]) * math.cos(aim[0]), math.cos(aim[1]) * math.sin(aim[0]), math.sin(aim[1]))
        # gun
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            bd = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            bullets.append(dict(pos=[origin[0] + 3 * bd[0], origin[1] + 3 * bd[1], z0 + MECH["muzzle_height"] + 3 * bd[2]],
                                dir=bd, travelled=3.0))
            out["shots"] += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # mortar
        if tube is not None:
            tube["cooldown"] = max(0.0, tube["cooldown"] - DT)
            if fire[1] and tube["cooldown"] == 0:
                start = [origin[0] + 3 * d[0], origin[1] + 3 * d[1], z0 + MECH["height"] + 0.5 + 3 * d[2]]
                shells.append(dict(pos=start, vel=[MORTAR["speed"] * d[i] for i in range(3)], age=0.0))
                out["shells"] += 1
                tube["cooldown"] = MORTAR["cooldown"]
        # bullets
        alive = []
        for b in bullets:
            step = GUN["speed"] * DT
            tx, ty, tz = target["pos"]
            dx, dy, dz = b["dir"]
            s = max(0.0, min(step, ((tx - b["pos"][0]) * dx + (ty - b["pos"][1]) * dy) / (dx * dx + dy * dy)))
            px, py, pz = b["pos"][0] + s * dx, b["pos"][1] + s * dy, b["pos"][2] + s * dz
            if math.hypot(px - tx, py - ty) <= MECH["radius"] + BULLET_R and tz <= pz <= tz + MECH["height"]:
                out["hits"] += 1
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        bullets = alive
        # shells
        flying = []
        for sh in shells:
            burst = None
            for _ in range(SUB):
                h = DT / SUB
                sh["vel"][2] -= MORTAR["gravity"] * h
                sh["pos"] = [sh["pos"][i] + sh["vel"][i] * h for i in range(3)]
                sh["age"] += h
                x, y, z = sh["pos"]
                tx, ty, tz = target["pos"]
                if math.hypot(x - tx, y - ty) <= MECH["radius"] and tz <= z <= tz + MECH["height"]:
                    burst = ("direct", sh["pos"])
                    break
                if z <= et.ground(x, y) or COVER.solid(x, y, z) or sh["age"] >= MORTAR["ttl"]:
                    burst = ("ground", sh["pos"])
                    break
            if burst is None:
                flying.append(sh)
                continue
            kind, at = burst
            if kind == "direct":
                out["direct"] += 1
                out["mortar_dmg"] += MORTAR["damage"]
            else:
                out["mortar_dmg"] += splash_to(at, target["pos"])
            out["self_dmg"] += 0.5 * splash_to(at, me_body)
        shells = flying
    bot.close()
    return out


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    cover_origin, cover_bearing, cover_distance, _ = et.COVER_SPOT
    scenarios = []
    for distance in (40, 80, 120, 180):
        scenarios.append((f"standing, {distance} m", HOME, path(HOME, OPEN, distance, 0.0), True, "activates"))
    for distance in (40, 80, 120, 180):
        scenarios.append((f"walking across, {distance} m", HOME, path(HOME, OPEN, distance, 11.7), True, "activates"))
    scenarios += [
        ("standing, 12 m (too close to lob)", HOME, path(HOME, OPEN, 12, 0.0), True, "identical"),
        ("gun only, standing 80 m", HOME, path(HOME, OPEN, 80, 0.0), False, "identical"),
        ("behind a building (v6 holds fire)", cover_origin, path(cover_origin, cover_bearing, cover_distance, 0.0), True, "identical"),
    ]
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; open bearing {OPEN} deg; 8 s each\n")
    print(f"{'opponent (aiming at us)':36}{'shells':>11}{'direct':>11}{'mortar dmg':>15}{'gun hits':>13}{'self dmg':>12}  check")
    print(f"{'':36}{'base|cand':>11}{'base|cand':>11}{'base | cand':>15}{'base|cand':>13}{'base|cand':>12}")
    failures, total = [], {"base": [0.0, 0], "cand": [0.0, 0]}
    for k, (name, origin, motion, mortar, expect) in enumerate(scenarios):
        b = fight(folder, origin, motion, seed=500 + k, mortar=mortar)
        c = fight(ROOT, origin, motion, seed=500 + k, mortar=mortar)
        for key, r in (("base", b), ("cand", c)):
            total[key][0] += r["mortar_dmg"]
            total[key][1] += r["hits"]
        if expect == "identical":
            ok, text = b == c, "identical to lead-shots"
        else:
            ok = c["mortar_dmg"] >= b["mortar_dmg"] and c["self_dmg"] <= b["self_dmg"] + 1e-9
            text = "at least as much mortar damage, no more self-damage"
        print(f"{name:36}{b['shells']:>5}|{c['shells']:<5}{b['direct']:>5}|{c['direct']:<5}{b['mortar_dmg']:>7.0f} | {c['mortar_dmg']:<5.0f}"
              f"{b['hits']:>6}|{c['hits']:<6}{b['self_dmg']:>5.0f}|{c['self_dmg']:<6.0f}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    print(f"{'all scenarios':36}{'':22}{total['base'][0]:>7.0f} | {total['cand'][0]:<5.0f}{total['base'][1]:>6}|{total['cand'][1]:<6}")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(base_bot.act(copy.deepcopy(o)) != cand_bot.act(copy.deepcopy(o)) for o in et.STREAM)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: arcs aimed {getattr(local.mortar, 'arcs', 0)}, mortar trigger pressed {getattr(local.mortar, 'shells', 0)}"
          f" (we never hold a mortar there); {differ} of {len(et.STREAM)} decisions differ from the baseline")
    if differ:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
