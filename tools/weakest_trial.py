"""weakest-first: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/weakest_trial.py [--baseline <git revision>]

1. Scripted decisions from identical observations: two attackers at similar distance with
   one at 25% HP, a weak passive mech beside a healthy attacker, equal HP, and a weak mech
   behind cover. The opponent each bot faces is read back from its emitted aim.
2. A closed-loop duel against two opponents who both aim at us, one at full HP and one at
   350 HP: bullets (252 m/s, 0.24 s, 12-round magazine, 2.4 s reload, 0.6 deg spread from the
   same seeded draws), 45 damage per hit, an opponent leaves the list when its HP reaches 0
   and a kill event is sent. Measures time to the first kill and kills within the duel.
3. Activation on the standard recording.
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
import engagement_trial as et
import lead_trial as lt
from harness import BotProcess, export, plain

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
GUN, MECH = lt.GUN, lt.MECH
HOME = et.HOME
OPEN = lt.OPEN


def mech(key, bearing, distance, hp, aim_at_us=True, origin=HOME):
    m = et.mech(key, bearing, distance, aim_at_us=aim_at_us, origin=origin)
    m["hp"] = hp
    return m


def scripted():
    cases = []
    a, b = mech(3, OPEN - 15, 60, 1400), mech(7, OPEN + 15, 64, 350)
    hits = [et.damaged(3, OPEN - 15), et.damaged(7, OPEN + 15)]
    cases.append(("two attackers, one at 25% HP", et.frame(0, [a, b], hits), 7, 3))
    a2, b2 = mech(3, OPEN - 15, 60, 1400), mech(7, OPEN + 15, 40, 140, aim_at_us=False)
    cases.append(("weak passive mech beside a healthy attacker", et.frame(0, [a2, b2], [et.damaged(3, OPEN - 15)]), 3, 3))
    a3, b3 = mech(3, OPEN - 15, 60, 700), mech(7, OPEN + 15, 64, 700)
    cases.append(("equal HP, both attacking", et.frame(0, [a3, b3], hits), "identical", None))
    origin, bearing, distance, other = et.COVER_SPOT
    weak = mech(3, bearing, distance, 200, aim_at_us=False, origin=origin)
    healthy = mech(7, other, distance + 3, 1400, aim_at_us=False, origin=origin)
    cases.append(("weak mech behind cover, healthy one in the open", et.frame(0, [weak, healthy], origin=origin), "identical", None))
    return cases


def run_scripted(folder):
    print(f"{'scripted decision':50}{'base faces':>12}{'cand faces':>12}  check")
    failures, trace = [], None
    for name, obs, expect, base_expect in scripted():
        base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
        a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        base_bot.close()
        cand_bot.close()
        ta, tc = et.identify(a, obs), et.identify(c, obs)
        if expect == "identical":
            ok, text = plain(a) == plain(c), "identical to the baseline"
        else:
            ok = tc == expect and (base_expect is None or ta == base_expect)
            text = f"candidate faces mech {expect}" + (" (baseline the nearer one)" if expect != base_expect else " (tier still wins)")
        if name.startswith("two attackers"):
            trace = (a, c, ta, tc)
        print(f"{name:50}{str(ta):>12}{str(tc):>12}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    return failures, trace


def duel(folder, seed, seconds=15.0):
    """Two opponents walking across 60 and 66 m away, both aiming at us; return kill times."""
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    paths = {3: lt.path(60, 11.7, 0), 7: lt.path(66, 11.7, 180)}
    hp = {3: 1400.0, 7: 350.0}
    alive = {3, 7}
    kills, events = [], []
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    z0 = et.ground(*HOME)
    aim, commanded, fire, bullets = None, None, [False, False], []
    for tick in range(int(seconds / lt.DT)):
        t = tick * lt.DT
        bodies = {}
        for key in alive:
            pos, vel = paths[key](t)
            body = lt.opponent(pos, vel)
            body.update(id=key, hp=hp[key])
            bodies[key] = body
        if aim is None:
            first = bodies[3]["pos"]
            aim = [math.atan2(first[1] - HOME[1], first[0] - HOME[0]), 0.0]
            commanded = list(aim)
        if tick % 2 == 0:
            obs = et.frame(tick // 2, list(bodies.values()), events, origin=list(HOME), weapons=[copy.deepcopy(gun), None])
            obs["t"] = round(t, 2)
            obs["self"]["aim"] = list(aim)
            events = []
            action = bot.act(obs)
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * lt.DT, min(MECH["turn_rate"] * lt.DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * lt.DT, min(MECH["pitch_rate"] * lt.DT, commanded[1] - aim[1]))
        gun["cooldown"] = max(0.0, gun["cooldown"] - lt.DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - lt.DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            bullets.append(dict(pos=[HOME[0] + 3 * d[0], HOME[1] + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]],
                                dir=d, travelled=3.0))
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        flying = []
        for b in bullets:
            step = GUN["speed"] * lt.DT
            struck = next((k for k, body in bodies.items() if lt.body_hit(b["pos"], b["dir"], step, body)), None)
            if struck is not None:
                hp[struck] -= GUN["damage"]
                events.append(dict(type="hit", target=struck, amount=GUN["damage"], weapon="gun"))
                if hp[struck] <= 0 and struck in alive:
                    alive.discard(struck)
                    kills.append((round(t, 1), struck))
                    events.append(dict(type="kill", target=struck))
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                flying.append(b)
        bullets = flying
        if not alive:
            break
    bot.close()
    return kills


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    failures, trace = run_scripted(folder)
    if trace:
        a, c, ta, tc = trace
        print(f"\ntrace, two attackers (mech 3 at 60 m full HP, mech 7 at 64 m with 350 HP): baseline faces {ta}"
              f" (aim yaw {a['aim'][0]:+.3f}), candidate faces {tc} (aim yaw {c['aim'][0]:+.3f}); both fire {a.get('fire')} / {c.get('fire')}")
    print(f"\n{'duel: full-HP mech 60 m, 350-HP mech 66 m':46}{'first kill (s, mech)':>24}{'kills in 15 s':>16}")
    firsts = {"base": [], "cand": []}
    for seed in (11, 12, 13):
        kb, kc = duel(folder, seed), duel(ROOT, seed)
        firsts["base"].append(kb[0][0] if kb else None)
        firsts["cand"].append(kc[0][0] if kc else None)
        fmt = lambda k: f"{k[0][0]:.1f} s, mech {k[0][1]}" if k else "none"
        print(f"{'  seed ' + str(seed):46}{fmt(kb) + ' | ' + fmt(kc):>24}{f'{len(kb)} | {len(kc)}':>16}")
    sooner = all(c is not None and (b is None or c < b) for b, c in zip(firsts["base"], firsts["cand"]))
    print(f"  {'ok' if sooner else 'FAIL'}: the candidate's first kill comes sooner in every seed")
    if not sooner:
        failures.append("duel: first kill not sooner")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o))) for o in et.STREAM)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: HP term changed the best-ranked opponent on {local.engagement.weakest} decisions"
          f" (only one mech is ever listed); {differ} of {len(et.STREAM)} decisions differ from the baseline")
    if differ:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
