"""vision-scan: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/vision_trial.py [--baseline <git revision>]

A closed-loop walk with simulated vision. Our mech walks from an open lawn toward a zone
centre 300 m away (the world moves it along its `move` command at walk speed, its torso slews
toward the commanded aim at the configured turn rate). One opponent stands 60-180 m away,
50-110 deg off our walking heading, aiming at us. It is listed only as the rules of §8 say:
within near_range (45 m) in any direction, or within vision range (200 m) inside the 120 deg
yaw wedge centred on our actual torso yaw, with a clear line by the cover raster; once seen it
stays listed with its real position for memory_s (5 s).

Two variants per placement:
  quiet    it has not noticed us yet and does not shoot;
  hunting  it shoots us from t=0.5 s (252 m/s bullets, 0.24 s, 12-round magazine, 2.4 s
           reload, 0.6 deg spread, led on our motion). Hits arrive as `damaged` events with the
           shooter's bearing and `rear` when outside our front arc (x1.5 damage).
Our gun works as in tools/lead_trial.py. Measured: when the opponent is first in view, our
first shot, our hits, the damage we take and how much of it came from behind. Bullets are not
listed as projectiles, so the v8 dodge stays out of it (it is unchanged by this candidate).

Controls: the opponent straight ahead, an opponent already listed from memory, and a pickup
detour; all must answer identically. Also the standard recording: only aim may differ.
Standard library only.
"""
import copy
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
SECONDS = 8.0
HOME = list(et.HOME)
NAV = Navigator()


def ground(x, y):
    return et.ground(x, y)


def at(origin, bearing_deg, distance):
    a = math.radians(bearing_deg)
    return [origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)]


def heading_ok(b):
    """A walking heading with a straight, walkable 120 m route."""
    end = at(HOME, b, 120)
    return NAV.clear_segment([HOME[0], HOME[1], ground(*HOME)], [end[0], end[1], ground(*end)])


HEADING = next(b for b in range(0, 360, 5) if heading_ok(b))


def sees(eye, other):
    centre = [other[0], other[1], ground(other[0], other[1]) + MECH["height"] / 2]
    top = [other[0], other[1], ground(other[0], other[1]) + MECH["height"]]
    return et.COVER.clear(eye, centre) or et.COVER.clear(eye, top)


def in_view(me, yaw, other):
    eye = [me[0], me[1], ground(*me) + MECH["eye_height"]]
    distance = math.dist(me[:2], other[:2])
    if distance <= VISION["near_range"]:
        return sees(eye, other)
    if distance > VISION["range"]:
        return False
    bearing = math.atan2(other[1] - me[1], other[0] - me[0])
    off = abs((bearing - yaw + math.pi) % math.tau - math.pi)
    return off <= math.radians(VISION["fov_deg"] / 2) and sees(eye, other)


def body_hit(origin, direction, length, target_pos):
    tx, ty, tz = target_pos
    dx, dy, dz = direction
    flat2 = dx * dx + dy * dy
    s = max(0.0, min(length, ((tx - origin[0]) * dx + (ty - origin[1]) * dy) / flat2))
    px, py, pz = origin[0] + s * dx, origin[1] + s * dy, origin[2] + s * dz
    return math.hypot(px - tx, py - ty) <= MECH["radius"] + BULLET_R and tz <= pz <= tz + MECH["height"]


def lead_yaw(origin, target, vel, speed):
    rx, ry = target[0] - origin[0], target[1] - origin[1]
    a = vel[0] ** 2 + vel[1] ** 2 - speed * speed
    b = 2 * (rx * vel[0] + ry * vel[1])
    c = rx * rx + ry * ry
    disc = b * b - 4 * a * c
    if disc < 0 or abs(a) < 1e-9:
        return math.atan2(ry, rx)
    t = max((-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a))
    return math.atan2(ry + vel[1] * t, rx + vel[0] * t)


class Gun:
    def __init__(self):
        self.ammo, self.cooldown, self.reload = GUN["mag"], 0.0, 0.0

    def step(self, trigger):
        """Advance DT; True when a round leaves the barrel this step."""
        self.cooldown = max(0.0, self.cooldown - DT)
        if self.reload > 0:
            self.reload = max(0.0, self.reload - DT)
            if self.reload == 0:
                self.ammo = GUN["mag"]
            return False
        if trigger and self.cooldown == 0 and self.ammo > 0:
            self.ammo -= 1
            self.cooldown = GUN["cooldown"]
            if self.ammo == 0:
                self.reload = GUN["reload"]
            return True
        return False


def walk(folder, opponent_at=None, hunting=False, remembered=False, pickup=None, seconds=SECONDS, seed=1):
    """Run one closed-loop walk; returns the measurements and the per-decision actions."""
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    goal = at(HOME, HEADING, 300)
    me = [HOME[0], HOME[1]]
    yaw = math.radians(HEADING)
    commanded = [yaw, 0.0]
    move = [0.0, 0.0]
    fire = False
    ours, theirs = Gun(), Gun()
    bullets, incoming = [], []
    last_seen = -1e9 if not remembered else -0.1
    first_seen = first_shot = None
    shots = hits = taken = rear = scans = 0
    hp, events, actions = 1400.0, [], []
    for tick in range(int(seconds / DT)):
        t = round(tick * DT, 2)
        my_pos = [me[0], me[1], ground(*me)]
        opp_pos = [opponent_at[0], opponent_at[1], ground(*opponent_at)] if opponent_at else None
        if opp_pos and in_view(me, yaw, opp_pos):
            if first_seen is None:
                first_seen = t
            last_seen = t
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [], events)
            obs["t"] = t
            obs["self"].update(pos=my_pos, vel=[move[0] * MECH["walk_speed"], move[1] * MECH["walk_speed"], 0.0],
                               aim=[yaw, 0.0], hp=round(hp))
            obs["self"]["weapons"][0].update(ammo=ours.ammo, cooldown=round(ours.cooldown, 2), reload=round(ours.reload, 2))
            obs["zone"].update(center=list(HOME), radius=600, next_center=goal, next_radius=20,
                               shrink_start=400, shrink_end=450)
            if opp_pos and t - last_seen <= VISION["memory_s"]:
                toward_us = math.atan2(me[1] - opp_pos[1], me[0] - opp_pos[0])
                obs["mechs"] = [dict(id=5, kind="mech", pos=[round(v, 2) for v in opp_pos], vel=[0.0, 0.0, 0.0],
                                     aim=[toward_us, 0.0], hp=1400, max_hp=1400, cubes=0, weapons=["gun"],
                                     charging=False)]
            if pickup:
                obs["pickups"] = [dict(id=8001, kind="laser", pos=[pickup[0], pickup[1], ground(*pickup)])]
            events = []
            action = bot.act(obs)
            actions.append(plain(action))
            move = list(action.get("move") or [0.0, 0.0])
            commanded = list(action.get("aim") or commanded)
            fire = bool((action.get("fire") or [False])[0])
            if action.get("reload") and ours.reload == 0 and ours.ammo < GUN["mag"]:
                ours.reload = GUN["reload"]
        # legs and torso
        speed = MECH["walk_speed"] * min(1.0, math.hypot(*move))
        norm = math.hypot(*move) or 1.0
        me = [me[0] + move[0] / norm * speed * DT, me[1] + move[1] / norm * speed * DT]
        turn = (commanded[0] - yaw + math.pi) % math.tau - math.pi
        yaw += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        my_pos = [me[0], me[1], ground(*me)]
        # our gun
        if ours.step(fire):
            d_yaw = yaw + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = commanded[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(d_yaw), math.cos(pitch) * math.sin(d_yaw), math.sin(pitch))
            origin = [me[0] + 3 * d[0], me[1] + 3 * d[1], my_pos[2] + MECH["muzzle_height"] + 3 * d[2]]
            bullets.append([origin, d, 3.0])
            shots += 1
            first_shot = t if first_shot is None else first_shot
        # its gun
        if opp_pos and hunting and t >= 0.5:
            vel = (move[0] / norm * speed, move[1] / norm * speed)
            if theirs.step(True):
                yaw_in = lead_yaw(opp_pos, my_pos, vel, GUN["speed"]) + math.radians(rng.gauss(0, GUN["spread_deg"]))
                flat = math.dist(opp_pos[:2], my_pos[:2])
                pitch = math.atan2(my_pos[2] + 4.5 - opp_pos[2] - MECH["muzzle_height"], flat) + math.radians(rng.gauss(0, GUN["spread_deg"]))
                d = (math.cos(pitch) * math.cos(yaw_in), math.cos(pitch) * math.sin(yaw_in), math.sin(pitch))
                origin = [opp_pos[0] + 3 * d[0], opp_pos[1] + 3 * d[1], opp_pos[2] + MECH["muzzle_height"] + 3 * d[2]]
                incoming.append([origin, d, 3.0])
        step = GUN["speed"] * DT
        alive = []
        for b in bullets:
            if opp_pos and body_hit(b[0], b[1], step, opp_pos):
                hits += 1
                continue
            b[0] = [b[0][i] + b[1][i] * step for i in range(3)]
            b[2] += step
            if b[2] <= GUN["range"]:
                alive.append(b)
        bullets = alive
        alive = []
        for b in incoming:
            if body_hit(b[0], b[1], step, my_pos):
                bearing = math.atan2(opp_pos[1] - me[1], opp_pos[0] - me[0])
                behind = abs((bearing - yaw + math.pi) % math.tau - math.pi) > math.radians(MECH["front_arc_deg"] / 2)
                amount = GUN["damage"] * (MECH["rear_mult"] if behind else 1.0)
                hp -= amount
                taken += amount
                rear += amount if behind else 0
                events.append(dict(type="damaged", amount=amount, weapon="gun", bearing=bearing, by=5, rear=behind))
                continue
            b[0] = [b[0][i] + b[1][i] * step for i in range(3)]
            b[2] += step
            if b[2] <= GUN["range"]:
                alive.append(b)
        incoming = alive
    bot.close()
    return dict(seen=first_seen, shot=first_shot, shots=shots, hits=hits, taken=taken, rear=rear), actions


def placements():
    """(name, opponent position) for every placement whose spot is open ground."""
    found = []
    for off in (50, 70, 90, 110):
        for side in (1, -1):
            for distance in (60, 120, 180):
                spot = at(HOME, HEADING + side * off, distance)
                if NAV.snap([spot[0], spot[1], ground(*spot)]) is None:
                    continue
                found.append((f"{distance:3d} m, {off:3d} deg {'left' if side > 0 else 'right'}", spot))
    return found


def fmt(value):
    return "-" if value is None else f"{value:.1f}"


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`;"
          f" walking heading {HEADING} deg from {HOME}, {SECONDS:.0f} s per walk\n")
    failures = []
    totals = {}
    for variant in ("quiet", "hunting"):
        print(f"{variant}: {'opponent':24}{'first in view s':>18}{'first shot s':>16}{'hits':>10}"
              f"{'dmg taken':>14}{'from behind':>14}")
        print(f"{'':33}{'base | scan':>18}{'base | scan':>16}{'base | scan':>10}{'base | scan':>14}{'base | scan':>14}")
        tot = dict(base_seen=0, cand_seen=0, base_hits=0, cand_hits=0, base_taken=0, cand_taken=0,
                   base_rear=0, cand_rear=0, earlier=0, later=0, cases=0)
        for k, (name, spot) in enumerate(placements()):
            base, _ = walk(folder, spot, hunting=variant == "hunting", seed=500 + k)
            cand, _ = walk(ROOT, spot, hunting=variant == "hunting", seed=500 + k)
            tot["cases"] += 1
            for key, r in (("base", base), ("cand", cand)):
                tot[f"{key}_seen"] += r["seen"] is not None
                tot[f"{key}_hits"] += r["hits"]
                tot[f"{key}_taken"] += r["taken"]
                tot[f"{key}_rear"] += r["rear"]
            bs, cs = base["seen"], cand["seen"]
            if cs is not None and (bs is None or cs < bs - 1e-9):
                tot["earlier"] += 1
            if bs is not None and (cs is None or cs > bs + 1e-9):
                tot["later"] += 1
            print(f"  {name:31}{fmt(bs):>8} | {fmt(cs):<7}{fmt(base['shot']):>6} | {fmt(cand['shot']):<7}"
                  f"{base['hits']:>4} | {cand['hits']:<4}{base['taken']:>6.0f} | {cand['taken']:<5.0f}"
                  f"{base['rear']:>6.0f} | {cand['rear']:<5.0f}")
        totals[variant] = tot
        print(f"  {'all placements':31}seen in {tot['base_seen']} | {tot['cand_seen']} of {tot['cases']};"
              f" seen earlier by the candidate in {tot['earlier']}, later in {tot['later']};"
              f" hits {tot['base_hits']} | {tot['cand_hits']}; damage taken {tot['base_taken']:.0f} | {tot['cand_taken']:.0f}"
              f" ({tot['base_rear']:.0f} | {tot['cand_rear']:.0f} from behind)\n")
    quiet = totals["quiet"]
    if not (quiet["earlier"] > 0 and quiet["cand_seen"] > quiet["base_seen"]):
        failures.append("quiet walks: the sweep never revealed an opponent the baseline missed")

    # Controls: identical answers on every decision.
    straight = at(HOME, HEADING, 120)
    side = at(HOME, HEADING + 90, 100)
    pickup = at(HOME, HEADING + 60, 30)
    controls = [
        ("opponent straight ahead, 120 m, hunting", dict(opponent_at=straight, hunting=True)),
        ("opponent straight ahead, 120 m, quiet", dict(opponent_at=straight)),
        ("opponent 90 deg off, 100 m, already listed", dict(opponent_at=side, remembered=True)),
        ("pickup detour, laser 30 m away, 3 s", dict(pickup=pickup, seconds=3.0)),
    ]
    print(f"{'control':48}{'decisions':>10}{'differ':>8}  check")
    for name, kwargs in controls:
        (b, ba), (c, ca) = walk(folder, **kwargs), walk(ROOT, **kwargs)
        differ = sum(x != y for x, y in zip(ba, ca))
        ok = differ == 0 and b == c
        print(f"{name:48}{len(ba):>10}{differ:>8}  {'ok  ' if ok else 'FAIL'} identical")
        if not ok:
            failures.append(name)

    # A before/after trace of one quiet walk.
    name, spot = next(p for p in placements() if p[0].startswith("120 m,  90 deg left"))
    _, ba = walk(folder, spot)
    _, ca = walk(ROOT, spot)
    print(f"\ntrace, quiet opponent {name} (yaw relative to the walking heading, deg):")
    print("     t   base aim   scan aim")
    for k in (0, 3, 6, 9, 12, 15, 18, 21, 24, 30):
        rel = lambda a: (math.degrees(a["aim"][0]) - HEADING + 180) % 360 - 180
        print(f"  {k * 0.1:4.1f}   {rel(ba[k]):+7.1f}    {rel(ca[k]):+7.1f}   fire {ba[k].get('fire')} | {ca[k].get('fire')}")

    # The standard recording: only aim may differ.
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    aim_diff = other_diff = 0
    for obs in et.STREAM:
        a, c = plain(base_bot.act(copy.deepcopy(obs))), plain(cand_bot.act(copy.deepcopy(obs)))
        aim_diff += a.get("aim") != c.get("aim")
        other_diff += {k: v for k, v in a.items() if k != "aim"} != {k: v for k, v in c.items() if k != "aim"}
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: {getattr(local, 'scans', 0)} scan decisions of {len(et.STREAM)}"
          f" ({sum(1 for o in et.STREAM if not o['mechs'])} with nothing listed); aim differs on {aim_diff},"
          f" any other command on {other_diff}")
    if other_diff:
        failures.append("recording: a command other than aim changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
