"""loot-power: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/loot_power_trial.py [--baseline <git revision>]

Closed-loop pickup scenarios from tools/pickup_trial.py (the mech goes where the bot steers it on
the navigation grid; a pickup leaves the world only after a valid take), run for both builds from
identical starts:
- choice: a lightning (or mortar) nearer the route and a laser (or lightning) a little farther;
  the candidate takes the better kind (laser, then lightning, then mortar), the baseline the nearer;
- before 180 s, a laser 165-200 m away (up to 240 m of route) or a lightning 120-150 m away, 85-110 m
  off the route: the candidate detours for it every time, the baseline (70 m limit) only when its own
  route happens to pass close enough;
- the far laser after 180 s: both leave it (identical);
- controls: a single laser near the route, and the far pickup with slot 1 already full (both
  identical).
Standard library only.
"""
import copy
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import pickup_trial as pt
from harness import BotProcess, export

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
INSTANCES = 8


def simulate(folder, scenario):
    """pickup_trial.simulate with a real bot process and a match-time offset `t0`."""
    bot = BotProcess(folder, pt.HELLO)
    stats = pt.CONFIG["mech"]
    t0 = scenario.get("t0", 0.0)
    x, y = scenario["start"]
    zone = scenario["zone"]
    pickups = {p["id"]: p for p in copy.deepcopy(scenario["pickups"])}
    weapons = copy.deepcopy(pt.TEMPLATE["self"]["weapons"])
    weapons[1] = copy.deepcopy(scenario.get("slot1"))
    yaw = math.atan2(zone["next_center"][1] - y, zone["next_center"][0] - x)
    events, result = [], dict(taken=None, taken_at=None, reached=None, outside=0)
    for tick in range(int(scenario["seconds"] / pt.DT)):
        now = t0 + tick * pt.DT
        f = min(1.0, max(0.0, (now - zone["shrink_start"]) / (zone["shrink_end"] - zone["shrink_start"])))
        centre = [zone["center"][k] + f * (zone["next_center"][k] - zone["center"][k]) for k in (0, 1)]
        radius = zone["radius"] + f * (zone["next_radius"] - zone["radius"])
        in_zone = math.dist((x, y), centre) <= radius
        result["outside"] += not in_zone
        z = pt.ground(x, y)
        visible = []
        for p in pickups.values():
            distance = math.dist((x, y), p["pos"][:2])
            bearing = math.atan2(p["pos"][1] - y, p["pos"][0] - x)
            off_axis = abs((bearing - yaw + math.pi) % math.tau - math.pi)
            if distance <= pt.CONFIG["vision"]["near_range"] or (
                    distance <= pt.CONFIG["vision"]["range"]
                    and off_axis <= math.radians(pt.CONFIG["vision"]["fov_deg"]) / 2):
                visible.append(copy.deepcopy(p))
        obs = copy.deepcopy(pt.TEMPLATE)
        obs.update(tick=2 * tick, t=round(now, 2), mechs=[], projectiles=[], crates=[], cubes=[],
                   pickups=visible, sounds=[], beams=[], events=events, drops=[], offer=None, alive=16)
        obs["zone"] = dict(center=centre, radius=radius, next_center=list(zone["next_center"]),
                           next_radius=zone["next_radius"], shrink_start=zone["shrink_start"],
                           shrink_end=zone["shrink_end"], dps=zone["dps"])
        obs["self"].update(pos=[x, y, z], vel=[0, 0, 0], aim=[yaw, 0.0], hp=stats["hp"], max_hp=stats["hp"],
                           energy=stats["energy"], grounded=True, in_zone=in_zone, cubes=0, upgrades=[],
                           weapons=copy.deepcopy(weapons))
        action = bot.act(obs)
        events = []
        wanted = pickups.get(action.get("take")) if action.get("take") is not None else None
        if wanted is not None and weapons[1] is None and math.dist((x, y), wanted["pos"][:2]) <= pt.CONFIG["loot"]["pickup_radius"] \
                and abs(wanted["pos"][2] - z) <= 4:
            del pickups[wanted["id"]]
            weapons[1] = dict(kind=wanted["kind"], cooldown=pt.CONFIG["loot"]["equip_s"], stats={})
            events.append(dict(type="took", id=wanted["id"], kind=wanted["kind"], slot=1))
            result["taken"], result["taken_at"] = wanted["kind"], round(now - t0, 1)
        if "aim" in action:
            turn = (action["aim"][0] - yaw + math.pi) % math.tau - math.pi
            yaw += max(-stats["turn_rate"] * pt.DT, min(stats["turn_rate"] * pt.DT, turn))
        mx, my = action.get("move", [0, 0])
        length = math.hypot(mx, my)
        if length > 1:
            mx, my = mx / length, my / length
        for axis, delta in enumerate((mx, my)):
            candidate = [x, y]
            candidate[axis] += delta * stats["walk_speed"] * pt.DT
            if pt.walkable(candidate):
                x, y = candidate
        if result["reached"] is None and math.dist((x, y), zone["next_center"]) <= 4:
            result["reached"] = round(now - t0 + pt.DT, 1)
            break
    bot.close()
    return result


def zone_at(goal, t0):
    zone = pt.roomy_zone(goal)
    zone["shrink_start"] += t0
    zone["shrink_end"] += t0
    return zone


def build(name, rng):
    for _ in range(200000):
        start, goal, along, across = pt.frame(rng, 150, 260)
        side = rng.choice((-1, 1))
        t0 = 200.0 if "after 180 s" in name else 0.0
        scenario = dict(name=name, start=start, zone=zone_at(goal, t0), seconds=60, t0=t0)
        if name.startswith("choice"):
            worse, better = ("lightning", "laser") if "lightning near" in name else ("mortar", "lightning")
            near = pt.offset(start, along, across, rng.uniform(15, 25), side * rng.uniform(8, 12))
            far = pt.offset(start, along, across, rng.uniform(35, 45), -side * rng.uniform(8, 12))
            if not all(pt.walkable(p) and pt.GRID.clear_segment(start, p) for p in (near, far)):
                continue
            scenario["pickups"] = [pt.pickup_at(near, key=8001, kind=worse), pt.pickup_at(far, key=8002, kind=better)]
        elif name.startswith("far") or name.startswith("control: far"):
            kind = "lightning" if "lightning" in name else "laser"
            if kind == "laser":
                spot = pt.offset(start, along, across, rng.uniform(140, 165), side * rng.uniform(85, 110))
                low, high = 150, 240
            else:
                spot = pt.offset(start, along, across, rng.uniform(85, 110), side * rng.uniform(85, 100))
                low, high = 0, 150
            if (not pt.walkable(spot) or math.dist(start, spot) > 199
                    or not low < pt.route_length(start, spot, limit=8000) <= high):
                continue
            scenario["pickups"] = [pt.pickup_at(spot, kind=kind)]
            scenario["seconds"] = 90
            if "slot 1 full" in name:
                scenario["slot1"] = dict(kind="mortar", cooldown=0, stats={})
        else:  # control: a single laser near the route
            spot = pt.offset(start, along, across, rng.uniform(20, 35), side * rng.uniform(8, 15))
            if not pt.walkable(spot) or not pt.GRID.clear_segment(start, spot):
                continue
            scenario["pickups"] = [pt.pickup_at(spot, kind="laser")]
        return scenario
    raise RuntimeError("no geometry for " + name)


# name -> what the candidate should do
SCENARIOS = {
    "choice: lightning near, laser farther": "laser",
    "choice: mortar near, lightning farther": "lightning",
    "far laser (150-240 m of route), before 180 s": "detour laser",
    "far lightning (up to 150 m of route), before 180 s": "detour lightning",
    "far laser, after 180 s": "identical",
    "control: single laser near the route": "identical",
    "control: far laser, slot 1 full": "identical",
}


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; {INSTANCES} instances each\n")
    print(f"{'scenario':58}{'taken (base | cand)':>34}{'median take s':>16}{'zone goal':>12}{'outside':>10}  check")
    failures = []
    for index, (name, expect) in enumerate(SCENARIOS.items()):
        rng = random.Random(9150 + index)
        instances = [build(name, rng) for _ in range(INSTANCES)]
        base = [simulate(folder, s) for s in instances]
        cand = [simulate(ROOT, s) for s in instances]
        kinds = lambda runs: ",".join(sorted({str(r["taken"]) for r in runs}))
        count = lambda runs, kind: sum(r["taken"] == kind for r in runs)
        took = lambda runs: [r["taken_at"] for r in runs if r["taken_at"] is not None]
        med = lambda runs: f"{statistics.median(took(runs)):.1f}" if took(runs) else "-"
        reached = lambda runs: sum(r["reached"] is not None for r in runs)
        outside = lambda runs: sum(r["outside"] for r in runs)
        if expect in ("lightning", "laser"):
            ok = count(cand, expect) == INSTANCES and outside(cand) <= outside(base)
            text = f"takes the {expect} in {count(cand, expect)}/{INSTANCES} (baseline {count(base, expect)})"
        elif expect.startswith("detour"):
            kind = expect.split()[1]
            # The baseline also takes it when its own route happens to pass within 70 m.
            ok = count(cand, kind) == INSTANCES and count(base, kind) < INSTANCES and outside(cand) == 0
            text = f"detours and takes it in {count(cand, kind)}/{INSTANCES} (baseline {count(base, kind)})"
        else:
            ok = base == cand
            text = "identical"
        taken = f"{kinds(base)} | {kinds(cand)}"
        print(f"{name:58}{taken:>34}{med(base) + ' | ' + med(cand):>16}{f'{reached(base)} | {reached(cand)}':>12}"
              f"{f'{outside(base)} | {outside(cand)}':>10}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
