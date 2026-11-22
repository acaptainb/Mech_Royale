"""laser-cover: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/laser_cover_trial.py [--baseline <git revision>]

A closed-loop laser duel. A stationary opponent 100 m away aims at us and cycles its laser:
it charges for the configured charge time (listed with `charging: true`), releases at full
charge and waits out the cooldown. A release hits us (315 damage) when the line from its eye
to our body centre is clear by cover.py. Our mech moves where the bot steers it (ground
acceleration, walk and boost speed, boost energy, the navigation grid). Reports laser hits
taken and the time from the first charge until we stand hidden. Also checks the controls
(open ground, charging at someone else, urgent zone return), that a bullet on course still
gets the v8 dodge, and activation on the standard recording. Standard library only.
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
from cover import Cover
from harness import BotProcess, export, plain

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90
CONFIG = et.HELLO["config"]
MECH, LASER = CONFIG["mech"], CONFIG["weapons"]["laser"]
COVER = Cover()
DT = 0.05


def body(p):
    return (p[0], p[1], et.ground(*p[:2]) + 4.5)


def exposed(shooter, p):
    return COVER.clear((shooter[0], shooter[1], shooter[2] + 8.0), body(p), skip_start=3.0, skip_end=2.5)


def find_covered_spot():
    """A walkable point in the open toward some bearing, with a hidden, reachable point 5-8 m
    away and none closer than 5 m."""
    grid = dt.GRID
    for index in range(0, len(grid.free), 5):
        if not grid.free[index]:
            continue
        p = grid.point(index)
        i, j = index % grid.width, index // grid.width
        if not (10 <= i < grid.width - 10 and 10 <= j < grid.height - 10):
            continue  # away from the map edge, so the cover is a building, not the boundary
        for bearing in range(0, 360, 15):
            a = math.radians(bearing)
            s = (p[0] + 100 * math.cos(a), p[1] + 100 * math.sin(a))
            shooter = (s[0], s[1], et.ground(*s))
            if not exposed(shooter, p):
                continue
            near = []
            for radius in (3.0, 5.0, 7.0, 8.0):
                for k in range(16):
                    b = k * math.tau / 16
                    q = (p[0] + radius * math.cos(b), p[1] + radius * math.sin(b))
                    if grid.clear_segment(p, q) and not exposed(shooter, q):
                        near.append(radius)
            if near and min(near) >= 5.0:
                return list(p), shooter
    raise RuntimeError("no covered spot")


def find_open_spot():
    """HOME lawn with a shooter bearing where nothing within 10 m hides us."""
    p = list(et.HOME)
    for bearing in range(0, 360, 15):
        a = math.radians(bearing)
        s = (p[0] + 100 * math.cos(a), p[1] + 100 * math.sin(a))
        shooter = (s[0], s[1], et.ground(*s))
        if not exposed(shooter, p):
            continue
        hidden = any(not exposed(shooter, (p[0] + r * math.cos(k * math.tau / 16), p[1] + r * math.sin(k * math.tau / 16)))
                     for r in (3.0, 5.0, 7.0, 10.0) for k in range(16))
        if not hidden:
            return p, shooter
    raise RuntimeError("no open spot")


def shooter_mech(shooter, me, charging, aim_off_deg=0.0):
    toward = math.atan2(me[1] - shooter[1], me[0] - shooter[0]) + math.radians(aim_off_deg)
    return dict(id=5, kind="mech", pos=list(shooter), vel=[0, 0, 0], aim=[toward, 0.0], hp=1400, max_hp=1400,
                cubes=0, weapons=["gun", "laser"], charging=charging)


def duel(folder, start, shooter, seconds=8.0, aim_off_deg=0.0, zone=None):
    """Closed loop: returns laser hits on us, seconds from first charge until hidden, and actions."""
    bot = BotProcess(folder, et.HELLO)
    x, y = start
    vx = vy = 0.0
    energy, spent_at, hp = MECH["energy"], -10.0, 1400.0
    zone = zone or (list(start), 400.0)
    centre, radius = zone
    phase, phase_t = "cooldown", 0.5          # first charge begins at t = 0.5 s
    hits, hidden_at, actions, events, move, boost = 0, None, [], [], [0.0, 0.0], False
    for tick in range(int(seconds / DT)):
        now = tick * DT
        phase_t -= DT
        if phase_t <= 0:
            if phase == "cooldown":
                phase, phase_t = "charging", LASER["charge"]
            else:
                if aim_off_deg == 0.0 and exposed(shooter, (x, y)):
                    hits += 1
                    hp -= LASER["damage"]
                    events.append(dict(type="damaged", amount=LASER["damage"], weapon="laser", by=5,
                                       bearing=math.atan2(shooter[1] - y, shooter[0] - x)))
                phase, phase_t = "cooldown", LASER["cooldown"]
        if hidden_at is None and now >= 0.5 and not exposed(shooter, (x, y)):
            hidden_at = round(now - 0.5, 2)
        if tick % 2 == 0:
            obs = dt.observation(tick // 2, [x, y], (vx, vy), list(centre), (),
                                 [shooter_mech(shooter, (x, y), phase == "charging", aim_off_deg)],
                                 zone=(centre, radius), events=events, hp=hp, energy=energy)
            obs["t"] = round(now, 2)
            action = bot.act(obs)
            actions.append(plain(action))
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        speed = MECH["walk_speed"]
        if boost and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            energy = max(0.0, energy - MECH["boost_drain"] * DT)
            spent_at = now
        elif now - spent_at >= MECH["energy_regen_delay"]:
            energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT)
        dvx, dvy = mx * speed - vx, my * speed - vy
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
    bot.close()
    return dict(hits=hits, hidden_at=hidden_at, actions=actions)


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    failures = []
    cspot, cshooter = find_covered_spot()
    ospot, oshooter = find_open_spot()
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`")
    print(f"covered spot {[round(v, 1) for v in cspot]} (nearest hidden point 5-8 m), open spot {[round(v, 1) for v in ospot]};"
          f" laser charge {LASER['charge']} s, cooldown {LASER['cooldown']} s, 8 s duels\n")
    print(f"{'case':44}{'laser hits':>14}{'hidden after s':>18}  check")
    print(f"{'':44}{'base | cand':>14}{'base | cand':>18}")
    cases = [
        ("charging at us, building 5-8 m away", cspot, cshooter, dict(), "activates"),
        ("charging at us, open ground, no cover", ospot, oshooter, dict(), "identical"),
        ("charging at someone else (aim 90 deg off)", cspot, cshooter, dict(aim_off_deg=90.0), "identical"),
        ("charging at us, zone return urgent", cspot, cshooter,
         dict(zone=([cspot[0] + 150.0, cspot[1]], 40.0), seconds=4.0), "identical"),
    ]
    trace = None
    for name, spot, shooter, extra, expect in cases:
        b, c = duel(folder, spot, shooter, **extra), duel(ROOT, spot, shooter, **extra)
        hid = lambda r: "-" if r["hidden_at"] is None else f"{r['hidden_at']:.2f}"
        if expect == "identical":
            ok, text = b["actions"] == c["actions"], "identical to the baseline"
        else:
            ok = c["hits"] < b["hits"] and c["hidden_at"] is not None
            text = "fewer laser hits; ends up hidden"
            trace = (b["actions"], c["actions"])
        print(f"{name:44}{b['hits']:>6} | {c['hits']:<6}{hid(b):>9} | {hid(c):<7}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    # A bullet on course while a laser is charging at us: the v8 dodge has the final say.
    me = cspot
    obs = dt.observation(0, list(me), (0.0, 0.0), list(me), [dt.bullet_at(1, me, (0, 0), 150, 200)],
                         [shooter_mech(cshooter, me, True)])
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
    base_bot.close()
    cand_bot.close()
    ok = a["move"] == c["move"] and a.get("boost") == c.get("boost") and math.hypot(*c["move"]) > 0.9
    print(f"{'bullet on course while charged at':44}{'':14}{'':18}  {'ok  ' if ok else 'FAIL'}"
          f" dodge wins: base move {[round(v, 2) for v in a['move']]}, cand {[round(v, 2) for v in c['move']]}")
    if not ok:
        failures.append("dodge override")

    if trace:
        base, cand = trace
        print("\ntrace, charging at us with a building 5-8 m away (decision: move / boost):")
        for k in (4, 5, 6, 7, 8, 9, 12, 16):
            fmt = lambda x: f"[{x['move'][0]:+.2f},{x['move'][1]:+.2f}] {str(x.get('boost')):5}"
            print(f"  t={k * 0.1:4.1f}  baseline {fmt(base[k])}   laser-cover {fmt(cand[k])}")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    for o in et.STREAM:
        local.act(copy.deepcopy(o))
    counts = local.laser_cover.counts
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    moved = aimfire = 0
    for o in et.STREAM:
        a, c = base_bot.act(copy.deepcopy(o)), cand_bot.act(copy.deepcopy(o))
        moved += a.get("move") != c.get("move") or a.get("boost") != c.get("boost")
        aimfire += a.get("aim") != c.get("aim") or a.get("fire") != c.get("fire")
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    charging = sum(1 for o in et.STREAM for m in o["mechs"] if m.get("charging"))
    print(f"\nrecording: {charging} decisions list a charging mech; rule outcomes {dict(sorted(counts.items()))};"
          f" move or boost differs on {moved}, aim or fire on {aimfire} of {len(et.STREAM)}; round trip p99 {p99:.1f} ms")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (laser hits are from the simplified duel world, not placements)")


if __name__ == "__main__":
    main()
