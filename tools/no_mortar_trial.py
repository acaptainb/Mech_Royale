"""no-mortar: baseline (3b290b0, official 2.63) and candidate as real bot processes.

    py tools/no_mortar_trial.py [--baseline <git revision>]

Closed-loop pickup layouts from tools/pickup_trial.py (the mech moves where it steers, a
pickup disappears only after a valid take), each played by both bots from the same start:
a lone nearby mortar, a mortar with a laser a little farther, a mortar lying on the route
(the take-on-the-way rule), and a lone laser as a control. Reports what each bot carried
away and when it reached the zone goal, then counts mortar opportunities on the recording.
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
import pickup_trial as pt
import engagement_trial as et
from harness import BotProcess, export

BASELINE = "3b290b0b87bee98c418a74546671c82dd232c2d0"  # v8 + v7, official 2.63
INSTANCES = 8


class Processes:
    """A controller for pickup_trial.simulate that runs a bot folder as a real process."""

    def __init__(self, folder):
        self.folder, self.live = folder, []

    def __call__(self, hello):
        bot = BotProcess(self.folder, hello)
        self.live.append(bot)
        return bot

    def close(self):
        for bot in self.live:
            bot.close()
        self.live = []


def layouts(rng):
    out = []
    for k in range(INSTANCES):
        base = pt.build("easy nearby pickup", rng)
        spot = base["pickups"][0]["pos"][:2]
        start, goal = base["start"], base["zone"]["next_center"]
        ux, uy = goal[0] - start[0], goal[1] - start[1]
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n
        farther = [spot[0] + 10 * ux, spot[1] + 10 * uy]
        on_route = [start[0] + 25 * ux, start[1] + 25 * uy]
        if not (pt.walkable(farther) and pt.walkable(on_route) and pt.GRID.clear_segment(start, farther)):
            continue
        out.append(("lone mortar nearby", dict(base, pickups=[pt.pickup_at(spot, 8001, "mortar")])))
        out.append(("mortar, laser 10 m farther", dict(base, pickups=[pt.pickup_at(spot, 8001, "mortar"),
                                                                       pt.pickup_at(farther, 8002, "laser")])))
        out.append(("mortar lying on the route", dict(base, pickups=[pt.pickup_at(on_route, 8003, "mortar")])))
        out.append(("lone laser (control)", dict(base, pickups=[pt.pickup_at(spot, 8001, "laser")])))
    return out


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    rng = random.Random(4242)
    cases = layouts(rng)
    rows = {}
    for name, scenario in cases:
        for key, path in (("base", folder), ("cand", ROOT)):
            runner = Processes(path)
            result = pt.simulate(runner, scenario)
            runner.close()
            row = rows.setdefault((name, key), dict(taken={}, reached=[], unreached=0))
            for kind in result["taken"] or ["nothing"]:
                row["taken"][kind] = row["taken"].get(kind, 0) + 1
            if result["reached"] is None:
                row["unreached"] += 1
            else:
                row["reached"].append(result["reached"])
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; "
          f"{len(cases) // 4} layouts per case\n")
    print(f"{'case':30}{'carried away (base)':>26}{'carried away (no-mortar)':>28}{'goal at s (base | cand)':>26}  check")
    failures = []
    for name in dict.fromkeys(n for n, _ in cases):
        b, c = rows[(name, "base")], rows[(name, "cand")]
        fmt = lambda t: ", ".join(f"{k} {v}" for k, v in sorted(t.items()))
        mean = lambda r: sum(r["reached"]) / len(r["reached"]) if r["reached"] else float("nan")
        if name.startswith("lone laser"):
            ok = b["taken"] == c["taken"] and b["reached"] == c["reached"]
            text = "identical to the baseline"
        else:
            ok = "mortar" not in c["taken"] and c["unreached"] <= b["unreached"]
            text = "never carries a mortar; still reaches the goal"
            if "laser" in name:
                ok = ok and c["taken"].get("laser", 0) == sum(c["taken"].values())
                text = "takes the laser instead of the mortar"
        print(f"{name:30}{fmt(b['taken']):>26}{fmt(c['taken']):>28}{mean(b):>14.1f} | {mean(c):<9.1f}"
              f"  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    bot = Bot(et.HELLO)
    seen = near = 0
    for obs in et.STREAM:
        me = obs["self"]["pos"]
        for p in obs["pickups"]:
            if p["kind"] == "mortar":
                seen += 1
                near += math.dist(p["pos"][:2], me[:2]) <= bot.loot.MAX_ROUTE
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    differ = sum(base_bot.act(copy.deepcopy(o)) != cand_bot.act(copy.deepcopy(o)) for o in et.STREAM)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: mortar sightings {seen}, within the 70 m pickup reach {near};"
          f" decisions answered differently from the baseline (debug included): {differ}")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
