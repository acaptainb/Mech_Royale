"""reload-lull: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/reload_trial.py [--baseline <git revision>]

A closed-loop gunfight in the style of tools/lead_trial.py, at a spot where an opponent who
walks along an arc 100 m away passes behind a building and comes out again. It aims at us
the whole time, so v6 fires whenever the line is clear and holds ("behind cover") while it
is not; it stays listed meanwhile, as memory_s keeps it. The world models the gun: 252 m/s
bullets, one per 0.24 s, 12 rounds, an automatic 2.4 s reload when empty, an early reload
on the bot's `reload` command, 0.6 deg spread from one seeded generator per case, and a hit
only while the line of fire is clear. Reports gun hits in the 4 s after the opponent comes
back into view and the time it is visible while our magazine is empty or reloading.
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
import lead_trial as lt
from harness import BotProcess, export

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10
CONFIG = et.HELLO["config"]
MECH, GUN = CONFIG["mech"], CONFIG["weapons"]["gun"]
DT = 0.05
ORIGIN = tuple(et.COVER_SPOT[0])   # (-417, -326): a building north-east, open either side
RADIUS = 100.0
SPEED = 11.7


def arc(start_deg):
    """The opponent walks counter-clockwise along a 100 m arc round ORIGIN."""
    omega = SPEED / RADIUS

    def at(t):
        a = math.radians(start_deg) + omega * t
        pos = (ORIGIN[0] + RADIUS * math.cos(a), ORIGIN[1] + RADIUS * math.sin(a))
        vel = (-SPEED * math.sin(a), SPEED * math.cos(a))
        return pos, vel
    return at


def opponent(pos, vel):
    toward_us = math.atan2(ORIGIN[1] - pos[1], ORIGIN[0] - pos[0])
    return dict(id=5, kind="mech", pos=[pos[0], pos[1], et.ground(*pos)], vel=[vel[0], vel[1], 0.0],
                aim=[toward_us, 0.0], hp=1400, max_hp=1400, cubes=0, weapons=["gun"], charging=False)


def visible(target, z0):
    t = target["pos"]
    return et.COVER.clear([ORIGIN[0], ORIGIN[1], z0 + MECH["muzzle_height"]], [t[0], t[1], t[2] + 4.5])


def fight(folder, motion, seconds, seed):
    bot = BotProcess(folder, et.HELLO)
    rng = random.Random(seed)
    z0 = et.ground(*ORIGIN)
    gun = copy.deepcopy(et.gun())
    gun.update(ammo=GUN["mag"], cooldown=0.0, reload=0.0)
    aim, commanded, fire = [0.0, 0.0], [0.0, 0.0], [False, False]
    bullets, rows = [], []
    reload_requests = 0
    for tick in range(int(seconds / DT)):
        t = tick * DT
        pos, vel = motion(t)
        target = opponent(pos, vel)
        seen = visible(target, z0)
        if tick == 0:
            aim = [math.atan2(pos[1] - ORIGIN[1], pos[0] - ORIGIN[0]), 0.0]
            commanded = list(aim)
        hit_now = 0
        if tick % 2 == 0:
            obs = et.frame(tick // 2, [target], origin=ORIGIN, weapons=[copy.deepcopy(gun), None])
            obs["t"] = round(t, 2)
            obs["self"]["aim"] = list(aim)
            action = bot.act(obs)
            fire = list(action.get("fire") or [False, False])
            commanded = list(action.get("aim") or commanded)
            if action.get("reload") and gun["reload"] == 0 and gun["ammo"] < GUN["mag"]:
                gun["reload"] = GUN["reload"]
                reload_requests += 1
        turn = (commanded[0] - aim[0] + math.pi) % math.tau - math.pi
        aim[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        aim[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, commanded[1] - aim[1]))
        gun["cooldown"] = max(0.0, gun["cooldown"] - DT)
        if gun["reload"] > 0:
            gun["reload"] = max(0.0, gun["reload"] - DT)
            if gun["reload"] == 0:
                gun["ammo"] = GUN["mag"]
        elif fire[0] and gun["cooldown"] == 0 and gun["ammo"] > 0:
            yaw = aim[0] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            pitch = aim[1] + math.radians(rng.gauss(0, GUN["spread_deg"]))
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            bullets.append(dict(pos=[ORIGIN[0] + 3 * d[0], ORIGIN[1] + 3 * d[1], z0 + MECH["muzzle_height"] + 3 * d[2]],
                                dir=d, travelled=3.0))
            gun["ammo"] -= 1
            gun["cooldown"] = GUN["cooldown"]
            if gun["ammo"] == 0:
                gun["reload"] = GUN["reload"]
        alive = []
        for b in bullets:
            step = GUN["speed"] * DT
            if lt.body_hit(b["pos"], b["dir"], step, target):
                hit_now += seen  # a bullet that reaches a hidden opponent hits the wall instead
                continue
            b["pos"] = [b["pos"][i] + b["dir"][i] * step for i in range(3)]
            b["travelled"] += step
            if b["travelled"] <= GUN["range"]:
                alive.append(b)
        bullets = alive
        rows.append(dict(t=t, seen=seen, hits=hit_now, empty=gun["reload"] > 0 or gun["ammo"] == 0, ammo=gun["ammo"]))
    bot.close()
    return rows, reload_requests


def summarise(rows):
    back = None
    for prev, row in zip(rows, rows[1:]):
        if not prev["seen"] and row["seen"]:
            back = row["t"]
            break
    window = [r for r in rows if back is not None and back <= r["t"] < back + 4.0]
    hidden_ammo = next((r["ammo"] for r in rows if not r["seen"]), None)
    return dict(back=back, hits_after=sum(r["hits"] for r in window),
                empty_seen=round(sum(DT for r in rows if r["seen"] and r["empty"]), 2),
                hits=sum(r["hits"] for r in rows), ammo_at_back=next((r["ammo"] for r in rows if r["t"] == back), None),
                ammo_into_cover=hidden_ammo)


CASES = [
    ("cover break mid-fight (open 2.2 s, hidden 3.4 s)", arc(90), 10.0, "activates"),
    ("continuous fight in the open, no lull", arc(130), 8.0, "identical"),
    ("hidden from the start: full magazine during the lull", arc(106), 9.0, "identical"),
]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`;"
          f" shooter at {ORIGIN}, opponent on a {RADIUS:.0f} m arc at {SPEED} m/s\n")
    print(f"{'case':54}{'hits 4 s after back':>21}{'visible but empty s':>21}{'all hits':>12}{'reloads asked':>15}  check")
    print(f"{'':54}{'base | cand':>21}{'base | cand':>21}{'base | cand':>12}{'base | cand':>15}")
    failures = []
    trace = None
    for k, (name, motion, seconds, expect) in enumerate(CASES):
        (brow, breq), (crow, creq) = fight(folder, motion, seconds, 500 + k), fight(ROOT, motion, seconds, 500 + k)
        b, c = summarise(brow), summarise(crow)
        if expect == "identical":
            ok = brow == crow
            text = "identical to the baseline"
        else:
            ok = c["hits_after"] > b["hits_after"] and c["empty_seen"] < b["empty_seen"] and creq > breq
            text = "reloads in the lull; more hits after it, less visible time empty"
            trace = (b, c)
        back = lambda s: "-" if s["back"] is None else f"{s['back']:.1f}"
        print(f"{name:54}{b['hits_after']:>10} | {c['hits_after']:<8}{b['empty_seen']:>10} | {c['empty_seen']:<8}"
              f"{b['hits']:>5} | {c['hits']:<5}{breq:>7} | {creq:<6}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    if trace:
        b, c = trace
        print(f"\ncover break: rounds left on entering cover base {b['ammo_into_cover']}, cand {c['ammo_into_cover']};"
              f" back in view at t={b['back']} s with base {b['ammo_at_back']} rounds, cand {c['ammo_at_back']} rounds")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    lulls, previous = 0, False
    for obs in et.STREAM:
        action = local.act(copy.deepcopy(obs))
        asked = bool(action.get("reload"))
        lulls += asked and not previous
        previous = asked
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    reload_diff = other_diff = 0
    for obs in et.STREAM:
        a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        reload_diff += bool(a.get("reload")) != bool(c.get("reload"))
        rest = lambda x: {k: v for k, v in x.items() if k not in ("reload", "tick", "debug")}
        other_diff += rest(a) != rest(c)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: the lull rule asked for a reload on {local.lull_reloads} decisions ({lulls} separate lulls);"
          f" reload differs from the baseline on {reload_diff} of {len(et.STREAM)}; any other command differs on {other_diff}")
    print("  (the recording does not react: its ammo never refills, so a real match would see one reload per lull)")
    if other_diff:
        failures.append("recording: a command other than reload changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
