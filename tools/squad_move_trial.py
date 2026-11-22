"""squad-move: farm-power (8064167, official 3.25) and candidate as real bot processes.

    py tools/squad_move_trial.py [--baseline <git revision>] [--skip-fights]

Practice mode (from 20 s of match time while every death is one of our kills) hands our
movement to squad.py during fights. Both builds run as `python -u bot.py` on the same
observations; the candidate names what set its move in a debug text ("squad fight",
"squad cover", ...), which the server never reads.

The world (shared by every loop): our mech moves as commanded (ground acceleration, walk and
boost speed, boost energy, half speed while a laser charges, walls from the ground grid). Our
gun fires along the torso's actual aim (turn rates from the config) with seeded spread; a held
laser charges and fires its beam when let go. Scripted house mechs stand, or hunt: walk the
navigation grid toward us until they see us within their standoff. A gun hunter leads its
shots (252 m/s, 0.24 s, 12 rounds, 2.4 s reload, 0.6 deg spread); a lightning hunter deals 60
every 0.25 s within 45 m with a clear line. Bullets stop at solid matter (cover.py), hits from
behind deal x1.5, everyone regenerates 45 HP/s after 5 s out of combat, kills drop 2 cubes and
lower `alive`. A mech is listed as the server does (45 m all round or 200 m inside our 120 deg
wedge, with a clear line; kept 5 s), or always when a scenario says so. Standard library only.

1. Scripted scenarios: range held with a laser and gun-only, a spot with a line of fire, a spot
   a second hunter cannot see, the strafe, a mid-fight cube grab, finish mode, the LoseRule
   pulse (and finishing and late cancelling it), the cover search, the laser sidestep, and
   identity with the baseline before 20 s, after an outside death and on an urgent zone return.
2. Closed-loop fights against hunters walking in from 200 m: damage taken, kills, kill time.
3. Decision time, a fuzz pass for exceptions, and the standard recording.
"""
import copy
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from cover import Cover
from harness import BotProcess, export, plain

BASELINE = "8064167d11936561991186bf35261946ffbec33d"  # farm-power, official 3.25
CONFIG = et.HELLO["config"]
MECH, GUN = CONFIG["mech"], CONFIG["weapons"]["gun"]
LASER, LIGHTNING = CONFIG["weapons"]["laser"], CONFIG["weapons"]["lightning"]
BULLET_R = CONFIG["projectile"]["gun_radius"]
PICKUP_R = CONFIG["cubes"].get("pickup_radius", 3.5)
COVER = Cover()
GRID = dt.GRID
DT = 0.05
VISION_M, NEAR_M, FOV = 200.0, 45.0, math.radians(120)
T0 = 30.0
TIMES = []      # candidate round trips, seconds


def eye(p):
    return (p[0], p[1], et.ground(*p[:2]) + MECH["eye_height"])


def body(p, frac=0.5):
    return (p[0], p[1], et.ground(*p[:2]) + MECH["height"] * frac)


def sees(a, b):
    """Eye at a has a clear line to the body centre at b (vision and hunter awareness)."""
    return COVER.clear(eye(a), body(b), skip_start=1.0, skip_end=1.0)


def shot_clear(a, b):
    """Our muzzle at a has a clear line of fire to a mech body centre at b (Cover.clear, 1 m)."""
    return COVER.clear((a[0], a[1], et.ground(*a[:2]) + MECH["muzzle_height"]), body(b))


def hidden_from(p, threat):
    """Both the threat's eye-to-head and eye-to-mid-body lines at p are blocked."""
    e = eye(threat)
    return (not COVER.clear(body(p, 1.0), e, skip_start=1.0, skip_end=1.0)
            and not COVER.clear(body(p, 0.5), e, skip_start=1.0, skip_end=1.0))


def safe_ground(x, y):
    i = int((x - COVER.ox) / COVER.cell)
    j = int((y - COVER.oy) / COVER.cell)
    return COVER.ground[j * COVER.nx + i] / 100 if 0 <= i < COVER.nx and 0 <= j < COVER.ny else 0.0


def point(origin, bearing_deg, distance):
    a = math.radians(bearing_deg)
    return (origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a))


def blocked_at(origin, d, length):
    s = 0.0
    while s <= length:
        if COVER.solid(origin[0] + s * d[0], origin[1] + s * d[1], origin[2] + s * d[2]):
            return s
        s += 1.0
    return None


def body_param(origin, d, length, centre, radius=None):
    tx, ty, tz = centre[0], centre[1], et.ground(*centre[:2])
    flat2 = d[0] * d[0] + d[1] * d[1]
    s = max(0.0, min(length, ((tx - origin[0]) * d[0] + (ty - origin[1]) * d[1]) / flat2))
    px, py, pz = origin[0] + s * d[0], origin[1] + s * d[1], origin[2] + s * d[2]
    if math.hypot(px - tx, py - ty) <= (radius or MECH["radius"]) + BULLET_R and tz <= pz <= tz + MECH["height"]:
        return s
    return None


def squad_mode(action):
    for item in ((action.get("debug") or {}).get("text") or ()):
        text = item.get("text", "")
        if text.startswith("squad"):
            return text[6:] or "-"
    return None


# --- the world ---------------------------------------------------------------------------------

def hunter(key, pos, weapon="gun", mode="hunt", standoff=60.0, hp=1400.0, shoots=True, listed=False,
           charging=False, aim_off=0.0, leave_at=None, weapons=None):
    return dict(id=key, pos=list(pos), weapon=weapon, mode=mode, standoff=standoff, hp=float(hp),
                shoots=shoots, always=listed, charging=charging, aim_off=aim_off, leave_at=leave_at,
                weapons=weapons or [weapon or "gun"])


def run(folder, start, hunters, seconds=20.0, t0=T0, hp0=1400.0, laser=False, zone=None, cubes=(),
        move_us=True, damage_hunters=True, seed=1, alive=None, outside_death_at=None, energy0=100.0,
        gun_state=None, bot=None, record=True):
    """One loop. Returns per-decision records and totals."""
    own_bot = bot is None
    bot = bot or BotProcess(folder, et.HELLO)
    rng_us, rng_them = random.Random(seed), random.Random(seed + 1000)
    x, y = start
    vx = vy = 0.0
    energy, spent_at = energy0, -10.0
    hp, max_hp, last_combat = float(hp0), 1400.0, -10.0
    ws = [h for h in hunters]
    for h in ws:
        h.update(alive=True, ammo=GUN["mag"], cooldown=0.3, reload=0.0, last_combat=-10.0, listed_until=-1.0,
                 next_zap=0.0, nav=dt.Navigator(), max_hp=1400.0)
    first = ws[0]["pos"] if ws else (x + 1, y)
    aim = [math.atan2(first[1] - y, first[0] - x), 0.0]
    commanded = list(aim)
    gun = et.gun()
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    if gun_state:
        gun.update(gun_state)
    las = dict(kind="laser", cooldown=0.0, charge=0.0, stats=copy.deepcopy(LASER)) if laser else None
    held = 0.0
    zone = copy.deepcopy(zone) if zone else dict(center=list(start), radius=400.0, next_center=list(start),
                                                 next_radius=250.0, shrink_start=1000.0, shrink_end=1050.0, dps=20)
    items = [dict(id=5000 + n, pos=[c[0], c[1], et.ground(*c)]) for n, c in enumerate(cubes)]
    next_cube = 5000 + len(items)
    alive_count = alive if alive is not None else 16  # practice: us and 15 house mechs
    bullets, events, rows = [], [], []
    move, boost, fire = [0.0, 0.0], False, [False, False]
    taken = dealt = 0.0
    kills, kill_times, collected, cube_count = 0, [], 0, 0
    died = None
    for tick in range(int(seconds / DT)):
        now = round(t0 + tick * DT, 2)
        if outside_death_at is not None and abs(now - outside_death_at) < 1e-6:
            alive_count -= 1
        for h in ws:
            if h["alive"] and h["leave_at"] is not None and now >= h["leave_at"] - 1e-9:
                h["alive"] = False
                h["listed_until"] = -1.0
        # hunters move and fire
        for h in ws:
            if not h["alive"]:
                continue
            hx, hy = h["pos"]
            d = math.dist((hx, hy), (x, y))
            visible = d <= VISION_M and sees((hx, hy), (x, y))
            if h["mode"] == "hunt" and not (visible and d <= h["standoff"]):
                # Route to our position rounded to 16 m, so the planner's search can finish.
                goal = [round(x / 16) * 16, round(y / 16) * 16]
                if d < 24 or GRID.clear_segment((hx, hy), (x, y)):
                    goal = [x, y]
                nav = h["nav"]
                for _ in range(40):
                    w = nav.waypoint([hx, hy, et.ground(hx, hy)], goal)
                    if goal != nav.goal or nav.snap((hx, hy)) in nav.toward or not nav.queue:
                        break
                ddx, ddy = w[0] - hx, w[1] - hy
                L = math.hypot(ddx, ddy)
                if L > 0.5:
                    step = MECH["walk_speed"] * DT
                    nx_, ny_ = hx + ddx / L * min(step, L), hy + ddy / L * min(step, L)
                    if dt.walkable((nx_, ny_)):
                        h["pos"] = [nx_, ny_]
            if not h["shoots"]:
                continue
            h["cooldown"] = max(0.0, h["cooldown"] - DT)
            if h["weapon"] == "lightning":
                if visible and d <= LIGHTNING["range"] and now >= h["next_zap"] - 1e-9:
                    came = math.atan2(hy - y, hx - x)
                    rear = abs((came - aim[0] + math.pi) % math.tau - math.pi) > math.radians(MECH["front_arc_deg"] / 2)
                    amount = LIGHTNING["damage"] * (MECH["rear_mult"] if rear else 1.0)
                    hp -= amount
                    taken += amount
                    last_combat = h["last_combat"] = now
                    events.append(dict(type="damaged", amount=amount, weapon="lightning", by=h["id"], rear=rear, bearing=came))
                    h["next_zap"] = now + LIGHTNING["cooldown"]
                continue
            if h["reload"] > 0:
                h["reload"] = max(0.0, h["reload"] - DT)
                if h["reload"] == 0:
                    h["ammo"] = GUN["mag"]
            elif visible and h["cooldown"] == 0 and h["ammo"] > 0 and d <= GUN["range"]:
                yaw = dt.lead_aim(tuple(h["pos"]), (x, y), (vx, vy), GUN["speed"]) + math.radians(rng_them.gauss(0, GUN["spread_deg"]))
                z0 = et.ground(*h["pos"]) + MECH["muzzle_height"]
                dz = ((et.ground(x, y) + 4.5) - z0) / max(d, 1.0)
                norm = math.sqrt(1 + dz * dz)
                direction = (math.cos(yaw) / norm, math.sin(yaw) / norm, dz / norm)
                bullets.append(dict(owner=h["id"], pos=[h["pos"][0] + 3 * direction[0], h["pos"][1] + 3 * direction[1],
                                                        z0 + 3 * direction[2]], dir=direction, travelled=3.0,
                                    origin=tuple(h["pos"])))
                h["ammo"] -= 1
                h["cooldown"] = GUN["cooldown"]
                if h["ammo"] == 0:
                    h["reload"] = GUN["reload"]
        # decision
        if tick % 2 == 0:
            listed = []
            for h in ws:
                if not h["alive"]:
                    continue
                d = math.dist(h["pos"], (x, y))
                bearing = math.atan2(h["pos"][1] - y, h["pos"][0] - x)
                in_wedge = abs((bearing - aim[0] + math.pi) % math.tau - math.pi) <= FOV / 2
                if h["always"] or ((d <= NEAR_M or (d <= VISION_M and in_wedge)) and sees((x, y), h["pos"])):
                    h["listed_until"] = now + 5.0
                if now <= h["listed_until"] + 1e-9:
                    toward = math.atan2(y - h["pos"][1], x - h["pos"][0]) + h["aim_off"]
                    hvx = hvy = 0.0
                    listed.append(dict(id=h["id"], kind="mech", pos=[h["pos"][0], h["pos"][1], et.ground(*h["pos"])],
                                       vel=[hvx, hvy, 0.0], aim=[toward, 0.0], hp=round(h["hp"]), max_hp=1400, cubes=0,
                                       weapons=list(h["weapons"]), charging=h["charging"]))
            seen_cubes = [dict(id=c["id"], pos=list(c["pos"])) for c in items
                          if math.dist(c["pos"][:2], (x, y)) <= VISION_M]
            projectiles = [dict(id=1000 + k, kind="gun", pos=list(b["pos"]), vel=[GUN["speed"] * c for c in b["dir"]])
                           for k, b in enumerate(bullets) if b["owner"] != 0]
            obs = et.frame(tick // 2, listed, events, origin=[x, y], hp=round(hp, 1))
            obs["tick"] = tick
            obs["t"] = now
            obs["alive"] = alive_count
            obs["projectiles"] = projectiles
            obs["cubes"] = seen_cubes
            obs["self"].update(pos=[x, y, et.ground(x, y)], vel=[vx, vy, 0.0], energy=round(energy, 2), aim=list(aim),
                               max_hp=round(max_hp, 1), cubes=cube_count,
                               weapons=[copy.deepcopy(gun), copy.deepcopy(las)])
            obs["zone"] = copy.deepcopy(zone)
            obs["self"]["in_zone"] = math.dist((x, y), zone["center"]) <= zone["radius"]
            started = time.perf_counter()
            action = bot.act(obs)
            if folder == ROOT:
                TIMES.append(time.perf_counter() - started)
            events = []
            move = action.get("move", move)
            boost = bool(action.get("boost"))
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
            if record:
                rows.append(dict(t=now, pos=(x, y), hp=hp, mode=squad_mode(action), move=list(move), boost=boost,
                                 action=plain(action), listed=len(listed),
                                 dist=[math.dist(h["pos"], (x, y)) if h["alive"] else None for h in ws]))
        # torso
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        # our gun
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        damage_scale = 1 + 0.04 * min(cube_count, 10)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng_us.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng_us.gauss(0, GUN["spread_deg"]))
            d3 = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            z0 = et.ground(x, y) + MECH["muzzle_height"]
            bullets.append(dict(owner=0, pos=[x + 3 * d3[0], y + 3 * d3[1], z0 + 3 * d3[2]], dir=d3, travelled=3.0,
                                origin=(x, y)))
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        # our laser: charge while held, the beam fires when let go (or after hold_s at full charge)
        charging = False
        if las is not None:
            las["cooldown"] = max(0.0, las["cooldown"] - DT)
            if fire[1] and las["cooldown"] == 0:
                las["charge"] = min(LASER["charge"], las["charge"] + DT)
                held = held + DT if las["charge"] >= LASER["charge"] - 1e-9 else 0.0
                charging = True
            release = las["charge"] > 0 and (not fire[1] or held >= LASER["hold_s"])
            if release and las["charge"] >= LASER["min_charge"] - 1e-9:
                frac = LASER["min_frac"] + (1 - LASER["min_frac"]) * las["charge"] / LASER["charge"]
                muzzle = (x, y, et.ground(x, y) + MECH["muzzle_height"])
                d3 = (math.cos(aim[1]) * math.cos(aim[0]), math.cos(aim[1]) * math.sin(aim[0]), math.sin(aim[1]))
                hit = None
                for h in ws:
                    if not h["alive"]:
                        continue
                    s = body_param(muzzle, d3, LASER["range"], h["pos"])
                    if s is not None and COVER.clear(muzzle, body(h["pos"])) and (hit is None or s < hit[0]):
                        hit = (s, h)
                if hit and damage_hunters:
                    h = hit[1]
                    amount = LASER["damage"] * frac * damage_scale
                    h["hp"] -= amount
                    dealt += amount
                    h["last_combat"] = last_combat = now
                    events.append(dict(type="hit", target=h["id"], amount=amount, weapon="laser"))
                las["charge"], held = 0.0, 0.0
                las["cooldown"] = LASER["cooldown"]
                charging = False
            elif release:
                las["charge"], held = 0.0, 0.0
        # our movement
        if move_us:
            length = math.hypot(*move)
            mx, my = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
            speed = MECH["walk_speed"]
            if boost and length > 0 and energy > 0:
                speed = MECH["boost_speed"]
                energy = max(0.0, energy - MECH["boost_drain"] * DT)
                spent_at = now
            elif now - spent_at >= MECH["energy_regen_delay"]:
                energy = min(MECH["energy"], energy + MECH["energy_regen"] * DT)
            if charging:
                speed *= 0.5
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
        # cubes
        for c in list(items):
            if math.dist(c["pos"][:2], (x, y)) <= PICKUP_R:
                items.remove(c)
                collected += 1
                cube_count += 1
                max_hp += 56.0
                hp += 56.0
                events.append(dict(type="pickup", cubes=cube_count))
        # bullets
        alive_b = []
        step = GUN["speed"] * DT
        for b in bullets:
            wall = blocked_at(b["pos"], b["dir"], step)
            if b["owner"] == 0:
                hit = None
                for h in ws:
                    if h["alive"]:
                        s = body_param(b["pos"], b["dir"], step, h["pos"])
                        if s is not None and (wall is None or s < wall) and (hit is None or s < hit[0]):
                            hit = (s, h)
                if hit:
                    h = hit[1]
                    if damage_hunters:
                        amount = GUN["damage"] * damage_scale
                        h["hp"] -= amount
                        dealt += amount
                        events.append(dict(type="hit", target=h["id"], amount=amount, weapon="gun"))
                    h["last_combat"] = last_combat = now
                    continue
            else:
                s = body_param(b["pos"], b["dir"], step, (x, y))
                if s is not None and (wall is None or s < wall):
                    came = math.atan2(-b["dir"][1], -b["dir"][0])
                    rear = abs((came - aim[0] + math.pi) % math.tau - math.pi) > math.radians(MECH["front_arc_deg"] / 2)
                    amount = GUN["damage"] * (MECH["rear_mult"] if rear else 1.0)
                    hp -= amount
                    taken += amount
                    last_combat = now
                    for h in ws:
                        if h["id"] == b["owner"]:
                            h["last_combat"] = now
                    events.append(dict(type="damaged", amount=amount, weapon="gun", by=b["owner"], rear=rear,
                                       bearing=math.atan2(b["origin"][1] - y, b["origin"][0] - x)))
                    continue
            if wall is not None:
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive_b.append(b)
        bullets = alive_b
        for h in ws:
            if h["alive"] and h["hp"] <= 0:
                h["alive"] = False
                kills += 1
                kill_times.append(round(now - t0, 1))
                alive_count -= 1
                events.append(dict(type="kill", target=h["id"]))
                for off in (-1.5, 1.5):
                    items.append(dict(id=next_cube, pos=[h["pos"][0] + off, h["pos"][1], et.ground(*h["pos"])]))
                    next_cube += 1
        # regeneration
        if now - last_combat >= MECH["regen_delay"] and hp > 0:
            hp = min(max_hp, hp + MECH["regen_per_s"] * DT)
        for h in ws:
            if h["alive"] and now - h["last_combat"] >= MECH["regen_delay"]:
                h["hp"] = min(1400.0, h["hp"] + MECH["regen_per_s"] * DT)
        if hp <= 0:
            died = round(now - t0, 1)
            break
    if own_bot:
        bot.close()
    return dict(rows=rows, taken=round(taken), dealt=round(dealt), kills=kills, kill_times=kill_times, died=died,
                hp=round(max(hp, 0)), collected=collected, end=(x, y))


# --- geometry ----------------------------------------------------------------------------------

def ring(origin):
    out = []
    for k in range(16):
        p = point(origin, k * 22.5, 6.0)
        if GRID.clear_segment(origin, p):
            out.append(p)
    return out


def open_line():
    """A start with clear lines along one bearing out to 170 m, walkable ground 70 m behind
    and 30 m to each side, so range can be held both ways."""
    starts = [tuple(et.HOME)] + [GRID.point(i) for i in range(0, len(GRID.free), 11) if GRID.free[i]]
    for origin in starts:
        for bearing in range(0, 360, 5):
            if not all(et.clear_from(origin, bearing + d, r) for d in (-15, 0, 15) for r in (40, 80, 120, 170)):
                continue
            back = point(origin, bearing + 180, 70)
            if not (GRID.clear_segment(origin, back) and dt.walkable(back)):
                continue
            if not all(GRID.clear_segment(origin, point(origin, bearing + s, 30)) for s in (90, -90)):
                continue
            if not all(dt.walkable(point(origin, bearing, r)) for r in (50, 60, 85, 90, 160, 170)):
                continue
            return origin, bearing
    raise RuntimeError("no open line")


def fire_spot():
    """A start with no line of fire to a foe 50-110 m away, while some walkable 6 m ring points
    have one and others do not."""
    for index in range(0, len(GRID.free), 5):
        if not GRID.free[index]:
            continue
        origin = GRID.point(index)
        pts = ring(origin)
        if len(pts) < 10:
            continue
        for bearing in range(0, 360, 10):
            for distance in (60, 80, 100):
                foe = point(origin, bearing, distance)
                if not dt.walkable(foe) or shot_clear(origin, foe):
                    continue
                good = [p for p in pts if shot_clear(p, foe)]
                if 2 <= len(good) <= len(pts) - 4:
                    return origin, foe, good
    raise RuntimeError("no fire spot")


def watcher_spot():
    """A start where a foe 70-100 m away has a line of fire from every walkable ring point, and a
    second (passive) mech 60-150 m away sees our body now and some ring points but not at least
    three others that keep the line of fire."""
    for index in range(0, len(GRID.free), 3):
        if not GRID.free[index]:
            continue
        origin = GRID.point(index)
        pts = ring(origin)
        if len(pts) < 12:
            continue
        for fb in range(0, 360, 20):
            foe = point(origin, fb, 80)
            if not dt.walkable(foe) or not all(shot_clear(p, foe) for p in pts + [origin]):
                continue
            for sb in range(0, 360, 15):
                if abs((sb - fb + 180) % 360 - 180) < 40:
                    continue
                for sd in (70, 100, 130):
                    second = point(origin, sb, sd)
                    if not dt.walkable(second) or not sees(second, origin):
                        continue
                    unseen = [p for p in pts if not COVER.clear(eye(second), body(p, 0.6), skip_start=1.0, skip_end=1.0)]
                    if 3 <= len(unseen) <= len(pts) - 3:
                        return origin, foe, second, unseen
    raise RuntimeError("no watcher spot")


def cover_spot(distances=(80, 120), spread=35):
    """A start exposed to stationary mechs at `distances` (bearings `spread` deg apart), with a
    walkable spot hidden from all of them within 10-30 m."""
    for index in range(0, len(GRID.free), 7):
        if not GRID.free[index]:
            continue
        i, j = index % GRID.width, index // GRID.width
        if not (15 <= i < GRID.width - 15 and 15 <= j < GRID.height - 15):
            continue
        origin = GRID.point(index)
        for bearing in range(0, 360, 20):
            ms = []
            for n, d in enumerate(distances):
                m = point(origin, bearing + n * spread, d)
                if not dt.walkable(m) or not sees(m, origin):
                    break
                ms.append(m)
            if len(ms) != len(distances):
                continue
            hidden = []
            for r in (10, 14, 18, 24, 30):
                for k in range(16):
                    q = point(origin, k * 22.5, r)
                    if GRID.clear_segment(origin, q) and all(hidden_from(q, m) for m in ms):
                        hidden.append(q)
            if len(hidden) >= 2:
                return origin, ms, bearing
    raise RuntimeError("no cover spot")


def fight_spots():
    """Starts for the closed-loop fights: the open lawn and two places among buildings, each with
    walkable hunter starts 170-200 m away."""
    spots = []
    candidates = [tuple(et.HOME)]
    for index in range(0, len(GRID.free), 97):
        if GRID.free[index]:
            i, j = index % GRID.width, index // GRID.width
            if 60 <= i < GRID.width - 60 and 50 <= j < GRID.height - 50:
                candidates.append(GRID.point(index))
    for origin in candidates:
        starts = []
        for bearing in range(0, 360, 10):
            for d in (200, 190, 180):
                p = point(origin, bearing, d)
                if dt.walkable(p):
                    starts.append((bearing, p))
                    break
        if len(starts) < 6:
            continue
        near_cover = sum(1 for k in range(16) for r in (10, 20)
                         if GRID.clear_segment(origin, point(origin, k * 22.5, r))
                         and not et.clear_from(origin, k * 22.5, r + 40))
        if spots and near_cover < 4:
            continue
        spots.append((origin, starts))
        if len(spots) == 3:
            break
    return spots


# --- scenario helpers -------------------------------------------------------------------------

def pair(folder, label, results, *args, **kwargs):
    base = run(folder, *copy.deepcopy(args), **copy.deepcopy(kwargs))
    cand = run(ROOT, *copy.deepcopy(args), **copy.deepcopy(kwargs))
    results.append(label)
    return base, cand


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def modes(r):
    out = {}
    for row in r["rows"]:
        out[row["mode"]] = out.get(row["mode"], 0) + 1
    return out


def fresh(spec):
    return [dict(h) for h in spec]


CHECKS = []


def check(name, ok, text):
    CHECKS.append((name, ok))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: {text}")


def scenarios(folder):
    labels = []
    origin, bearing = open_line()
    print(f"open line from ({origin[0]:.0f}, {origin[1]:.0f}) toward {bearing} deg")

    # 1. range held: laser 120 m, gun-only 85 m (the foe stands, aims at us, takes no damage)
    for name, laser, start_d, want in (("gun only, foe from 160 m", False, 160, 85.0),
                                       ("gun only, foe from 50 m", False, 50, 85.0),
                                       ("laser, foe from 60 m", True, 60, 120.0),
                                       ("laser, foe from 170 m", True, 170, 120.0)):
        foe = point(origin, bearing, start_d)
        spec = [hunter(5, foe, mode="hold", shoots=False, listed=True)]
        b, c = pair(folder, name, labels, origin, fresh(spec), seconds=20.0, laser=laser, damage_hunters=False)
        tail = lambda r: mean(row["dist"][0] for row in r["rows"] if row["t"] >= T0 + 12)
        ok = abs(tail(c) - want) <= 15
        check(f"holds range, {name}", ok, f"mean distance over the last 8 s: base {tail(b):.0f} m, cand {tail(c):.0f} m"
              f" (want {want:.0f} +-15); cand modes {modes(c)}")

    # 2. a spot with a line of fire
    o2, foe2, good = fire_spot()
    spec = [hunter(5, foe2, mode="hold", shoots=False, listed=True)]
    b, c = pair(folder, "line of fire", labels, o2, fresh(spec), seconds=0.1, move_us=False, damage_hunters=False)
    mv = c["rows"][0]["move"]
    target = (o2[0] + 6 * mv[0], o2[1] + 6 * mv[1])
    ok = math.hypot(*mv) > 0.9 and shot_clear(target, foe2) and not shot_clear(o2, foe2)
    check("prefers a spot with a line of fire", ok,
          f"from ({o2[0]:.0f}, {o2[1]:.0f}) foe {math.dist(o2, foe2):.0f} m behind cover, {len(good)} ring points"
          f" have a line; cand moves {[round(v, 2) for v in mv]} -> line {shot_clear(target, foe2)};"
          f" base moves {[round(v, 2) for v in b['rows'][0]['move']]}")

    # 3. a spot a second enemy cannot see
    o3, foe3, second, unseen = watcher_spot()
    spec = [hunter(5, foe3, mode="hold", shoots=False, listed=True),
            hunter(6, second, mode="hold", shoots=False, listed=True, aim_off=math.pi / 2)]
    b, c = pair(folder, "second watcher", labels, o3, fresh(spec), seconds=0.1, move_us=False, damage_hunters=False)
    mv = c["rows"][0]["move"]
    target = (o3[0] + 6 * mv[0], o3[1] + 6 * mv[1]) if math.hypot(*mv) > 0.5 else o3
    unseen_now = not COVER.clear(eye(second), body(target, 0.6), skip_start=1.0, skip_end=1.0)
    ok = unseen_now and shot_clear(target, foe3) and c["rows"][0]["mode"] == "fight"
    check("avoids a spot a second enemy can see", ok,
          f"foe 80 m, second {math.dist(o3, second):.0f} m sees us now; {len(unseen)} ring points hidden from it;"
          f" cand moves {[round(v, 2) for v in mv]} -> hidden from second {unseen_now}, line to foe {shot_clear(target, foe3)}")

    # 4. strafe: lateral steps that flip side; the same run twice is identical
    foe = point(origin, bearing, 85)
    spec = [hunter(5, foe, mode="hold", shoots=False, listed=True)]
    b, c = pair(folder, "strafe", labels, origin, fresh(spec), seconds=10.0, damage_hunters=False)
    c2 = run(ROOT, origin, fresh(spec), seconds=10.0, damage_hunters=False)
    lateral, flips, last = [], 0, None
    for row in c["rows"]:
        if row["mode"] != "fight" or math.hypot(*row["move"]) < 0.5:
            continue
        fx, fy = foe
        bx, by = fx - row["pos"][0], fy - row["pos"][1]
        L = math.hypot(bx, by)
        along = (row["move"][0] * bx + row["move"][1] * by) / L
        side = row["move"][0] * -by / L + row["move"][1] * bx / L
        lateral.append(abs(along))
        sign = 1 if side > 0 else -1
        if last is not None and sign != last:
            flips += 1
        last = sign
    same = [r["action"] for r in c["rows"]] == [r["action"] for r in c2["rows"]]
    ok = lateral and mean(lateral) < 0.5 and flips >= 2 and same
    check("strafes", ok, f"mean |move . bearing| {mean(lateral):.2f} over {len(lateral)} fight steps, {flips} side flips"
          f" in 10 s, repeat run identical {same}")

    # 5. mid-fight cube grab within 40 m (and not beyond 22.8 m at half HP)
    foe = point(origin, bearing, 90)
    cube = point(origin, bearing + 180, 25)
    spec = [hunter(5, foe, mode="hold", shoots=False, listed=True)]
    b, c = pair(folder, "cube grab", labels, origin, fresh(spec), seconds=6.0, cubes=[cube], damage_hunters=False)
    ok = c["collected"] == 1 and modes(c).get("grab", 0) > 0 and b["collected"] == 0
    check("grabs a cube 25 m away mid-fight", ok, f"collected base {b['collected']}, cand {c['collected']};"
          f" cand modes {modes(c)}")
    cube = point(origin, bearing + 180, 30)
    b, c = pair(folder, "no grab hurt", labels, origin, fresh(spec), seconds=4.0, cubes=[cube], hp0=600.0,
                damage_hunters=False)
    early = [row["mode"] for row in c["rows"] if math.dist(row["pos"], cube) > 22.8 + 1.2]
    grab_at = [round(math.dist(row["pos"], cube), 1) for row in c["rows"] if row["mode"] == "grab"]
    ok = early and all(m == "fight" for m in early) and all(d <= 22.8 + 1.2 for d in grab_at)
    check("at 43% HP a cube 30 m away only pulls until it is within 22.8 m", ok,
          f"{len(early)} fight decisions beyond 22.8 m, grabs from {max(grab_at, default='-')} m;"
          f" collected base {b['collected']}, cand {c['collected']}")

    # 6. finish mode closes to 20 m
    foe = point(origin, bearing, 60)
    spec = [hunter(5, foe, mode="hold", shoots=False, listed=True, hp=420)]
    b, c = pair(folder, "finish", labels, origin, fresh(spec), seconds=10.0, damage_hunters=False)
    closest = lambda r: min(row["dist"][0] for row in r["rows"])
    tail = lambda r: mean(row["dist"][0] for row in r["rows"] if row["t"] >= T0 + 7)
    ok = closest(c) <= 26 and tail(c) <= 30
    check("finish mode closes to 20 m (foe at 30% HP)", ok, f"closest base {closest(b):.0f} m, cand {closest(c):.0f} m;"
          f" mean over the last 3 s base {tail(b):.0f}, cand {tail(c):.0f}")

    # 7. LoseRule pulse: two mechs listed while we are at 50% HP, the second leaves at t0+1.0
    o7, ms, cb = cover_spot()
    spec = [hunter(5, ms[0], mode="hold", shoots=False, listed=True),
            hunter(6, ms[1], mode="hold", shoots=False, listed=True, aim_off=math.pi / 2, leave_at=T0 + 1.0)]
    b, c = pair(folder, "lose pulse", labels, o7, fresh(spec), seconds=4.0, hp0=700.0, damage_hunters=False)
    retreating = [row["t"] for row in c["rows"] if row["mode"] in ("cover", "cornered", "flee")]
    fighting = [row["t"] for row in c["rows"] if row["mode"] == "fight"]
    last_losing = T0 + 0.9
    want_end = round(last_losing + 1.4, 1)
    ok = (retreating and min(retreating) == T0 and round(max(retreating), 1) == want_end
          and fighting and round(min(fighting), 1) == round(want_end + 0.1, 1)
          and len(retreating) == round((want_end - T0) / 0.1) + 1)
    check("LoseRule pulse lasts 1.5 s after the last losing decision", ok,
          f"last losing t={last_losing:.1f}; retreat decisions t={min(retreating, default=0):.1f}..{max(retreating, default=0):.1f}"
          f" ({len(retreating)}), fight from t={min(fighting, default=0):.1f}")
    # finishing and late cancel the retreat movement (three mechs keep `losing` set)
    three = [hunter(5, ms[0], mode="hold", shoots=False, listed=True),
             hunter(6, ms[1], mode="hold", shoots=False, listed=True, aim_off=math.pi / 2),
             hunter(7, point(o7, cb + 180, 140), mode="hold", shoots=False, listed=True, aim_off=math.pi / 2)]
    if not dt.walkable(three[2]["pos"]):
        three[2]["pos"] = list(point(o7, cb + 70, 140))
    variants = (("finishing (target 150 HP, 3 mechs near)", dict(hp=150), {}, None),
                ("late (next radius 60)", {}, dict(next_radius=60.0), None),
                ("late (alive 3)", {}, {}, 3))
    for vname, target_change, zone_change, alive in variants:
        spec = fresh(three)
        spec[0].update(target_change)
        zone = dict(center=list(o7), radius=400.0, next_center=list(o7), next_radius=250.0, shrink_start=1000.0,
                    shrink_end=1050.0, dps=20)
        zone.update(zone_change)
        b, c = pair(folder, vname, labels, o7, spec, seconds=2.0, hp0=700.0, damage_hunters=False, zone=zone,
                    alive=alive)
        m = modes(c)
        ok = m.get("fight", 0) == len(c["rows"]) and not any(k in m for k in ("cover", "cornered", "flee"))
        check(f"{vname} cancels the retreat movement", ok, f"cand modes {m}")
    # control: the same three mechs without finishing or late -> retreat movement
    b, c = pair(folder, "three mechs, retreat", labels, o7, fresh(three), seconds=2.0, hp0=700.0, damage_hunters=False)
    m = modes(c)
    ok = m.get("fight", 0) == 0 and sum(m.get(k, 0) for k in ("cover", "cornered", "flee")) == len(c["rows"])
    check("three mechs at 50% HP without finishing or late retreat (control)", ok, f"cand modes {m}")

    # 8. cover search near a building: two stationary mechs, our HP 50%
    spec = [hunter(5, ms[0], mode="hold", shoots=False, listed=True),
            hunter(6, ms[1], mode="hold", shoots=False, listed=True, aim_off=math.pi / 2)]
    b, c = pair(folder, "cover search", labels, o7, fresh(spec), seconds=8.0, hp0=700.0, damage_hunters=False)
    end_c, end_b = c["end"], b["end"]
    hid_c = all(hidden_from(end_c, m) for m in ms)
    hid_b = all(hidden_from(end_b, m) for m in ms)
    first_hidden = next((row["t"] - T0 for row in c["rows"] if all(hidden_from(row["pos"], m) for m in ms)), None)
    ok = hid_c and modes(c).get("cover", 0) > 0
    check("cover search finds a hidden cell near a building", ok,
          f"start ({o7[0]:.0f}, {o7[1]:.0f}) seen by mechs at {', '.join(f'{math.dist(o7, m):.0f}' for m in ms)} m;"
          f" after 8 s cand at {math.dist(o7, end_c):.0f} m from start, hidden {hid_c}"
          f" (first hidden after {first_hidden if first_hidden is None else round(first_hidden, 1)} s); base hidden {hid_b};"
          f" cand modes {modes(c)}")

    # 9. laser sidestep (our gun reloading, so no strafe of its own)
    foe = point(origin, bearing, 100)
    reloading = dict(ammo=0, reload=2.0)
    for name, charging, off, want in (("charging at us", True, 0.0, True), ("not charging", False, 0.0, False),
                                      ("charging 0.3 rad off us", True, 0.3, False)):
        spec = [hunter(5, foe, mode="hold", shoots=False, listed=True, charging=charging, aim_off=off,
                       weapons=["gun", "laser"])]
        b, c = pair(folder, name, labels, origin, spec, seconds=0.1, move_us=False, damage_hunters=False,
                    gun_state=reloading)
        row = c["rows"][0]
        bx, by = foe[0] - origin[0], foe[1] - origin[1]
        L = math.hypot(bx, by)
        side = abs(row["move"][0] * -by / L + row["move"][1] * bx / L)
        stepped = "sidestep" in (row["mode"] or "")
        ok = stepped == want and (not want or (side >= 0.6 and row["boost"]))
        check(f"laser sidestep, mech {name}", ok, f"cand mode {row['mode']}, move {[round(v, 2) for v in row['move']]}"
              f" (sideways {side:.2f}), boost {row['boost']}; base move {[round(v, 2) for v in b['rows'][0]['move']]},"
              f" boost {b['rows'][0]['boost']}")

    # 10. identity with the baseline
    spots = fight_spots()
    o10, starts = spots[0]
    # hunters that walk in and aim at us without shooting, so every run lasts its full length
    two = [hunter(5, starts[0][1], mode="hunt", shoots=False), hunter(6, starts[len(starts) // 3][1], mode="hunt", shoots=False)]
    for name, kwargs in (("before 20 s (t 5-19 s, two hunters)", dict(t0=5.0, seconds=14.0)),
                         ("outside death at 16 s (t 15-45 s, two hunters)", dict(t0=15.0, seconds=30.0,
                                                                                outside_death_at=16.0))):
        b, c = pair(folder, name, labels, o10, fresh(two), seed=77, **kwargs)
        n = min(len(b["rows"]), len(c["rows"]))
        same = [r["action"] for r in b["rows"]] == [r["action"] for r in c["rows"]]
        check(f"identical to the baseline {name}", same and n > 0,
              f"{n} decisions compared, all identical {same}; cand modes {modes(c)}")
    b, c = pair(folder, "active control", labels, o10, fresh(two), seed=77, seconds=14.0)
    differ = sum(rb["action"] != rc["action"] for rb, rc in zip(b["rows"], c["rows"]))
    check("the same hunters from t = 30 s are fought (control)", modes(c).get("fight", 0) > 0 and differ > 0,
          f"{differ} of {len(c['rows'])} decisions differ; cand modes {modes(c)}")
    # urgent zone return with a hunter shooting (practice on): identical
    far = point(o10, 0, 300)
    zone = dict(center=list(far), radius=150.0, next_center=list(far), next_radius=100.0, shrink_start=1000.0,
                shrink_end=1050.0, dps=20)
    b, c = pair(folder, "urgent", labels, o10, fresh(two), seconds=8.0, zone=zone, seed=78)
    same = [r["action"] for r in b["rows"]] == [r["action"] for r in c["rows"]]
    check("identical to the baseline on an urgent zone return (t 30-38 s, two hunters)", same,
          f"{len(c['rows'])} decisions, cand modes {modes(c)}")
    # our own kill keeps practice on
    one = [hunter(5, point(origin, bearing, 70), mode="hold", hp=200, shoots=False, listed=True),
           hunter(6, point(origin, bearing + 20, 150), mode="hold", shoots=False, listed=True, aim_off=math.pi / 2)]
    b, c = pair(folder, "own kill", labels, origin, fresh(one), seconds=6.0, seed=79)
    after = [row["mode"] for row in c["rows"] if c["kill_times"] and row["t"] - T0 > c["kill_times"][0] + 0.6]
    ok = c["kills"] == 1 and any(m is not None for m in after)
    check("our own kill keeps practice mode on", ok, f"kills base {b['kills']}, cand {c['kills']};"
          f" cand modes after the kill {sorted(set(map(str, after)))}")
    return spots


def fights(folder, spots, seconds=60.0):
    print(f"\nclosed-loop fights, {seconds:.0f} s from t = {T0:.0f} s; our gun only, hunters 1400 HP walking in")
    print(f"{'fight':44}{'damage taken':>16}{'kills':>9}{'first kill s':>16}{'died at s':>14}{'HP left':>14}")
    print(f"{'':44}{'base | cand':>16}{'b | c':>9}{'base | cand':>16}{'base | cand':>14}{'base | cand':>14}")
    totals = {"base": [0, 0, 0, 0.0], "cand": [0, 0, 0, 0.0]}
    rows = []
    cases = []
    for n, (origin, starts) in enumerate(spots):
        s0, s1 = starts[0][1], starts[min(len(starts) - 1, 4)][1]
        cases.append((f"spot {n + 1}: 1 gun hunter from {math.dist(origin, s0):.0f} m", origin,
                      [hunter(5, s0, mode="hunt", standoff=60.0)]))
        cases.append((f"spot {n + 1}: 2 gun hunters", origin,
                      [hunter(5, s0, mode="hunt", standoff=60.0), hunter(6, s1, mode="hunt", standoff=70.0)]))
        cases.append((f"spot {n + 1}: 1 lightning hunter", origin,
                      [hunter(5, s0, weapon="lightning", mode="hunt", standoff=15.0, weapons=["gun", "lightning"])]))
    for k, (name, origin, spec) in enumerate(cases):
        b, c = pair(folder, name, [], origin, fresh(spec), seconds=seconds, seed=300 + k)
        fk = lambda r: "-" if not r["kill_times"] else f"{r['kill_times'][0]:.1f}"
        dd = lambda r: "-" if r["died"] is None else f"{r['died']:.1f}"
        print(f"{name:44}{b['taken']:>7} | {c['taken']:<6}{b['kills']:>4} | {c['kills']:<3}{fk(b):>7} | {fk(c):<6}"
              f"{dd(b):>6} | {dd(c):<6}{b['hp']:>6} | {c['hp']:<6}  cand modes {modes(c)}")
        for tag, r in (("base", b), ("cand", c)):
            totals[tag][0] += r["taken"]
            totals[tag][1] += r["kills"]
            totals[tag][2] += r["died"] is not None
            totals[tag][3] += r["kill_times"][0] if r["kill_times"] else seconds
        rows.append((name, b, c))
    tb, tc = totals["base"], totals["cand"]
    print(f"{'total (first kill: mean, no kill = ' + str(int(seconds)) + ' s)':44}{tb[0]:>7} | {tc[0]:<6}{tb[1]:>4} | {tc[1]:<3}"
          f"{tb[3] / len(cases):>7.1f} | {tc[3] / len(cases):<6.1f}{tb[2]:>6} | {tc[2]:<6}  (deaths)")
    return rows


def fuzz(n=1500, seed=11):
    """Random observations straight into the candidate (in process): no exception may escape and
    squad.py must not swallow any."""
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = mf.draw.text = lambda *args, **kw: None
    from bot import Bot
    rng = random.Random(seed)
    free = [i for i in range(len(GRID.free)) if GRID.free[i]]
    bot = Bot(et.HELLO)
    worst, failures = 0.0, 0
    weapons_pool = ["gun", "laser", "lightning", "mortar"]
    t = 20.0
    for k in range(n):
        if k % 300 == 0:
            bot = Bot(et.HELLO)
            t = 20.0
        t = round(t + 0.1, 2)
        p = GRID.point(rng.choice(free)) if rng.random() < 0.8 else (rng.uniform(-600, 600), rng.uniform(-400, 400))
        mechs = []
        for m in range(rng.randrange(0, 7)):
            q = (p[0] + rng.uniform(-250, 250), p[1] + rng.uniform(-250, 250))
            mechs.append(dict(id=rng.choice([m, m + 100]) if rng.random() < 0.9 else m,
                              kind="mech" if rng.random() < 0.85 else "npc",
                              pos=[q[0], q[1], safe_ground(*q) + rng.choice([0, 0, 0, 12])],
                              vel=[rng.uniform(-12, 12), rng.uniform(-12, 12), 0.0],
                              aim=[rng.uniform(-4, 4), rng.uniform(-0.5, 0.5)], hp=rng.choice([0, 1, 150, 600, 1400]),
                              max_hp=rng.choice([1400, 1456, 1]), cubes=rng.randrange(0, 12),
                              weapons=rng.sample(weapons_pool, rng.randrange(0, 3)), charging=rng.random() < 0.3))
        obs = et.frame(k, mechs, [], origin=[0.0, 0.0], hp=rng.choice([1, 300, 700, 1000, 1400]))
        obs["self"]["pos"] = [p[0], p[1], safe_ground(*p)]
        obs["t"] = t
        obs["tick"] = k
        obs["alive"] = 16 if rng.random() < 0.95 else rng.randrange(1, 17)
        ws = [et.gun(), None]
        r = rng.random()
        if r < 0.3:
            ws[1] = et.laser(rng.choice([0, 0.3, 0.75]))
        elif r < 0.5:
            ws[1] = dict(kind="lightning", cooldown=0.0, stats=copy.deepcopy(LIGHTNING))
        ws[0]["ammo"] = rng.randrange(0, 13)
        ws[0]["reload"] = rng.choice([0, 0, 0.2, 1.5])
        obs["self"].update(weapons=ws, energy=rng.uniform(0, 100), vel=[rng.uniform(-12, 12), rng.uniform(-12, 12), 0.0])
        obs["self"]["pos"][2] += rng.choice([0, 0, 0, 5, 20])
        obs["cubes"] = [dict(id=5000 + c, pos=[p[0] + rng.uniform(-60, 60), p[1] + rng.uniform(-60, 60), obs["self"]["pos"][2]
                                               + rng.uniform(-6, 6)]) for c in range(rng.randrange(0, 4))]
        zr = rng.choice([400, 140, 60, 20, 5])
        obs["zone"].update(center=[p[0] + rng.uniform(-50, 50), p[1] + rng.uniform(-50, 50)], radius=zr * 1.3,
                           next_center=[p[0] + rng.uniform(-80, 80), p[1] + rng.uniform(-80, 80)], next_radius=zr,
                           shrink_start=t + rng.uniform(-20, 40), shrink_end=t + 60)
        obs["self"]["in_zone"] = math.dist(p, obs["zone"]["center"]) <= obs["zone"]["radius"]
        if rng.random() < 0.1:
            obs["events"] = [dict(type="kill", target=rng.randrange(0, 16))]
        try:
            started = time.perf_counter()
            bot.act(obs)
            worst = max(worst, time.perf_counter() - started)
        except Exception:
            failures += 1
        failures += bot.squad.errors
        bot.squad.errors = 0
    return failures, worst


def recording(folder):
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = 0
    for o in et.STREAM:
        a, c = plain(base_bot.act(copy.deepcopy(o))), plain(cand_bot.act(copy.deepcopy(o)))
        differ += a != c
    times = list(cand_bot.times)
    base_bot.close()
    cand_bot.close()
    return differ, times


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    print("scripted scenarios (t from 30 s, practice mode on unless stated)")
    spots = scenarios(folder)
    if "--skip-fights" not in sys.argv:
        fights(folder, spots)
    differ, rec_times = recording(folder)
    ok = differ == 0
    print(f"\nrecording ({len(et.STREAM)} decisions, an outside death at 18 s switches practice off):"
          f" {differ} differ from the baseline")
    CHECKS.append(("recording identical", ok))
    failures, worst = fuzz()
    print(f"fuzz: 1500 random observations in process, {failures} exceptions; slowest decision {worst * 1e3:.1f} ms")
    CHECKS.append(("fuzz", failures == 0))
    times = sorted(TIMES + rec_times)
    if times:
        p50, p99 = times[len(times) // 2] * 1e3, times[int(0.99 * len(times))] * 1e3
        print(f"candidate round trip over {len(times)} decisions: p50 {p50:.1f} ms, p99 {p99:.1f} ms,"
              f" max {times[-1] * 1e3:.1f} ms (this machine)")
    failed = [name for name, ok in CHECKS if not ok]
    if failed:
        print("\nFAIL:", "; ".join(failed))
        sys.exit(1)
    print("\nPASS (fight damage, kills and times are measurements from the simplified world)")


if __name__ == "__main__":
    main()
