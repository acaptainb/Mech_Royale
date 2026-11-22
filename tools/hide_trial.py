"""hide-spot on dodge-tuned (dd9b731, official 3.10) and this tree as real bot processes.

    py tools/hide_trial.py [--baseline <git revision>] [--runs N]

Closed loop on the navigation grid: the mech goes where the bot steers it, the zone is fixed
for the episode (shrink far away unless a case says otherwise), and vision follows the rules:
a mech's eye (ground + 8 m) sees a body's centre (+4.5 m) or top (+9 m) through a clear line on
the cover map, within 45 m in any direction or 200 m inside a 120 degree wedge around its
facing; seen mechs stay listed for 5 s. Trees are not modelled (the cover map has no canopy).

1. Exposure: where the bot stands over the last 20 s of a 40 s episode near a zone centre,
   measured independently of exposure.u8 (36 bearings x 30/70/140/200 m observers).
2. Hunters: three scripted hunters (shared vision) that patrol around the zone centre, or walk
   straight at our true position ("omniscient"), and shoot when they see us: 45 damage per hit,
   one shot per 0.24 s, hit chance falling with distance, x1.5 from behind. Our own shots are
   not simulated, so this isolates positioning. Reported: first time any hunter saw us, damage
   taken and deaths in 90 s.
3. Controls that must match the baseline on every decision: an urgent zone return, an opponent
   listed from the start, and a supply drop the bot is walking to.
Also prints decision timing and the recording comparison. Standard library only.
"""
import copy
import gzip
import json
import math
import random
import statistics
import sys
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from cover import Cover
from harness import BotProcess, export, plain
from hide import HideSpot
from navigation import Navigator

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
with gzip.open(ROOT / "check/stream.jsonl.gz", "rt") as f:
    HELLO, TEMPLATE = json.loads(next(f)), json.loads(next(f))
    STREAM = [json.loads(line) for line in f if '"obs"' in line]
CONFIG, MECH, VISION = HELLO["config"], HELLO["config"]["mech"], HELLO["config"]["vision"]
GRID, COVER = Navigator(), Cover()
HEIGHTS = array("h")
HEIGHTS.frombytes((ROOT / "heights.i16").read_bytes())
if sys.byteorder == "big":
    HEIGHTS.byteswap()
FREE = [i for i, free in enumerate(GRID.free) if free]
DT = 0.1
EYE, CENTRE, TOP = MECH["eye_height"], 4.5, MECH["height"]


def ground(x, y):
    u = min(GRID.width - 1.001, max(0.0, (x - GRID.ox) / GRID.step))
    v = min(GRID.height - 1.001, max(0.0, (y - GRID.oy) / GRID.step))
    i, j = int(u), int(v)
    fu, fv = u - i, v - j
    k = j * GRID.width + i
    low = HEIGHTS[k] * (1 - fu) + HEIGHTS[k + 1] * fu
    high = HEIGHTS[k + GRID.width] * (1 - fu) + HEIGHTS[k + GRID.width + 1] * fu
    return (low * (1 - fv) + high * fv) / 100


def walkable(point):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


def sees(eye_xy, body_xy):
    """A mech standing at eye_xy has a clear line from its eye to the body's centre or top."""
    ez = ground(*eye_xy) + EYE
    bz = ground(*body_xy)
    eye = (eye_xy[0], eye_xy[1], ez)
    return (COVER.clear(eye, (body_xy[0], body_xy[1], bz + TOP), skip_start=0.5, skip_end=2.5)
            or COVER.clear(eye, (body_xy[0], body_xy[1], bz + CENTRE), skip_start=0.5, skip_end=2.5))


def in_view(eye_xy, facing, body_xy):
    distance = math.dist(eye_xy, body_xy)
    if distance > VISION["range"]:
        return False
    if distance > VISION["near_range"]:
        bearing = math.atan2(body_xy[1] - eye_xy[1], body_xy[0] - eye_xy[0])
        if abs((bearing - facing + math.pi) % math.tau - math.pi) > math.radians(VISION["fov_deg"]) / 2:
            return False
    return sees(eye_xy, body_xy)


_measured = {}


def measured_exposure(point):
    """Independent of exposure.u8: 36 bearings x 30/70/140/200 m walkable observers."""
    k = GRID.snap(point)
    if k not in _measured:
        here = GRID.point(k)
        seen = total = 0
        for d in range(36):
            a = d * math.tau / 36 + 0.05
            for r in (30.0, 70.0, 140.0, 200.0):
                total += 1
                o = (here[0] + r * math.cos(a), here[1] + r * math.sin(a))
                if walkable(o) and sees(GRID.point(GRID.snap(o)), here):
                    seen += 1
        _measured[k] = seen / total
    return _measured[k]


def interpolate(zone, now):
    f = min(1.0, max(0.0, (now - zone["shrink_start"]) / (zone["shrink_end"] - zone["shrink_start"])))
    centre = [zone["center"][k] + f * (zone["next_center"][k] - zone["center"][k]) for k in (0, 1)]
    return centre, zone["radius"] + f * (zone["next_radius"] - zone["radius"])


def simulate(folder, scenario):
    """One closed-loop episode. Returns positions, actions and what the hunters did."""
    bot = BotProcess(folder, HELLO)
    rng = random.Random(scenario["seed"])
    x, y = scenario["start"]
    zone = scenario["zone"]
    yaw = math.atan2(zone["next_center"][1] - y, zone["next_center"][0] - x)
    hp = scenario.get("hp", MECH["hp"])
    energy, spent_at, hurt_at = MECH["energy"], -10.0, -10.0
    events = []
    hunters = [dict(h, nav=Navigator(), shot_clock=0.0, wander=None, facing=h.get("facing", 0.0),
                    listed_until=-1.0) for h in copy.deepcopy(scenario.get("hunters", []))]
    known_at, known = -10.0, None
    out = dict(positions=[], hurt=[], seen=[], actions=[], first_seen=None, damage=0.0, died=None, hits=0, rear=0)
    for tick in range(int(scenario["seconds"] / DT)):
        now = round(tick * DT, 2)
        centre, radius = interpolate(zone, now)
        in_zone = math.dist((x, y), centre) <= radius
        if not in_zone:
            hp -= zone["dps"] * DT
            hurt_at = now
        # --- hunters: shared vision, then shooting ---
        seen_now = [h for h in hunters if in_view(h["pos"], h["facing"], (x, y))]
        if seen_now:
            known_at, known = now, (x, y)
            if out["first_seen"] is None:
                out["first_seen"] = now
        hunting = now - known_at <= VISION["memory_s"]
        for h in hunters:
            h["shot_clock"] = max(0.0, h["shot_clock"] - DT)
            distance = math.dist(h["pos"], (x, y))
            if hunting and h["shot_clock"] == 0.0 and distance <= 200 and sees(h["pos"], (x, y)):
                h["shot_clock"] = 0.24
                h["facing"] = math.atan2(y - h["pos"][1], x - h["pos"][0])
                if rng.random() < max(0.15, 0.85 - distance / 300):
                    bearing = math.atan2(h["pos"][1] - y, h["pos"][0] - x)
                    rear = abs((bearing - yaw + math.pi) % math.tau - math.pi) > math.pi / 2
                    amount = 45 * (MECH["rear_mult"] if rear else 1)
                    hp -= amount
                    hurt_at = now
                    out["damage"] += amount
                    out["hits"] += 1
                    out["rear"] += rear
                    events.append(dict(type="damaged", amount=amount, weapon="gun", bearing=bearing,
                                       by=h["id"], rear=rear))
        if hp <= 0:
            out["died"] = now
            break
        # --- what we see ---
        listed = []
        for h in hunters:
            if in_view((x, y), yaw, h["pos"]):
                h["listed_until"] = now + VISION["memory_s"]
            if h.get("always_listed") or now <= h["listed_until"]:
                hz = ground(*h["pos"])
                listed.append(dict(id=h["id"], kind="mech", pos=[h["pos"][0], h["pos"][1], hz],
                                   vel=[0, 0, 0], aim=[h["facing"], 0.0], hp=1400, max_hp=1400, cubes=0,
                                   weapons=["gun"], charging=False))
        z = ground(x, y)
        obs = copy.deepcopy(TEMPLATE)
        obs.update(tick=2 * tick, t=now, mechs=listed, projectiles=[], crates=[], cubes=[], pickups=[],
                   sounds=[], beams=[], events=events, drops=copy.deepcopy(scenario.get("drops", [])),
                   offer=None, alive=16)
        obs["zone"] = dict(center=centre, radius=radius, next_center=list(zone["next_center"]),
                           next_radius=zone["next_radius"], shrink_start=zone["shrink_start"],
                           shrink_end=zone["shrink_end"], dps=zone["dps"])
        obs["self"].update(pos=[x, y, z], vel=[0, 0, 0], aim=[yaw, 0.0], hp=hp, max_hp=MECH["hp"],
                           energy=energy, grounded=True, in_zone=in_zone, cubes=0, upgrades=[])
        action = bot.act(obs)
        events = []
        out["actions"].append(plain(action))
        out["positions"].append((x, y))
        out["hurt"].append(out["damage"])
        out["seen"].append(bool(seen_now))
        # --- our movement ---
        if "aim" in action:
            turn = (action["aim"][0] - yaw + math.pi) % math.tau - math.pi
            yaw += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        mx, my = action.get("move", [0, 0])
        length = math.hypot(mx, my)
        if length > 1:
            mx, my = mx / length, my / length
        speed = MECH["walk_speed"]
        if action.get("boost") and length > 0 and energy > 0:
            speed = MECH["boost_speed"]
            energy = max(0.0, energy - MECH["boost_drain"] * DT)
            spent_at = now
        elif now - spent_at >= MECH["energy_regen_delay"]:
            energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT)
        for axis, delta in enumerate((mx, my)):
            candidate = [x, y]
            candidate[axis] += delta * speed * DT
            if walkable(candidate):
                x, y = candidate
        if scenario.get("regen", True) and in_zone and now - hurt_at >= MECH["regen_delay"]:
            hp = min(MECH["hp"], hp + MECH["regen_per_s"] * DT)
        # --- hunter movement ---
        for h in hunters:
            if h.get("static"):
                continue
            if hunting:
                goal = known
                if math.dist(h["pos"], (x, y)) <= 60 and sees(h["pos"], (x, y)):
                    continue  # in a firing position
            elif scenario["search"] == "omniscient":
                goal = (x, y)
            else:
                if h["wander"] is None or math.dist(h["pos"], h["wander"]) < 4:
                    for _ in range(200):
                        a, r = rng.uniform(0, math.tau), rng.uniform(0, 70)
                        p = (zone["next_center"][0] + r * math.cos(a), zone["next_center"][1] + r * math.sin(a))
                        if walkable(p):
                            h["wander"] = GRID.point(GRID.snap(p))
                            break
                goal = h["wander"]
            step = goal if GRID.clear_segment(h["pos"], goal) else h["nav"].waypoint(h["pos"], goal)
            dx, dy = step[0] - h["pos"][0], step[1] - h["pos"][1]
            d = math.hypot(dx, dy)
            if d > 0.3:
                h["facing"] = math.atan2(dy, dx)
                nxt = [h["pos"][0] + dx / d * min(d, MECH["walk_speed"] * DT),
                       h["pos"][1] + dy / d * min(d, MECH["walk_speed"] * DT)]
                if walkable(nxt):
                    h["pos"] = nxt
    out["times"] = bot.times
    bot.close()
    return out


# --- scenarios ------------------------------------------------------------------------------

def zone_around(centre, radius, shrink_start=600.0):
    return dict(center=list(centre), radius=radius + 150, next_center=list(centre), next_radius=radius,
                shrink_start=shrink_start, shrink_end=shrink_start + 40, dps=35)


def sample_zone(rng, want_spot=None):
    """A next circle around a walkable node; want_spot True/False filters on whether the
    candidate's search finds a sheltered spot there."""
    probe = HideSpot(HELLO, GRID)
    while True:
        centre = GRID.point(rng.choice(FREE))
        radius = rng.choice((70.0, 140.0, 240.0))
        zone = zone_around(centre, radius)
        if math.dist(centre, (41.3, -72.8)) + radius > 520:
            continue
        probe.search(zone)
        if want_spot is None or (probe.spot is not None) == want_spot:
            return zone, probe


def start_near(rng, zone, low, high):
    c = zone["next_center"]
    while True:
        a, r = rng.uniform(0, math.tau), rng.uniform(low, high)
        p = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        if walkable(p):
            return list(GRID.point(GRID.snap(p)))


def hunters_around(rng, zone, count=3):
    out = []
    c = zone["next_center"]
    while len(out) < count:
        a, r = rng.uniform(0, math.tau), rng.uniform(150, 250)
        p = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        if walkable(p):
            out.append(dict(id=len(out) + 1, pos=list(GRID.point(GRID.snap(p))),
                            facing=math.atan2(c[1] - p[1], c[0] - p[0])))
    return out


def summary(values):
    return f"{statistics.median(values):.2f}" if values else "-"


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 24
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    failures, times = [], []

    # 1. exposure where the bot stands
    print("1. exposure of where the bot stands, last 20 s of 40 s near a zone centre "
          "(independent 36 x 4 observer sample; lower is better)")
    rng = random.Random(9101)
    rows = []
    for n in range(runs):
        zone, probe = sample_zone(rng)
        scenario = dict(seed=n, start=start_near(rng, zone, 30, 120), zone=zone, seconds=40, search="none")
        base, cand = simulate(folder, scenario), simulate(ROOT, scenario)
        times += cand["times"]
        tail = slice(-200, None)
        eb = statistics.mean(measured_exposure(p) for p in base["positions"][tail])
        ec = statistics.mean(measured_exposure(p) for p in cand["positions"][tail])
        moved = base["actions"] != cand["actions"]
        rows.append((probe.spot is not None, eb, ec, moved, base["positions"][-1], cand["positions"][-1]))
        if probe.spot is None and moved:
            failures.append(f"exposure run {n}: no spot found yet the actions differ")
        if probe.spot is not None and math.dist(cand["positions"][-1], probe.spot) > 3:
            failures.append(f"exposure run {n}: did not reach its spot")
    act = [r for r in rows if r[0]]
    rest = [r for r in rows if not r[0]]
    print(f"   {'zones':34}{'runs':>5}{'base':>8}{'cand':>8}   actions differ")
    print(f"   {'spot found (activates)':34}{len(act):>5}{summary([r[1] for r in act]):>8}"
          f"{summary([r[2] for r in act]):>8}   {sum(r[3] for r in act)}/{len(act)}")
    print(f"   {'no spot clearly better (control)':34}{len(rest):>5}{summary([r[1] for r in rest]):>8}"
          f"{summary([r[2] for r in rest]):>8}   {sum(r[3] for r in rest)}/{len(rest)}")
    better = sum(r[2] < r[1] - 0.02 for r in act)
    worse = sum(r[2] > r[1] + 0.02 for r in act)
    print(f"   activating runs measured lower / higher than the baseline: {better} / {worse}"
          f"   (median metres from the centre: {summary([math.dist(r[5], r[4]) for r in act])})")
    if act and statistics.median(r[2] for r in act) >= statistics.median(r[1] for r in act):
        failures.append("exposure: the candidate is not less exposed where it activates")

    # 2. hunters
    print("\n2. three hunters, 90 s, our mech starts within 25 m of the centre "
          "(median first seen s; damage and deaths summed)")
    trace_case = None
    for search in ("patrol", "omniscient"):
        rng = random.Random(4242 if search == "patrol" else 5353)
        res = {"base": [], "cand": []}
        for n in range(max(8, runs // 2)):
            zone, probe = sample_zone(rng, want_spot=True)
            scenario = dict(seed=100 + n, start=start_near(rng, zone, 0, 25), zone=zone, seconds=90,
                            search=search, hunters=hunters_around(rng, zone))
            for key, where in (("base", folder), ("cand", ROOT)):
                r = simulate(where, scenario)
                res[key].append(r)
                if key == "cand":
                    times += r["times"]
            if trace_case is None and search == "patrol":
                trace_case = (scenario, res["base"][-1], res["cand"][-1])
        for key in ("base", "cand"):
            rs = res[key]
            first = [r["first_seen"] if r["first_seen"] is not None else 90.0 for r in rs]
            print(f"   {search:11} {'baseline' if key == 'base' else 'hide-spot':14} first seen "
                  f"{summary(first):>6}  never seen {sum(r['first_seen'] is None for r in rs):>2}/{len(rs)}"
                  f"  damage {sum(r['damage'] for r in rs):>7.0f} ({sum(r['rear'] for r in rs)} rear hits)"
                  f"  deaths {sum(r['died'] is not None for r in rs)}/{len(rs)}")
    scenario, base, cand = trace_case
    probe = HideSpot(HELLO, GRID)
    probe.search(scenario["zone"])
    c = scenario["zone"]["next_center"]
    print(f"\n   trace, patrol case 1: centre {[round(v) for v in c]} (exposure.u8 {probe.centre_exposure:.2f}),"
          f" spot {[round(v) for v in probe.spot]} ({probe.spot_exposure:.2f})")
    print(f"   {'t s':>5}  {'baseline: from centre, exposure, seen, hp lost':52}hide-spot: same")
    for t in (0, 2, 4, 6, 8, 10, 20, 40, 60, 89):
        def cell(r):
            k = min(int(t / DT), len(r["positions"]) - 1)
            p = r["positions"][k]
            state = "dead" if r["died"] is not None and t >= r["died"] else ("seen" if r["seen"][k] else "unseen")
            return f"{math.dist(p, c):5.1f} m  {measured_exposure(p):.2f}  {state:6}  {r['hurt'][k]:5.0f}"
        print(f"   {t:>5}  {cell(base):52}{cell(cand)}")
    print(f"          over 90 s: damage {base['damage']:.0f} vs {cand['damage']:.0f}; first seen at "
          f"{base['first_seen']} vs {cand['first_seen']} s; died at {base['died']} vs {cand['died']}")

    # 3. controls
    print("\n3. controls (must match the baseline on every decision)")
    rng = random.Random(7777)
    controls = []
    for n in range(4):
        zone, probe = sample_zone(rng, want_spot=True)
        c = zone["next_center"]
        far = start_near(rng, dict(zone, next_center=c), zone["next_radius"] + 60, zone["next_radius"] + 90)
        gap = math.dist(far, c) - zone["next_radius"]
        urgent = dict(zone, shrink_start=round(gap / MECH["walk_speed"] + 3, 1))
        urgent["shrink_end"] = urgent["shrink_start"] + 40
        urgent["radius"] = math.dist(far, c) + 40
        controls.append((f"urgent zone return #{n + 1}", dict(seed=n, start=far, zone=urgent, seconds=12,
                                                              search="none")))
        start = start_near(rng, zone, 20, 50)
        watcher = hunters_around(rng, zone, 1)[0]
        watcher.update(static=True, always_listed=True)
        controls.append((f"opponent listed from the start #{n + 1}",
                         dict(seed=n, start=start, zone=zone, seconds=20, search="none", hunters=[watcher])))
        drop_at = start_near(rng, zone, 5, 30)
        drop = dict(id=20000 + n, pos=[drop_at[0], drop_at[1], ground(*drop_at)], radius=8, lands_in=0,
                    capture_s=4, progress=0, holder=None)
        controls.append((f"supply drop at HP 60% #{n + 1}",
                         dict(seed=n, start=start, zone=zone, seconds=10, search="none", hp=840, regen=False,
                              drops=[drop])))
    for name, scenario in controls:
        base, cand = simulate(folder, scenario), simulate(ROOT, scenario)
        times += cand["times"]
        upto, note = len(base["actions"]), ""
        if name.startswith("urgent"):
            # The control covers the return itself: once 3 m inside the next circle the plain
            # zone objective is back, and the hide spot is meant to take over from there.
            c, r = scenario["zone"]["next_center"], scenario["zone"]["next_radius"]
            upto = next((k for k, p in enumerate(base["positions"]) if math.dist(p, c) - r <= -3), upto)
            after = sum(a != b for a, b in zip(base["actions"][upto:], cand["actions"][upto:]))
            note = f"; then inside the next circle, {after} of {len(base['actions']) - upto} differ (hide spot)"
        same = base["actions"][:upto] == cand["actions"][:upto]
        diff = sum(a != b for a, b in zip(base["actions"][:upto], cand["actions"][:upto]))
        print(f"   {name:40} {'identical' if same else f'DIFFERS on {diff}'} ({upto} decisions{note})")
        if not same or upto == 0:
            failures.append(name)

    # 4. timing and 5. the recording
    times.sort()
    print(f"\n4. candidate decision time over {len(times)} decisions: p99 {1000 * times[int(0.99 * len(times))]:.1f} ms,"
          f" max {1000 * times[-1]:.1f} ms (round trip through the pipe, this machine)")
    a, b = BotProcess(folder, HELLO), BotProcess(ROOT, HELLO)
    differ = keys = 0
    changed = {}
    for obs in STREAM:
        x, y = plain(a.act(copy.deepcopy(obs))), plain(b.act(copy.deepcopy(obs)))
        if x != y:
            differ += 1
            for k in set(x) | set(y):
                if x.get(k) != y.get(k):
                    changed[k] = changed.get(k, 0) + 1
    a.close()
    b.close()
    print(f"5. recording: {differ} of {len(STREAM)} decisions differ"
          + (f" ({', '.join(f'{k} {v}' for k, v in sorted(changed.items()))})" if changed else ""))
    if failures:
        print("\nFAIL:", "; ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
