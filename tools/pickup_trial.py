"""Closed-loop pickup trial: v4 and v5 from identical starting positions.

The simulated mech goes where the bot steers it, the zone shrinks on schedule, and a pickup
leaves the world only after a valid take (in reach, within 4 m of height, slot 1 empty).
Collision uses the bundled navigation grid and vision ignores buildings and trees, so this
measures the pickup decisions, not combat or the real match physics. Standard library only.
"""
import copy
import gzip
import json
import math
import random
import statistics
import sys
from array import array
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mechfight as mf
from bot import Bot as V5
from bot_v4 import Bot as V4
from loot import PickupDetour
from navigation import Navigator

# Debug drawing has no consumer in a direct controller call.
mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None

with gzip.open(ROOT / "check/stream.jsonl.gz", "rt") as f:
    HELLO, TEMPLATE = json.loads(next(f)), json.loads(next(f))
CONFIG = HELLO["config"]
GRID = Navigator()
WORLD = json.loads((ROOT / "arena/v2/world.json").read_text())["terrain"]
TERRAIN = array("h")
TERRAIN.frombytes((ROOT / "arena/v2" / WORLD["file"]).read_bytes())
if sys.byteorder == "big":
    TERRAIN.byteswap()
DT = 0.1
INSTANCES = 10


def ground(x, y):
    """Terrain height from the arena file itself, independent of the bot's own height grid."""
    u = min(WORLD["nx"] - 1.001, max(0.0, x - WORLD["minX"]))
    v = min(WORLD["ny"] - 1.001, max(0.0, y - WORLD["minY"]))
    i, j = int(u), int(v)
    fu, fv = u - i, v - j
    k = j * WORLD["nx"] + i
    low = TERRAIN[k] * (1 - fu) + TERRAIN[k + 1] * fu
    high = TERRAIN[k + WORLD["nx"]] * (1 - fu) + TERRAIN[k + WORLD["nx"] + 1] * fu
    return (low * (1 - fv) + high * fv) * WORLD["scale"]


def cell_of(point):
    return (round((point[0] - GRID.ox) / GRID.step), round((point[1] - GRID.oy) / GRID.step))


def walkable(point):
    i, j = cell_of(point)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


def route_length(a, b, limit=4000):
    """Shortest 4-connected walk between two points on the grid, in metres."""
    start, goal = GRID.snap(a), GRID.snap(b)
    seen, queue = {start: 0}, deque([start])
    while queue and len(seen) < limit:
        i = queue.popleft()
        if i == goal:
            return seen[i] * GRID.step
        for j in (i - 1, i + 1, i - GRID.width, i + GRID.width):
            if GRID.free[j] and j not in seen:
                seen[j] = seen[i] + 1
                queue.append(j)
    return math.inf


def simulate(controller, scenario):
    """Run one bot through one scenario and return what actually happened."""
    bot = controller(HELLO)
    stats = CONFIG["mech"]
    x, y = scenario["start"]
    zone = scenario["zone"]
    pickups = {p["id"]: p for p in copy.deepcopy(scenario["pickups"])}
    weapons = copy.deepcopy(TEMPLATE["self"]["weapons"])
    weapons[1] = None
    yaw = math.atan2(zone["next_center"][1] - y, zone["next_center"][0] - x)
    hp = max_hp = stats["hp"]
    energy, spent_at = stats["energy"], -10.0
    events = []
    result = dict(acquired=0, take_requests=0, reached=None, outside_ticks=0, zone_damage=0.0)
    for tick in range(int(scenario["seconds"] / DT)):
        now = tick * DT
        f = min(1.0, max(0.0, (now - zone["shrink_start"]) / (zone["shrink_end"] - zone["shrink_start"])))
        centre = [zone["center"][k] + f * (zone["next_center"][k] - zone["center"][k]) for k in (0, 1)]
        radius = zone["radius"] + f * (zone["next_radius"] - zone["radius"])
        in_zone = math.dist((x, y), centre) <= radius
        if not in_zone:
            result["outside_ticks"] += 1
            result["zone_damage"] += zone["dps"] * DT
            hp = max(1.0, hp - zone["dps"] * DT)
        z = ground(x, y)
        for key, limit in scenario.get("vanish", {}).items():
            if key in pickups and math.dist((x, y), pickups[key]["pos"][:2]) <= limit:
                del pickups[key]  # somebody else took it
        visible = []
        for p in pickups.values():
            distance = math.dist((x, y), p["pos"][:2])
            bearing = math.atan2(p["pos"][1] - y, p["pos"][0] - x)
            off_axis = abs((bearing - yaw + math.pi) % math.tau - math.pi)
            if distance <= CONFIG["vision"]["near_range"] or (
                    distance <= CONFIG["vision"]["range"]
                    and off_axis <= math.radians(CONFIG["vision"]["fov_deg"]) / 2):
                visible.append(copy.deepcopy(p))
        obs = copy.deepcopy(TEMPLATE)
        obs.update(tick=2 * tick, t=round(now, 2), mechs=copy.deepcopy(scenario.get("mechs", [])),
                   projectiles=[], crates=[], cubes=[], pickups=visible, sounds=[], beams=[],
                   events=events, drops=[], offer=None)
        obs["zone"] = dict(center=centre, radius=radius, next_center=list(zone["next_center"]),
                           next_radius=zone["next_radius"], shrink_start=zone["shrink_start"],
                           shrink_end=zone["shrink_end"], dps=zone["dps"])
        obs["self"].update(pos=[x, y, z], vel=[0, 0, 0], aim=[yaw, 0.0], hp=hp, max_hp=max_hp,
                           energy=energy, grounded=True, in_zone=in_zone, cubes=0, upgrades=[],
                           weapons=copy.deepcopy(weapons))
        action = bot.act(obs)
        events = []
        if action.get("take") is not None:
            result["take_requests"] += 1
            wanted = pickups.get(action["take"])
            if wanted is None:
                events.append(dict(type="take_failed", id=action["take"], reason="gone"))
            elif (math.dist((x, y), wanted["pos"][:2]) > CONFIG["loot"]["pickup_radius"]
                  or abs(wanted["pos"][2] - z) > 4):
                events.append(dict(type="take_failed", id=action["take"], reason="range"))
            elif weapons[1] is not None:
                events.append(dict(type="take_failed", id=action["take"], reason="full"))
            else:
                del pickups[wanted["id"]]
                weapons[1] = dict(kind=wanted["kind"], cooldown=CONFIG["loot"]["equip_s"], stats={})
                events.append(dict(type="took", id=wanted["id"], kind=wanted["kind"], slot=1))
                result["acquired"] += 1
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
            wall = scenario.get("wall")
            if walkable(candidate) and not (wall and math.dist(candidate, wall[0]) < wall[1]):
                x, y = candidate
        if result["reached"] is None and math.dist((x, y), zone["next_center"]) <= 4:
            result["reached"] = round(now + DT, 1)
            if not scenario.get("run_out"):
                break
    loot = getattr(bot, "loot", None)
    result["pursued"] = len(loot.pursued) if loot else 0
    result["abandoned"] = dict(loot.abandoned) if loot else {}
    return result


# --- scenarios ------------------------------------------------------------------------------

FREE = [i for i, free in enumerate(GRID.free) if free]


def pickup_at(point, key=8001, kind="laser", lift=0.1):
    return dict(id=key, kind=kind, pos=[point[0], point[1], round(ground(*point) + lift, 2)])


def frame(rng, low, high, direct=False):
    """A start, a zone goal and the unit vectors along and across the route between them."""
    while True:
        start, goal = (GRID.point(i) for i in rng.sample(FREE, 2))
        span = math.dist(start, goal)
        if low <= span <= high and (not direct or GRID.clear_segment(start, goal)):
            ux, uy = (goal[0] - start[0]) / span, (goal[1] - start[1]) / span
            return start, goal, (ux, uy), (-uy, ux)


def offset(start, along, across, a, b):
    return [start[0] + a * along[0] + b * across[0], start[1] + a * along[1] + b * across[1]]


def roomy_zone(goal):
    return dict(center=list(goal), radius=520, next_center=list(goal), next_radius=330,
                shrink_start=60, shrink_end=110, dps=20)


def build(name, rng):
    """One instance of a named scenario. Geometry is resampled until it fits the description."""
    speed = CONFIG["mech"]["walk_speed"]
    for _ in range(200000):
        timed = name in ("expiring zone", "roomy zone (control)", "deadline closes mid-route")
        start, goal, along, across = frame(rng, 150, 260, direct=timed)
        side = rng.choice((-1, 1))
        scenario = dict(name=name, start=start, zone=roomy_zone(goal), seconds=75, mechs=[])
        if name == "off-route pickup":
            spot = offset(start, along, across, rng.uniform(-10, 30), side * rng.uniform(30, 55))
            if not walkable(spot) or GRID.clear_segment(start, spot) or route_length(start, spot) > 60:
                continue
        elif name == "rooftop pickup":
            spot = offset(start, along, across, rng.uniform(15, 45), side * rng.uniform(5, 30))
            i, j = cell_of(spot)
            if not (3 <= i < GRID.width - 3 and 3 <= j < GRID.height - 3) or any(
                    GRID.free[(j + dj) * GRID.width + i + di] for di in (-2, -1, 0, 1, 2) for dj in (-2, -1, 0, 1, 2)):
                continue
        elif name == "pickup disappears mid-route":
            spot = offset(start, along, across, rng.uniform(45, 60), side * rng.uniform(8, 15))
            if not walkable(spot) or not GRID.clear_segment(start, spot):
                continue
            scenario["vanish"] = {8001: 15.0}
        else:
            spot = offset(start, along, across, rng.uniform(20, 35), side * rng.uniform(8, 15))
            if not walkable(spot) or not GRID.clear_segment(start, spot):
                continue
        if name == "blocked approach":
            # An obstacle the bot's map does not know about keeps the pickup out of reach.
            scenario["wall"] = (spot, CONFIG["loot"]["pickup_radius"] + 2.0)
        lift = 15.0 if name == "rooftop pickup"else 12.0 if name == "bridge-deck pickup" else 0.1
        scenario["pickups"] = [pickup_at(spot, lift=lift)]
        if timed:
            # The mech starts outside the next circle. The zone-return rule fires when
            # walk time + 5 s reaches shrink_start; "expiring" leaves 1.5 s before that.
            gap = math.dist(start, goal) - 80
            slack = 1.5 if name == "expiring zone" else 25.0
            begin = round(gap / speed + 5 + slack, 1)
            if name == "deadline closes mid-route":
                # Time for the detour with one second to spare, then an unmapped obstacle
                # slows the approach so the spare second runs out on the way.
                via = math.dist(start, spot) + math.dist(spot, goal) - 80
                begin = round(via / speed + 1 + 5 + PickupDetour.ZONE_MARGIN_S + 1, 1)
                scenario["wall"] = (spot, CONFIG["loot"]["pickup_radius"] + 2.0)
            scenario["zone"] = dict(center=list(goal), radius=math.dist(start, goal) + 60,
                                    next_center=list(goal), next_radius=80,
                                    shrink_start=begin, shrink_end=begin + 30, dps=20)
            scenario["run_out"] = True
            scenario["seconds"] = begin + 32
        if name == "distant NPC in view":
            away = offset(start, along, across, -150, 0)
            scenario["mechs"] = [dict(id=104, kind="npc", pos=[away[0], away[1], ground(*away)],
                                      vel=[1.1, 0, 0], aim=[0.1, 0], hp=350, max_hp=350)]
        if name == "opponent beside pickup":
            near = offset(spot, along, across, 0, side * 20)
            scenario["mechs"] = [dict(id=5, kind="mech", pos=[near[0], near[1], ground(*near)],
                                      vel=[0, 0, 0], aim=[0, 0], hp=1400, max_hp=1400, cubes=0,
                                      weapons=["gun"], charging=False)]
        return scenario
    raise RuntimeError("no geometry found for " + name)


# name -> should v5 detour for the weapon? Where it should not, a take can still happen
# exactly as in v4, when the zone route itself passes within reach of the pickup.
SCENARIOS = {
    "easy nearby pickup": True,
    "off-route pickup": True,
    "distant NPC in view": True,
    "roomy zone (control)": True,
    "expiring zone": False,
    "rooftop pickup": False,
    "bridge-deck pickup": False,
    "pickup disappears mid-route": False,
    "opponent beside pickup": False,
    "blocked approach": False,
    "deadline closes mid-route": False,
}


def main():
    failures = []
    print(f"{INSTANCES} seeded instances per scenario; both bots start from the same positions.\n")
    print(f"{'scenario':30}{'bot':16}{'acquired':>9}{'take req':>9}{'missed zone':>12}"
          f"{'reached':>8}{'median s':>9}{'detours':>8}  abandoned")
    for index, (name, should_acquire) in enumerate(SCENARIOS.items()):
        rng = random.Random(51739 + index)
        instances = [build(name, rng) for _ in range(INSTANCES)]
        rows = {}
        for controller in (V4, V5):
            runs = [simulate(controller, scenario) for scenario in instances]
            reasons = {}
            for run in runs:
                for reason, count in run["abandoned"].items():
                    reasons[reason] = reasons.get(reason, 0) + count
            reached = [run["reached"] for run in runs if run["reached"] is not None]
            rows[controller.name] = row = dict(
                acquired=sum(run["acquired"] for run in runs),
                requests=sum(run["take_requests"] for run in runs),
                missed=sum(run["outside_ticks"] > 0 for run in runs),
                reached=len(reached), median=statistics.median(reached) if reached else math.nan,
                detours=sum(run["pursued"] for run in runs))
            print(f"{name:30}{controller.name:16}{row['acquired']:>6}/{INSTANCES:<2}{row['requests']:>9}"
                  f"{row['missed']:>9}/{INSTANCES:<2}{row['reached']:>5}/{INSTANCES:<2}{row['median']:>9.1f}{row['detours']:>8}"
                  f"  {', '.join(f'{k} {v}' for k, v in sorted(reasons.items())) or '-'}")
        old, new = rows[V4.name], rows[V5.name]
        if should_acquire and new["acquired"] != INSTANCES:
            failures.append(f"{name}: v5 acquired {new['acquired']}/{INSTANCES}")
        if not should_acquire and new["acquired"] > old["acquired"]:
            failures.append(f"{name}: v5 acquired {new['acquired']}, v4 {old['acquired']}")
        if new["missed"] > old["missed"]:
            failures.append(f"{name}: v5 missed the zone in {new['missed']} runs, v4 in {old['missed']}")
        if new["reached"] < old["reached"]:
            failures.append(f"{name}: v5 reached the zone goal in {new['reached']} runs, v4 in {old['reached']}")
    print()
    print("acquired = valid takes in the simulation; take req = decisions that sent a take;")
    print("missed zone = runs with any decision spent outside the current circle;")
    print("detours = distinct pickups the bot left its zone route for.")
    if failures:
        print("\nFAIL")
        for line in failures:
            print(" ", line)
        sys.exit(1)
    print("\nPASS: v5 took every pickup it should detour for, no extra ones elsewhere, "
          "and missed no zone deadline v4 met.")


if __name__ == "__main__":
    main()
