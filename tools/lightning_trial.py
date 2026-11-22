"""lightning-gate: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/lightning_trial.py [--baseline <git revision>]

The closed-loop gunfight of tools/lead_trial.py with a lightning weapon in slot 1. The world
fires the gun as lead_trial does (same seeded spread for both bots) and fires the lightning
when its trigger is held: one arc per `cooldown` 0.25 s while energy lasts, costing `energy` 3
each, hit or miss; it hits when the opponent is within `range` 45 m and `cone_deg` 30 deg of
the torso's actual aim yaw with a clear line. Energy regenerates at `energy_regen` 18/s after
`energy_regen_delay` 0.6 s without spending. Lead-shots holds the lightning trigger whenever it
fires the gun; the candidate only while the opponent is in the arc's reach. Controls carry no
lightning. Also replays the standard recording with a lightning in slot 1: only fire may
differ. Standard library only.
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
import lead_trial as lt
from harness import BotProcess, export

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
CONFIG = et.HELLO["config"]
MECH, GUN = CONFIG["mech"], CONFIG["weapons"]["gun"]
ARC, MORTAR = CONFIG["weapons"]["lightning"], CONFIG["weapons"]["mortar"]
DT = lt.DT
HOME = lt.HOME


def lightning(cooldown=0.0):
    return dict(kind="lightning", cooldown=round(cooldown, 3), stats=copy.deepcopy(ARC))


def mortar():
    return dict(kind="mortar", cooldown=0.0, stats=copy.deepcopy(MORTAR))


def arc_hits(aim, z0, target):
    """Does an arc fired along this torso yaw reach the opponent?"""
    muzzle = [HOME[0], HOME[1], z0 + MECH["muzzle_height"]]
    tx, ty, tz = target["pos"]
    centre = [tx, ty, tz + MECH["height"] / 2]
    if math.dist(muzzle, centre) > ARC["range"]:
        return False
    off = abs((math.atan2(ty - HOME[1], tx - HOME[0]) - aim[0] + math.pi) % math.tau - math.pi)
    return math.degrees(off) <= ARC["cone_deg"] and et.COVER.clear(muzzle, centre)


def gunfight(folder, motion, seconds=6.0, seed=1, slot1="lightning"):
    """Our mech stands still; the opponent aims at us (so v6 always fires) and moves on `motion`."""
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    arc_cd, energy, last_spend = 0.0, float(MECH["energy"]), -10.0
    bullets = []
    r = dict(shots=0, hits=0, arcs=0, arc_hits=0, spent=0, min_energy=energy, actions=[], trace=[])
    fire, aim, commanded = [False, False], [0.0, 0.0], [0.0, 0.0]
    z0 = et.ground(*HOME)
    for tick in range(int(round(seconds / DT))):
        t = tick * DT
        pos, vel = motion(t)
        target = lt.opponent(pos, vel)
        if tick == 0:
            aim = [math.atan2(pos[1] - HOME[1], pos[0] - HOME[0]), 0.0]
            commanded = list(aim)
        if tick % 2 == 0:
            second = {"lightning": lightning(arc_cd), "mortar": mortar(), None: None}[slot1]
            obs = et.frame(tick // 2, [target], origin=HOME, weapons=[copy.deepcopy(gun), second])
            obs["t"] = round(t, 2)
            obs["self"]["aim"] = list(aim)
            obs["self"]["energy"] = round(energy, 2)
            action = bot.act(obs)
            r["actions"].append({k: v for k, v in action.items() if k not in ("tick", "debug")})
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
            r["trace"].append((round(t, 1), round(math.dist(pos, HOME)), fire[0], fire[1], round(energy)))
        # torso
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        # lightning: fires on its cooldown while held and energy lasts, hit or miss
        arc_cd = max(0.0, arc_cd - DT)
        if slot1 == "lightning" and fire[1] and arc_cd <= 1e-9 and energy >= ARC["energy"]:
            r["arcs"] += 1
            r["arc_hits"] += arc_hits(aim, z0, target)
            energy -= ARC["energy"]
            r["spent"] += ARC["energy"]
            last_spend = t
            arc_cd = ARC["cooldown"]
        elif t - last_spend >= MECH["energy_regen_delay"] - 1e-9:
            energy = min(float(MECH["energy"]), energy + MECH["energy_regen"] * DT)
        r["min_energy"] = min(r["min_energy"], energy)
        # gun, as in lead_trial
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
            r["shots"] += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        alive = []
        for b in bullets:
            step = GUN["speed"] * DT
            if lt.body_hit(b["pos"], b["dir"], step, target):
                r["hits"] += 1
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        bullets = alive
    r["end_energy"] = round(energy)
    r["min_energy"] = round(r["min_energy"])
    bot.close()
    return r


# name, motion, seconds, slot 1, expectation
SCENARIOS = [
    ("standing, 100 m", lt.path(100, 0.0, 0), 6.0, "lightning", "activates"),
    ("walking across, 120 m", lt.path(120, 11.7, 0), 6.0, "lightning", "activates"),
    ("walking across, 150 m", lt.path(150, 11.7, 0), 6.0, "lightning", "activates"),
    ("walking straight at us from 80 m", lt.path(80, 11.7, 90), 6.0, "lightning", "measure"),
    ("standing, 30 m", lt.path(30, 0.0, 0), 6.0, "lightning", "identical"),
    ("standing, 42 m", lt.path(42, 0.0, 0), 6.0, "lightning", "identical"),
    ("walking across, 30 m (1.5 s)", lt.path(30, 11.7, 0), 1.5, "lightning", "identical"),
    ("no lightning: gun only, walking across, 100 m (control)", lt.path(100, 11.7, 0), 6.0, None, "identical"),
    ("no lightning: gun + mortar, standing, 100 m (control)", lt.path(100, 0.0, 0), 6.0, "mortar", "identical"),
]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; open bearing {lt.OPEN} deg\n")
    print(f"{'opponent (aiming at us)':56}{'gun hits':>11}{'arcs':>11}{'arc hits':>11}{'energy spent':>15}{'lowest energy':>15}  check")
    print(f"{'':56}{'base | cand':>11}{'base | cand':>11}{'base | cand':>11}{'base | cand':>15}{'base | cand':>15}")
    failures, traces = [], {}
    for k, (name, motion, seconds, slot1, expect) in enumerate(SCENARIOS):
        base = gunfight(folder, motion, seconds, seed=400 + k, slot1=slot1)
        cand = gunfight(ROOT, motion, seconds, seed=400 + k, slot1=slot1)
        traces[name] = (base["trace"], cand["trace"])
        same = {key: base[key] for key in base if key != "trace"} == {key: cand[key] for key in cand if key != "trace"}
        if expect == "identical":
            ok, text = same, "identical commands and outcome"
        elif expect == "activates":
            ok = (cand["arcs"] < base["arcs"] and cand["spent"] < base["spent"]
                  and cand["arc_hits"] >= base["arc_hits"]
                  and (cand["shots"], cand["hits"]) == (base["shots"], base["hits"]))
            text = "fewer wasted arcs, gun shots and hits unchanged"
        else:
            ok = cand["arc_hits"] >= base["arc_hits"] and cand["spent"] <= base["spent"]
            text = "measurement: arcs only once in reach, no arc hit lost"
        print(f"{name:56}{base['hits']:>5} | {cand['hits']:<5}{base['arcs']:>5} | {cand['arcs']:<5}"
              f"{base['arc_hits']:>5} | {cand['arc_hits']:<5}{base['spent']:>7} | {cand['spent']:<7}"
              f"{base['min_energy']:>7} | {cand['min_energy']:<7}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    print("\ntrace, walking straight at us from 80 m (t, distance m, fire gun/lightning, energy):")
    b, c = traces["walking straight at us from 80 m"]
    for (t, d, bg, bl, be), (_, _, cg, cl, ce) in zip(b, c):
        if t in (0.0, 0.5, 1.0, 2.0, 2.8, 3.0, 3.2, 4.0, 5.0, 5.9):
            print(f"  t={t:3.1f}  {d:3d} m   base gun {'fire' if bg else 'hold':4} arc {'fire' if bl else 'hold':4} energy {be:3d}"
                  f"   |   cand gun {'fire' if cg else 'hold':4} arc {'fire' if cl else 'hold':4} energy {ce:3d}")

    # The standard recording carries only a gun; replay it once more with a lightning in slot 1.
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    stream = []
    for obs in et.STREAM:
        obs = copy.deepcopy(obs)
        obs["self"]["weapons"][1] = lightning()
        stream.append(obs)
    local = Bot(et.HELLO)
    for obs in stream:
        local.act(copy.deepcopy(obs))
    # loot-power: on the standard recording (slot 1 empty, match time under 180 s) the wider early
    # detour walks to a laser the baseline left alone; move, boost, jump, aim and take are the
    # detour's on those decisions and are not compared there.
    looter, detour = Bot(et.HELLO), set()
    for i, obs in enumerate(et.STREAM):
        looter.act(copy.deepcopy(obs))
        if looter.loot.target is not None:
            detour.add(i)
    for name, frames in (("standard recording", et.STREAM), ("recording, lightning in slot 1", stream)):
        base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
        fire_diff = other_diff = base_arcs = cand_arcs = 0
        for i, obs in enumerate(frames):
            a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
            fire_diff += a.get("fire") != c.get("fire")
            skip = ("fire", "tick", "debug") + (("move", "boost", "jump", "aim", "take")
                                               if frames is et.STREAM and i in detour else ())
            rest = lambda x: {k: v for k, v in x.items() if k not in skip}
            other_diff += rest(a) != rest(c)
            base_arcs += bool((a.get("fire") or [0, 0])[1])
            cand_arcs += bool((c.get("fire") or [0, 0])[1])
        base_bot.close()
        cand_bot.close()
        print(f"\n{name}: fire differs on {fire_diff} of {len(frames)} decisions; any other command differs on {other_diff};"
              f" slot-1 trigger held base {base_arcs}, cand {cand_arcs}"
              + (f" (move, boost, jump, aim and take not compared on the {len(detour)} early-detour decisions)"
                 if frames is et.STREAM else ""))
        if other_diff:
            failures.append(f"{name}: a command other than fire changed")
        if name == "standard recording" and fire_diff:
            failures.append("standard recording: fire changed without a lightning")
    print(f"  candidate lightning_gated counter on the lightning replay: {local.lightning_gated}")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
