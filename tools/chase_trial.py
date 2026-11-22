"""chase-wounded: baseline (4d8a32d, lead-shots, official 2.90) and candidate as real bot processes.

    py tools/chase_trial.py [--baseline <git revision>]

1. Scripted decisions: one observation each, for the rule's trigger and for each condition
   that must keep it off (the answer must then be identical to the baseline).
2. Closed-loop chases, 10 s each. Our mech starts at rest on an open lawn with its zone route
   leading away to the side; the opponent moves on a script (retreating straight away, or
   crossing) with the given HP and is listed while it is within vision range, inside the
   vision wedge (or proximity range) and not behind cover. Our movement follows the bot's
   commands (acceleration, walk and boost speed, boost energy, the walkable ground grid), the
   torso turns at the configured rates, and the world fires our gun when the bot holds the
   trigger: 252 m/s bullets from our moving muzzle along the actual torso aim, one per
   0.24 s, 12-round magazine, 2.4 s reload, 0.6 deg spread from one seeded generator per case
   (the same draws for both bots). Each body hit removes 45 HP (no rear bonus) and is reported
   to the bot as a `hit` event; at 0 HP the opponent is killed and leaves the list. Measured:
   time to kill, distance we walked, closest approach, decisions outside the zone. A copy of
   the candidate runs in process on the same observations to count its chase decisions and to
   check every one of them against the rule's conditions.
3. The standard recording: how often the rule activates and how many decisions differ.

The world model is simple (the opponent does not shoot back or react); it measures the
chase decision and its first-order effect on finishing a kill, not placement. Standard
library only.
"""
import copy
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
from harness import BotProcess, export, plain
from navigation import Navigator

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90
CONFIG = et.HELLO["config"]
MECH, GUN, VISION = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["vision"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
DT = 0.05
SECONDS = 10.0
HOME = list(et.HOME)
GRID = Navigator()
OPEN = 355           # bearing from HOME with clear lines along the retreat and crossing paths
SIDE = 35            # a second, healthy mech stands on this bearing, inside the vision wedge
ROUTE = 265          # our zone route leads this way, across the opponent's bearing
FULL = 1400.0


def import_candidate():
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    import chase
    from bot import Bot
    return Bot, chase.WoundedChase


Bot, Rule = import_candidate()
WOUNDED = 0.30 * FULL  # below the rule's HP fraction
assert WOUNDED < Rule.HP_FRAC * FULL


def pt(origin, bearing_deg, distance):
    a = math.radians(bearing_deg)
    return [origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)]


ROUTE_GOAL = pt(HOME, ROUTE, 150)


def walkable(point):
    i = round((point[0] - GRID.ox) / GRID.step)
    j = round((point[1] - GRID.oy) / GRID.step)
    return 0 <= i < GRID.width and 0 <= j < GRID.height and bool(GRID.free[j * GRID.width + i])


def clear(a, b):
    return et.COVER.clear([a[0], a[1], et.ground(*a[:2]) + MECH["eye_height"]],
                          [b[0], b[1], et.ground(*b[:2]) + MECH["height"] / 2])


# --- opponents -----------------------------------------------------------------------------

def retreat(distance, speed=11.7):
    start, b = pt(HOME, OPEN, distance), math.radians(OPEN)
    d = (math.cos(b), math.sin(b))
    return lambda t: ((start[0] + d[0] * speed * t, start[1] + d[1] * speed * t), (d[0] * speed, d[1] * speed))


def crossing(distance, side, speed=11.7):
    start, a = pt(HOME, OPEN, distance), math.radians(OPEN + side)
    d = (math.cos(a), math.sin(a))
    return lambda t: ((start[0] + d[0] * speed * t, start[1] + d[1] * speed * t), (d[0] * speed, d[1] * speed))


def still(distance, bearing=OPEN):
    spot = pt(HOME, bearing, distance)
    return lambda t: (tuple(spot), (0.0, 0.0))


def mech_entry(key, pos, vel, hp):
    """A passive game mech: its torso faces the way it walks (or away from HOME at rest)."""
    if math.hypot(*vel) > 0.1:
        facing = math.atan2(vel[1], vel[0])
    else:
        facing = math.atan2(pos[1] - HOME[1], pos[0] - HOME[0])
    return dict(id=key, kind="mech", pos=[pos[0], pos[1], et.ground(*pos)], vel=[vel[0], vel[1], 0.0],
                aim=[facing, 0.0], hp=hp, max_hp=FULL, cubes=0, weapons=["gun"], charging=False)


# --- scripted decisions --------------------------------------------------------------------

def scripted_obs(mechs, origin=HOME, hp=FULL, events=(), zone=None):
    obs = et.frame(0, mechs, events, origin=origin, hp=hp)
    if zone:
        obs["zone"].update(zone)
        obs["self"]["in_zone"] = math.dist(origin, obs["zone"]["center"]) <= obs["zone"]["radius"]
    return obs


def scripted():
    wounded = lambda d, bearing=OPEN, hp=WOUNDED, origin=HOME, key=5: mech_entry(key, pt(origin, bearing, d), (0, 0), hp)
    origin, bearing, distance, _ = et.COVER_SPOT
    drone = dict(id=8, kind="npc", pos=pt(HOME, OPEN, 60) + [et.ground(*pt(HOME, OPEN, 60))], vel=[0.0, 0.0, 0.0],
                 aim=[0.0, 0.0], hp=60, max_hp=350)
    return [
        ("wounded mech alone, 120 m, clear", True, scripted_obs([wounded(120)])),
        ("healthy mech alone, 120 m", False, scripted_obs([wounded(120, hp=FULL)])),
        ("wounded at 36% HP (just above)", False, scripted_obs([wounded(120, hp=0.36 * FULL)])),
        ("wounded, already close (30 m)", False, scripted_obs([wounded(30)])),
        (f"wounded, behind cover ({distance} m)", False,
         scripted_obs([mech_entry(5, et.at(bearing, distance, origin)[:2], (0, 0), WOUNDED)], origin=origin)),
        ("wounded drone that hit us", False,
         scripted_obs([drone], events=[et.damaged(8, OPEN, amount=25)])),
        ("wounded + healthy mech listed", False,
         scripted_obs([wounded(120), wounded(150, bearing=SIDE, hp=FULL, key=6)])),
        ("wounded, own HP 35%", False, scripted_obs([wounded(120)], hp=0.35 * FULL)),
        ("wounded, we are outside the zone", False,
         scripted_obs([wounded(120)], zone=dict(center=pt(HOME, ROUTE, 300), radius=50,
                                                 next_center=pt(HOME, ROUTE, 300), next_radius=40))),
        ("wounded, opponent outside the zone", False,
         scripted_obs([wounded(120)], zone=dict(center=list(HOME), radius=100))),
        ("wounded, zone shrinks in 12 s", False,
         scripted_obs([wounded(120)], zone=dict(next_center=list(HOME), next_radius=30, shrink_start=12))),
    ]


def run_scripted(folder):
    print(f"{'scripted decision':40}{'baseline move':>18}{'candidate move':>18}  check")
    failures = []
    for name, expect, obs in scripted():
        base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
        a, b = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        base_bot.close()
        cand_bot.close()
        if expect:
            target = obs["mechs"][0]["pos"]
            want = math.atan2(target[1] - HOME[1], target[0] - HOME[0])
            got = math.atan2(b["move"][1], b["move"][0])
            off = abs((got - want + math.pi) % math.tau - math.pi)
            rest = lambda act: {k: v for k, v in plain(act).items() if k not in ("move", "jump")}
            ok = off < math.radians(10) and rest(a) == rest(b)
            text = "moves toward the opponent; aim, fire and boost unchanged"
        else:
            ok = plain(a) == plain(b)
            text = "identical to baseline"
        fmt = lambda act: f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}]"
        print(f"{name:40}{fmt(a):>18}{fmt(b):>18}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    return failures


# --- closed-loop chases --------------------------------------------------------------------

def body_hit(origin, direction, length, target):
    tx, ty, tz = target["pos"]
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((tx - origin[0]) * dx + (ty - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return (math.hypot(px - tx, py - ty) <= MECH["radius"] + BULLET_R and tz <= pz <= tz + MECH["height"], s)


def visible(me, aim_yaw, other):
    distance = math.dist(me, other)
    if distance > VISION["range"]:
        return False
    bearing = math.atan2(other[1] - me[1], other[0] - me[0])
    in_wedge = abs((bearing - aim_yaw + math.pi) % math.tau - math.pi) <= math.radians(VISION["fov_deg"]) / 2
    return (in_wedge or distance <= VISION["near_range"]) and clear(me, other)


def fight(folder, case, mirror=False):
    bot = BotProcess(folder, et.HELLO)
    local = Bot(et.HELLO) if mirror else None
    rng = random.Random(case["seed"])
    x, y = HOME
    vx = vy = 0.0
    energy, spent_at = MECH["energy"], -10.0
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    foes = [dict(id=5 + k, motion=m, hp=hp, alive=True) for k, (m, hp) in enumerate(case["foes"])]
    first = foes[0]["motion"](0.0)[0]
    aim = [math.atan2(first[1] - y, first[0] - x), 0.0]  # facing the opponent, as when it was spotted
    commanded = list(aim)
    zone_centre, zone_radius = case.get("zone", (list(HOME), 400.0))
    next_centre, next_radius, shrink = case.get("next", (ROUTE_GOAL, 10.0, 1000.0))
    own_hp = case.get("own_hp", FULL)
    bullets, events = [], []
    move, boost, fire = [0.0, 0.0], False, [False, False]
    travelled, outside, closest, kill = 0.0, 0, math.inf, None
    decisions, chased, violations, mismatch = [], 0, [], 0
    per_target = {}
    for tick in range(int(SECONDS / DT)):
        now = tick * DT
        for foe in foes:
            if foe["alive"]:
                foe["pos"], foe["vel"] = foe["motion"](now)
        if foes[0]["alive"]:
            closest = min(closest, math.dist((x, y), foes[0]["pos"]))
        if tick % 2 == 0:
            listed = [mech_entry(f["id"], f["pos"], f["vel"], f["hp"]) for f in foes
                      if f["alive"] and visible((x, y), aim[0], f["pos"])]
            obs = et.frame(tick // 2, listed, events, origin=(x, y), hp=own_hp,
                           weapons=[copy.deepcopy(gun), None])
            obs["t"] = round(now, 2)
            obs["self"].update(vel=[vx, vy, 0.0], aim=list(aim), energy=energy)
            obs["zone"] = dict(center=list(zone_centre), radius=zone_radius, next_center=list(next_centre),
                               next_radius=next_radius, shrink_start=shrink, shrink_end=shrink + 50, dps=20)
            obs["self"]["in_zone"] = math.dist((x, y), zone_centre) <= zone_radius
            outside += not obs["self"]["in_zone"]
            action = bot.act(copy.deepcopy(obs))
            if local is not None:
                mirrored = json.loads(json.dumps(local.act(copy.deepcopy(obs))))
                mismatch += plain(mirrored) != plain(action)
                if local.chase.active:
                    chased += 1
                    violations += check_chase(obs, local, per_target)
            decisions.append((case["control"](obs) if "control" in case else False, plain(action)))
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
        # torso
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        # gun
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            z0 = et.ground(x, y) + MECH["muzzle_height"]
            bullets.append(dict(pos=[x + 3 * d[0], y + 3 * d[1], z0 + 3 * d[2]], dir=d, travelled=3.0))
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # our movement
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
        before = (x, y)
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * DT
            if walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
        travelled += math.dist(before, (x, y))
        # bullets fly after everyone has moved for this tick
        alive = []
        for b in bullets:
            step = GUN["speed"] * DT
            struck = None
            for foe in foes:
                if foe["alive"]:
                    hit, s = body_hit(b["pos"], b["dir"], step, dict(pos=[*foe["pos"], et.ground(*foe["pos"])]))
                    if hit and (struck is None or s < struck[1]):
                        struck = (foe, s)
            if struck:
                foe = struck[0]
                foe["hp"] -= GUN["damage"]
                events.append(dict(type="hit", target=foe["id"], amount=GUN["damage"], weapon="gun", rear=False))
                if foe["hp"] <= 0:
                    foe["alive"] = False
                    events.append(dict(type="kill", target=foe["id"], weapon="gun"))
                    if foe is foes[0]:
                        kill = round(now, 2)
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        bullets = alive
    bot.close()
    counts = dict(local.chase.counts) if local is not None else {}
    return dict(kill=kill, travelled=travelled, outside=outside, closest=closest, decisions=decisions,
                chased=chased, violations=violations, mismatch=mismatch, counts=counts, per_target=per_target)


def check_chase(obs, local, per_target):
    """Every chase decision must meet the rule's conditions, checked from the observation."""
    problems = []
    me, zone = obs["self"], obs["zone"]
    decision = local.engagement.decision
    mechs = [m for m in obs["mechs"] if m["kind"] == "mech"]
    chosen = next((m for m in mechs if m["id"] == decision.get("target")), None)
    if chosen is None or len(mechs) != 1:
        problems.append(f"t={obs['t']}: chased without exactly one selected game mech")
        return problems
    if chosen["hp"] >= Rule.HP_FRAC * chosen["max_hp"]:
        problems.append(f"t={obs['t']}: chased a mech at {chosen['hp']:.0f} HP")
    if math.dist(chosen["pos"][:2], me["pos"][:2]) <= Rule.CLOSE_M or not decision.get("clear"):
        problems.append(f"t={obs['t']}: chased while close or without a clear line")
    if not me["in_zone"] or me["hp"] < Rule.OWN_HP_FRAC * me["max_hp"]:
        problems.append(f"t={obs['t']}: chased outside the zone or with low HP")
    if math.dist(chosen["pos"][:2], zone["center"]) + 3 > zone["radius"]:
        problems.append(f"t={obs['t']}: chased an opponent outside the zone circle")
    per_target[chosen["id"]] = per_target.get(chosen["id"], 0) + 1
    if per_target[chosen["id"]] > round(Rule.MAX_S / 0.1) + 1:
        problems.append(f"t={obs['t']}: chased mech {chosen['id']} for more than {Rule.MAX_S} s")
    return problems


wounded_alone = lambda obs: True
TRACE = "wounded retreating, 180 m"
CASES = [
    # name, expectation, case
    ("wounded retreating, 120 m", "chase", dict(foes=[(retreat(120), WOUNDED)], seed=11)),
    ("wounded retreating, 180 m", "chase", dict(foes=[(retreat(180), WOUNDED)], seed=12)),
    ("wounded crossing toward route, 120 m", "chase", dict(foes=[(crossing(120, -90), WOUNDED)], seed=13)),
    ("wounded crossing away, 120 m", "chase", dict(foes=[(crossing(120, 90), WOUNDED)], seed=14)),
    ("wounded crossing, 80 m", "chase", dict(foes=[(crossing(80, 90), WOUNDED)], seed=15)),
    ("wounded retreating out of zone", "chase",
     dict(foes=[(retreat(120), WOUNDED)], zone=(list(HOME), 150.0), seed=16)),
    ("healthy retreating, 120 m", "same",
     dict(foes=[(retreat(120), FULL)], seed=21,
          control=lambda obs: all(m["hp"] >= Rule.HP_FRAC * m["max_hp"] for m in obs["mechs"]))),
    ("healthy crossing, 120 m", "same",
     dict(foes=[(crossing(120, 90), FULL)], seed=22,
          control=lambda obs: all(m["hp"] >= Rule.HP_FRAC * m["max_hp"] for m in obs["mechs"]))),
    ("wounded + second mech listed", "same",
     dict(foes=[(retreat(120), WOUNDED), (still(150, SIDE), FULL)], seed=23,
          control=lambda obs: sum(m["kind"] == "mech" for m in obs["mechs"]) >= 2)),
    ("wounded, urgent zone return", "same",
     dict(foes=[(retreat(120), WOUNDED)], zone=(pt(HOME, ROUTE, 320), 50.0),
          next=(pt(HOME, ROUTE, 320), 40.0, 1000.0), seed=24, control=lambda obs: not obs["self"]["in_zone"])),
    ("wounded, own HP 35%", "same",
     dict(foes=[(retreat(120), WOUNDED)], own_hp=0.35 * FULL, seed=25, control=wounded_alone)),
]


def run_closed_loop(folder):
    print(f"\n{'closed loop (10 s)':38}{'kill at s':>14}{'walked m':>14}{'closest m':>14}{'outside':>10}"
          f"{'chase':>7}  check")
    print(f"{'':38}{'base | cand':>14}{'base | cand':>14}{'base | cand':>14}{'b | c':>10}{'dec':>7}")
    failures, trace_case, kills, outcomes = [], None, {"base": 0, "cand": 0}, {}
    for name, expect, case in CASES:
        base, cand = fight(folder, case), fight(ROOT, case, mirror=True)
        kills["base"] += base["kill"] is not None
        kills["cand"] += cand["kill"] is not None
        for key, value in cand["counts"].items():
            outcomes[key] = outcomes.get(key, 0) + value
        problems = list(cand["violations"])
        if cand["mismatch"]:
            problems.append(f"in-process copy disagreed on {cand['mismatch']} decisions")
        if cand["outside"] > base["outside"]:
            problems.append("more decisions outside the zone")
        if expect == "chase":
            if not cand["chased"]:
                problems.append("never chased")
            text = "chases within the rule's conditions"
            if name == TRACE:
                trace_case = (name, case)
        else:
            prefix = 0
            for (control, a), (_, b) in zip(base["decisions"], cand["decisions"]):
                if not control:
                    break
                prefix += 1
                if a != b:
                    problems.append(f"decision {prefix} differs")
                    break
            if cand["chased"] and prefix == len(base["decisions"]):
                problems.append("chased")
            text = f"identical while the condition holds ({prefix} decisions)"
        ok = not problems
        fmt = lambda r: "-" if r["kill"] is None else f"{r['kill']:.1f}"
        print(f"{name:38}{fmt(base):>6} | {fmt(cand):<6}{base['travelled']:>6.0f} | {cand['travelled']:<6.0f}"
              f"{base['closest']:>6.0f} | {cand['closest']:<6.0f}{base['outside']:>4} | {cand['outside']:<4}"
              f"{cand['chased']:>6}  {'ok  ' if ok else 'FAIL'} {text}")
        for p in problems:
            print(f"      {p}")
        if not ok:
            failures.append(name)
    print(f"{'kills within 10 s':38}{kills['base']:>6} | {kills['cand']:<6}")
    print("candidate rule outcomes across the closed-loop cases:", dict(sorted(outcomes.items())))
    return failures, trace_case


def trace(folder, name, case):
    """Positions and commands every 0.5 s for one chase, baseline against candidate."""
    rows = {}
    for label, where in (("base", folder), ("cand", ROOT)):
        rows[label] = fight_trace(where, case)
    print(f"\ntrace, {name} (opponent at 30% HP; our zone route leads to bearing {ROUTE} deg):")
    print("    t   baseline: distance  move        fire     candidate: distance  move        fire   opp HP b|c"
          "  (distance nan = not listed: out of sight or killed)")
    for (t, d1, m1, f1, h1), (_, d2, m2, f2, h2) in zip(rows["base"], rows["cand"]):
        if t > 5.0:
            break
        hp = lambda h: "-" if h is None else f"{h:.0f}"
        print(f"  {t:4.1f}   {d1:>14.0f}  [{m1[0]:+.2f},{m1[1]:+.2f}]  {str(f1):5}   {d2:>18.0f}  [{m2[0]:+.2f},{m2[1]:+.2f}]"
              f"  {str(f2):5}  {hp(h1):>4}|{hp(h2):<4}")


def fight_trace(folder, case):
    """Re-run a case and sample the bot's decisions every 0.5 s (same world as fight())."""
    samples = []
    original = BotProcess.act

    def act(self, obs):
        action = original(self, obs)
        if round(obs["t"] * 10) % 5 == 0:
            me = obs["self"]["pos"]
            listed = [m for m in obs["mechs"] if m["id"] == 5]
            d = math.dist(me[:2], listed[0]["pos"][:2]) if listed else float("nan")  # nan: not listed
            hp = listed[0]["hp"] if listed else None
            samples.append((obs["t"], d, action["move"], bool(action["fire"][0]), hp))
        return action
    BotProcess.act = act
    try:
        fight(folder, case)
    finally:
        BotProcess.act = original
    return samples


def run_recording(folder):
    bot = Bot(et.HELLO)
    below = 0
    for obs in et.STREAM:
        below += any(m["kind"] == "mech" and m["hp"] < Rule.HP_FRAC * m["max_hp"] for m in obs["mechs"])
        bot.act(copy.deepcopy(obs))
    lowest = min((m["hp"] / m["max_hp"] for o in et.STREAM for m in o["mechs"] if m["kind"] == "mech"), default=None)
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(plain(base_bot.act(copy.deepcopy(o))) != plain(cand_bot.act(copy.deepcopy(o))) for o in et.STREAM)
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: lowest listed opponent HP {lowest:.0%} of max; decisions with a listed mech below"
          f" {Rule.HP_FRAC:.0%}: {below}; rule outcomes {dict(sorted(bot.chase.counts.items())) or 'none'};"
          f" {differ} of {len(et.STREAM)} decisions answered differently from the baseline;"
          f" round trip p99 {p99:.1f} ms")
    return differ


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`;"
          f" rule: HP below {Rule.HP_FRAC:.0%}, farther than {Rule.CLOSE_M:.0f} m, at most {Rule.MAX_S:.0f} s,"
          f" own HP at least {Rule.OWN_HP_FRAC:.0%}\n")
    failures = run_scripted(folder)
    more, trace_case = run_closed_loop(folder)
    failures += more
    if trace_case:
        trace(folder, *trace_case)
    if run_recording(folder):
        failures.append("recording: decisions differ although no listed opponent is wounded")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS (scripted and condition checks; kill times are measurements)")


if __name__ == "__main__":
    main()
