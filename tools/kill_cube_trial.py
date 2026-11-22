"""v11 post-kill cube detour: baseline and candidate as real bot processes from matched starts.

    py tools/kill_cube_trial.py [--baseline <git revision>]

Each episode: a short fight with mech 7 (it hits us twice), then a `kill` event at t=0.5 and
three cubes on the ground where it stood. Our mech walks toward the next circle under the
bot's own commands (ground acceleration, walk and boost speed, boost energy, the navigation
grid). A cube is collected within 3.5 m; each adds 4% of base HP to max HP and heals that much.
HP regenerates after 5 s without damage while inside the zone. At t=14 s a fresh mech appears
and aims at us: our HP on that decision is "HP at the next encounter". The episode runs until the
mech reaches the next circle's centre (cap 25 s), so the detour's travel cost shows. Reports cubes collected,
detour seconds (decisions spent going for cubes in the window), HP at the next encounter, and decisions spent
outside the current circle. Standard library only.
"""
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
from harness import BASELINE, BotProcess, export, plain
from navigation import Navigator

CONFIG = et.HELLO["config"]
MECH = CONFIG["mech"]
CUBES = CONFIG["cubes"]
GRID = Navigator()
DT_TICK = 0.05
T_KILL = 0.5
T_ENCOUNTER = 14.0
CAP_S = 25.0
CUBE_HP = CUBES["hp_per_cube"] * MECH["hp"]


def walkable(point):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


def at_ground(x, y):
    return [round(x, 2), round(y, 2), round(et.ground(x, y), 2)]


def opponent(key, pos, me, aim_at_us):
    toward = math.atan2(me[1] - pos[1], me[0] - pos[0])
    return dict(id=key, kind="mech", pos=list(pos), vel=[0.0, 0.0, 0.0],
                aim=[toward if aim_at_us else toward + math.pi / 2, 0.0], hp=1400, max_hp=1400,
                cubes=0, weapons=["gun"], charging=False)


def zone_at(ep, now):
    z = ep["zone"]
    f = min(1.0, max(0.0, (now - z["shrink_start"]) / (z["shrink_end"] - z["shrink_start"])))
    centre = [z["center"][k] + f * (z["next_center"][k] - z["center"][k]) for k in (0, 1)]
    radius = z["radius"] + f * (z["next_radius"] - z["radius"])
    return dict(z, center=centre, radius=radius)


def simulate(act, ep):
    """Run one episode with `act(obs) -> action`; return the measurements and actions."""
    x, y = ep["start"]
    vx = vy = 0.0
    energy, spent_at = MECH["energy"], -10.0
    hp, max_hp, cubes_held, last_damage = 1400.0, 1400.0, 0, -10.0
    cubes, outside, actions, reached = [], 0, [], None
    move, boost, events = [0.0, 0.0], False, []
    hp_at_encounter = None
    for tick in range(int(CAP_S / DT_TICK) + 2):
        now = round(tick * DT_TICK, 2)
        zone = zone_at(ep, now)
        inside = math.dist((x, y), zone["center"]) <= zone["radius"]
        if tick % 2 == 0:
            k = tick // 2
            me = [x, y, et.ground(x, y)]
            mechs = []
            if now < T_KILL - 1e-9:
                mechs.append(opponent(7, ep["dead_at"], me, True))
                if k in (0, 3):
                    events.append(dict(type="damaged", amount=45, weapon="gun", by=7,
                                       bearing=math.atan2(ep["dead_at"][1] - y, ep["dead_at"][0] - x)))
                    hp -= 45
                    last_damage = now
            if abs(now - T_KILL) < 1e-9:
                if ep["kill"]:
                    events += [dict(type="hit", target=7, amount=45, weapon="gun"), dict(type="kill", target=7)]
                cubes = [dict(id=5000 + n, pos=at_ground(ep["dead_at"][0] + dx, ep["dead_at"][1] + dy))
                         for n, (dx, dy) in enumerate(((0, 0), (1.5, 1.0), (-1.2, 1.4)))]
            for other in ep.get("others", []):
                if other["from"] <= now:
                    walked = (now - other["from"]) * other.get("speed", 0.0)
                    sx, sy = other["pos"][:2]
                    d = math.dist((sx, sy), (x, y))
                    f = min(1.0, walked / d) if d > 0 else 0.0
                    pos = at_ground(sx + (x - sx) * f * 0.8, sy + (y - sy) * f * 0.8)
                    mechs.append(opponent(other["id"], pos, me, other["aims"]))
            if now >= T_ENCOUNTER - 1e-9:
                ahead = ep["encounter_at"]
                mechs.append(opponent(9, at_ground(*ahead), me, True))
                if hp_at_encounter is None:
                    hp_at_encounter = round(hp, 1)
            visible = [c for c in cubes if math.dist(c["pos"][:2], (x, y)) <= 100]
            obs = et.frame(k, mechs, events, origin=(x, y), hp=hp)
            obs["self"].update(pos=me, vel=[vx, vy, 0.0], energy=energy, max_hp=max_hp, cubes=cubes_held,
                               in_zone=inside)
            obs["zone"] = dict(zone)
            obs["cubes"] = copy.deepcopy(visible)
            obs["t"] = now
            if not inside:
                outside += 1
            action = act(obs)
            actions.append(plain(action))
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            if hp_at_encounter is not None and reached is not None:
                break
        # cubes
        for c in list(cubes):
            if math.dist(c["pos"][:2], (x, y)) <= CUBES["pickup_radius"] and abs(c["pos"][2] - et.ground(x, y)) <= 4:
                cubes.remove(c)
                cubes_held += 1
                max_hp += CUBE_HP
                hp += CUBE_HP
                events.append(dict(type="pickup", cubes=cubes_held))
        # health
        if not inside:
            hp -= zone["dps"] * DT_TICK
            last_damage = now
        elif now - last_damage >= MECH["regen_delay"]:
            hp = min(max_hp, hp + MECH["regen_per_s"] * DT_TICK)
        # movement
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        speed = MECH["walk_speed"]
        if boost and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            energy = max(0.0, energy - MECH["boost_drain"] * DT_TICK)
            spent_at = now
        elif now - spent_at >= MECH["energy_regen_delay"]:
            energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT_TICK)
        dvx, dvy = mx * speed - vx, my * speed - vy
        dv = math.hypot(dvx, dvy)
        limit = MECH["ground_accel"] * DT_TICK
        if dv > limit:
            dvx, dvy = dvx * limit / dv, dvy * limit / dv
        vx, vy = vx + dvx, vy + dvy
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * DT_TICK
            if walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        if reached is None and math.dist((x, y), ep["zone"]["next_center"]) <= 4:
            reached = round(now, 1)
    return dict(cubes=cubes_held, hp=hp_at_encounter, outside_s=round(outside * 0.1, 1),
                reached=reached, actions=actions)


# --- episodes -----------------------------------------------------------------------------

def layout():
    """A start on the open lawn, a clear heading to the next circle, and clear sides."""
    home = list(et.HOME)
    for bearing in range(0, 360, 5):
        a = math.radians(bearing)
        goal = [home[0] + 100 * math.cos(a), home[1] + 100 * math.sin(a)]
        if not (GRID.clear_segment(home, goal) and walkable(goal)):
            continue
        for sign in (1, -1):
            side = (-math.sin(a) * sign, math.cos(a) * sign)
            near = [home[0] + side[0] * 25 + math.cos(a) * 5, home[1] + side[1] * 25 + math.sin(a) * 5]
            far = [home[0] + side[0] * 70 + math.cos(a) * 5, home[1] + side[1] * 70 + math.sin(a) * 5]
            if all(walkable(p) and GRID.clear_segment(home, p) for p in (near, far)):
                return home, a, goal, near, far, side
    raise RuntimeError("no layout")


def episodes():
    home, a, goal, near, far, side = layout()
    roomy = dict(center=home, radius=400.0, next_center=goal, next_radius=150.0,
                 shrink_start=1000.0, shrink_end=1050.0, dps=20)
    ahead = [home[0] + math.cos(a) * 80, home[1] + math.sin(a) * 80]
    approach_from = [home[0] + math.cos(a) * 110 + side[0] * 20, home[1] + math.sin(a) * 110 + side[1] * 20]
    far_passive = [home[0] - math.cos(a) * 180, home[1] - math.sin(a) * 180]
    # Closing: we stand 5 m outside a next circle whose shrink starts at t=3 s; the cubes lie
    # inside that next circle, within detour reach.
    closing = dict(center=home, radius=400.0, next_center=goal, next_radius=95.0,
                   shrink_start=3.0, shrink_end=23.0, dps=20)
    closing_cubes = [home[0] + side[0] * 25 + math.cos(a) * 30, home[1] + side[1] * 25 + math.sin(a) * 30]
    # Same shrink, but the cubes lie beyond the next circle: they may never be chased.
    beyond = [home[0] + side[0] * 30 - math.cos(a) * 10, home[1] + side[1] * 30 - math.sin(a) * 10]
    near, far, closing_cubes, beyond = (at_ground(*p) for p in (near, far, closing_cubes, beyond))
    base = dict(start=home, encounter_at=ahead, kill=True, zone=roomy)
    return [
        dict(base, name="nearby reward (25 m), nobody else", dead_at=near, expect="collect"),
        dict(base, name="nearby reward, far passive mech listed", dead_at=near, expect="collect",
             others=[dict(id=12, pos=at_ground(*far_passive), from_=0.0, aims=False)]),
        dict(base, name="distant reward (70 m)", dead_at=far, expect="identical"),
        dict(base, name="opponent approaches mid-detour", dead_at=near, expect="cancel",
             others=[dict(id=11, pos=at_ground(*approach_from), aims=True, speed=11.7, from_=3.5)]),
        dict(base, name="closing zone, cubes in the next circle", dead_at=closing_cubes, zone=closing,
             expect="zone-safe"),
        dict(base, name="closing zone, cubes beyond it", dead_at=beyond, zone=closing, expect="identical"),
        dict(base, name="control: cubes without a kill", dead_at=near, kill=False, expect="identical"),
    ]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`;"
          f" kill at t={T_KILL} s, next encounter at t={T_ENCOUNTER} s\n")
    print(f"{'episode':40}{'cubes':>11}{'detour s':>10}{'HP at next encounter':>23}{'s outside':>12}"
          f"{'at goal s':>13}  check")
    print(f"{'':40}{'base | v11':>11}{'v11':>10}{'base | v11':>23}{'base | v11':>12}{'base | v11':>13}")
    failures, traces = [], {}
    for ep in episodes():
        for other in ep.get("others", []):
            other["from"] = other.pop("from_", other.get("from", 0.0))
        rows = {}
        for key, where in (("base", folder), ("cand", ROOT)):
            bot = BotProcess(where, et.HELLO)
            rows[key] = simulate(bot.act, ep)
            bot.close()
        local = Bot(et.HELLO)  # the same deterministic run in-process, to read the rule's counters
        unsafe, timeline = [], {}

        def watched(obs):
            before = local.kill_cubes.counts.get("detour decisions", 0)
            cancels_before = sum(v for k, v in local.kill_cubes.counts.items() if k.startswith("cancelled"))
            action = local.act(obs)
            if any(m["id"] == 11 for m in obs["mechs"]):
                timeline.setdefault("threat listed", obs["t"])
            if sum(v for k, v in local.kill_cubes.counts.items() if k.startswith("cancelled")) > cancels_before:
                timeline.setdefault("cancelled", obs["t"])
            if local.kill_cubes.counts.get("detour decisions", 0) > before:
                zone = obs["zone"]
                inside_next = math.dist(obs["self"]["pos"][:2], zone["next_center"]) <= zone["next_radius"]
                if not (obs["self"]["in_zone"] and (inside_next or local.kill_cubes.comfortable(obs, "zone"))):
                    unsafe.append(obs["t"])
            return action

        simulate(watched, ep)
        counts = dict(local.kill_cubes.counts)
        detour_s = counts.get("detour decisions", 0) * 0.1
        base, cand = rows["base"], rows["cand"]
        if ep["expect"] == "identical":
            ok = base["actions"] == cand["actions"] and cand["outside_s"] <= base["outside_s"]
            text = "identical to baseline"
        elif ep["expect"] == "zone-safe":
            ok = not unsafe and cand["outside_s"] <= base["outside_s"]
            text = "detours only while safely inside; no extra time outside"
        elif ep["expect"] == "collect":
            ok = cand["cubes"] > base["cubes"] and cand["outside_s"] <= base["outside_s"]
            text = "collects cubes the baseline leaves"
        else:
            cancels = {k: v for k, v in counts.items() if k.startswith("cancelled")}
            ok = (bool(cancels) and cand["outside_s"] <= base["outside_s"]
                  and timeline.get("cancelled") == timeline.get("threat listed"))
            text = (f"cancelled ({', '.join(cancels) or 'never'}) at t={timeline.get('cancelled')} s,"
                    f" threat first listed at t={timeline.get('threat listed')} s")
        hp = lambda r: "-" if r["hp"] is None else f"{r['hp']:.0f}"
        goal = lambda r: "-" if r["reached"] is None else f"{r['reached']:.1f}"
        print(f"{ep['name']:40}{base['cubes']:>5} | {cand['cubes']:<4}{detour_s:>9.1f}"
              f"{hp(base):>14} | {hp(cand):<7}{base['outside_s']:>5.1f} | {cand['outside_s']:<5.1f}"
              f"{goal(base):>6} | {goal(cand):<5}  {'ok  ' if ok else 'FAIL'} {text}")
        traces[ep["name"]] = (base, cand, counts)
        if not ok:
            failures.append(ep["name"])
    base, cand, counts = traces["opponent approaches mid-detour"]
    print(f"\nopponent case, rule outcomes: {counts}")
    base, cand, counts = traces["nearby reward, far passive mech listed"]
    print("\ntrace, nearby reward with a far passive mech listed (decision: move):")
    for k in (4, 5, 6, 10, 20, 28, 34, 40):
        if k < len(base["actions"]) and k < len(cand["actions"]):
            fmt = lambda act: f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}]"
            print(f"  t={k * 0.1:4.1f}  baseline {fmt(base['actions'][k])}   v11 {fmt(cand['actions'][k])}")
    # The standard recording: no kill events, so nothing may change.
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o))) for o in et.STREAM)
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    kills = sum(1 for o in et.STREAM for e in o["events"] if e.get("type") == "kill")
    print(f"\nrecording: {kills} kill events; rule outcomes {local.kill_cubes.counts or 'none'};"
          f" {differ} of {len(et.STREAM)} decisions answered differently; round trip p99 {p99:.1f} ms")
    if differ:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
