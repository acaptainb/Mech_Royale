"""v10 pickup tie-break: baseline and candidate as real bot processes from identical starts.

    py tools/pickup_tiebreak_trial.py [--baseline <git revision>]

The closed-loop world is tools/pickup_trial.py's: the mech goes where the bot steers it on the
navigation grid, pickups are visible within proximity range or the vision wedge, and a pickup
leaves the world only after a valid take. Every episode puts the next circle 120-220 m away,
so after the take the mech still has to walk to safety. Measures: which pickup was taken,
time to reach safety (inside the next circle), and decisions spent outside the shrinking
current circle (missed zone deadline). Standard library only.
"""
import copy
import math
import random
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import pickup_trial as pt
from harness import BASELINE, BotProcess, export

HELLO, TEMPLATE, CONFIG, GRID = pt.HELLO, pt.TEMPLATE, pt.CONFIG, pt.GRID
DT = 0.1
CAP_S = 45.0


def distance_field(goal):
    """Walking distance (m) from every free cell to the goal cell, by breadth-first search."""
    start = GRID.snap(goal)
    seen, queue = {start: 0}, deque([start])
    while queue:
        i = queue.popleft()
        for j in (i - 1, i + 1, i - GRID.width, i + GRID.width):
            if GRID.free[j] and j not in seen:
                seen[j] = seen[i] + 1
                queue.append(j)
    return {cell: steps * GRID.step for cell, steps in seen.items()}


def onward(field, spot):
    return field.get(GRID.snap(spot), math.inf)


def simulate(act, scenario):
    """One episode with act(obs) -> action; returns what actually happened."""
    stats = CONFIG["mech"]
    x, y = scenario["start"]
    zone = scenario["zone"]
    pickups = {p["id"]: p for p in copy.deepcopy(scenario["pickups"])}
    weapons = copy.deepcopy(TEMPLATE["self"]["weapons"])
    weapons[1] = None
    yaw = math.atan2(zone["next_center"][1] - y, zone["next_center"][0] - x)
    energy, spent_at, events = stats["energy"], -10.0, []
    out = dict(taken=None, take_t=None, safe_t=None, outside=0, walked=0.0)
    for tick in range(int(CAP_S / DT)):
        now = tick * DT
        f = min(1.0, max(0.0, (now - zone["shrink_start"]) / (zone["shrink_end"] - zone["shrink_start"])))
        centre = [zone["center"][k] + f * (zone["next_center"][k] - zone["center"][k]) for k in (0, 1)]
        radius = zone["radius"] + f * (zone["next_radius"] - zone["radius"])
        in_zone = math.dist((x, y), centre) <= radius
        out["outside"] += not in_zone
        if math.dist((x, y), zone["next_center"]) <= zone["next_radius"] and out["taken"] is not None:
            out["safe_t"] = round(now, 1)
            break
        z = pt.ground(x, y)
        visible = []
        for p in pickups.values():
            d = math.dist((x, y), p["pos"][:2])
            off = abs((math.atan2(p["pos"][1] - y, p["pos"][0] - x) - yaw + math.pi) % math.tau - math.pi)
            if d <= CONFIG["vision"]["near_range"] or (d <= CONFIG["vision"]["range"]
                                                       and off <= math.radians(CONFIG["vision"]["fov_deg"]) / 2):
                visible.append(copy.deepcopy(p))
        obs = copy.deepcopy(TEMPLATE)
        obs.update(tick=2 * tick, t=round(now, 2), mechs=[], projectiles=[], crates=[], cubes=[],
                   pickups=visible, sounds=[], beams=[], events=events, drops=[], offer=None)
        obs["zone"] = dict(center=centre, radius=radius, next_center=list(zone["next_center"]),
                           next_radius=zone["next_radius"], shrink_start=zone["shrink_start"],
                           shrink_end=zone["shrink_end"], dps=20)
        obs["self"].update(pos=[x, y, z], vel=[0, 0, 0], aim=[yaw, 0.0], hp=1400, max_hp=1400,
                           energy=energy, grounded=True, in_zone=in_zone, cubes=0, upgrades=[],
                           weapons=copy.deepcopy(weapons))
        action = act(obs)
        events = []
        wanted = pickups.get(action.get("take"))
        if action.get("take") is not None:
            if (wanted and weapons[1] is None and math.dist((x, y), wanted["pos"][:2]) <= CONFIG["loot"]["pickup_radius"]
                    and abs(wanted["pos"][2] - z) <= 4):
                del pickups[wanted["id"]]
                weapons[1] = dict(kind=wanted["kind"], cooldown=1.0, stats={})
                events.append(dict(type="took", id=wanted["id"], kind=wanted["kind"], slot=1))
                out["taken"], out["take_t"] = wanted["id"], round(now, 1)
            else:
                events.append(dict(type="take_failed", id=action["take"], reason="range" if wanted else "gone"))
        if "aim" in action:
            turn = (action["aim"][0] - yaw + math.pi) % math.tau - math.pi
            yaw += max(-stats["turn_rate"] * DT, min(stats["turn_rate"] * DT, turn))
        mx, my = action.get("move", [0, 0])
        length = math.hypot(mx, my)
        if length > 1:
            mx, my = mx / length, my / length
        speed = stats["walk_speed"]
        if action.get("boost") and length > 0 and energy > 0:
            speed = stats["boost_speed"]
            energy = max(0.0, energy - stats["boost_drain"] * DT)
            spent_at = now
        elif now - spent_at >= stats["energy_regen_delay"]:
            energy = min(stats["energy"], energy + stats["energy_regen"] * DT)
        for axis, delta in enumerate((mx, my)):
            candidate = [x, y]
            candidate[axis] += delta * speed * DT
            if pt.walkable(candidate):
                out["walked"] += abs(delta * speed * DT)
                x, y = candidate
    return out


# --- crafted layouts ----------------------------------------------------------------------

def zone_for(start, goal):
    mid = [(start[0] + goal[0]) / 2, (start[1] + goal[1]) / 2]
    radius = math.dist(start, goal) / 2 + 120
    return dict(center=mid, radius=radius, next_center=list(goal), next_radius=25.0,
                shrink_start=55.0, shrink_end=85.0)


def ring(start, low, high):
    """Walkable spots low-high m from start with a clear straight route from it."""
    spots = []
    for r in range(int(low), int(high) + 1, 3):
        for b in range(0, 360, 10):
            a = math.radians(b)
            p = [start[0] + r * math.cos(a), start[1] + r * math.sin(a)]
            if pt.walkable(p) and GRID.clear_segment(start, p):
                spots.append(p)
    return spots


def find_layouts():
    """Search the map once for the three crafted two-pickup layouts."""
    found = {}
    rng = random.Random(4040)
    free = [i for i, v in enumerate(GRID.free) if v]
    tries = 0
    while len(found) < 3 and tries < 4000:
        tries += 1
        start = list(GRID.point(rng.choice(free)))
        a = rng.uniform(0, math.tau)
        goal = [start[0] + rng.uniform(120, 200) * math.cos(a), start[1] + rng.uniform(120, 200) * math.sin(a)]
        if not pt.walkable(goal):
            continue
        field = distance_field(goal)
        if GRID.snap(start) not in field:
            continue
        spots = ring(start, 18, 40)
        info = [(math.dist(start, p), p, GRID.clear_segment(p, goal), onward(field, p)) for p in spots]
        blocked = [s for s in info if not s[2] and s[3] < math.inf and s[3] - math.dist(s[1], goal) >= 30]
        clear = [s for s in info if s[2]]
        if "courtyard vs open" not in found:
            for d1, p1, _, w1 in blocked:
                pair = next((s for s in clear if d1 + 1 <= s[0] <= d1 + 6 and w1 >= s[3] + 25), None)
                if pair:
                    found["courtyard vs open"] = (start, goal, p1, pair[1])
                    break
        if "faster courtyard pickup wins" not in found:
            near = [s for s in blocked if s[0] <= 22]
            for d1, p1, _, w1 in near:
                pair = next((s for s in clear if s[0] >= d1 + 18), None)
                if pair:
                    found["faster courtyard pickup wins"] = (start, goal, p1, pair[1])
                    break
        if "shared doorway" not in found:
            for d1, p1, _, w1 in blocked:
                pair = next((s for s in blocked if s[1] is not p1 and d1 + 1 <= s[0] <= d1 + 6
                             and abs(s[3] - w1) <= 12 and math.dist(s[1], p1) <= 15), None)
                if pair:
                    found["shared doorway"] = (start, goal, p1, pair[1])
                    break
    return found


def scenario(start, goal, spots):
    pickups = [pt.pickup_at(p, key=8001 + k, kind=("laser", "mortar")[k]) for k, p in enumerate(spots)]
    return dict(start=start, zone=zone_for(start, goal), pickups=pickups)


def run_pair(folder, sc):
    rows = {}
    for label, place in (("base", folder), ("cand", ROOT)):
        bot = BotProcess(place, HELLO)
        rows[label] = simulate(bot.act, sc)
        bot.close()
    return rows


def local_count(sc):
    """The same deterministic episode in-process, to read the tie-break counters."""
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    bot = Bot(HELLO)
    simulate(bot.act, sc)
    return bot.loot.ties, bot.loot.tiebreaks


def fmt(row):
    taken = {8001: "first", 8002: "second", None: "none"}[row["taken"]]
    safe = "never" if row["safe_t"] is None else f"{row['safe_t']:.1f}"
    after = "-" if row["safe_t"] is None or row["take_t"] is None else f"{row['safe_t'] - row['take_t']:.1f}"
    return taken, safe, after, row["outside"]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    layouts = find_layouts()
    failures = []
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    print(f"{'layout':32}{'taken':>16}{'safe at s':>14}{'take->safe s':>16}{'outside':>10}{'ties/breaks':>13}  check")
    print(f"{'':32}{'base | v10':>16}{'base | v10':>14}{'base | v10':>16}{'base|v10':>10}")
    cases = []
    for name in ("courtyard vs open", "faster courtyard pickup wins", "shared doorway"):
        if name not in layouts:
            failures.append(f"{name}: no geometry found")
            continue
        start, goal, p1, p2 = layouts[name]
        cases.append((name, scenario(start, goal, [p1, p2]), name == "courtyard vs open"))
    start, goal, p1, _ = layouts["courtyard vs open"]
    cases.append(("single pickup (control)", scenario(start, goal, [p1]), False))
    traces = {}
    for name, sc, activates in cases:
        rows = run_pair(folder, sc)
        ties, breaks = local_count(sc)
        b, c = fmt(rows["base"]), fmt(rows["cand"])
        if activates:
            ok = (rows["base"]["taken"] == 8001 and rows["cand"]["taken"] == 8002
                  and rows["cand"]["safe_t"] is not None and rows["base"]["safe_t"] is not None
                  and rows["cand"]["safe_t"] < rows["base"]["safe_t"] and breaks == 1)
            text = "takes the open pickup and reaches safety sooner"
        else:
            ok = rows["base"] == rows["cand"] and breaks == 0
            text = "identical to the baseline"
        print(f"{name:32}{b[0]:>7} | {c[0]:<7}{b[1]:>6} | {c[1]:<6}{b[2]:>7} | {c[2]:<7}{b[3]:>4} | {c[3]:<4}{ties:>5}/{breaks:<6} "
              f"{'ok  ' if ok else 'FAIL'} {text}")
        traces[name] = (sc, rows)
        if not ok:
            failures.append(name)
    sc, rows = traces["courtyard vs open"]
    start, goal, p1, p2 = layouts["courtyard vs open"]
    print(f"\ncourtyard vs open geometry: start {[round(v, 1) for v in start]}, next circle {[round(v, 1) for v in goal]};"
          f" first pickup {math.dist(start, p1):.0f} m (onward line blocked), second {math.dist(start, p2):.0f} m (onward line clear)")

    # Activation outside the crafted layouts.
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    counted = []

    class Counting(Bot):
        def __init__(self, hello):
            super().__init__(hello)
            counted.append(self)

    for index, (name, _) in enumerate(pt.SCENARIOS.items()):
        rng = random.Random(51739 + index)
        for _ in range(pt.INSTANCES):
            pt.simulate(Counting, pt.build(name, rng))
    pickup_ties = sum(b.loot.ties for b in counted)
    pickup_breaks = sum(b.loot.tiebreaks for b in counted)
    bot = Bot(HELLO)
    for obs in pt.STREAM if hasattr(pt, "STREAM") else []:
        bot.act(copy.deepcopy(obs))
    import gzip, json
    with gzip.open(ROOT / "check/stream.jsonl.gz", "rt") as f:
        next(f)
        stream = [json.loads(line) for line in f if '"obs"' in line]
    bot = Bot(HELLO)
    for obs in stream:
        bot.act(copy.deepcopy(obs))
    print(f"\nactivation: pickup_trial ({len(counted)} episodes) ties {pickup_ties}, tie-breaks {pickup_breaks};"
          f" standard recording ties {bot.loot.ties}, tie-breaks {bot.loot.tiebreaks}")

    # Held-out randomized two-pickup layouts (seed fixed before the run, never tuned on).
    rng = random.Random(90901)
    free = [i for i, v in enumerate(GRID.free) if v]
    layouts_run = activated = 0
    better = worse = same = 0
    delta = []
    while layouts_run < 150:
        start = list(GRID.point(rng.choice(free)))
        a = rng.uniform(0, math.tau)
        goal = [start[0] + rng.uniform(120, 200) * math.cos(a), start[1] + rng.uniform(120, 200) * math.sin(a)]
        if not pt.walkable(goal):
            continue
        spots = ring(start, 15, 42)
        if len(spots) < 2:
            continue
        p1, p2 = rng.sample(spots, 2)
        sc = scenario(start, goal, [p1, p2])
        local = Bot(HELLO)
        simulate(local.act, sc)
        layouts_run += 1
        if local.loot.tiebreaks:
            activated += 1
            rows = run_pair(folder, sc)
            bs, cs = rows["base"]["safe_t"], rows["cand"]["safe_t"]
            if bs is not None and cs is not None:
                delta.append(cs - bs)
                better += cs < bs - 0.05
                worse += cs > bs + 0.05
                same += abs(cs - bs) <= 0.05
            elif cs is not None:
                better += 1
            elif bs is not None:
                worse += 1
            if rows["cand"]["outside"] > rows["base"]["outside"]:
                failures.append(f"held-out layout {layouts_run}: more decisions outside the zone")
    mean = sum(delta) / len(delta) if delta else 0.0
    print(f"held-out random layouts: {layouts_run} run, tie-break fired in {activated}"
          f" ({100 * activated / layouts_run:.0f}%); where it fired, safety reached sooner in {better},"
          f" later in {worse}, same in {same}; mean change {mean:+.1f} s")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
