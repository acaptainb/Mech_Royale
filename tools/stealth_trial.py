"""stealth: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/stealth_trial.py [--baseline <git revision>]

Single decisions near a building, with one game mech 90 m away in the open:
- a passive, standing mech: dodge-tuned shoots ("shots land"); stealth holds fire and steps
  out of its sight;
- the same scene with 4 mechs alive, or with the next circle at 25 m (the endgame): identical
  to dodge-tuned;
- the same mech aiming at us and having just hit us: stealth fights back exactly as
  dodge-tuned does (fire, aim and move identical);
- nobody listed: stealth never steers (hide-spot sets the goal, as on its own branch).
Also reports how the candidate answers the standard recording. Standard library only.
"""
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from harness import BotProcess, export, plain

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10


def find_scene():
    """A walkable spot with a mech 90 m away in the open and solid cover within 24 m."""
    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from cover import Cover
    from navigation import Navigator
    from stealth import Stealth
    nav, cover = Navigator(), Cover()
    probe = Stealth(et.HELLO, nav, cover)
    free = [i for i, v in enumerate(nav.free) if v]
    for index in free[::97]:
        origin = nav.point(index)
        for bearing in range(0, 360, 30):
            mech = et.mech(3, bearing, 90, origin=origin)
            eye = (mech["pos"][0], mech["pos"][1], mech["pos"][2] + 8)
            body = (origin[0], origin[1], et.ground(*origin) + 4.5)
            if not cover.clear(eye, body, skip_start=3.0, skip_end=2.5):
                continue
            obs = scene(origin, bearing)
            eyes = probe.observers(obs)
            probe.resume = 0
            found = False
            while found is False:
                found = probe.search(obs, eyes)
            if found and math.dist(found, origin) >= 5:
                return origin, bearing
    raise SystemExit("no scene found")


def scene(origin, bearing, alive=16, next_radius=300.0, attacked=False):
    mech = et.mech(3, bearing, 90, origin=origin, aim_at_us=attacked)
    events = [dict(type="damaged", amount=45, weapon="gun", by=3,
                   bearing=math.atan2(mech["pos"][1] - origin[1], mech["pos"][0] - origin[0]))] if attacked else []
    obs = dt.observation(0, origin, (0.0, 0.0), origin, mechs=[mech], zone=(list(origin), 400.0), events=events)
    obs["zone"]["next_radius"] = next_radius
    obs["alive"] = alive
    obs["t"] = 30.0
    return obs


def ask(folder, obs, decisions=6):
    """The answer to the last of `decisions` repeats of the scene, 0.1 s apart (the cover
    search spreads over a few decisions to keep each answer inside the time budget)."""
    bot = BotProcess(folder, et.HELLO)
    for k in range(decisions):
        frame = copy.deepcopy(obs)
        frame["tick"] = obs["tick"] + k
        frame["t"] = round(obs["t"] + 0.1 * k, 2)
        if k:
            frame["events"] = []
        answer = bot.act(frame)
    bot.close()
    return answer


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    origin, bearing = find_scene()
    print(f"baseline {revision[:12]} vs this working tree; scene at ({origin[0]:.0f}, {origin[1]:.0f}),"
          f" mech 90 m away at bearing {bearing} deg\n")
    cases = [
        ("passive standing mech, 16 alive", scene(origin, bearing), "stealth"),
        ("same, 4 alive (endgame)", scene(origin, bearing, alive=4), "identical"),
        ("same, next circle 25 m (endgame)", scene(origin, bearing, next_radius=25.0), "identical"),
        ("mech aiming at us that just hit us, 16 alive", scene(origin, bearing, attacked=True), "fights"),
    ]
    empty = scene(origin, bearing)
    empty["mechs"] = []
    failures = []
    fmt = lambda a: f"move [{a['move'][0]:+.2f},{a['move'][1]:+.2f}] fire {str(a.get('fire')):14}"
    print("each answer is the 6th decision of the scene (0.5 s in)\n")
    print(f"{'case':46}{'dodge-tuned':>40}{'stealth':>40}  check")
    for name, obs, expect in cases:
        a, b = ask(folder, obs), ask(ROOT, obs)
        if expect == "stealth":
            ok = a.get("fire") and any(a["fire"]) and not any(b.get("fire") or []) and b["move"] != a["move"]
            text = "holds fire and steps out of sight"
        elif expect == "fights":
            ok = plain(a) == plain(b) and any(b.get("fire") or [])
            text = "fights back exactly as dodge-tuned"
        else:
            ok = plain(a) == plain(b)
            text = "identical to dodge-tuned"
        print(f"{name:46}{fmt(a):>40}{fmt(b):>40}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    a, b = ask(folder, empty), ask(ROOT, empty)
    print(f"{'nobody listed, 16 alive (measurement)':46}{fmt(a):>40}{fmt(b):>40}  hide-spot goal")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    reasons = {}
    for obs in et.STREAM:
        local.act(copy.deepcopy(obs))
        r = local.engagement.decision.get("reason")
        reasons[r] = reasons.get(r, 0) + 1
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    fire_diff = move_diff = other_diff = 0
    for obs in et.STREAM:
        a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        fire_diff += a.get("fire") != c.get("fire")
        move_diff += (a.get("move"), a.get("boost"), a.get("jump")) != (c.get("move"), c.get("boost"), c.get("jump"))
        rest = lambda x: {k: v for k, v in x.items() if k not in ("fire", "move", "boost", "jump", "tick", "debug")}
        other_diff += rest(a) != rest(c)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording ({len(et.STREAM)} decisions; alive goes 16 -> 13, next circle 380 m): fire differs on"
          f" {fire_diff}, move/boost/jump on {move_diff}, anything else on {other_diff}")
    print(f"  stealth outcomes: {dict(sorted(local.stealth.counts.items()))}; shots held: {local.stealth.held}")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
