"""lead-shots: baseline (3b290b0, official 2.63) and candidate as real bot processes.

    py tools/lead_trial.py [--baseline <git revision>]

A closed-loop gunfight. Our mech stands still and shoots at one opponent who aims at us (so
v6 always fires) and moves on a scripted path. The world fires the gun when the bot holds the
trigger: 252 m/s bullets, one per 0.24 s, 12-round magazine with a 2.4 s reload, 0.6 deg
spread from one seeded generator per scenario (the same draws for both bots). Bullets leave
3 m out along the torso's actual aim, which turns at the configured rates. A hit is a
bullet passing within the opponent's radius plus the bullet radius, at body height. Also
checks that a full laser is still released onto a moving opponent, and counts how often the
aim was led on the standard recording. Standard library only.
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

BASELINE = "3b290b0b87bee98c418a74546671c82dd232c2d0"  # v8 + v7, official 2.63
CONFIG = et.HELLO["config"]
MECH, GUN, LASER = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["weapons"]["laser"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT = 0.05
HOME = list(et.HOME)
OPEN = next(b for b in range(0, 360, 5) if all(et.clear_from(et.HOME, b + d, r) for d in (-25, 0, 25) for r in (60, 100, 150)))


def path(distance, speed, angle_deg, flip_s=None):
    """Opponent position over time: starts `distance` m away on the open bearing, moving at
    `speed` m/s, `angle_deg` from crossing (0 = straight across, 90 = straight at us),
    reversing every `flip_s` seconds if given."""
    b = math.radians(OPEN)
    start = (HOME[0] + distance * math.cos(b), HOME[1] + distance * math.sin(b))
    across = (-math.sin(b), math.cos(b))
    toward = (-math.cos(b), -math.sin(b))
    a = math.radians(angle_deg)
    direction = (across[0] * math.cos(a) + toward[0] * math.sin(a), across[1] * math.cos(a) + toward[1] * math.sin(a))

    def at(t):
        sign, x, y, remaining, k = 1, start[0], start[1], t, 0
        if flip_s:
            while remaining > flip_s:
                x += sign * direction[0] * speed * flip_s
                y += sign * direction[1] * speed * flip_s
                remaining -= flip_s
                sign = -sign
        x += sign * direction[0] * speed * remaining
        y += sign * direction[1] * speed * remaining
        return (x, y), (sign * direction[0] * speed, sign * direction[1] * speed)
    return at


SCENARIOS = [
    ("stationary, 100 m (control)", path(100, 0.0, 0)),
    ("walking across, 60 m", path(60, 11.7, 0)),
    ("walking across, 100 m", path(100, 11.7, 0)),
    ("walking across, 150 m", path(150, 11.7, 0)),
    ("boosting across, 100 m", path(100, 19.5, 0)),
    ("walking at 45 deg, 100 m", path(100, 11.7, 45)),
    ("walking straight at us, 150 m", path(150, 11.7, 90)),
    ("zigzag across every 1 s, 100 m", path(100, 11.7, 0, flip_s=1.0)),
    ("zigzag across every 0.5 s, 60 m", path(60, 11.7, 0, flip_s=0.5)),
]


def opponent(pos, vel, passive=False):
    z = et.ground(*pos)
    toward_us = math.atan2(HOME[1] - pos[1], HOME[0] - pos[0])
    aim = toward_us + (math.pi / 2 if passive else 0.0)
    return dict(id=5, kind="mech", pos=[pos[0], pos[1], z], vel=[vel[0], vel[1], 0.0], aim=[aim, 0.0],
                hp=1400, max_hp=1400, cubes=0, weapons=["gun", "laser"], charging=False)


def body_hit(origin, direction, length, target):
    """Does the segment from origin along direction for length pass through the target body?"""
    tx, ty, tz = target["pos"]
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((tx - origin[0]) * dx + (ty - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - tx, py - ty) <= MECH["radius"] + BULLET_R and tz <= pz <= tz + MECH["height"]


def gunfight(folder, motion, seconds=6.0, seed=1, laser=False, passive=False):
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    aim = [0.0, 0.0]
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    beam = dict(kind="laser", cooldown=0.0, charge=LASER["charge"] if laser else 0.0, stats=copy.deepcopy(LASER)) if laser else None
    held_full = 0.0
    bullets, shots, hits, beams, beam_hits = [], 0, 0, 0, 0
    fire, commanded = [False, False], [0.0, 0.0]
    z0 = et.ground(*HOME)
    for tick in range(int(seconds / DT)):
        t = tick * DT
        pos, vel = motion(t)
        target = opponent(pos, vel, passive)
        if tick == 0:
            aim = [math.atan2(pos[1] - HOME[1], pos[0] - HOME[0]), 0.0]
            commanded = list(aim)
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [target], origin=HOME, weapons=[copy.deepcopy(gun), copy.deepcopy(beam)])
            obs["t"] = round(t, 2)
            obs["self"]["aim"] = list(aim)
            action = bot.act(obs)
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
            # Laser: charge while held, release on letting go, auto-fire after hold_s at full.
            if beam is not None:
                if beam["cooldown"] > 0:
                    beam["cooldown"] = max(0.0, beam["cooldown"] - 0.1)
                elif fire[1]:
                    if beam["charge"] >= LASER["charge"] - 1e-9:
                        held_full += 0.1
                    beam["charge"] = min(LASER["charge"], beam["charge"] + 0.1)
                    if held_full >= LASER["hold_s"] - 1e-9:
                        beams += 1
                        beam_hits += laser_hits(aim, z0, target)
                        beam.update(charge=0.0, cooldown=LASER["cooldown"])
                        held_full = 0.0
                elif beam["charge"] > 0:
                    beams += 1
                    beam_hits += laser_hits(aim, z0, target)
                    beam.update(charge=0.0, cooldown=LASER["cooldown"])
                    held_full = 0.0
        # torso
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        # gun
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            origin = [HOME[0] + 3 * d[0], HOME[1] + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]]
            bullets.append(dict(pos=origin, dir=d, travelled=3.0))
            shots += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # bullets fly after the opponent has moved to its position for this tick
        alive = []
        for b in bullets:
            step = GUN["speed"] * DT
            if body_hit(b["pos"], b["dir"], step, target):
                hits += 1
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        bullets = alive
    bot.close()
    return dict(shots=shots, hits=hits, beams=beams, beam_hits=beam_hits)


def laser_hits(aim, z0, target):
    d = (math.cos(aim[1]) * math.cos(aim[0]), math.cos(aim[1]) * math.sin(aim[0]), math.sin(aim[1]))
    origin = [HOME[0], HOME[1], z0 + MECH["muzzle_height"]]
    return body_hit(origin, d, LASER["range"], target)


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; open bearing {OPEN} deg\n")
    print(f"{'opponent (6 s, aiming at us)':34}{'shots':>12}{'hits':>12}{'hit rate':>16}  check")
    print(f"{'':34}{'base | lead':>12}{'base | lead':>12}{'base | lead':>16}")
    failures, total = [], {"base": [0, 0], "cand": [0, 0]}
    for k, (name, motion) in enumerate(SCENARIOS):
        base, cand = gunfight(folder, motion, seed=100 + k), gunfight(ROOT, motion, seed=100 + k)
        for key, r in (("base", base), ("cand", cand)):
            total[key][0] += r["shots"]
            total[key][1] += r["hits"]
        rate = lambda r: r["hits"] / r["shots"] if r["shots"] else 0.0
        if name.startswith("stationary"):
            ok, text = base == cand, "identical (nothing to lead)"
        elif name.startswith("zigzag"):
            ok, text = True, "measurement: lead assumes steady motion"
        else:
            ok, text = cand["hits"] >= base["hits"], "at least as many hits"
        print(f"{name:34}{base['shots']:>5} | {cand['shots']:<5}{base['hits']:>5} | {cand['hits']:<5}"
              f"{100 * rate(base):>8.0f}% | {100 * rate(cand):<5.0f}%  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    b, c = total["base"], total["cand"]
    print(f"{'all scenarios':34}{b[0]:>5} | {c[0]:<5}{b[1]:>5} | {c[1]:<5}{100 * b[1] / b[0]:>8.0f}% | {100 * c[1] / c[0]:<5.0f}%")

    laser_case = path(60, 11.7, 0)
    lb, lc = gunfight(folder, laser_case, seconds=4.0, seed=7, laser=True), gunfight(ROOT, laser_case, seconds=4.0, seed=7, laser=True)
    ok = lc["beams"] >= 1 and lc["beam_hits"] >= lb["beam_hits"]
    print(f"\nfull laser + gun, opponent walking across at 60 m (4 s): laser beams on target base {lb['beam_hits']}/{lb['beams']},"
          f" lead {lc['beam_hits']}/{lc['beams']}; gun hits base {lb['hits']}, lead {lc['hits']}"
          f"  {'ok' if ok else 'FAIL'}: the laser is still released onto the target")
    if not ok:
        failures.append("laser release onto a moving opponent")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    kiting = set()
    for k, obs in enumerate(et.STREAM):
        local.act(copy.deepcopy(obs))
        if getattr(local, "kite", None) is not None and local.kite.active:
            kiting.add(k)  # kite-distance: backing away owns move, boost and jump here
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    aim_diff = other_diff = 0
    trace = []
    for k, obs in enumerate(et.STREAM):
        a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        aim_diff += a.get("aim") != c.get("aim")
        # crossing-fire onward also opens fire on led, passive targets
        skip = ("aim", "fire", "tick", "debug") + (("move", "boost", "jump") if k in kiting else ())
        rest = lambda x: {key: v for key, v in x.items() if key not in skip}
        other_diff += rest(a) != rest(c)
        if a.get("aim") != c.get("aim") and len(trace) < 3:
            trace.append((obs["t"], a["aim"], c["aim"], obs["mechs"][0]["vel"][:2], round(math.dist(obs["mechs"][0]["pos"], obs["self"]["pos"]))))
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: aim led on {getattr(local.engagement, 'led', 0)} decisions; aim differs from the baseline on"
          f" {aim_diff} of {len(et.STREAM)}; any other command differs on {other_diff}"
          f" (move, boost and jump not compared on the {len(kiting)} kite decisions)")
    for t, a, c, v, d in trace:
        print(f"  t={t:4.1f}  opponent {d} m away moving {v}: baseline aim yaw {a[0]:+.3f}, lead aim yaw {c[0]:+.3f}")
    if other_diff:
        failures.append("recording: a command other than aim changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
