"""duel-strafe: baseline (3b290b0, official 2.63) and candidate as real bot processes.

    py tools/strafe_trial.py [--baseline <git revision>]

1. Scripted decisions from identical starts: an open duel before any damage, one blocked
   side, both sides blocked, a second opponent, an urgent zone return, a bullet on course
   (the v8 dodge must take over), and a run of decisions to check the side intervals.
2. Aim and fire must stay identical to the baseline everywhere.
3. A reactive duel (the v8 dodge trial's world: a stationary shooter leading every bullet)
   measures hits taken, hit rate and route progress. It is a measurement, not a pass/fail:
   the world has no walls for bullets and no return fire.
4. The standard recording: eligible decisions, decisions where the strafe changed the move,
   and why it was skipped.
Standard library only.
"""
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from harness import BotProcess, export, plain

BASELINE = "3b290b0b87bee98c418a74546671c82dd232c2d0"  # v8 + v7, official 2.63


def duel(origin, bearing_deg, distance, key=5, aim_at_us=True):
    return et.mech(key, bearing_deg, distance, origin=origin, aim_at_us=aim_at_us)


def standing(origin, mechs, projectiles=(), zone=None):
    """Standing at our own zone goal, so the baseline's move is [0, 0]."""
    return dt.observation(0, list(origin), (0.0, 0.0), list(origin), projectiles, mechs, zone=zone)


def walking(mechs, projectiles=(), zone=None):
    home = list(et.HOME)
    heading, ahead = dt.clear_heading(home)
    h = math.radians(heading)
    vel = (dt.MECH["walk_speed"] * math.cos(h), dt.MECH["walk_speed"] * math.sin(h))
    return dt.observation(0, home, vel, ahead, projectiles, mechs, zone=zone), heading


def side_spot(both):
    """A walkable point with a wall within 3 m along some axis on one side (or both), and,
    for the one-sided case, the other side clear for 6 m even when turned 5 degrees either
    way, so the 4 m lookahead never lands on a cell boundary by rounding. Returns the point,
    the axis, and an opponent position perpendicular to it with a clear line of fire."""
    grid = dt.GRID

    def clear(p, angle, distance):
        return grid.clear_segment(p, (p[0] + distance * math.cos(angle), p[1] + distance * math.sin(angle)))

    for index in range(0, len(grid.free), 3):
        if not grid.free[index]:
            continue
        p = grid.point(index)
        for degrees in range(0, 180, 15):
            a = math.radians(degrees)
            blocked_plus = not clear(p, a, 3)
            blocked_minus = not clear(p, a + math.pi, 3)
            shaped = (both and blocked_plus and blocked_minus) or (
                not both and blocked_plus
                and all(clear(p, a + math.pi + math.radians(t), 6) for t in (-5, 0, 5)))
            if not shaped:
                continue
            for offset in (90, -90):
                for distance in (40, 60, 80, 100):
                    if et.clear_from(p, degrees + offset, distance):
                        return p, (math.cos(a), math.sin(a)), (degrees + offset, distance)
    raise RuntimeError("no side spot")


def perpendicular(move, origin, target):
    bearing = math.atan2(target[1] - origin[1], target[0] - origin[0])
    return abs(move[0] * math.cos(bearing) + move[1] * math.sin(bearing)) < 0.01 and math.hypot(*move) > 0.99


def scripted():
    home = list(et.HOME)
    cases = []
    obs, heading = walking([duel(home, 0, 80)])
    obs["mechs"][0] = duel(home, heading + 60, 80)
    cases.append(("open duel before any damage", "strafe", obs))
    spot, side, (bearing, distance) = side_spot(both=False)
    cases.append(("one side blocked by a wall", ("open side", side),
                  standing(spot, [duel(spot, bearing, distance)])))
    spot2, side2, (bearing2, distance2) = side_spot(both=True)
    cases.append(("both sides blocked", "identical", standing(spot2, [duel(spot2, bearing2, distance2)])))
    obs, heading = walking([duel(home, 0, 80), duel(home, 0, 90, key=7)])
    obs["mechs"] = [duel(home, heading + 60, 80), duel(home, heading - 70, 90, key=7)]
    cases.append(("a second opponent listed", "identical", obs))
    obs, heading = walking([duel(home, 0, 80)], zone=([home[0] - 80, home[1]], 50.0))
    obs["mechs"][0] = duel(home, heading + 60, 80)
    cases.append(("urgent zone return (outside the zone)", "identical", obs))
    obs, heading = walking([duel(home, 0, 80)])
    obs["mechs"][0] = duel(home, heading + 60, 80)
    h = math.radians(heading)
    vel = (dt.MECH["walk_speed"] * math.cos(h), dt.MECH["walk_speed"] * math.sin(h))
    obs["projectiles"] = [dt.bullet_at(1, home, vel, 150, heading + 90)]
    cases.append(("bullet on course during the duel", "dodge", obs))
    return cases


def run_scripted(folder):
    failures, trace = [], None
    print(f"{'scripted decision':40}{'baseline move / boost':>26}{'strafe move / boost':>26}  check")
    for name, expect, obs in scripted():
        base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
        a, b = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        base_bot.close()
        cand_bot.close()
        me = obs["self"]["pos"]
        target = obs["mechs"][0]["pos"]
        same_aim_fire = a.get("aim") == b.get("aim") and a.get("fire") == b.get("fire")
        if expect == "strafe":
            ok = perpendicular(b["move"], me, target) and b["move"] != a["move"] and not b.get("boost")
            text = "walks perpendicular to the opponent at walk speed"
            trace = (name, a, b)
        elif expect == "identical":
            ok = plain(a) == plain(b)
            text = "identical to the baseline"
        elif expect == "dodge":
            ok = a["move"] == b["move"] and a.get("boost") == b.get("boost") and b.get("boost")
            text = "the v8 dodge has the final say, exactly as in the baseline"
        else:
            side = expect[1]
            ok = perpendicular(b["move"], me, target) and (b["move"][0] * side[0] + b["move"][1] * side[1]) < -0.99
            text = "strafes to the open side only"
        ok = ok and same_aim_fire
        fmt = lambda act: f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}] / {str(act.get('boost')):5}"
        print(f"{name:40}{fmt(a):>26}{fmt(b):>26}  {'ok  ' if ok else 'FAIL'} {text}"
              f"{'' if same_aim_fire else '  (aim or fire changed!)'}")
        if not ok:
            failures.append(name)
    return failures, trace


def run_intervals(folder):
    """A static open duel for 6 s: the side flips after 0.75-1.15 s each time."""
    home = list(et.HOME)
    cand = BotProcess(ROOT, et.HELLO)
    signs = []
    target = duel(home, 30, 80)
    for k in range(60):
        obs = standing(home, [target])
        obs.update(tick=2 * k, t=round(k * 0.1, 2))
        move = cand.act(obs)["move"]
        bearing = math.radians(30)
        left = (-math.sin(bearing), math.cos(bearing))
        signs.append(1 if move[0] * left[0] + move[1] * left[1] > 0 else -1)
    cand.close()
    runs, count = [], 1
    for a, b in zip(signs, signs[1:]):
        if a == b:
            count += 1
        else:
            runs.append(count)
            count = 1
    complete = runs  # the last, unfinished run is left out
    ok = bool(complete) and all(8 <= r <= 12 for r in complete)
    print(f"\nside intervals over 6 s of a static duel: runs of {complete} decisions (0.1 s each)"
          f"  {'ok' if ok else 'FAIL'}: every run lasts 0.75-1.15 s")
    return [] if ok else ["side intervals"]


def run_reactive(folder):
    print(f"\n{'reactive duel (shooter leads)':32}{'hits':>12}{'hits per 10 s':>16}{'arrival s':>14}")
    print(f"{'':32}{'base | strafe':>12}{'base | strafe':>16}{'base | strafe':>14}")
    totals = {"base": [0, 0.0, 0], "cand": [0, 0.0, 0]}
    for title, eps in (("tuning", dt.episodes()), ("held-out", dt.heldout_episodes())):
        sums = {"base": [0, 0.0, 0], "cand": [0, 0.0, 0]}
        for ep in eps:
            for key, path in (("base", folder), ("cand", ROOT)):
                r = dt.react(path, ep)
                exposure = r["reached"] if r["reached"] is not None else 30.0
                sums[key][0] += r["hits"]
                sums[key][1] += exposure
                sums[key][2] += r["reached"] is None
        b, c = sums["base"], sums["cand"]
        print(f"{title + f' ({len(eps)} episodes)':32}{b[0]:>5} | {c[0]:<6}{10 * b[0] / b[1]:>7.1f} | {10 * c[0] / c[1]:<7.1f}"
              f"   unfinished {b[2]} | {c[2]}")
    print("  (episodes end on arrival or at 30 s; the shooter never stops, so a mech that strafes"
          " instead of walking stays exposed longer)")


def run_recording(folder):
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    bot = Bot(et.HELLO)
    for obs in et.STREAM:
        bot.act(copy.deepcopy(obs))
    counts = bot.strafe.counts
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    moved = aim_fire = 0
    for obs in et.STREAM:
        a, b = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        moved += a.get("move") != b.get("move") or a.get("boost") != b.get("boost")
        aim_fire += a.get("aim") != b.get("aim") or a.get("fire") != b.get("fire")
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    skips = {k[len("skipped: "):]: v for k, v in counts.items() if k.startswith("skipped: ")}
    print(f"\nrecording ({len(et.STREAM)} decisions): eligible {counts.get('eligible', 0)},"
          f" strafe changed the move on {counts.get('changed movement', 0)},"
          f" side switched for a blocked lookahead {counts.get('switched side: lookahead blocked', 0)}")
    print("  skipped:", ", ".join(f"{k} {v}" for k, v in sorted(skips.items(), key=lambda kv: -kv[1])))
    print(f"  against the baseline process: move or boost differs on {moved}, aim or fire differs on"
          f" {aim_fire}; round trip p99 {p99:.1f} ms")
    return [] if aim_fire == 0 else ["recording: aim or fire changed"]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    failures, trace = run_scripted(folder)
    if trace:
        name, a, b = trace
        print(f"\ntrace, {name}: baseline move {a['move']} boost {a.get('boost')};"
              f" strafe move {[round(v, 2) for v in b['move']]} boost {b.get('boost')}; aim and fire identical")
    failures += run_intervals(folder)
    failures += run_recording(folder)
    run_reactive(folder)
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (scripted checks, intervals, aim and fire; the reactive duel is a measurement)")


if __name__ == "__main__":
    main()
