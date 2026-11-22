"""drop-always: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/drop_trial.py [--baseline <git revision>]

A closed-loop supply-drop trial. The simulated mech goes where each bot steers it (the
navigation grid blocks walls), a drop falls for `lands_in` seconds and is then captured by
standing alone inside its 8 m ring for 4 s, which gives 3 cubes (+4% max HP each), full HP and
full energy. The zone holds still for the whole run. dodge-tuned only goes for a drop below
80% HP when the capture finishes within 10 s; the candidate goes whatever its HP within 30 s.
Activating cases are drops the baseline leaves alone; controls are drops both treat the same.
Below 80% HP the baseline already walks to a drop within about 70 m once its capture fits in
10 s; that case is reported as a measurement (same capture, earlier departure).
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
import mechfight as mf
import pickup_trial as pt
from harness import BotProcess, export, plain

mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
CONFIG = pt.CONFIG
STATS = CONFIG["mech"]
DROPS = CONFIG["drops"]
CUBE_HP = CONFIG["cubes"]["hp_per_cube"]
DT = pt.DT
SECONDS = 40.0


def layout(seed, distance, spread=60):
    """A start and a drop `distance` metres away along a clear, roughly level straight line."""
    rng = random.Random(seed)
    while True:
        start, goal, along, across = pt.frame(rng, distance + 5, distance + spread, direct=True)
        at = pt.offset(start, along, across, distance, 0)
        if (pt.walkable(at) and pt.GRID.clear_segment(start, at)
                and abs(pt.ground(*at) - pt.ground(*start)) <= 3):
            return start, at


def simulate(bot, scenario, mirror=None, trace=None):
    """Run one bot through one scenario; `mirror` is an in-process copy checked against it."""
    x, y = scenario["start"]
    zone = scenario["zone"]
    drop = dict(id=20000, pos=[*scenario["drop"], round(pt.ground(*scenario["drop"]), 2)],
                radius=DROPS["radius"], lands_in=scenario["lands_in"],
                capture_s=DROPS["capture_s"], progress=0.0, holder=None)
    me_id = pt.TEMPLATE["self"]["id"]
    max_hp = float(STATS["hp"])
    hp = scenario["hp_frac"] * max_hp
    energy, cubes = float(STATS["energy"]), 0
    yaw = math.atan2(drop["pos"][1] - y, drop["pos"][0] - x)
    result = dict(captured=None, cubes=0, hp=None, closest=math.dist((x, y), drop["pos"][:2]),
                  moved=0.0, mirror_differs=0)
    for tick in range(int(SECONDS / DT)):
        now = round(tick * DT, 2)
        in_zone = math.dist((x, y), zone["center"]) <= zone["radius"]
        z = pt.ground(x, y)
        obs = copy.deepcopy(pt.TEMPLATE)
        obs.update(tick=2 * tick, t=now, mechs=copy.deepcopy(scenario.get("mechs", [])),
                   projectiles=[], crates=[], cubes=[], pickups=[], sounds=[], beams=[],
                   events=[], drops=[copy.deepcopy(drop)] if drop else [], offer=None)
        obs["zone"] = dict(center=list(zone["center"]), radius=zone["radius"],
                           next_center=list(zone["next_center"]), next_radius=zone["next_radius"],
                           shrink_start=zone["shrink_start"], shrink_end=zone["shrink_start"] + 50,
                           dps=20)
        obs["self"].update(pos=[x, y, z], vel=[0, 0, 0], aim=[yaw, 0.0], hp=round(hp, 1),
                           max_hp=round(max_hp, 1), energy=energy, grounded=True,
                           in_zone=in_zone, cubes=cubes, upgrades=[])
        action = bot.act(copy.deepcopy(obs))
        if mirror is not None:
            result["mirror_differs"] += plain(mirror.act(copy.deepcopy(obs))) != plain(action)
        if trace is not None and tick % 20 == 0:
            gap = math.dist((x, y), drop["pos"][:2]) if drop else None
            trace.append((now, gap, action.get("move"), dict(drop) if drop else None,
                          round(hp), cubes))
        # The drop falls, then a mech alone in its ring banks capture time.
        if drop:
            drop["lands_in"] = round(max(0.0, drop["lands_in"] - DT), 2)
            ours = math.dist((x, y), drop["pos"][:2]) <= drop["radius"]
            others = any(math.dist(m["pos"][:2], drop["pos"][:2]) <= drop["radius"]
                         for m in scenario.get("mechs", []))
            if drop["lands_in"] == 0 and ours and not others:
                drop["holder"] = me_id
                drop["progress"] = round(drop["progress"] + DT, 2)
                if drop["progress"] >= drop["capture_s"] - 1e-9:
                    cubes += DROPS["cubes"]
                    max_hp = STATS["hp"] * (1 + CUBE_HP * min(cubes, CONFIG["cubes"]["stat_cap"]))
                    hp, energy = max_hp, float(STATS["energy"])
                    result.update(captured=round(now + DT, 1), cubes=cubes, hp=round(hp))
                    drop = None
            elif not ours and not others:
                drop.update(holder=None, progress=0.0)
        if "aim" in action:
            turn = (action["aim"][0] - yaw + math.pi) % math.tau - math.pi
            yaw += max(-STATS["turn_rate"] * DT, min(STATS["turn_rate"] * DT, turn))
        mx, my = action.get("move", [0, 0])
        length = math.hypot(mx, my)
        if length > 1:
            mx, my = mx / length, my / length
        speed = STATS["boost_speed"] if action.get("boost") and length > 0 and energy > 0 else STATS["walk_speed"]
        before = (x, y)
        for axis, delta in enumerate((mx, my)):
            candidate = [x, y]
            candidate[axis] += delta * speed * DT
            if pt.walkable(candidate):
                x, y = candidate
        result["moved"] += math.dist(before, (x, y))
        if drop:
            result["closest"] = min(result["closest"], math.dist((x, y), drop["pos"][:2]))
    result["closest"] = round(result["closest"], 1)
    result["moved"] = round(result["moved"], 1)
    return result


def roomy(centre, next_radius=330):
    return dict(center=list(centre), radius=520, next_center=list(centre),
                next_radius=next_radius, shrink_start=120)


def scenarios():
    cases = []
    for k, (distance, hp, lands_in) in enumerate([(60, 1.0, 25), (100, 1.0, 25), (150, 1.0, 25),
                                                   (60, 0.9, 25), (150, 0.9, 25),
                                                   (100, 1.0, 0), (150, 0.7, 25)]):
        start, at = layout(500 + k, distance)
        state = "called now" if lands_in else "landed"
        cases.append(dict(name=f"{state}, {distance} m, HP {hp:.0%}", start=start, drop=at,
                          hp_frac=hp, lands_in=lands_in, zone=roomy(start), expect="activates"))
    start, at = layout(506, 60)
    cases.append(dict(name="called now, 60 m, HP 70% (base goes once within 10 s)", start=start,
                      drop=at, hp_frac=0.7, lands_in=25, zone=roomy(start), expect="measure"))
    start, at = layout(520, 30)
    cases.append(dict(name="landed, 30 m, HP 70% (both go)", start=start, drop=at, hp_frac=0.7,
                      lands_in=0, zone=roomy(start), expect="identical"))
    start, at = layout(521, 60)
    cases.append(dict(name="landed, 60 m, HP 100%, a mech on the ring", start=start, drop=at,
                      hp_frac=1.0, lands_in=0, zone=roomy(start), expect="identical",
                      mechs=[dict(id=9, kind="mech", pos=[at[0] + 3, at[1], pt.ground(*at)],
                                  hp=1400, max_hp=1400, cubes=0, weapons=["gun"],
                                  charging=False, vel=[0, 0, 0], aim=[0.0, 0.0])]))
    start, at = layout(522, 150)
    cases.append(dict(name="called now, 150 m, HP 100%, outside the next circle", start=start,
                      drop=at, hp_frac=1.0, lands_in=25, zone=roomy(start, next_radius=120),
                      expect="identical"))
    start, at = layout(523, 60)
    away = pt.offset(start, ((at[0] - start[0]) / 60, (at[1] - start[1]) / 60), (0, 0), -200, 0)
    cases.append(dict(name="landed, 60 m, HP 100%, urgent zone return", start=start, drop=at,
                      hp_frac=1.0, lands_in=0, expect="identical",
                      zone=dict(center=away, radius=150, next_center=away, next_radius=100,
                                shrink_start=120)))
    return cases


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    from bot import Bot
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`, "
          f"{SECONDS:.0f} s per case\n")
    head = f"{'case':52}{'captured at s':>16}{'cubes':>9}{'HP after':>14}{'closest m':>14}  check"
    print(head)
    print(f"{'':52}{'base | cand':>16}{'b | c':>9}{'base | cand':>14}{'base | cand':>14}")
    failures, traces = [], {}
    for k, case in enumerate(scenarios()):
        base_bot, cand_bot = BotProcess(folder, pt.HELLO), BotProcess(ROOT, pt.HELLO)
        mirror = Bot(pt.HELLO)
        base = simulate(base_bot, case, trace=traces.setdefault((k, "base"), []))
        cand = simulate(cand_bot, case, mirror=mirror, trace=traces.setdefault((k, "cand"), []))
        base_bot.close()
        cand_bot.close()
        case["drop_decisions"] = mirror.objectives.drop_decisions
        case["captures"] = mirror.objectives.captures
        if case["expect"] == "identical":
            ok = base == {**cand, "mirror_differs": 0} and cand["mirror_differs"] == 0
            text = "identical"
        elif case["expect"] == "measure":
            ok = base["captured"] == cand["captured"] and cand["mirror_differs"] == 0
            text = "same capture; the candidate leaves at once and waits in the ring"
        else:
            ok = (base["captured"] is None and cand["captured"] is not None
                  and cand["mirror_differs"] == 0 and case["captures"] == 1)
            text = "candidate captures, baseline leaves it"
        fmt = lambda v: "-" if v is None else v
        print(f"{case['name']:52}{fmt(base['captured']):>7} | {fmt(cand['captured']):<6}"
              f"{base['cubes']:>4} | {cand['cubes']:<3}{fmt(base['hp']):>6} | {fmt(cand['hp']):<6}"
              f"{base['closest']:>6} | {cand['closest']:<6}  {'ok  ' if ok else 'FAIL'} {text}"
              f"  [drop decisions {case['drop_decisions']}, captures counted {case['captures']}]")
        if not ok:
            failures.append(case["name"])

    print("\ntrace, case 'called now, 100 m, HP 100%' (every 2 s): t, distance to drop, move, drop")
    for side in ("base", "cand"):
        print(f"  {side}:")
        for now, gap, move, drop, hp, cubes in traces[(1, side)]:
            state = ("taken" if drop is None else
                     f"lands in {drop['lands_in']:.1f} s, progress {drop['progress']:.1f}")
            move = "-" if move is None else f"[{move[0]:+.2f}, {move[1]:+.2f}]"
            gap = "-" if gap is None else f"{gap:6.1f} m"
            print(f"    t={now:5.1f}  {gap:>9}  move {move:16}  {state:32} HP {hp}  cubes {cubes}")

    # The recording: drops are never listed there, so no decision may differ.
    import engagement_trial as et
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o)))
                 for o in et.STREAM)
    base_bot.close()
    cand_bot.close()
    listed = sum(bool(o.get("drops")) for o in et.STREAM)
    print(f"\nrecording: drops listed on {listed} of {len(et.STREAM)} decisions; "
          f"answers differ on {differ}")
    if differ:
        failures.append("recording differs")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
