"""crate-shoot: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/crate_shoot_trial.py [--baseline <git revision>]

A closed loop with loot crates (300 HP, radius 1.4 m, height 2.4 m, from hello.config). Our mech
stands still; the world fires our gun when the bot holds slot 0's trigger (252 m/s, 0.24 s,
12-round magazine, 2.4 s reload, 0.6 deg spread, torso turning at the configured rates) and the
bullets hit a crate's cylinder for 45 damage. A destroyed crate leaves its 1 cube and, on a
seeded coin flip at the configured 50%, a weapon pickup; both are then listed. Every crate is
listed every decision (vision is not modelled), so the bot's own range and cover checks decide.
Reports crates destroyed, the time each went, the cubes and pickups listed afterwards, shots,
and decisions with slot 1's trigger held. Also checks the recorded match and single decisions:
a pickup detour, a laser in slot 1. Standard library only.
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
MECH, GUN, CRATE = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["crates"]
CHANCE = CONFIG["loot"]["crate_weapon_chance"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT = 0.05
OPEN = next(b for b in range(0, 360, 5)
            if all(et.clear_from(et.HOME, b + d, r) for d in (-25, 0, 25) for r in (30, 60, 85, 120, 150)))


def hits_body(origin, direction, length, base, radius, height):
    cx, cy, cz = base
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((cx - origin[0]) * dx + (cy - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - cx, py - cy) <= radius + BULLET_R and cz <= pz <= cz + height


def at(origin, bearing, distance):
    a = math.radians(bearing)
    x, y = origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)
    return [round(x, 2), round(y, 2), round(et.ground(x, y), 2)]


class Local:
    """The candidate in-process, logging each decision for the trace."""

    def __init__(self):
        import mechfight as mf
        mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
        from bot import Bot
        self.bot, self.log = Bot(et.HELLO), []

    def act(self, obs):
        action = self.bot.act(copy.deepcopy(obs))
        decision = self.bot.engagement.decision
        me = obs["self"]["pos"]
        self.log.append(dict(t=obs["t"], crate=decision.get("crate"), reason=decision.get("reason"),
                             fire=list(action.get("fire") or [False, False]),
                             ammo=obs["self"]["weapons"][0].get("ammo"),
                             crates=[(c["id"], round(math.dist(c["pos"], me)), c["hp"]) for c in obs["crates"]],
                             cubes=len(obs["cubes"]), pickups=len(obs["pickups"])))
        return action

    def close(self):
        pass


def run(folder, origin, crate_spots, mechs=(), events0=(), seconds=12.0, seed=1, weapons=None, bot=None):
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
            obs["t"] = round(t, 2)
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


def decisions(folder, frames):
    base = BotProcess(folder, et.HELLO)
    cand = BotProcess(ROOT, et.HELLO)
    rows = [(base.act(copy.deepcopy(f)), cand.act(copy.deepcopy(f))) for f in frames]
    base.close()
    cand.close()
    return rows


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    home = list(et.HOME)
    origin_c, bearing_c, distance_c, _ = et.COVER_SPOT
    far_mech = et.mech(5, OPEN + 60, 180, aim_at_us=False)
    mortar_hit = [dict(type="damaged", amount=160, weapon="mortar", by=7, bearing=None)]
    cases = [
        ("crate at 30 m", home, [at(home, OPEN, 30)], (), (), 12.0, "activates"),
        ("crate at 60 m", home, [at(home, OPEN, 60)], (), (), 12.0, "activates"),
        ("crate at 85 m", home, [at(home, OPEN, 85)], (), (), 12.0, "activates"),
        ("crates at 30, 60 and 85 m", home, [at(home, OPEN - 20, 85), at(home, OPEN, 30), at(home, OPEN + 20, 60)],
         (), (), 15.0, "activates"),
        ("crate at 120 m (beyond 90 m)", home, [at(home, OPEN, 120)], (), (), 12.0, "identical"),
        ("crate behind cover", list(origin_c), [at(origin_c, bearing_c, distance_c)], (), (), 12.0, "identical"),
        ("crate at 60 m, a mech listed", home, [at(home, OPEN, 60)], (far_mech,), (), 12.0, "identical"),
        ("crate at 60 m, unseen mech shelled us at t=0", home, [at(home, OPEN, 60)], (), mortar_hit, 4.8, "identical"),
    ]
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    print(f"{'case':46}{'destroyed':>11}{'cubes':>9}{'pickups':>9}{'shots':>11}{'slot 1':>9}  check")
    print(f"{'':46}{'base | cand':>11}{'b | c':>9}{'b | c':>9}{'base | cand':>11}{'b | c':>9}")
    failures = []
    for k, (name, origin, spots, mechs, ev, seconds, expect) in enumerate(cases):
        base = run(folder, origin, spots, mechs, ev, seconds=seconds, seed=700 + k)
        cand = run(ROOT, origin, spots, mechs, ev, seconds=seconds, seed=700 + k)
        if expect == "identical":
            ok, text = base == cand, "identical"
        else:
            ok = (len(cand["destroyed"]) == len(spots) and not base["destroyed"] and base["shots"] == 0
                  and cand["slot1"] == 0)
            text = "destroys what the baseline ignores: " + ", ".join(f"{i} at {s:.1f} s" for i, s in cand["destroyed"])
        print(f"{name:46}{len(base['destroyed']):>5} | {len(cand['destroyed']):<5}{base['cubes']:>3} | {cand['cubes']:<5}"
              f"{base['pickups']:>3} | {cand['pickups']:<5}{base['shots']:>5} | {cand['shots']:<5}"
              f"{base['slot1']:>3} | {cand['slot1']:<5}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    # slot 1 holds a laser: only the gun shoots the crate, the laser trigger stays released
    laser = et.laser(0.0)
    base = run(folder, home, [at(home, OPEN, 60)], seconds=8.0, seed=790, weapons=[None, laser])
    cand = run(ROOT, home, [at(home, OPEN, 60)], seconds=8.0, seed=790, weapons=[None, laser])
    ok = cand["destroyed"] and cand["slot1"] == 0 and base["shots"] == 0
    print(f"{'crate at 60 m, laser in slot 1':46}{len(base['destroyed']):>5} | {len(cand['destroyed']):<5}"
          f"{base['cubes']:>3} | {cand['cubes']:<5}{base['pickups']:>3} | {cand['pickups']:<5}"
          f"{base['shots']:>5} | {cand['shots']:<5}{base['slot1']:>3} | {cand['slot1']:<5}  "
          f"{'ok  ' if ok else 'FAIL'} gun only; laser trigger held on {cand['slot1']} decisions")
    if not ok:
        failures.append("laser in slot 1")

    # a pickup detour keeps facing its pickup: no crate shooting while one is active
    pickup = dict(id=8005, kind="laser", pos=at(home, OPEN + 90, 40))
    frames = []
    for k in range(20):
        f = et.frame(k, pickups=[pickup])
        f["crates"] = [dict(id=1001, pos=at(home, OPEN, 30), hp=300)]
        frames.append(f)
    rows = decisions(folder, frames)
    local = Local()
    for f in frames:
        local.act(f)
    detour = local.bot.loot.target is not None
    differ = sum(a != c for a, c in rows)
    ok = detour and differ == 0 and local.bot.engagement.crate_shots == 0
    print(f"\npickup detour active with a crate at 30 m: detour {detour}; decisions differing {differ} of {len(rows)}"
          f"  {'ok' if ok else 'FAIL'}")
    if not ok:
        failures.append("pickup detour")

    name, origin, spots, mechs, ev, seconds, _ = cases[3]
    local = Local()
    result = run(ROOT, origin, spots, mechs, ev, seconds=seconds, seed=703, bot=local)
    print(f"\ntrace ({name}, candidate in-process, same seed; destroyed {result['destroyed']}):")
    print(f"{'t':>5}  {'reason':14}{'crate':>6}{'fire':>15}{'ammo':>6}  crates listed (id, m, hp)")
    last = None
    for row in local.log:
        key = (row["reason"], row["crate"], len(row["crates"]))
        if key != last or row["t"] in (0.0, 1.0, 2.0):
            print(f"{row['t']:>5.1f}  {row['reason']:14}{str(row['crate']):>6}{str(row['fire']):>15}{row['ammo']:>6}  "
                  f"{row['crates']}" + (f"  cubes {row['cubes']}, pickups {row['pickups']}" if row["cubes"] else ""))
        last = key

    local = Local()
    for obs in et.STREAM:
        local.act(obs)
    rows = decisions(folder, et.STREAM)
    differ = [(o["t"], sorted(k for k in set(a) | set(c) if a.get(k) != c.get(k) and k != "debug"))
              for o, (a, c) in zip(et.STREAM, rows) if a != c]
    crate_rows = [r for r in local.log if r["reason"] == "crate shoot"]
    print(f"\nrecording: decisions listing a crate {sum(bool(o.get('crates')) for o in et.STREAM)};"
          f" crate-shoot decisions {local.bot.engagement.crate_shots}; decisions answered differently {len(differ)}")
    for t, keys in differ:
        print(f"  t={t}: {', '.join(keys) or 'debug only'}")
    other = [keys for _, keys in differ if set(keys) - {"aim", "fire"}]
    if other or len(differ) != len(crate_rows):
        failures.append("recording: a difference outside crate-shoot decisions")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
