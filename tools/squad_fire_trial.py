"""squad-fire: practice-mode targeting, triggers, weapon wishes and upgrades, as real bot processes.

    py tools/squad_fire_trial.py [--baseline <git revision>] [--quick]

Practice mode starts after 20 s of match time while every death so far is one of our kills.
The scripted scenarios run at t = 30 s on the open lawn west of the Oval (engagement_trial's
HOME), with the parent (default farm-power 8064167, official 3.25) exported from git and this
working tree both run as `python -u bot.py`:

1. engagement: each rule that makes a mech engaged, just inside and just outside its limit;
   a passive mech at 120 m is ignored (no aim, no shot);
2. target choice: a weak far mech beats a healthy close one; the current target holds through
   a small change and gives way to a large one;
3. laser: the lethal early release, the full-charge release only when the torso is on the body;
4. loot: laser over lightning, lightning swapped for a laser, far lasers sought, never a mortar;
5. the upgrade order;
6. the mode switch: before 20 s, or after a death we did not cause, the parent's answers;
7. a closed-loop fight: a hunter walks in from 200 m aiming and shooting at us; gun only, and
   gun plus laser (--quick skips it);
8. timing (p99 of every candidate answer here, plus 15 engaged mechs) and an in-process fuzz pass.

The torso slews toward the commanded aim at the configured rates, a laser charges while held
and fires when let go (or after hold_s at full). Opponents follow scripts. Standard library only.
"""
import copy
import json
import math
import random
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from harness import BotProcess, export, plain

BASELINE = "8064167d11936561991186bf35261946ffbec33d"  # farm-power, official 3.25
CONFIG = et.HELLO["config"]
MECH, GUN, LASER = CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["weapons"]["laser"]
LIGHTNING, MORTAR = CONFIG["weapons"]["lightning"], CONFIG["weapons"]["mortar"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
HOME = et.HOME
T0 = 30.0
DT = 0.1
OPEN = 105      # clear lines from HOME out to 240 m, 10 degrees either side
SIDE = 40       # another clear bearing
GOAL_BEARING = OPEN + 180   # the zone goal, so "looking at the zone goal" is never at a test mech
CANDIDATES = []  # candidate processes, for the timing line
FAILURES = []


def launch(folder):
    bot = BotProcess(folder, et.HELLO)
    if folder == ROOT:
        CANDIDATES.append(bot)
    return bot


def check(ok, name):
    if not ok:
        FAILURES.append(name)
    return "ok  " if ok else "FAIL"


# --- scenario pieces ---------------------------------------------------------------------------

def laser(charge=0.0, cooldown=0.0):
    return dict(et.laser(charge), cooldown=cooldown)


def weapon(kind):
    if kind == "gun":
        return et.gun()
    if kind == "laser":
        return laser()
    stats = LIGHTNING if kind == "lightning" else MORTAR
    return dict(kind=kind, cooldown=0.0, stats=copy.deepcopy(stats))


def opponent(key, bearing, distance, hp=1400, aim_off=math.pi / 2, vel=(0.0, 0.0), weapons=("gun",), cubes=0):
    """A mech `distance` m out on `bearing` (degrees); aim_off is its torso's angle off us (rad)."""
    other = et.mech(key, bearing, distance, vel=vel, aim_off_deg=math.degrees(aim_off))
    other.update(hp=hp, weapons=list(weapons), cubes=cubes)
    return other


def frame(k, mechs=(), events=(), weapons=None, t0=T0, alive=16, late=False, pickups=(), offer=None,
          hp=1400, energy=100, cubes=0, origin=HOME):
    obs = et.frame(k, mechs, events, hp=hp, origin=origin, weapons=weapons, pickups=pickups)
    obs["t"] = round(t0 + k * DT, 2)
    obs["alive"] = alive
    obs["offer"] = offer
    obs["self"].update(energy=energy, cubes=cubes)
    goal = et.at(GOAL_BEARING, 100, origin)
    obs["zone"].update(center=list(origin), radius=400.0, next_center=goal[:2],
                       next_radius=60.0 if late else 250.0, shrink_start=1000.0, shrink_end=1050.0)
    return obs


def bearing_to(obs, other):
    me = obs["self"]["pos"]
    return math.atan2(other["pos"][1] - me[1], other["pos"][0] - me[0])


def aims_at(action, obs, other, tol_deg=3.0):
    yaw = (action.get("aim") or [None])[0]
    return yaw is not None and abs((yaw - bearing_to(obs, other) + math.pi) % math.tau - math.pi) <= math.radians(tol_deg)


def fires(action):
    return any(action.get("fire") or [])


def direct_pitch(other, origin=HOME):
    z0 = et.ground(*origin)
    flat = math.dist(other["pos"][:2], origin)
    return math.atan2(other["pos"][2] + MECH["height"] / 2 - (z0 + MECH["muzzle_height"]), flat)


def lands(aim, other, origin=HOME):
    """A beam from our muzzle along `aim` passes through the opponent's body."""
    z0 = et.ground(*origin) + MECH["muzzle_height"]
    yaw, pitch = aim
    dx, dy, dz = math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)
    tx, ty, tz = other["pos"]
    flat = math.hypot(dx, dy)
    along = ((tx - origin[0]) * dx + (ty - origin[1]) * dy) / (flat * flat)
    if along <= 0:
        return False
    miss = abs((tx - origin[0]) * dy - (ty - origin[1]) * dx) / flat
    z = z0 + along * dz
    return miss <= MECH["radius"] and tz <= z <= tz + MECH["height"]


class Rig:
    """Our side of a scripted scenario: torso slew and the laser's charge, release and cooldown."""

    def __init__(self, aim, weapons, slew=True):
        self.aim, self.commanded = list(aim), list(aim)
        self.weapons = copy.deepcopy(weapons)
        self.slew = slew
        self.held_full = 0.0
        self.beams = []   # (decision, charge, aim, how)

    def apply(self, k, action):
        fire = list(action.get("fire") or [False, False]) + [False, False]
        for slot, w in enumerate(self.weapons):
            if not w or w["kind"] != "laser":
                continue
            if w["cooldown"] > 0:
                w["cooldown"] = max(0.0, round(w["cooldown"] - DT, 6))
            elif fire[slot]:
                if w["charge"] >= LASER["charge"] - 1e-9:
                    self.held_full += DT
                w["charge"] = min(LASER["charge"], round(w["charge"] + DT, 6))
                if self.held_full >= LASER["hold_s"] - 1e-9:
                    self.beams.append((k, w["charge"], list(self.aim), "auto"))
                    w.update(charge=0.0, cooldown=LASER["cooldown"])
                    self.held_full = 0.0
            elif w["charge"] > 0:
                self.beams.append((k, w["charge"], list(self.aim), "release"))
                w.update(charge=0.0, cooldown=LASER["cooldown"])
                self.held_full = 0.0
        if "aim" in action:
            self.commanded = list(action["aim"])
        if self.slew:
            turn = (self.commanded[0] - self.aim[0] + math.pi) % math.tau - math.pi
            self.aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
            lift = self.commanded[1] - self.aim[1]
            self.aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, lift))


def play(folder, make, n, aim=(0.0, 0.0), weapons=None, slew=True):
    """Run frames make(k) for k < n; returns (rows, rig). Each row is (obs, action)."""
    bot = launch(folder)
    rig = Rig(aim, weapons or [et.gun(), None], slew)
    rows = []
    for k in range(n):
        obs = make(k)
        obs["self"]["aim"] = list(rig.aim)
        obs["self"]["weapons"] = copy.deepcopy(rig.weapons)
        action = bot.act(obs)
        rows.append((obs, action))
        rig.apply(k, action)
    bot.close()
    return rows, rig


# --- 1. engagement rules ----------------------------------------------------------------------

KILLED = [0, 1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14]   # ids other than ours (3) and the test mech (5)


def rule_cases():
    """(rule, label, expect engaged, make(k), decisions, window of decisions judged)."""
    toward = math.radians(OPEN + 180)
    closing = lambda speed: (speed * math.cos(toward), speed * math.sin(toward))
    plain_frame = lambda m, **kw: (lambda k: frame(k, [m], **kw))
    cases = [
        ("near", "55 m", True, plain_frame(opponent(5, OPEN, 55)), 15, range(10, 15)),
        ("near", "65 m", False, plain_frame(opponent(5, OPEN, 65)), 15, range(0, 15)),
        ("hit us in 6 s", "120 m, hit 5.5-6.0 s ago", True,
         lambda k: frame(k, [opponent(5, OPEN, 120)], [et.damaged(5, OPEN)] if k == 0 else []), 75, range(55, 61)),
        ("hit us in 6 s", "120 m, hit 6.1-7.4 s ago", False,
         lambda k: frame(k, [opponent(5, OPEN, 120)], [et.damaged(5, OPEN)] if k == 0 else []), 75, range(61, 75)),
        ("late", "120 m, next radius 70", True,
         lambda k: dict(frame(k, [opponent(5, OPEN, 120)]), zone=dict(frame(k)["zone"], next_radius=70.0)), 15, range(10, 15)),
        ("late", "120 m, next radius 71", False,
         lambda k: dict(frame(k, [opponent(5, OPEN, 120)]), zone=dict(frame(k)["zone"], next_radius=71.0)), 15, range(0, 15)),
        ("late", "120 m, 3 alive (13 our kills)", True,
         lambda k: frame(k, [opponent(5, OPEN, 120)], [dict(type="kill", target=i) for i in KILLED] if k == 1 else [],
                         alive=16 if k == 0 else 3), 15, range(10, 15)),
        ("late", "120 m, 4 alive (12 our kills)", False,
         lambda k: frame(k, [opponent(5, OPEN, 120)], [dict(type="kill", target=i) for i in KILLED[:12]] if k == 1 else [],
                         alive=16 if k == 0 else 4), 15, range(0, 15)),
        ("closing", "150 m at 3.5 m/s", True, plain_frame(opponent(5, OPEN, 150, vel=closing(3.5))), 15, range(10, 15)),
        ("closing", "150 m at 2.5 m/s", False, plain_frame(opponent(5, OPEN, 150, vel=closing(2.5))), 15, range(0, 15)),
        ("closing", "185 m at 3.5 m/s", False, plain_frame(opponent(5, OPEN, 185, vel=closing(3.5))), 15, range(0, 15)),
        ("weak", "150 m, 500 HP (36%)", True, plain_frame(opponent(5, OPEN, 150, hp=500)), 15, range(10, 15)),
        ("weak", "150 m, 600 HP (43%)", False, plain_frame(opponent(5, OPEN, 150, hp=600)), 15, range(0, 15)),
        ("weak", "165 m, 500 HP", False, plain_frame(opponent(5, OPEN, 165, hp=500)), 15, range(0, 15)),
        ("aimed", "150 m, torso 0.20 rad off us", True, plain_frame(opponent(5, OPEN, 150, aim_off=0.20)), 15, range(10, 15)),
        ("aimed", "150 m, torso 0.25 rad off us", False, plain_frame(opponent(5, OPEN, 150, aim_off=0.25)), 15, range(0, 15)),
        ("aimed", "195 m, torso 0.20 rad off us", False, plain_frame(opponent(5, OPEN, 195, aim_off=0.20)), 15, range(0, 15)),
        ("none (passive)", "120 m, passive", False, plain_frame(opponent(5, OPEN, 120)), 30, range(0, 30)),
    ]
    return cases


def judge(rows, window, engaged):
    """engaged: aims at it on every judged decision and the gun fires on one of them.
    ignored: never aims within 10 degrees of it and never presses a trigger."""
    picked = [rows[k] for k in window]
    if engaged:
        return all(aims_at(a, o, o["mechs"][0]) for o, a in picked) and any((a.get("fire") or [False])[0] for o, a in picked)
    return not any(aims_at(a, o, o["mechs"][0], 10.0) or fires(a) for o, a in picked)


def describe(rows, window):
    picked = [rows[k] for k in window]
    aimed = sum(aims_at(a, o, o["mechs"][0], 10.0) for o, a in picked)
    shot = sum(fires(a) for o, a in picked)
    return f"aim {aimed:>2}/{len(picked):<2} fire {shot:>2}/{len(picked):<2}"


def engagement(folder):
    print("1. engagement rules (one mech, open lawn, t = 30 s; torso starts 90 deg off it)")
    print(f"   {'rule':16}{'case':34}{'parent':>24}{'squad-fire':>24}  check")
    for rule, label, engaged, make, n, window in rule_cases():
        start = (math.radians(OPEN) + math.pi / 2, 0.0)
        base, _ = play(folder, make, n, aim=start)
        cand, _ = play(ROOT, make, n, aim=start)
        ok = judge(cand, window, engaged)
        print(f"   {rule:16}{label:34}{describe(base, window):>24}{describe(cand, window):>24}  "
              f"{check(ok, 'engagement: ' + rule + ', ' + label)} {'engaged' if engaged else 'ignored'}")


# --- 2. target choice --------------------------------------------------------------------------

def target_choice(folder):
    print("\n2. target choice (late zone, so both are engaged; scores = distance + 0.2 x HP, -100 at <= 30% HP,"
          " -120 for the target of the last 2 s)")
    far_hp = lambda k: 400 if k < 15 else 450
    near_hp = lambda k: 1400 if k < 15 else 1000 if k < 30 else 500

    def make(k):
        return frame(k, [opponent(5, OPEN, 200, hp=far_hp(k)), opponent(7, SIDE, 50, hp=near_hp(k))], late=True)
    start = (math.radians(SIDE), 0.0)
    base, _ = play(folder, make, 45, aim=start)
    cand, _ = play(ROOT, make, 45, aim=start)
    fresh, _ = play(ROOT, lambda k: make(k + 15), 15, aim=start)   # phase 2 with no history

    def on(rows, window, key):
        return all(aims_at(a, o, next(m for m in o["mechs"] if m["id"] == key)) for o, a in (rows[k] for k in window))
    phases = [
        ("far 400 HP (180) vs near 1400 HP (330)", range(5, 15), 5),
        ("far 450 HP (290-120) vs near 1000 HP (250)", range(15, 30), 5),
        ("far 450 HP (290-120) vs near 500 HP (150)", range(35, 45), 7),
    ]
    for text, window, key in phases:
        who = lambda rows: "far" if on(rows, window, 5) else "near" if on(rows, window, 7) else "mixed"
        print(f"   {text:46} parent faces {who(base):5}  squad-fire faces {who(cand):5}  "
              f"{check(on(cand, window, key), 'target choice: ' + text)} {'far' if key == 5 else 'near'}")
    ok = on(fresh, range(5, 15), 7)
    print(f"   {'same as phase 2 without the stickiness history':46} squad-fire faces {'near' if ok else 'far'}"
          f"{'':18}{check(ok, 'target choice: stickiness control')} near (so the hold above is stickiness)")
    gun_shots = sum((a.get("fire") or [False])[0] for o, a in cand[5:15])
    print(f"   gun fire at the far target on {gun_shots}/10 decisions of phase 1  {check(gun_shots >= 5, 'target choice: fire')}")


# --- 3. laser ----------------------------------------------------------------------------------

def laser_trials(folder):
    print("\n3. laser (one engaged mech 60 m out unless noted; charge builds 0.1 s per decision)")
    full = LASER["charge"]
    need = lambda hp, mult=1.0: full * ((hp / (0.8 * LASER["damage"] * mult)) - LASER["min_frac"]) / (1 - LASER["min_frac"])
    cases = [
        ("150 HP target", dict(hp=150), 0, (need(150), 0.4), "released early, at the first charge >= {:.3f} s"),
        ("1400 HP target aiming at us (control)", dict(hp=1400, aim_off=0.0), 0, (full - 0.051, full + 1e-9), "released only at full charge"),
        ("240 HP target holding a mortar (cook-off x1.6)", dict(hp=240, weapons=("gun", "mortar")), 0,
         (need(240, 1.6), 0.4), "released early, at the first charge >= {:.3f} s"),
        ("150 HP target, our 10 cubes (x1.4)", dict(hp=150), 10, (LASER["min_charge"], 0.28),
         "released early: min charge {:.2f} s, the first charge past it"),
    ]
    for text, spec, cubes, (low, high), expect in cases:
        target = opponent(5, OPEN, 60, **spec)
        make = lambda k, t=target, c=cubes: frame(k, [t], cubes=c)
        start = (math.radians(OPEN), 0.0)
        results = []
        for folder_ in (folder, ROOT):
            rows, rig = play(folder_, make, 25, aim=start, weapons=[et.gun(), laser()])
            first = rig.beams[0] if rig.beams else None
            results.append(first)
        b, c = results
        ok = c is not None and low - 1e-9 <= c[1] < high and lands(c[2], target)
        fmt = lambda r: "none" if r is None else f"{r[1]:.2f} s {r[3]}{' on body' if lands(r[2], target) else ' MISS'}"
        print(f"   {text:48} parent {fmt(b):24} squad-fire {fmt(c):24} "
              f"{check(ok, 'laser: ' + text)} {expect.format(low)}")

    print("   full charge, torso held still at an offset from a mech 100 m out aiming at us"
          f" (squad tolerance 0.9 x atan(0.75 x 2.5 / 100) = {0.9 * math.atan(1.875 / 100):.4f} rad;"
          f" parent {math.atan(2.5 / 100):.4f})")
    target = opponent(5, OPEN, 100, aim_off=0.0)
    pitch = direct_pitch(target)
    for offset in (0.0, 0.010, 0.016, 0.020, 0.040):
        expect_release = offset < 0.9 * math.atan(1.875 / 100)
        commands = []
        for folder_ in (folder, ROOT):
            rows, rig = play(folder_, lambda k: frame(k, [target]), 5, aim=(math.radians(OPEN) + offset, pitch),
                             weapons=[et.gun(), laser(full)], slew=False)
            commands.append(rows[0][1].get("fire"))
        released = commands[1][1] is False
        print(f"     offset {offset:.3f} rad: parent fire {str(commands[0]):14} squad-fire fire {str(commands[1]):14}"
              f" {check(released == expect_release, f'laser: full charge at offset {offset}')}"
              f" {'release' if expect_release else 'hold'}")
    rows, rig = play(ROOT, lambda k: frame(k, [target]), 40, aim=(math.radians(OPEN) + math.radians(40), 0.0),
                     weapons=[et.gun(), laser(full)])
    ok = bool(rig.beams) and all(lands(b[2], target) for b in rig.beams)
    first = rig.beams[0] if rig.beams else None
    print(f"   full charge, torso 40 deg off and turning: first release on decision {first[0] if first else '-'},"
          f" {sum(lands(b[2], target) for b in rig.beams)}/{len(rig.beams)} beams on the body"
          f"  {check(ok, 'laser: release only when aligned (turning)')}")
    rows, rig = play(ROOT, lambda k: frame(k, [opponent(5, OPEN, 60, aim_off=0.0)]), 30,
                     aim=(math.radians(OPEN), 0.0), weapons=[et.gun(), laser()])
    held = [a["fire"][1] for o, a in rows[:4]]
    print(f"   empty laser, aimed-at-us mech at 60 m: trigger held on decisions 0-3 {held}"
          f"  {check(all(held), 'laser: held while a target is in reach')}")
    drone_rows, _ = play(ROOT, lambda k: frame(k, [et.npc(104, OPEN, 60)], [et.damaged(104, OPEN, weapon="npc")] if k == 0 else []),
                         10, aim=(math.radians(OPEN), 0.0), weapons=[et.gun(), laser()])
    no_drone_charge = not any(a["fire"][1] for o, a in drone_rows)
    drone_gun = any(a["fire"][0] for o, a in drone_rows)
    print(f"   a drone that hit us, 60 m: laser never held {no_drone_charge}, gun fires {drone_gun}"
          f"  {check(no_drone_charge and drone_gun, 'laser: never charged at a drone')}")


# --- 4. loot -------------------------------------------------------------------------------------

def loot_walk(folder, weapons, pickups, seconds=30.0, t0=T0, origin=HOME):
    """Our mech walks where the bot steers it on the ground grid; every pickup is listed; a take
    within reach moves the pickup into the empty slot, or into the `drop` slot, leaving the old
    weapon at our feet."""
    bot = launch(folder)
    x, y = origin
    vx = vy = 0.0
    slots = copy.deepcopy(weapons)
    ground = {p["id"]: copy.deepcopy(p) for p in pickups}
    events, taken, move, next_id, yaw = [], [], [0.0, 0.0], 8100, 0.0
    for tick in range(int(seconds / 0.05)):
        t = tick * 0.05
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [], events, origin=(x, y), weapons=slots, pickups=list(ground.values()))
            obs["t"] = round(t0 + t, 2)
            obs["zone"].update(center=list(origin), radius=400.0, next_center=list(origin), next_radius=250.0,
                               shrink_start=1000.0, shrink_end=1050.0)
            obs["self"].update(vel=[vx, vy, 0.0], aim=[yaw, 0.0])
            action = bot.act(obs)
            events = []
            move = action.get("move", move)
            yaw = (action.get("aim") or [yaw])[0]
            key = action.get("take")
            if key is not None and key in ground:
                p = ground[key]
                z = et.ground(x, y)
                near = math.dist(p["pos"][:2], (x, y)) <= CONFIG["loot"]["pickup_radius"] and abs(p["pos"][2] - z) <= 4
                held = {w["kind"] for w in slots if w}
                drop = action.get("drop")
                slot = drop if drop in (0, 1) else next((i for i, w in enumerate(slots) if w is None), None)
                if not near:
                    events.append(dict(type="take_failed", id=key, reason="range"))
                elif p["kind"] in held:
                    events.append(dict(type="take_failed", id=key, reason="have"))
                elif slot is None:
                    events.append(dict(type="take_failed", id=key, reason="full"))
                else:
                    old = slots[slot]
                    slots[slot] = weapon(p["kind"])
                    del ground[key]
                    events.append(dict(type="took", id=key, kind=p["kind"], slot=slot))
                    taken.append((p["kind"], round(t, 1), drop))
                    if old is not None:
                        ground[next_id] = dict(id=next_id, kind=old["kind"], pos=[x, y, z])
                        events.append(dict(type="dropped", id=next_id, kind=old["kind"], slot=slot))
                        next_id += 1
        length = math.hypot(*move)
        mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        dvx, dvy = mx * MECH["walk_speed"] - vx, my * MECH["walk_speed"] - vy
        dv = math.hypot(dvx, dvy)
        limit = MECH["ground_accel"] * 0.05
        if dv > limit:
            dvx, dvy = dvx * limit / dv, dvy * limit / dv
        vx, vy = vx + dvx, vy + dvy
        for axis in (0, 1):
            candidate = [x, y]
            candidate[axis] += (vx, vy)[axis] * 0.05
            if dt.walkable(candidate):
                x, y = candidate
            elif axis == 0:
                vx = 0.0
            else:
                vy = 0.0
    bot.close()
    return dict(taken=taken, slots=[w["kind"] if w else None for w in slots])


def loot(folder):
    print("\n4. loot and swaps (closed loop: we walk where the bot steers; t = 30 s, no opponents)")
    pick = lambda key, kind, bearing, distance: dict(id=key, kind=kind, pos=et.at(bearing, distance))
    gun = et.gun()
    cases = [
        ("laser 2.5 m and lightning 1.5 m away, slot 1 empty", [gun, None],
         [pick(8001, "lightning", OPEN, 1.5), pick(8002, "laser", SIDE, 2.5)], 2.0, lambda r: r["slots"][1] == "laser"),
        ("laser and lightning both 60 m away, slot 1 empty", [gun, None],
         [pick(8001, "lightning", OPEN + 30, 60), pick(8002, "laser", OPEN - 30, 60)], 20.0,
         lambda r: r["taken"] and r["taken"][0][0] == "laser"),
        ("laser 200 m away, slot 1 empty", [gun, None], [pick(8002, "laser", OPEN, 200)], 30.0,
         lambda r: r["slots"][1] == "laser"),
        ("laser 100 m away, holding lightning", [gun, weapon("lightning")], [pick(8002, "laser", OPEN, 100)], 20.0,
         lambda r: r["slots"][1] == "laser" and r["taken"][0][2] == 1),
        ("lightning 2 m away, holding a laser", [gun, weapon("laser")], [pick(8001, "lightning", OPEN, 2)], 4.0,
         lambda r: r["slots"][1] == "laser" and not r["taken"]),
        ("mortar 20 m away, slot 1 empty", [gun, None], [pick(8003, "mortar", OPEN, 20)], 10.0,
         lambda r: r["slots"][1] is None and not r["taken"]),
        ("lightning 40 m away, holding a mortar", [gun, weapon("mortar")], [pick(8001, "lightning", OPEN, 40)], 15.0,
         lambda r: r["slots"][1] == "lightning" and r["taken"][0][2] == 1),
    ]
    print(f"   {'case':54}{'parent ends with':>22}{'squad-fire ends with':>26}  check")
    for text, weapons, pickups, seconds, ok_fn in cases:
        base = loot_walk(folder, weapons, pickups, seconds)
        cand = loot_walk(ROOT, weapons, pickups, seconds)
        show = lambda r: f"{r['slots'][1] or 'empty'}" + (f" ({r['taken'][-1][1]:.1f} s)" if r["taken"] else "")
        print(f"   {text:54}{show(base):>22}{show(cand):>26}  {check(bool(ok_fn(cand)), 'loot: ' + text)}")


# --- 5. upgrades ---------------------------------------------------------------------------------

def upgrades(folder):
    from squad import UPGRADES
    rng = random.Random(4242)
    known = [u["id"] for u in CONFIG["upgrades"]]
    offers = []
    for _ in range(60):
        ids = rng.sample(known + ["unknown_upgrade"], 3)
        offers.append(dict(id=len(offers) + 1, choices=[dict(id=i, name=i, desc="") for i in ids], expires=99))
    expected = [min(range(3), key=lambda i: (UPGRADES.index(o["choices"][i]["id"]) if o["choices"][i]["id"] in UPGRADES
                                                else len(UPGRADES), i)) for o in offers]
    picks = {}
    for folder_ in (folder, ROOT):
        rows, _ = play(folder_, lambda k: frame(k, offer=offers[k]), len(offers))
        picks[folder_] = [a.get("pick") for o, a in rows]
    matched = sum(p == e for p, e in zip(picks[ROOT], expected))
    differs = sum(p != q for p, q in zip(picks[folder], picks[ROOT]))
    print(f"\n5. upgrade order: 60 random offers (3 of the 22 ids plus an unknown one): squad-fire picks the earliest"
          f" in the practice list on {matched}/60; the parent's pick differs on {differs}"
          f"  {check(matched == 60, 'upgrades')}")
    sample = offers[0]
    print(f"   e.g. {[c['id'] for c in sample['choices']]}: parent {picks[folder][0]}, squad-fire {picks[ROOT][0]}")


# --- 6. mode switch ------------------------------------------------------------------------------

def rich(k, t0=0.0, alive_from=None, kill_from=None):
    """Three mechs (an attacker hitting us at 80 m, a passive one at 120 m, a weak one at 150 m),
    a drone, offers, a draining magazine; alive drops to 15 from decision alive_from, and our
    kill event for that death arrives from decision kill_from (None: never)."""
    mechs = [opponent(5, OPEN, 80, aim_off=0.0), opponent(7, OPEN + 60, 120), opponent(9, OPEN - 50, 150, hp=500),
             et.npc(104, OPEN + 120, 100)]
    events = [et.damaged(5, OPEN)] if k % 8 == 0 else []
    if kill_from is not None and k == kill_from:
        events.append(dict(type="kill", target=11))
    alive = 15 if alive_from is not None and k >= alive_from else 16
    gun = et.gun()
    gun["ammo"] = 12 - (k // 3) % 13
    gun["reload"] = 0.0
    offer = dict(id=k, choices=[dict(id=i, name=i, desc="") for i in ("servos", "laser_charge", "armor")],
                 expires=99) if k % 30 == 5 else None
    obs = frame(k, mechs, events, weapons=[gun, None], t0=t0, alive=alive, offer=offer)
    return obs


def compare(folder, make, n):
    bot_a, bot_b = launch(folder), launch(ROOT)
    differ = []
    for k in range(n):
        obs = make(k)
        a, b = bot_a.act(copy.deepcopy(obs)), bot_b.act(copy.deepcopy(obs))
        if plain(a) != plain(b):
            differ.append(k)
    bot_a.close()
    bot_b.close()
    return differ


def mode_switch(folder):
    print("\n6. mode switch: every command compared with the parent")
    total = same = 0
    for name, (builder, _, _) in et.SCENARIOS.items():
        frames = builder()
        if any(f["t"] > 20 for f in frames):
            continue   # the one engagement scenario set after 180 s is practice mode by design
        d = compare(folder, lambda k: frames[k], len(frames))
        total += len(frames)
        same += len(frames) - len(d)
    print(f"   engagement_trial scenarios (all before 20 s): identical on {same}/{total} decisions"
          f"  {check(same == total, 'mode switch: engagement scenarios before 20 s')}")
    d = compare(folder, lambda k: rich(k), 200)
    print(f"   three mechs, a drone, offers, 0-19.9 s: identical on {200 - len(d)}/200"
          f"  {check(not d, 'mode switch: before 20 s')}")
    d = compare(folder, lambda k: rich(k, alive_from=100), 450)
    print(f"   same, a death we did not cause at 10 s, run to 45 s: identical on {450 - len(d)}/450"
          f"  {check(not d, 'mode switch: outside death before 20 s')}")
    d = compare(folder, lambda k: rich(k, alive_from=350), 450)
    during = [k for k in d if 200 < k < 350]
    after = [k for k in d if k >= 355]
    print(f"   same, a death we did not cause at 35 s: differs on {len(during)}/149 decisions at 20.1-34.9 s,"
          f" identical from 35.5 s on ({100 - len(after)}/95 identical)"
          f"  {check(len(during) > 100 and not after, 'mode switch: outside death in practice')}")
    d = compare(folder, lambda k: rich(k, alive_from=300, kill_from=301), 450)
    late = [k for k in d if k >= 305]
    print(f"   same, a death at 30 s with our kill event one decision late: still practice mode"
          f" (differs on {len(late)}/145 decisions after 30.5 s)  {check(len(late) > 100, 'mode switch: kill-event lag')}")
    d_rec = compare(folder, lambda k: copy.deepcopy(et.STREAM[k]), len(et.STREAM))
    print(f"   standard recording (a mech dies to someone else at 18 s): identical on {len(et.STREAM) - len(d_rec)}"
          f"/{len(et.STREAM)}  {check(not d_rec, 'mode switch: recording')}")


# --- 7. closed-loop fight ------------------------------------------------------------------------

def body_hit(origin, direction, length, base, radius, height):
    cx, cy, cz = base
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((cx - origin[0]) * dx + (cy - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - cx, py - cy) <= radius + BULLET_R and cz <= pz <= cz + height


def hunter_path(bearing, stop, approach_deg=0.0, flip_s=1.5):
    """A hunter starts 200 m out on `bearing`, walks toward us (approach_deg off the straight
    line) at walk speed until `stop` m away, then strafes across, reversing every flip_s."""
    b = math.radians(bearing)
    start = (HOME[0] + 200 * math.cos(b), HOME[1] + 200 * math.sin(b))
    speed = MECH["walk_speed"]

    def at(t, state):
        x, y = state.get("pos", start)
        dx, dy = HOME[0] - x, HOME[1] - y
        dist = math.hypot(dx, dy)
        if state.get("strafe_from") is None and dist > stop:
            a = math.atan2(dy, dx) + math.radians(approach_deg)
            v = (speed * math.cos(a), speed * math.sin(a))
        else:
            if state.get("strafe_from") is None:
                state["strafe_from"] = t
            sign = 1 if int((t - state["strafe_from"]) / flip_s) % 2 == 0 else -1
            v = (-dy / dist * speed * sign, dx / dist * speed * sign)
        state["pos"] = (x + v[0] * 0.05, y + v[1] * 0.05)
        return state["pos"], v
    return at


def fight(folder, path, seed, with_laser, seconds=25.0):
    bot = launch(folder)
    rng = random.Random(seed)
    z0 = et.ground(*HOME)
    gun = et.gun()
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    beam = laser() if with_laser else None
    held_full = 0.0
    their = dict(cooldown=0.0, ammo=GUN["mag"], reload=0.0)
    state, hp_them, hp_us = {}, 1400.0, 1400.0
    ours, theirs, events = [], [], []
    shots = hits = beams = beam_hits = 0
    kill_at, aim, commanded, fire = None, [0.0, 0.0], [0.0, 0.0], [False, False]
    pos, vel = path(0.0, state)
    for tick in range(int(seconds / 0.05)):
        t = tick * 0.05
        if tick:
            pos, vel = path(t, state)
        hz = et.ground(*pos)
        target = dict(id=5, kind="mech", pos=[pos[0], pos[1], hz], vel=[vel[0], vel[1], 0.0],
                      aim=[math.atan2(HOME[1] - pos[1], HOME[0] - pos[0]), 0.0], hp=round(hp_them), max_hp=1400,
                      cubes=0, weapons=["gun"], charging=False)
        if tick == 0:
            aim = [math.atan2(pos[1] - HOME[1], pos[0] - HOME[0]), 0.0]
            commanded = list(aim)
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [target], events, origin=HOME, weapons=[copy.deepcopy(gun), copy.deepcopy(beam)],
                           hp=hp_us)
            obs["t"] = round(T0 + t, 2)
            obs["zone"].update(shrink_start=1000.0, shrink_end=1050.0)
            obs["self"]["aim"] = list(aim)
            action = bot.act(obs)
            events = []
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
            if beam is not None:
                released = None
                if beam["cooldown"] > 0:
                    beam["cooldown"] = max(0.0, round(beam["cooldown"] - 0.1, 6))
                elif fire[1]:
                    if beam["charge"] >= LASER["charge"] - 1e-9:
                        held_full += 0.1
                    beam["charge"] = min(LASER["charge"], round(beam["charge"] + 0.1, 6))
                    if held_full >= LASER["hold_s"] - 1e-9:
                        released = beam["charge"]
                elif beam["charge"] > 0:
                    released = beam["charge"]
                if released is not None:
                    beams += 1
                    d = (math.cos(aim[1]) * math.cos(aim[0]), math.cos(aim[1]) * math.sin(aim[0]), math.sin(aim[1]))
                    if body_hit([HOME[0], HOME[1], z0 + MECH["muzzle_height"]], d, LASER["range"], target["pos"],
                                MECH["radius"] - BULLET_R, MECH["height"]):
                        beam_hits += 1
                        amount = LASER["damage"] * (LASER["min_frac"] + (1 - LASER["min_frac"])
                                                    * max(released, LASER["min_charge"]) / LASER["charge"])
                        hp_them -= amount
                        events.append(dict(type="hit", target=5, amount=round(amount), weapon="laser"))
                    beam.update(charge=0.0, cooldown=LASER["cooldown"])
                    held_full = 0.0
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * 0.05, min(MECH["turn_rate"] * 0.05, turn))
        aim[1] += max(-MECH["pitch_rate"] * 0.05, min(MECH["pitch_rate"] * 0.05, commanded[1] - aim[1]))
        gun["cooldown"] = max(0.0, gun["cooldown"] - 0.05)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - 0.05)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            ours.append(dict(pos=[HOME[0] + 3 * d[0], HOME[1] + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]],
                             dir=d, travelled=3.0))
            shots += 1
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # the hunter's gun: aimed at our body centre, the same spread
        their["cooldown"] = max(0.0, their["cooldown"] - 0.05)
        if their["reload"] > 0:
            their["reload"] = max(0.0, their["reload"] - 0.05)
            if their["reload"] == 0:
                their["ammo"] = GUN["mag"]
        elif their["cooldown"] == 0 and math.dist(pos, HOME) <= GUN["range"]:
            yaw = math.atan2(HOME[1] - pos[1], HOME[0] - pos[0]) + math.radians(rng.gauss(0, GUN["spread_deg"]))
            flat = math.dist(pos, HOME)
            pitch = math.atan2(z0 + MECH["height"] / 2 - (hz + MECH["muzzle_height"]), flat) + math.radians(
                rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            theirs.append(dict(pos=[pos[0] + 3 * d[0], pos[1] + 3 * d[1], hz + MECH["muzzle_height"] + 3 * d[2]],
                               dir=d, travelled=3.0))
            their["ammo"] -= 1
            their["cooldown"] = GUN["cooldown"]
            if their["ammo"] == 0:
                their["reload"] = GUN["reload"]
        alive = []
        for b in ours:
            step = GUN["speed"] * 0.05
            if body_hit(b["pos"], b["dir"], step, target["pos"], MECH["radius"], MECH["height"]):
                hits += 1
                hp_them -= GUN["damage"]
                events.append(dict(type="hit", target=5, amount=GUN["damage"], weapon="gun"))
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        ours = alive
        alive = []
        for b in theirs:
            step = GUN["speed"] * 0.05
            if body_hit(b["pos"], b["dir"], step, [HOME[0], HOME[1], z0], MECH["radius"], MECH["height"]):
                hp_us -= GUN["damage"]
                events.append(dict(type="damaged", amount=GUN["damage"], weapon="gun", by=5,
                                   bearing=math.atan2(pos[1] - HOME[1], pos[0] - HOME[0])))
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        theirs = alive
        if hp_them <= 0:
            kill_at = round(t, 2)
            break
    bot.close()
    return dict(shots=shots, hits=hits, beams=beams, beam_hits=beam_hits, kill_at=kill_at,
                taken=round(1400 - hp_us), dealt=round(1400 - max(hp_them, 0)))


def fights(folder):
    print("\n7. closed-loop fight: one hunter (1400 HP, gun) walks in from 200 m aiming and shooting at us;"
          " we stand still; 25 s limit")
    paths = [
        ("straight in to 60 m, then strafing", lambda: hunter_path(OPEN, 60)),
        ("in at 30 deg to 100 m, then strafing", lambda: hunter_path(OPEN, 100, approach_deg=30)),
        ("in to 150 m, then strafing every 1 s", lambda: hunter_path(SIDE, 150, flip_s=1.0)),
    ]
    totals = {}
    print(f"   {'loadout / path / seed':52}{'gun hits':>12}{'beams on':>12}{'kill at s':>16}{'damage taken':>16}")
    print(f"   {'':52}{'base | squad':>12}{'base | squad':>12}{'base | squad':>16}{'base | squad':>16}")
    for with_laser in (False, True):
        loadout = "gun + laser" if with_laser else "gun only"
        agg = totals.setdefault(loadout, dict(base=[0, 0, 0, 0.0, 0], cand=[0, 0, 0, 0.0, 0]))
        for name, make in paths:
            for seed in (11, 12):
                b = fight(folder, make(), seed, with_laser)
                c = fight(ROOT, make(), seed, with_laser)
                for key, r in (("base", b), ("cand", c)):
                    agg[key][0] += r["hits"]
                    agg[key][1] += r["beam_hits"]
                    agg[key][2] += r["kill_at"] is not None
                    agg[key][3] += r["kill_at"] if r["kill_at"] is not None else 25.0
                    agg[key][4] += r["taken"]
                kill = lambda r: "-" if r["kill_at"] is None else f"{r['kill_at']:.1f}"
                print(f"   {loadout + ' / ' + name + ' / ' + str(seed):52}{b['hits']:>5} | {c['hits']:<5}"
                      f"{b['beam_hits']:>3}/{b['beams']:<2}| {c['beam_hits']}/{c['beams']:<3}"
                      f"{kill(b):>7} | {kill(c):<7}{b['taken']:>7} | {c['taken']:<7}")
                if c["shots"] == 0:
                    FAILURES.append(f"fight: candidate never fired ({loadout}, {name}, {seed})")
    for loadout, agg in totals.items():
        b, c = agg["base"], agg["cand"]
        print(f"   {loadout:12} totals over 6 fights: kills {b[2]} | {c[2]}, mean kill time (25 s if none)"
              f" {b[3] / 6:.1f} | {c[3] / 6:.1f} s, gun hits {b[0]} | {c[0]}, beams on target {b[1]} | {c[1]},"
              f" damage taken {b[4]} | {c[4]}")


# --- 8. timing and fuzz --------------------------------------------------------------------------

def timing():
    crowd = [opponent(20 + i, OPEN + (i - 7) * 9, 60 + 11 * i, hp=300 + 70 * i, aim_off=0.1 * (i % 3)) for i in range(15)]
    bot = launch(ROOT)
    for k in range(200):
        obs = frame(k, crowd, [et.damaged(20 + k % 15, OPEN)] if k % 5 == 0 else [], late=True,
                    weapons=[et.gun(), laser(min(LASER["charge"], 0.05 * (k % 20)))])
        bot.act(obs)
    crowd_p99 = sorted(bot.times)[int(0.99 * len(bot.times))] * 1e3
    bot.close()
    times = sorted(t for b in CANDIDATES for t in b.times)
    p99 = times[int(0.99 * len(times))] * 1e3
    worst = times[-1] * 1e3
    print(f"\n8. timing (round trip through stdin/stdout, this machine): all {len(times)} candidate answers in this"
          f" trial p99 {p99:.2f} ms, max {worst:.2f} ms; 15 engaged mechs with a charging laser p99 {crowd_p99:.2f} ms"
          f"  {check(p99 < 8 and crowd_p99 < 8, 'timing p99 under 8 ms')}")


def fuzz(seed=7, episodes=80, length=60):
    """In-process: random but well-formed observations, with practice mode active most of the time."""
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = mf.draw.text = lambda *args, **kw: None
    from bot import Bot
    rng = random.Random(seed)
    kinds = ["gun", "laser", "lightning", "mortar"]
    errors, decisions, squad_on, bad_actions = [], 0, 0, 0
    known = [u["id"] for u in CONFIG["upgrades"]] + ["mystery"]
    for episode in range(episodes):
        bot = Bot(et.HELLO)
        t0 = rng.choice([0.0, 15.0, 25.0, 60.0, 200.0, 300.0])
        alive, kills = 16, 0
        origin = (HOME[0] + rng.uniform(-30, 30), HOME[1] + rng.uniform(-30, 30))
        for k in range(length):
            mechs = []
            for i in range(rng.randint(0, 15)):
                m = opponent(20 + i, rng.uniform(0, 360), rng.uniform(5, 300), hp=rng.choice([None, 50, 400, 1400]),
                             aim_off=rng.uniform(0, math.pi), vel=(rng.uniform(-15, 15), rng.uniform(-15, 15)),
                             weapons=tuple(rng.sample(kinds, rng.randint(1, 2))), cubes=rng.randint(0, 12))
                if m["hp"] is None:
                    del m["hp"]
                if rng.random() < 0.1:
                    m.pop("aim")
                mechs.append(m)
            for i in range(rng.randint(0, 3)):
                mechs.append(et.npc(100 + i, rng.uniform(0, 360), rng.uniform(5, 200)))
            events = []
            for _ in range(rng.randint(0, 3)):
                kind = rng.choice(["damaged", "hit", "kill", "took", "take_failed"])
                if kind == "damaged":
                    events.append(dict(type="damaged", amount=45, weapon=rng.choice(["gun", "laser", "npc", "mortar", "zone", "lightning"]),
                                       by=rng.choice([None, 20, 21, 100, 5]), bearing=rng.choice([None, rng.uniform(-3, 3)])))
                elif kind == "kill" and alive > 2:
                    events.append(dict(type="kill", target=20 + kills))
                    kills += 1
                    alive -= 1
                elif kind == "hit":
                    events.append(dict(type="hit", target=rng.choice([20, 100, 1001]), amount=45, weapon="gun"))
            if rng.random() < 0.02:
                alive -= 1   # a death we did not cause
            slots = [et.gun(), None]
            slots[0].update(ammo=rng.randint(0, 12), reload=rng.choice([0.0, 0.0, 1.2]))
            second = rng.choice([None, "laser", "lightning", "mortar"])
            if second:
                slots[1] = weapon(second)
                if second == "laser":
                    slots[1].update(charge=rng.choice([0.0, 0.1, 0.3, 0.7, 0.75]), cooldown=rng.choice([0.0, 0.8]))
            pickups = [dict(id=8000 + i, kind=rng.choice(kinds), pos=et.at(rng.uniform(0, 360), rng.uniform(0, 250), origin))
                       for i in range(rng.randint(0, 4))]
            offer = (dict(id=k, choices=[dict(id=i, name=i, desc="") for i in rng.sample(known, 3)], expires=9)
                     if rng.random() < 0.1 else None)
            obs = frame(k, mechs, events, weapons=slots, t0=t0, alive=alive, pickups=pickups, offer=offer,
                        hp=rng.uniform(100, 1400), energy=rng.uniform(0, 100), cubes=rng.randint(0, 15), origin=origin)
            obs["self"]["aim"] = [rng.uniform(-math.pi, math.pi), rng.uniform(-0.5, 0.5)]
            obs["self"]["vel"] = [rng.uniform(-12, 12), rng.uniform(-12, 12), 0.0]
            if rng.random() < 0.1:
                obs["zone"]["next_radius"] = rng.choice([0.0, 25.0, 70.0])
            try:
                action = bot.act(copy.deepcopy(obs))
                json.dumps(action)
                fire = action.get("fire")
                if (not isinstance(fire, list) or len(fire) != 2 or not all(isinstance(f, bool) for f in fire)
                        or not all(math.isfinite(v) for v in action.get("aim", [0.0, 0.0]))):
                    bad_actions += 1
            except Exception:
                errors.append(traceback.format_exc(limit=3))
            decisions += 1
            squad_on += bot.practice.active
    print(f"   fuzz: {decisions} random decisions in-process ({squad_on} in practice mode):"
          f" {len(errors)} exceptions, {bad_actions} malformed actions"
          f"  {check(not errors and not bad_actions, 'fuzz')}")
    if errors:
        print("   first:", errors[0])


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; open bearing {OPEN} deg\n")
    engagement(folder)
    target_choice(folder)
    laser_trials(folder)
    loot(folder)
    upgrades(folder)
    mode_switch(folder)
    if "--quick" not in sys.argv:
        fights(folder)
    timing()
    fuzz()
    if FAILURES:
        print("\nFAIL:", "; ".join(FAILURES))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
