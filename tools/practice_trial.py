"""The practice-mode design as one bot: mode switch, decision time with every part busy, fuzz.

    py tools/practice_trial.py [--baseline <git revision>]

1. Mode switch: farm-power (default 8064167, official 3.25) and this tree as real bot processes
   (`python -u bot.py`) on the same observations. Before 20 s, after a death we did not cause and
   on the standard recording every answer must match; the same rich scenario after 20 s is the
   control that shows practice mode acting.
2. Decision time with the practice parts busy: a closed loop near buildings (our mech walks
   where the bot steers it) with hunters listed and aiming at us, our HP low enough for the
   LoseRule retreat (so the cover search runs), crates, cubes, drones and weapon pickups in view,
   bullets in the air, a charging laser, then 15 engaged mechs. Timed in process (act()) and
   through stdin/stdout; p99 must stay under 8 ms on this machine.
3. Fuzz: thousands of random, well-formed observations in process, before and after 20 s, with
   deaths with and without our kill events: no exception, a JSON action, finite move and aim,
   two boolean triggers, and nothing swallowed by squad_move.py's guard.
4. With squad_econ.py: the movement priority in practice mode, read from the debug label in
   scripted decisions (stuck > zone must > retreat > fight > the laser detour > zone should >
   loot > camp), the loot shot only without a mech target, no fight or stare at an unengaged
   mech, and the bullet dodge still having the last word. Then the fixes: no fight move
   toward an engaged mech without a line of fire or beyond 240 m (it is only faced); the
   laser detour held through a drone hit and while the laser is out of view; no supply-drop
   or relocate move; cubes (never crates) collected under threat.
Standard library only.
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
import mechfight as mf
from harness import BotProcess, export, plain

BASELINE = "8064167d11936561991186bf35261946ffbec33d"  # farm-power, official 3.25
CONFIG = et.HELLO["config"]
MECH, GUN, LASER, LIGHTNING = (CONFIG["mech"], CONFIG["weapons"]["gun"], CONFIG["weapons"]["laser"],
                               CONFIG["weapons"]["lightning"])
HOME = et.HOME
OPEN = 105      # clear lines from HOME out to 240 m
FAILURES = []


def check(ok, name):
    if not ok:
        FAILURES.append(name)
    return "ok  " if ok else "FAIL"


def ground(x, y):
    """Terrain height, clamped to the map so points beyond its edge get the edge's height."""
    c = et.COVER
    i = min(c.nx - 1, max(0, int((x - c.ox) / c.cell)))
    j = min(c.ny - 1, max(0, int((y - c.oy) / c.cell)))
    return c.ground[j * c.nx + i] / 100


def at(origin, bearing, distance):
    a = math.radians(bearing)
    x, y = origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)
    return [round(x, 2), round(y, 2), round(ground(x, y), 2)]


def mech(key, origin, bearing, distance, hp=1400, aim_at_us=False, vel=(0.0, 0.0), weapons=("gun",),
         charging=False, us=None):
    """A mech `distance` m from `origin` on `bearing`; its torso points at `us` (default: origin)
    when aim_at_us, else 90 degrees off."""
    pos = at(origin, bearing, distance)
    us = us or origin
    toward = math.atan2(us[1] - pos[1], us[0] - pos[0])
    aim = toward if aim_at_us else toward + math.pi / 2
    return dict(id=key, kind="mech", pos=pos, vel=[vel[0], vel[1], 0.0], aim=[aim, 0.0], hp=hp, max_hp=1400,
                cubes=0, weapons=list(weapons), charging=charging)


def drone(key, origin, bearing, distance):
    return dict(id=key, kind="npc", pos=at(origin, bearing, distance), vel=[0.0, 0.0, 0.0],
                aim=[0.0, 0.0], hp=350, max_hp=350)


def bullet(key, origin, bearing, distance, toward=True):
    """A gun bullet `distance` m out on `bearing`, flying at us (or across)."""
    start = at(origin, bearing, distance)
    start[2] += 5.0
    yaw = math.radians(bearing + 180) if toward else math.radians(bearing + 90)
    return dict(id=key, kind="gun", pos=start, vel=[GUN["speed"] * math.cos(yaw), GUN["speed"] * math.sin(yaw), 0.0])


# --- 1. mode switch ------------------------------------------------------------------------------

def rich(k, t0=0.0, alive_from=None, deaths=1):
    """Every kind of thing a decision can see: an attacker hitting us, a passive and a weak mech,
    a drone, a crate, cubes, weapon pickups, a bullet now and then, offers and a draining
    magazine. alive drops to 15 from decision alive_from (a death we did not cause)."""
    mechs = [mech(5, HOME, OPEN, 80, aim_at_us=True), mech(7, HOME, OPEN + 60, 120),
             mech(9, HOME, OPEN - 50, 150, hp=500), drone(104, HOME, OPEN + 120, 100)]
    events = [et.damaged(5, OPEN)] if k % 8 == 0 else []
    gun = et.gun()
    gun["ammo"] = 12 - (k // 3) % 13
    gun["reload"] = 0.0
    pickups = [dict(id=8001, kind="laser", pos=at(HOME, OPEN + 150, 50)),
               dict(id=8002, kind="lightning", pos=at(HOME, OPEN - 120, 20))]
    obs = et.frame(k, mechs, events, weapons=[gun, None], pickups=pickups)
    obs["t"] = round(t0 + 0.1 * k, 2)
    obs["alive"] = 16 - deaths if alive_from is not None and k >= alive_from else 16
    obs["crates"] = [dict(id=1001, pos=at(HOME, OPEN + 200, 60), hp=300)]
    obs["cubes"] = [dict(id=5001, pos=at(HOME, OPEN - 160, 30)), dict(id=5002, pos=at(HOME, OPEN + 100, 90))]
    obs["projectiles"] = [bullet(9000 + k, HOME, OPEN, 40)] if k % 25 == 3 else []
    obs["offer"] = (dict(id=k, choices=[dict(id=i, name=i, desc="") for i in ("servos", "laser_charge", "armor")],
                         expires=99) if k % 30 == 5 else None)
    obs["zone"].update(shrink_start=1000.0, shrink_end=1050.0)
    return obs


def compare(folder, make, n):
    a_bot, b_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = []
    for k in range(n):
        obs = make(k)
        if plain(a_bot.act(copy.deepcopy(obs))) != plain(b_bot.act(copy.deepcopy(obs))):
            differ.append(k)
    a_bot.close()
    b_bot.close()
    return differ


def mode_switch(folder):
    print("1. mode switch: every answer compared with farm-power")
    total = same = 0
    for name, (builder, _, _) in et.SCENARIOS.items():
        frames = builder()
        if any(f["t"] > 20 for f in frames):
            continue   # the scenario set after 180 s is practice mode by design
        d = compare(folder, lambda k: frames[k], len(frames))
        total += len(frames)
        same += len(frames) - len(d)
    print(f"   engagement_trial scenarios (all before 20 s): identical on {same}/{total}"
          f"  {check(same == total, 'mode switch: engagement scenarios')}")
    d = compare(folder, lambda k: rich(k), 200)
    print(f"   rich scenario, 0-19.9 s: identical on {200 - len(d)}/200  {check(not d, 'mode switch: before 20 s')}")
    d = compare(folder, lambda k: rich(k, alive_from=100, deaths=3), 600)
    print(f"   rich scenario, three deaths we did not cause at 10 s, run to 60 s: identical on {600 - len(d)}/600"
          f"  {check(not d, 'mode switch: three outside deaths')}")
    d = compare(folder, lambda k: rich(k, alive_from=100, deaths=2), 600)
    early = [k for k in d if k < 200]
    print(f"   squad-sticky: two outside deaths at 10 s: identical before 20 s ({200 - len(early)}/200), practice"
          f" mode after it ({len(d) - len(early)}/400 differ)  {check(not early and len(d) - len(early) > 200, 'mode switch: two outside deaths keep practice mode')}")
    d = compare(folder, lambda k: copy.deepcopy(et.STREAM[k]), len(et.STREAM))
    early = [k for k in d if et.STREAM[k]["t"] <= 20]
    print(f"   standard recording (one mech dies to someone else at 18 s): identical up to 20 s"
          f" ({len(early)} differ there); {len(d) - len(early)} later answers differ (practice mode)"
          f"  {check(not early, 'mode switch: recording before 20 s')}")
    d = compare(folder, lambda k: rich(k, t0=20.05), 200)
    print(f"   control, the rich scenario at 20.05-39.95 s (practice mode): {len(d)}/200 answers differ"
          f"  {check(len(d) > 100, 'mode switch: practice control')}")


# --- 2. decision time ----------------------------------------------------------------------------

def near_buildings():
    """A walkable start with buildings around: some cells within 30 m are hidden from a mech
    90 m away and some are not."""
    grid = dt.GRID
    for index in range(0, len(grid.free), 7):
        if not grid.free[index]:
            continue
        i, j = index % grid.width, index // grid.width
        if not (20 <= i < grid.width - 20 and 20 <= j < grid.height - 20):
            continue
        origin = grid.point(index)
        for bearing in range(0, 360, 30):
            spot = at(origin, bearing, 90)
            if not dt.walkable(spot):
                continue
            eye = (spot[0], spot[1], et.ground(*spot[:2]) + MECH["eye_height"])
            if not et.COVER.clear(eye, (origin[0], origin[1], et.ground(*origin) + 4.5)):
                continue
            hidden = 0
            for r in (12, 20, 28):
                for k in range(12):
                    q = at(origin, k * 30, r)
                    if grid.clear_segment(origin, q) and not et.COVER.clear(eye, (q[0], q[1], q[2] + 4.5)):
                        hidden += 1
            if 3 <= hidden <= 24:
                return origin, bearing
    raise RuntimeError("no start near buildings")


def busy_stream(bot, seconds_per_phase=20.0, seed=5):
    """Closed loop in process; returns the observations, the act() times and what set each move."""
    rng = random.Random(seed)
    origin, bearing = near_buildings()
    x, y = origin
    vx = vy = 0.0
    aim = [0.0, 0.0]
    gun = et.gun()
    las = et.laser(0.0)
    phases = ["retreat: 3 engaged hunters and 3 passive mechs, HP 45%, loot in view",
              "fight: the same hunters moving, full HP, laser charging",
              "loot: no mech listed, drones, crates, cubes and pickups in view",
              "crowd: 15 engaged mechs within 60-215 m, hits every 0.5 s, HP 45%"]
    out = dict(obs=[], times=[], modes=[], phase=[])
    k = 0
    for p, label in enumerate(phases):
        for n in range(int(seconds_per_phase * 10)):
            t = round(30.0 + 0.1 * k, 2)
            here = (x, y)
            # Everything stands where the loop started (origin); the hunters aim at where we are.
            if p in (0, 1):
                mechs = [mech(20 + i, origin, bearing + 40 * i, 90 + 40 * i, aim_at_us=True, us=here,
                              vel=(rng.uniform(-6, 6), rng.uniform(-6, 6)) if p == 1 else (0.0, 0.0),
                              weapons=("gun", "laser") if i == 0 else ("gun",), charging=(p == 1 and i == 0))
                         for i in range(3)]
                mechs += [mech(30 + i, origin, bearing + 150 + 50 * i, 100 + 40 * i, us=here) for i in range(3)]
            elif p == 3:
                mechs = [mech(40 + i, origin, bearing + 24 * i, 60 + 11 * i, hp=300 + 70 * i, aim_at_us=True, us=here)
                         for i in range(15)]
            else:
                mechs = []
            mechs += [drone(100 + i, origin, 60 * i + 10, 50 + 15 * i) for i in range(6)]
            events = []
            if p in (0, 3) and n % 5 == 0:
                events.append(et.damaged(20 if p == 0 else 40 + n % 15, bearing))
            hp = 630.0 if p in (0, 3) else 1400.0
            las["charge"] = min(LASER["charge"], 0.05 * (n % 20)) if p in (1, 3) else 0.0
            gun["ammo"] = 12 - (n // 3) % 13
            obs = et.frame(k, mechs, events, origin=here, hp=hp, weapons=[copy.deepcopy(gun), copy.deepcopy(las)],
                           pickups=[dict(id=8001 + i, kind=kind, pos=at(origin, 90 * i + 45, 25 + 20 * i))
                                    for i, kind in enumerate(("laser", "lightning", "mortar"))])
            obs["t"] = t
            obs["tick"] = 2 * k
            obs["alive"] = 16
            obs["self"]["aim"] = list(aim)
            obs["self"]["vel"] = [vx, vy, 0.0]
            obs["crates"] = [dict(id=1001 + i, pos=at(origin, 37 * i, 30 + 12 * i), hp=300) for i in range(10)]
            obs["cubes"] = [dict(id=5001 + i, pos=at(origin, 23 * i + 7, 50 + 6 * i)) for i in range(15)]
            obs["projectiles"] = [bullet(9000 + 10 * k + i, here, rng.uniform(0, 360), rng.uniform(20, 80),
                                         toward=rng.random() < 0.5) for i in range(4)]
            obs["zone"].update(center=list(origin), radius=400.0, next_center=list(origin), next_radius=250.0,
                               shrink_start=1000.0, shrink_end=1050.0)
            start = time.perf_counter()
            action = bot.act(copy.deepcopy(obs))
            out["times"].append(time.perf_counter() - start)
            drawn = mf.draw.take() or {}
            text = next((item["text"] for item in drawn.get("text", []) if item["text"].startswith("squad")), "-")
            out["obs"].append(obs)
            out["modes"].append(text)
            out["phase"].append(p)
            move = action.get("move") or [0.0, 0.0]
            length = math.hypot(*move)
            if length > 1:
                move = [move[0] / length, move[1] / length]
            step = MECH["walk_speed"] * 0.1
            nxt = (x + move[0] * step, y + move[1] * step)
            vx = vy = 0.0
            if dt.walkable(nxt):
                x, y = nxt
                vx, vy = move[0] * MECH["walk_speed"], move[1] * MECH["walk_speed"]
            yaw = (action.get("aim") or aim)[0]
            turn = (yaw - aim[0] + math.pi) % math.tau - math.pi
            aim = [aim[0] + max(-MECH["turn_rate"] * 0.1, min(MECH["turn_rate"] * 0.1, turn)), 0.0]
            k += 1
    out["labels"] = phases
    return out


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))] * 1e3


def timing():
    print("\n2. decision time with the practice parts busy (closed loop near buildings, t from 30 s)")
    from bot import Bot
    bot = Bot(et.HELLO)
    mf.draw.clear()
    run = busy_stream(bot)
    for p, label in enumerate(run["labels"]):
        times = [t for t, q in zip(run["times"], run["phase"]) if q == p]
        modes = {}
        for m, q in zip(run["modes"], run["phase"]):
            if q == p:
                modes[m] = modes.get(m, 0) + 1
        top = ", ".join(f"{m} {c}" for m, c in sorted(modes.items(), key=lambda item: -item[1])[:5])
        print(f"   {label}\n      act() p50 {pct(times, 0.5):.2f} ms, p99 {pct(times, 0.99):.2f} ms, max {max(times) * 1e3:.2f} ms;"
              f" moves: {top}")
    mover = getattr(bot, "squad_move", None)
    if mover is not None:
        print(f"   cover searches {mover.cover.searches} ({mover.cover.tests} cells tested); squad_move errors {mover.errors}")
    econ = getattr(bot, "squad_econ", None)
    if econ is not None:
        print(f"   squad_econ plans: {dict(sorted(econ.modes.items(), key=lambda item: -item[1]))}")
    p99, worst = pct(run["times"], 0.99), max(run["times"]) * 1e3
    print(f"   all {len(run['times'])} decisions in process: p99 {p99:.2f} ms, max {worst:.2f} ms"
          f"  {check(p99 < 8.0, 'timing: in-process p99 under 8 ms')}")
    proc = BotProcess(ROOT, et.HELLO)
    for obs in run["obs"]:
        proc.act(copy.deepcopy(obs))
    proc.close()
    p99, worst = pct(proc.times, 0.99), max(proc.times) * 1e3
    print(f"   the same {len(proc.times)} observations through stdin/stdout: p50 {pct(proc.times, 0.5):.2f} ms,"
          f" p99 {p99:.2f} ms, max {worst:.2f} ms  {check(p99 < 8.0, 'timing: round-trip p99 under 8 ms')}")


# --- 3. fuzz -------------------------------------------------------------------------------------

def random_obs(rng, k, t, alive, origin):
    kinds = ["gun", "laser", "lightning", "mortar"]
    mechs = []
    for i in range(rng.randint(0, 12)):
        m = mech(20 + i, origin, rng.uniform(0, 360), rng.uniform(3, 300), hp=rng.choice([1, 50, 400, 1400]),
                 aim_at_us=rng.random() < 0.4, vel=(rng.uniform(-15, 15), rng.uniform(-15, 15)),
                 weapons=tuple(rng.sample(kinds, rng.randint(0, 2))), charging=rng.random() < 0.2)
        m["cubes"] = rng.randint(0, 12)
        if rng.random() < 0.1:
            m.pop("aim")
        if rng.random() < 0.1:
            m.pop("hp")
        if rng.random() < 0.1:
            m["pos"][2] += 15.0
        mechs.append(m)
    for i in range(rng.randint(0, 6)):
        mechs.append(drone(100 + i, origin, rng.uniform(0, 360), rng.uniform(3, 220)))
    events = []
    for _ in range(rng.randint(0, 3)):
        kind = rng.choice(["damaged", "hit", "took", "take_failed", "pickup"])
        if kind == "damaged":
            events.append(dict(type="damaged", amount=45, weapon=rng.choice(["gun", "laser", "npc", "mortar", "zone", "lightning"]),
                               by=rng.choice([None, 20, 21, 100, 5]), bearing=rng.choice([None, rng.uniform(-3, 3)])))
        elif kind == "hit":
            events.append(dict(type="hit", target=rng.choice([20, 100, 1001]), amount=45, weapon="gun"))
        elif kind == "take_failed":
            events.append(dict(type="take_failed", id=8000, reason=rng.choice(["range", "have", "full"])))
        else:
            events.append(dict(type=kind, id=8000, kind="laser", slot=1, cubes=rng.randint(0, 12)))
    slots = [et.gun(), None]
    slots[0].update(ammo=rng.randint(0, 12), reload=rng.choice([0.0, 0.0, 1.2]))
    second = rng.choice([None, "laser", "lightning", "mortar"])
    if second == "laser":
        slots[1] = et.laser(rng.choice([0.0, 0.1, 0.3, 0.7, 0.75]))
        slots[1]["cooldown"] = rng.choice([0.0, 0.8])
    elif second:
        slots[1] = dict(kind=second, cooldown=0.0, stats=copy.deepcopy(CONFIG["weapons"][second]))
    if rng.random() < 0.05:
        slots = [None, None]
    pickups = [dict(id=8000 + i, kind=rng.choice(kinds), pos=at(origin, rng.uniform(0, 360), rng.uniform(0, 250)))
               for i in range(rng.randint(0, 4))]
    obs = et.frame(k, mechs, events, origin=origin, hp=rng.uniform(1, 1400), weapons=slots, pickups=pickups)
    obs["t"] = round(t, 2)
    obs["tick"] = 2 * k
    obs["alive"] = alive
    obs["self"].update(aim=[rng.uniform(-math.pi, math.pi), rng.uniform(-0.5, 0.5)],
                       vel=[rng.uniform(-12, 12), rng.uniform(-12, 12), 0.0], energy=rng.uniform(0, 100),
                       cubes=rng.randint(0, 15), grounded=rng.random() < 0.95, in_zone=rng.random() < 0.9)
    if rng.random() < 0.05:
        obs["self"]["pos"][2] += rng.choice([5.0, 20.0])
    obs["crates"] = [dict(id=1001 + i, pos=at(origin, rng.uniform(0, 360), rng.uniform(2, 200)), hp=300)
                     for i in range(rng.randint(0, 8))]
    obs["cubes"] = [dict(id=5001 + i, pos=at(origin, rng.uniform(0, 360), rng.uniform(1, 150))) for i in range(rng.randint(0, 10))]
    obs["projectiles"] = [dict(id=9000 + 10 * k + i, kind=rng.choice(["gun", "npc", "mortar"]),
                               pos=at(origin, rng.uniform(0, 360), rng.uniform(5, 80)),
                               vel=[rng.uniform(-250, 250), rng.uniform(-250, 250), rng.uniform(-20, 20)])
                          for i in range(rng.randint(0, 5))]
    obs["offer"] = (dict(id=k, choices=[dict(id=u["id"], name=u["id"], desc="") for u in rng.sample(CONFIG["upgrades"], 3)],
                         expires=9) if rng.random() < 0.05 else None)
    nr = rng.choice([250.0, 140.0, 70.0, 25.0, 5.0, 0.0])
    centre = at(origin, rng.uniform(0, 360), rng.uniform(0, 200))
    obs["zone"].update(center=centre[:2], radius=nr + rng.uniform(0, 200), next_center=centre[:2], next_radius=nr,
                       shrink_start=t + rng.uniform(-30, 30), shrink_end=t + rng.uniform(30, 60))
    if rng.random() < 0.03:
        obs["zone"]["shrink_end"] = obs["zone"]["shrink_start"]
    return obs


def fuzz(matches=6, length=1000, seed=31):
    print("\n3. fuzz")
    from bot import Bot
    rng = random.Random(seed)
    free = [i for i in range(len(dt.GRID.free)) if dt.GRID.free[i]]
    errors, bad, decisions, practice, swallowed = [], 0, 0, 0, 0
    for match in range(matches):
        bot = Bot(et.HELLO)
        t0 = rng.choice([0.0, 15.0, 25.0, 100.0, 250.0]) if match % 2 == 0 else rng.choice([15.0, 25.0, 100.0])
        alive, kills = 16, 0
        origin = dt.GRID.point(rng.choice(free))
        for k in range(length):
            if k % 100 == 0 and rng.random() < 0.5:
                origin = dt.GRID.point(rng.choice(free))
            obs = random_obs(rng, k, t0 + 0.1 * k, alive, origin)
            if rng.random() < 0.01 and alive > 2:
                # Every other match also has deaths we did not cause (practice mode ends there).
                alive -= 1
                obs["alive"] = alive
                if match % 2 or rng.random() < 0.5:
                    obs["events"].append(dict(type="kill", target=20 + kills))
                    kills += 1
            try:
                action = bot.act(obs)
                mf.draw.clear()
                json.dumps(action)
                fire = action.get("fire")
                if (not isinstance(fire, list) or len(fire) != 2 or not all(isinstance(f, bool) for f in fire)
                        or not all(math.isfinite(v) for key in ("move", "aim") for v in action.get(key, [0.0, 0.0]))):
                    bad += 1
            except Exception:
                errors.append(traceback.format_exc(limit=4))
            decisions += 1
            practice += bot.practice.active
            mover = getattr(bot, "squad_move", None)
            if mover is not None:
                swallowed += mover.errors
                mover.errors = 0
    ok = not errors and not bad and not swallowed
    print(f"   {decisions} random decisions in process ({practice} in practice mode): {len(errors)} exceptions,"
          f" {bad} malformed or non-finite actions, {swallowed} errors swallowed by squad_move.py"
          f"  {check(ok, 'fuzz')}")
    if errors:
        print("   first:", errors[0])


# --- 4. movement priority (with squad_econ.py) ---------------------------------------------------

def pframe(k, mechs=(), hp=1400.0, crates=(), cubes=(), pickups=(), in_zone=True, zone=None, projectiles=(),
           origin=HOME, events=(), drops=()):
    """A practice-mode decision (t = 30 s + 0.1 s per decision), on the open lawn unless `origin`
    says otherwise (the zone is centred there unless `zone` moves it)."""
    obs = et.frame(k, mechs, events, in_zone=in_zone, hp=hp, pickups=pickups, origin=origin)
    obs["drops"] = copy.deepcopy(list(drops))
    obs["t"] = round(30.0 + 0.1 * k, 2)
    obs["tick"] = 600 + 2 * k
    obs["alive"] = 16
    obs["crates"] = [dict(id=1001 + i, pos=list(p), hp=300) for i, p in enumerate(crates)]
    obs["cubes"] = [dict(id=5001 + i, pos=list(p)) for i, p in enumerate(cubes)]
    obs["projectiles"] = list(projectiles)
    if in_zone:
        obs["zone"].update(shrink_start=1000.0, shrink_end=1050.0)
    if zone:
        obs["zone"].update(zone)
    return obs


def scripted(make, n, frozen=False):
    """Decisions make(k) for k < n through the real entrypoint. The torso is where the bot last
    aimed it and, unless frozen, our velocity follows the last move (so only a frozen mech looks
    stuck). Returns [(obs, action, debug label)]."""
    bot = BotProcess(ROOT, et.HELLO)
    rows, last = [], {}
    for k in range(n):
        obs = make(k)
        if last.get("aim"):
            obs["self"]["aim"] = list(last["aim"])
        move = last.get("move") or [0.0, 0.0]
        if not frozen:
            obs["self"]["vel"] = [move[0] * MECH["walk_speed"], move[1] * MECH["walk_speed"], 0.0]
        action = bot.act(obs)
        rows.append((obs, action, (action.get("debug") or {}).get("label", "")))
        last = action
    bot.close()
    return rows


def walked(make, n, start=HOME):
    """Like scripted(), but our mech walks where the bot steers it (walk speed, walls from the
    ground grid) and the torso is where the bot last aimed it. make(k, here) builds decision k
    at our position. Returns [(obs, action, debug label)] and the final position."""
    bot = BotProcess(ROOT, et.HELLO)
    rows, last, here, vel = [], {}, tuple(start), [0.0, 0.0, 0.0]
    for k in range(n):
        obs = make(k, here)
        if last.get("aim"):
            obs["self"]["aim"] = list(last["aim"])
        obs["self"]["vel"] = list(vel)
        action = bot.act(obs)
        rows.append((obs, action, (action.get("debug") or {}).get("label", "")))
        last = action
        move = action.get("move") or [0.0, 0.0]
        length = math.hypot(*move)
        if length > 1:
            move = [move[0] / length, move[1] / length]
        step = MECH["walk_speed"] * 0.1
        nxt = (here[0] + move[0] * step, here[1] + move[1] * step)
        vel = [0.0, 0.0, 0.0]
        if dt.walkable(nxt):
            here = nxt
            vel = [move[0] * MECH["walk_speed"], move[1] * MECH["walk_speed"], 0.0]
    bot.close()
    return rows, here


def priority():
    print("\n4. movement priority in practice mode (open lawn, t = 30 s; the debug label names the rule)")
    hunter = lambda key, distance, bearing=OPEN: mech(key, HOME, bearing, distance, aim_at_us=True)
    two = [hunter(5, 80), hunter(6, 120, OPEN + 40)]

    def show(rows, first=0):
        seen = []
        for _, _, label in rows[first:]:
            if not seen or seen[-1][0] != label:
                seen.append([label, 0])
            seen[-1][1] += 1
        return ", ".join(f"'{label}' x{count}" for label, count in seen)

    def case(text, rows, ok, first=0):
        print(f"   {text}: {show(rows, first)}  {check(ok, 'priority: ' + text)}")

    rows = scripted(lambda k: pframe(k, [hunter(5, 100)]), 15, frozen=True)
    labels = [label for _, _, label in rows]
    start = labels.index("squad unstuck") if "squad unstuck" in labels else None
    case("the stuck recovery outranks the fight move (our mech cannot move)", rows,
         start is not None and all(label.startswith("squad fight") for label in labels[:start]))
    rows = scripted(lambda k: pframe(k, two, hp=630.0, in_zone=False), 10)
    case("zone must outranks the retreat (two hunters, HP 45%, outside the zone)", rows,
         all(label.startswith("squad zone must") for _, _, label in rows))
    rows = scripted(lambda k: pframe(k, two, hp=630.0), 10)
    case("the LoseRule retreat outranks the fight move (two hunters, HP 45%)", rows,
         all(label.split()[1] in ("cover", "cornered") for _, _, label in rows))
    loot = dict(crates=[at(HOME, OPEN + 120, 40)], pickups=[dict(id=8002, kind="laser", pos=at(HOME, OPEN - 120, 30))])
    rows = scripted(lambda k: pframe(k, [hunter(5, 150)], **loot), 10)
    case("the fight move outranks the laser detour and loot (hunter at 150 m, crate 40 m, laser 30 m)", rows,
         all(label.startswith("squad fight") for _, _, label in rows))
    should = dict(center=list(HOME), radius=400.0, next_center=at(HOME, OPEN + 180, 55)[:2], next_radius=60.0,
                  shrink_start=35.0, shrink_end=45.0)
    rows = scripted(lambda k: pframe(k, cubes=[at(HOME, OPEN, 20)], zone=should), 10)
    case("zone should outranks loot (shrink in 5 s, a cube 20 m away)", rows,
         all(label.startswith("squad zone should") for _, _, label in rows))
    rows = scripted(lambda k: pframe(k, cubes=[at(HOME, OPEN + 90, 25)],
                                     pickups=[dict(id=8002, kind="laser", pos=at(HOME, OPEN, 40))]), 10)
    case("the laser pickup squad_fire.py chose outranks loot (laser 40 m, cube 25 m)", rows,
         all(label == "squad pickup" for _, _, label in rows))
    rows = scripted(lambda k: pframe(k, cubes=[at(HOME, OPEN, 30)]), 10)
    case("loot when nothing outranks it (a cube 30 m away)", rows,
         all(label == "squad loot cube 5001" for _, _, label in rows))
    rows = scripted(lambda k: pframe(k), 10)
    case("camp with nothing to do", rows, all(label == "squad camp" for _, _, label in rows))
    rows = scripted(lambda k: pframe(k, [mech(7, HOME, OPEN, 120)]), 12)
    yaws = [action["aim"][0] for _, action, _ in rows]
    steps = [abs((b - a + math.pi) % math.tau - math.pi) for a, b in zip(yaws, yaws[1:])]
    case("an unengaged mech is neither fought nor faced: camp, the idle spin turns on", rows,
         all(label == "squad camp" for _, _, label in rows) and all(abs(s - 0.35) < 1e-6 for s in steps)
         and not any(any(action.get("fire") or []) for _, action, _ in rows))
    rows = scripted(lambda k: pframe(k, crates=[at(HOME, OPEN, 30)]), 10)
    case("the loot shot with no mech target (a crate 30 m away): the gun fires once aimed", rows,
         all(label == "squad loot crate shoot 1001" for _, _, label in rows)
         and any((action.get("fire") or [False])[0] for _, action, _ in rows))
    rows = scripted(lambda k: pframe(k, [hunter(5, 150)], crates=[at(HOME, OPEN + 120, 30)]), 10)
    case("no loot shot while there is a mech target (the same crate, a hunter at 150 m)", rows,
         all(label.startswith("squad fight") for _, _, label in rows))
    shot = bullet(9100, HOME, OPEN + 90, 150)   # 0.6 s out: far enough to step clear
    plain_run = scripted(lambda k: pframe(k, [hunter(5, 100)]), 6, frozen=True)
    dodged = scripted(lambda k: pframe(k, [hunter(5, 100)], projectiles=[shot] if k == 5 else []), 6, frozen=True)
    before, after = plain_run[5][1]["move"], dodged[5][1]["move"]
    across = abs(after[0] * shot["vel"][0] + after[1] * shot["vel"][1]) / GUN["speed"]
    case(f"the bullet dodge keeps the last word (fight move {[round(v, 2) for v in before]},"
         f" with a bullet on course {[round(v, 2) for v in after]})", dodged[5:],
         after != before and across < 0.2 and math.hypot(*after) > 0.9)

    print("   the fixes:")
    wrap = lambda a: (a + math.pi) % math.tau - math.pi
    camping = lambda rows: all(label == "squad camp" for _, _, label in rows)

    def faces(rows, other):
        here = rows[0][0]["self"]["pos"]
        yaw = math.atan2(other["pos"][1] - here[1], other["pos"][0] - here[0])
        return all(abs(wrap(action["aim"][0] - yaw)) < 0.01 for _, action, _ in rows[1:])
    # Only the target is fought: engaged, with a line of fire, within 240 m.
    origin, cover_bearing, cover_distance, clear_bearing = et.COVER_SPOT
    hidden = mech(9, origin, cover_bearing, cover_distance, aim_at_us=True)
    rows = scripted(lambda k: pframe(k, [hidden], origin=origin), 10)
    case(f"an engaged mech with no line of fire ({cover_distance} m, behind cover, aiming at us) is faced,"
         f" not walked to", rows, camping(rows) and faces(rows, hidden))
    far = mech(5, HOME, OPEN, 262)
    rows = scripted(lambda k: pframe(k, [far], events=[et.damaged(5, OPEN, weapon="laser")] if k == 0 else []), 10)
    case("a mech that hit us from 262 m (beyond 240 m) is faced, not walked to", rows,
         camping(rows) and faces(rows, far))
    # The laser detour: above zone should, through damage, and while the laser is out of view.
    rows = scripted(lambda k: pframe(k, pickups=[dict(id=8002, kind="laser", pos=at(HOME, OPEN + 180, 30))],
                                     zone=should), 10)
    case("the laser detour outranks zone should (shrink in 5 s, the laser 30 m away inside the next circle)", rows,
         all(label == "squad pickup" for _, _, label in rows))
    calm = dict(center=list(HOME), radius=400.0, next_center=list(HOME), next_radius=250.0, shrink_start=1000.0,
                shrink_end=1050.0)
    laser_far = dict(id=8003, kind="laser", pos=at(HOME, OPEN, 110))
    drone_hit = dict(type="damaged", amount=25, weapon="npc", by=104, bearing=1.0)
    rows, end = walked(lambda k, here: pframe(k, pickups=[laser_far], origin=here, zone=calm,
                                             hp=1400.0 if k < 10 else 1375.0,
                                             events=[drone_hit] if k == 10 else []), 40)
    left = math.dist(end, laser_far["pos"][:2])
    case(f"the laser detour holds through a drone hit at 1 s (laser 110 m away; {left:.0f} m left after 4 s)", rows,
         all(label == "squad pickup" for _, _, label in rows) and left < 70)
    laser_unseen = dict(id=8004, kind="laser", pos=at(HOME, OPEN, 200))
    rows, end = walked(lambda k, here: pframe(k, pickups=[laser_unseen] if k < 3 else [], origin=here, zone=calm), 60)
    left = math.dist(end, laser_unseen["pos"][:2])
    pursuing = sum(label == "squad pickup" for _, _, label in rows)
    case(f"a laser 200 m away listed on the first 3 decisions only is still followed ({pursuing}/60 decisions,"
         f" {left:.0f} m left after 6 s)", rows, all(label == "squad pickup" for _, _, label in rows[20:]) and left < 150)
    # No supply drop or relocate hop.
    drop = dict(id=20000, pos=at(HOME, OPEN, 30), radius=8, lands_in=0.0, capture_s=4, progress=0, holder=None)
    rows = scripted(lambda k: pframe(k, hp=840.0, drops=[drop]), 10)
    case("no supply-drop move (HP 60%, a drop on the ground 30 m away)", rows, camping(rows))
    rows = scripted(lambda k: pframe(k, hp=1400.0 if k < 2 else 1355.0,
                                     events=[et.damaged(104, OPEN, weapon="npc")] if k == 2 else []), 10)
    case("no relocate hop after damage (a drone hit at 0.2 s)", rows, camping(rows))
    # Cubes still count under threat; crates do not.
    spot = at(origin, clear_bearing, 30)
    rows = scripted(lambda k: pframe(k, [hidden], cubes=[spot], origin=origin), 10)
    case("a cube 30 m away is collected under threat (the engaged mech behind cover listed)", rows,
         all(label == "squad loot cube 5001" for _, _, label in rows))
    rows = scripted(lambda k: pframe(k, [hidden], crates=[spot], origin=origin), 10)
    case("control: a crate there is left alone under the same threat", rows, camping(rows))


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    mode_switch(folder)
    timing()
    fuzz()
    if (ROOT / "squad_econ.py").exists():
        priority()
    if FAILURES:
        print("\nFAIL:", "; ".join(FAILURES))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
