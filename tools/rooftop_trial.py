"""rooftop: dodge-tuned (dd9b731, official 3.10) and the candidate as real bot processes.

    py tools/rooftop_trial.py [--baseline <git revision>] [--cases N]

A closed-loop physics model of the movement rules in protocol.md section 7, over the cover
raster (2 m cells of ground and solid tops): ground_accel / air_accel toward the commanded
velocity, gravity, jump_speed, jets (jet_accel, capped at max_rise_speed, jet_drain), boost
running (boost_drain), energy regeneration after energy_regen_delay, walls that stop the part
of a move going into them (sliding), ledges up to step_up, and landing on a roof edge the mech
still overlaps. Bridges, eaves, trees, cars and fences are not modelled (the climb points in
roofs.json avoid them). No opponents shoot; this measures whether the command sequence gets
the mech onto the roof and how exposed it is there, not what the house bots do about it.

Cases:
  climbs      spawns 25-75 m from a climb point of a roof inside the next circle
  zone moves  camping, then the next circle moves away from the roof
  energy      a spawn with 20 energy: the bot waits at the wall until the climb is affordable
  controls    urgent zone return, an opponent listed, no roof within range: identical answers
  recording   the standard recording: decisions that differ
Exposure: ground observers at 20, 45 and 100 m in 16 directions (open ground, eye 8 m up)
with a line of sight to the mech's centre or top, both bots at the same moment. Standard library.
"""
import copy
import gzip
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from cover import NONE, Cover
from harness import BotProcess, export, plain
from navigation import Navigator

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10

with gzip.open(ROOT / "check/stream.jsonl.gz", "rt") as f:
    HELLO = json.loads(next(f))
    STREAM = [json.loads(line) for line in f if '"obs"' in line]
TEMPLATE = STREAM[0]
MECH = HELLO["config"]["mech"]
COVER = Cover()
GRID = Navigator()
ROOFS = json.loads((ROOT / "roofs.json").read_text())
DT, SUB = 0.1, 2
OUTER = [(2.4 * math.cos(a * math.pi / 4), 2.4 * math.sin(a * math.pi / 4)) for a in range(8)]
INNER = [(0.0, 0.0)] + [(1.2 * math.cos(a * math.pi / 4), 1.2 * math.sin(a * math.pi / 4)) for a in range(8)]


def surface(x, y):
    i, j = int((x - COVER.ox) / COVER.cell), int((y - COVER.oy) / COVER.cell)
    if not (0 <= i < COVER.nx and 0 <= j < COVER.ny):
        return 1e9
    k = j * COVER.nx + i
    top = COVER.top[k]
    return max(COVER.ground[k], top) / 100 if top != NONE else COVER.ground[k] / 100


def roof_id(x, y):
    i, j = int((x - COVER.ox) / COVER.cell), int((y - COVER.oy) / COVER.cell)
    k = j * COVER.nx + i
    for roof in ROOFS["roofs"]:
        for jj, i0, i1 in roof["runs"]:
            if jj == j and i0 <= i <= i1:
                return roof["id"]
    return None


class Body:
    """One mech under the movement rules (a vertical cylinder of radius 2.5 m)."""

    def __init__(self, x, y, energy=None, jets=True):
        self.jets = jets
        self.x, self.y = x, y
        self.z = surface(x, y)
        self.vx = self.vy = self.vz = 0.0
        self.grounded = True
        self.energy = MECH["energy"] if energy is None else energy
        self.spent_at = -10.0
        self.jet_s = 0.0

    def blocked(self, x, y, z, grounded):
        allowance = MECH["step_up"] if grounded else 0.02
        return any(surface(x + dx, y + dy) > z + allowance for dx, dy in OUTER + INNER)

    def support(self, x, y, below):
        """Highest surface under the inner footprint at or below `below` (a roof edge holds
        a mech that still overlaps it)."""
        return max((s for s in (surface(x + dx, y + dy) for dx, dy in INNER) if s <= below), default=-1e9)

    def step(self, action, now):
        mx, my = action.get("move", [0, 0])
        length = math.hypot(mx, my)
        if length > 1:
            mx, my = mx / length, my / length
        boost = bool(action.get("boost"))
        if action.get("jump") and self.grounded:
            self.vz = MECH["jump_speed"]
            self.grounded = False
        dt = DT / SUB
        for _ in range(SUB):
            spent = False
            running = boost and self.grounded and length > 0 and self.energy > 0
            speed = MECH["boost_speed"] if running else MECH["walk_speed"]
            if running:
                self.energy = max(0.0, self.energy - MECH["boost_drain"] * dt)
                spent = True
            accel = (MECH["ground_accel"] if self.grounded else MECH["air_accel"]) * dt
            dvx, dvy = mx * speed - self.vx, my * speed - self.vy
            dv = math.hypot(dvx, dvy)
            if dv > accel:
                dvx, dvy = dvx * accel / dv, dvy * accel / dv
            self.vx += dvx
            self.vy += dvy
            if not self.grounded:
                jet = boost and self.energy > 0 and self.jets
                if jet:
                    self.vz = min(self.vz + (MECH["jet_accel"] - MECH["gravity"]) * dt,
                                  max(MECH["max_rise_speed"], self.vz - MECH["gravity"] * dt))
                    self.energy = max(0.0, self.energy - MECH["jet_drain"] * dt)
                    self.jet_s += dt
                    spent = True
                else:
                    self.vz -= MECH["gravity"] * dt
            if spent:
                self.spent_at = now
            elif now - self.spent_at >= MECH["energy_regen_delay"]:
                self.energy = min(MECH["energy"], self.energy + MECH["energy_regen"] * dt)
            # Horizontal move with sliding along walls.
            nx, ny = self.x + self.vx * dt, self.y + self.vy * dt
            if not self.blocked(nx, ny, self.z, self.grounded):
                self.x, self.y = nx, ny
            elif not self.blocked(nx, self.y, self.z, self.grounded):
                self.x, self.vy = nx, 0.0
            elif not self.blocked(self.x, ny, self.z, self.grounded):
                self.y, self.vx = ny, 0.0
            else:
                self.vx = self.vy = 0.0
            if self.grounded:
                below = self.support(self.x, self.y, self.z + MECH["step_up"])
                if below < self.z - 0.3:
                    self.grounded, self.vz = False, 0.0
                else:
                    self.z = below
            else:
                nz = self.z + self.vz * dt
                if self.vz <= 0:
                    land = self.support(self.x, self.y, self.z + 0.01)
                    if nz <= land:
                        self.z, self.vz, self.grounded = land, 0.0, True
                        continue
                self.z = nz


def sees(observer, target_xy, z):
    """Vision as in protocol.md section 8, buildings only: line of sight to centre or top."""
    ex, ey = observer
    ez = surface(ex, ey) + 8
    for tz in (z + 4.5, z + 9.0):
        length = math.dist((ex, ey, ez), (target_xy[0], target_xy[1], tz))
        steps = max(1, int(length / 0.5))
        solid = 0.0
        for n in range(steps + 1):
            f = n / steps
            if f * length < 0.5 or (1 - f) * length < 2.5:
                continue
            if COVER.solid(ex + f * (target_xy[0] - ex), ey + f * (target_xy[1] - ey), ez + f * (tz - ez)):
                solid += length / steps
        if solid < 2.0:
            return True
    return False


def exposure(x, y, z):
    out = {}
    for ring in (20, 45, 100):
        seen = total = 0
        for b in range(16):
            ox, oy = x + ring * math.cos(b * math.pi / 8), y + ring * math.sin(b * math.pi / 8)
            i, j = int((ox - COVER.ox) / COVER.cell), int((oy - COVER.oy) / COVER.cell)
            if not (0 <= i < COVER.nx and 0 <= j < COVER.ny):
                continue
            k = j * COVER.nx + i
            if COVER.top[k] != NONE and COVER.top[k] - COVER.ground[k] > 50:
                continue  # inside a building: no observer there
            total += 1
            seen += sees((ox, oy), (x, y), z)
        out[ring] = (seen, total)
    return out


def observation(tick, body, zone, mechs, yaw, in_zone):
    obs = copy.deepcopy(TEMPLATE)
    obs.update(tick=2 * tick, t=round(tick * DT, 2), mechs=copy.deepcopy(mechs), projectiles=[], crates=[],
               cubes=[], pickups=[], sounds=[], beams=[], events=[], drops=[], offer=None, alive=16)
    obs["zone"] = dict(zone)
    obs["self"].update(pos=[round(body.x, 3), round(body.y, 3), round(body.z, 3)],
                       vel=[round(body.vx, 3), round(body.vy, 3), round(body.vz, 3)], aim=[yaw, 0.0],
                       hp=MECH["hp"], max_hp=MECH["hp"], energy=round(body.energy, 2), max_energy=MECH["energy"],
                       grounded=body.grounded, in_zone=in_zone, cubes=0, upgrades=[])
    return obs


def run(folder, case):
    """Drive one bot through one case. Returns the per-decision actions and a summary."""
    bot = BotProcess(folder, HELLO)
    body = Body(*case["start"], energy=case.get("energy"), jets=case.get("jets", True))
    yaw = 0.0
    actions, track = [], []
    zones = case["zones"]
    for tick in range(int(case["seconds"] / DT)):
        now = tick * DT
        zone = [z for at, z in zones if now >= at][-1]
        in_zone = math.dist((body.x, body.y), zone["center"]) <= zone["radius"]
        obs = observation(tick, body, zone, case.get("mechs", []), yaw, in_zone)
        action = bot.act(obs)
        actions.append(plain(action))
        if "aim" in action:
            turn = (action["aim"][0] - yaw + math.pi) % math.tau - math.pi
            yaw += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        track.append(dict(t=round(now, 1), x=body.x, y=body.y, z=body.z, grounded=body.grounded,
                          energy=body.energy, in_zone=in_zone, move=action.get("move"),
                          jump=action.get("jump"), boost=action.get("boost")))
        body.step(action, now)
    times = bot.times
    bot.close()
    return actions, track, times


ROOF_BY_ID = {roof["id"]: roof for roof in ROOFS["roofs"]}


def summary(track, case):
    """Where the mech stood: on any listed roof (grounded within 1 m of its top), and at that
    roof's camp spot."""
    on, camp = [], []
    for p in track:
        rid = roof_id(p["x"], p["y"]) if p["grounded"] else None
        roof = ROOF_BY_ID.get(rid)
        if roof and abs(p["z"] - roof["top"]) < 1.0:
            on.append(p)
            if math.dist((p["x"], p["y"]), roof["camp"]) <= 2.0:
                camp.append(p)
    first = on[0]["t"] if on else None
    jumps = sum(1 for p in track if p["jump"])
    lowest = min(p["energy"] for p in track)
    outside = sum(1 for p in track if not p["in_zone"])
    return dict(on_roof_at=first, on_roof_s=round(len(on) * DT, 1), camp_s=round(len(camp) * DT, 1),
                jumps=jumps, lowest_energy=round(lowest), outside=outside)


def zone_around(camp, rng, radius=380.0, next_radius=240.0, shift=90.0):
    a = rng.uniform(0, math.tau)
    centre = [camp[0] + shift * math.cos(a), camp[1] + shift * math.sin(a)]
    return dict(center=centre, radius=radius, next_center=centre, next_radius=next_radius,
                shrink_start=400.0, shrink_end=450.0, dps=20)


def free_nodes():
    return [GRID.point(i) for i, f in enumerate(GRID.free) if f]


def start_for(roof, foot, rng, low=25, high=75):
    """A navigation node low-high m from the climb point whose nearest climb point is this roof's."""
    options = [p for p in free_nodes() if low <= math.dist(p, foot["stage"]) <= high]
    rng.shuffle(options)
    for p in options:
        nearest = min((math.dist(p, f["stage"]), r["id"]) for r in ROOFS["roofs"] for f in r["feet"])
        if nearest[1] == roof["id"]:
            return p
    return None


def climb_cases(rng, count):
    roofs = list(ROOFS["roofs"])
    rng.shuffle(roofs)
    roofs.sort(key=lambda r: min(f["h"] for f in r["feet"]))
    picks = [roofs[int(n * (len(roofs) - 1) / max(1, count - 1))] for n in range(count)]
    cases = []
    for roof in dict((r["id"], r) for r in picks).values():
        foot = rng.choice(roof["feet"])
        start = start_for(roof, foot, rng)
        if start is None:
            continue
        cases.append(dict(name=f"roof {roof['id']:>2} ({foot['h']:.0f} m wall, start {math.dist(start, foot['stage']):.0f} m)",
                          start=start, roof=roof, seconds=30.0, zones=[(0.0, zone_around(roof["camp"], rng))]))
    return cases


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    count = int(sys.argv[sys.argv.index("--cases") + 1]) if "--cases" in sys.argv else 16
    folder = export(revision)
    rng = random.Random(2026)
    failures = []
    times = []
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`")
    print(f"roofs.json: {len(ROOFS['roofs'])} roofs, {sum(len(r['feet']) for r in ROOFS['roofs'])} climb points\n")

    # --- climbs ----------------------------------------------------------------------------
    print(f"{'climbs (30 s, no opponents)':44}{'on roof at':>11}{'camping':>9}{'jumps':>7}{'min energy':>11}"
          f"{'  seen at 20/45/100 m (t=25 s): base | rooftop':>48}")
    totals = dict(cases=0, completed=0, camped=0, base_seen=[0, 0, 0], cand_seen=[0, 0, 0],
                  base_obs=[0, 0, 0], cand_obs=[0, 0, 0])
    roof_times, heights = [], []
    for case in climb_cases(rng, count):
        base_actions, base_track, _ = run(folder, case)
        cand_actions, cand_track, t = run(ROOT, case)
        times += t
        s = summary(cand_track, case)
        sb = summary(base_track, case)
        at = int(25 / DT)
        eb = exposure(base_track[at]["x"], base_track[at]["y"], base_track[at]["z"])
        ec = exposure(cand_track[at]["x"], cand_track[at]["y"], cand_track[at]["z"])
        totals["cases"] += 1
        totals["completed"] += s["on_roof_at"] is not None
        totals["camped"] += s["camp_s"] > 0
        if s["on_roof_at"] is not None:
            roof_times.append(s["on_roof_at"])
            heights.append(case["roof"]["top"])
        for n, ring in enumerate((20, 45, 100)):
            totals["base_seen"][n] += eb[ring][0]
            totals["cand_seen"][n] += ec[ring][0]
            totals["base_obs"][n] += eb[ring][1]
            totals["cand_obs"][n] += ec[ring][1]
        seen = " ".join(f"{eb[r][0]:>2}/{eb[r][1]:<2}" for r in (20, 45, 100)) + " | " + \
               " ".join(f"{ec[r][0]:>2}/{ec[r][1]:<2}" for r in (20, 45, 100))
        print(f"{case['name']:44}{str(s['on_roof_at']) + ' s' if s['on_roof_at'] is not None else 'never':>11}"
              f"{s['camp_s']:>8.1f}s{s['jumps']:>7}{s['lowest_energy']:>11}   {seen}")
        if sb["on_roof_s"]:
            print(f"    note: the baseline stood on a listed roof for {sb['on_roof_s']} s")
        if s["outside"]:
            failures.append(f"{case['name']}: left the zone")
    print(f"\n{totals['completed']} of {totals['cases']} reached the roof, {totals['camped']} camped at the camp spot;"
          f" time to the roof {min(roof_times, default=0)}-{max(roof_times, default=0)} s"
          f" (median {statistics.median(roof_times) if roof_times else '-'})")
    for n, ring in enumerate((20, 45, 100)):
        b, c = totals["base_obs"][n], totals["cand_obs"][n]
        print(f"  observers at {ring:>3} m with a line of sight: base {totals['base_seen'][n]}/{b}"
              f" ({100 * totals['base_seen'][n] / max(1, b):.0f}%), rooftop {totals['cand_seen'][n]}/{c}"
              f" ({100 * totals['cand_seen'][n] / max(1, c):.0f}%)")
    if totals["completed"] < 0.75 * totals["cases"]:
        failures.append(f"climbs: only {totals['completed']} of {totals['cases']} reached the roof")

    # --- the zone moves on ------------------------------------------------------------------
    zrng = random.Random(7)
    roof = sorted(ROOFS["roofs"], key=lambda r: -r["depth"])[3]
    foot = roof["feet"][0]
    start = start_for(roof, foot, zrng, 30, 50)
    first = zone_around(roof["camp"], zrng)
    away = [roof["camp"][0] + 200, roof["camp"][1]]
    second = dict(center=list(first["center"]), radius=first["radius"], next_center=away, next_radius=120.0,
                  shrink_start=90.0, shrink_end=120.0, dps=20)
    case = dict(name="zone moves on at 35 s", start=start, roof=roof, seconds=60.0,
                zones=[(0.0, first), (35.0, second)])
    _, track, t = run(ROOT, case)
    times += t
    s = summary(track, case)
    left = next((p["t"] for p in track if p["t"] > 35 and p["grounded"] and p["z"] < roof["top"] - 3), None)
    toward = math.dist((track[-1]["x"], track[-1]["y"]), away) < math.dist((track[int(35 / DT)]["x"], track[int(35 / DT)]["y"]), away)
    ok = s["on_roof_at"] is not None and left is not None and toward and not s["outside"]
    print(f"\n{case['name']:44}on roof at {s['on_roof_at']} s, back on the ground at {left} s, "
          f"heading for the new circle: {toward}  {'ok' if ok else 'FAIL'}")
    if not ok:
        failures.append(case["name"])

    # --- low energy ----------------------------------------------------------------------
    # Spawned next to the wall with an empty tank: it must wait at the stage point until the
    # climb's energy (1.5 per metre plus the reserve) has regenerated, and never run dry mid-air.
    near_start = start_for(roof, foot, random.Random(11), 3, 15)
    case = dict(name="spawn by the wall with 0 energy", start=near_start, roof=roof, seconds=30.0, energy=0.0,
                zones=[(0.0, first)])
    _, track, t = run(ROOT, case)
    times += t
    s = summary(track, case)
    jump = next((p for p in track if p["jump"]), None)
    need = 1.5 * (foot["h"] + 0.8 + 1.5) + 15
    air = [p for p in track if not p["grounded"]]
    ok = (s["on_roof_at"] is not None and jump is not None and jump["energy"] >= need - 1
          and min((p["energy"] for p in air), default=1) > 0)
    print(f"{case['name']:44}jumped at {jump and jump['t']} s with {jump and round(jump['energy'])} energy "
          f"(needs {need:.0f}), on roof at {s['on_roof_at']} s, lowest energy in the air "
          f"{round(min((p['energy'] for p in air), default=0))}  {'ok' if ok else 'FAIL'}")
    if not ok:
        failures.append(case["name"])

    # --- safeguards: a climb that cannot succeed ------------------------------------------
    # The same spawn, but jets do nothing (as if the real wall or physics differed from the
    # model): the climb must time out or fall back, ban the roof and hand movement back.
    case = dict(name="jets disabled (climb cannot succeed)", start=start, roof=roof, seconds=60.0,
                jets=False, zones=[(0.0, first)])
    base_actions, base_track, _ = run(folder, case)
    _, track, t = run(ROOT, case)
    times += t
    s = summary(track, case)
    jumps = [p["t"] for p in track if p["jump"]]
    gap = lambda tr, k: math.dist((tr[k]["x"], tr[k]["y"]), first["next_center"])
    ok = s["on_roof_at"] is None and len(jumps) <= 8 and not s["outside"] and gap(track, -1) < gap(track, 0) - 50
    print(f"{case['name']:44}jumps at {jumps[:8]} s; distance to the zone centre {gap(track, 0):.0f} -> "
          f"{gap(track, -1):.0f} m (baseline -> {gap(base_track, -1):.0f} m)  {'ok' if ok else 'FAIL'}")
    if not ok:
        failures.append(case["name"])

    # --- controls ------------------------------------------------------------------------
    near = start
    far_zone = dict(center=[near[0] + 600, near[1]], radius=300.0, next_center=[near[0] + 600, near[1]],
                    next_radius=200.0, shrink_start=400.0, shrink_end=450.0, dps=20)
    passive = dict(id=7, kind="mech", pos=[near[0] + 100, near[1] + 60, surface(near[0] + 100, near[1] + 60)],
                   vel=[0, 0, 0], aim=[0.0, 0.0], hp=1400, max_hp=1400, cubes=0, weapons=["gun"], charging=False)
    nodes = free_nodes()
    lonely = max(nodes, key=lambda p: min(math.dist(p, f["stage"]) for r in ROOFS["roofs"] for f in r["feet"]))
    lonely_gap = min(math.dist(lonely, f["stage"]) for r in ROOFS["roofs"] for f in r["feet"])
    controls = [
        ("urgent zone return (outside the circle)", dict(start=near, seconds=15.0, zones=[(0.0, far_zone)])),
        ("an opponent listed throughout", dict(start=near, seconds=20.0, mechs=[passive], zones=[(0.0, first)])),
        (f"no roof within range ({lonely_gap:.0f} m)", dict(start=lonely, seconds=20.0,
                                                           zones=[(0.0, zone_around(lonely, random.Random(3)))])),
    ]
    print()
    for name, case in controls:
        a, _, _ = run(folder, case)
        b, _, t = run(ROOT, case)
        times += t
        differ = sum(x != y for x, y in zip(a, b))
        ok = differ == 0
        print(f"{name:44}answers differ on {differ} of {len(a)}  {'ok  identical' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    # --- the standard recording ----------------------------------------------------------
    base_bot, cand_bot = BotProcess(folder, HELLO), BotProcess(ROOT, HELLO)
    differ = 0
    for obs in STREAM:
        differ += plain(base_bot.act(copy.deepcopy(obs))) != plain(cand_bot.act(copy.deepcopy(obs)))
    base_bot.close()
    cand_bot.close()
    listed = sum(1 for obs in STREAM if any(m.get("kind") == "mech" for m in obs["mechs"]))
    me = STREAM[0]["self"]["pos"]
    gap = min(math.dist(me[:2], f["stage"]) for r in ROOFS["roofs"] for f in r["feet"])
    print(f"\nrecording: answers differ on {differ} of {len(STREAM)} (a mech listed on {listed}; "
          f"nearest climb point {gap:.0f} m from the first position)")

    times.sort()
    print(f"candidate answer time: p50 {1000 * times[len(times) // 2]:.1f} ms, p99 {1000 * times[int(len(times) * 0.99)]:.1f} ms, "
          f"max {1000 * times[-1]:.1f} ms")
    if failures:
        print("\nFAIL:", "; ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
