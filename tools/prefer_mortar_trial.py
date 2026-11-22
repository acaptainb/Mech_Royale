"""prefer-mortar: baseline (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/prefer_mortar_trial.py [--baseline <git revision>]

Closed-loop pickup layouts from tools/pickup_trial.py (the mech moves where it steers, a
pickup disappears only after a valid take), each played by both bots from the same start:
a mortar and a laser at similar distance, a mortar clearly farther than a laser, a lone laser
and a lone mortar. Reports what each bot carried away and when it reached the zone goal, then
counts mortar opportunities on the recording. Standard library only.
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

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90
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
    while len(out) < 4 * INSTANCES:
        base = pt.build("easy nearby pickup", rng)
        spot = base["pickups"][0]["pos"][:2]
        start, goal = base["start"], base["zone"]["next_center"]
        ux, uy = goal[0] - start[0], goal[1] - start[1]
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n
        across = (-uy, ux)
        # a second spot 4 m to the side (similar distance) and one 15 m farther along the route
        beside = [spot[0] + 4 * across[0], spot[1] + 4 * across[1]]
        farther = [spot[0] + 15 * ux, spot[1] + 15 * uy]
        if not all(pt.walkable(p) and pt.GRID.clear_segment(start, p) for p in (beside, farther)):
            continue
        if abs(math.dist(start, beside) - math.dist(start, spot)) > 3:
            continue
        near_first = math.dist(start, spot) <= math.dist(start, beside)
        laser_at, mortar_at = (spot, beside) if near_first else (beside, spot)
        out.append(("mortar and laser at similar distance", dict(base, pickups=[
            pt.pickup_at(laser_at, 8001, "laser"), pt.pickup_at(mortar_at, 8002, "mortar")])))
        out.append(("mortar 15 m farther than a laser", dict(base, pickups=[
            pt.pickup_at(spot, 8001, "laser"), pt.pickup_at(farther, 8002, "mortar")])))
        out.append(("lone laser (control)", dict(base, pickups=[pt.pickup_at(spot, 8001, "laser")])))
        out.append(("lone mortar (control)", dict(base, pickups=[pt.pickup_at(spot, 8001, "mortar")])))
    return out


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    rng = random.Random(5150)
    cases = layouts(rng)
    rows = {}
    for name, scenario in cases:
        for key, path in (("base", folder), ("cand", ROOT)):
            runner = Processes(path)
            result = pt.simulate(runner, scenario)
            runner.close()
            row = rows.setdefault((name, key), dict(taken={}, reached=[], unreached=0, results=[]))
            for kind in result["taken"] or ["nothing"]:
                row["taken"][kind] = row["taken"].get(kind, 0) + 1
            row["results"].append(result)
            if result["reached"] is None:
                row["unreached"] += 1
            else:
                row["reached"].append(result["reached"])
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`; "
          f"{INSTANCES} layouts per case\n")
    print(f"{'case':38}{'carried away (base)':>22}{'carried away (cand)':>22}{'goal at s (base | cand)':>26}  check")
    failures = []
    for name in dict.fromkeys(n for n, _ in cases):
        b, c = rows[(name, "base")], rows[(name, "cand")]
        fmt = lambda t: ", ".join(f"{k} {v}" for k, v in sorted(t.items()))
        mean = lambda r: sum(r["reached"]) / len(r["reached"]) if r["reached"] else float("nan")
        if "control" in name:
            ok = all(x["taken"] == y["taken"] and x["reached"] == y["reached"]
                     for x, y in zip(b["results"], c["results"]))
            text = "identical to the baseline"
        else:
            ok = c["taken"].get("mortar", 0) == INSTANCES and c["unreached"] <= b["unreached"]
            text = "takes the mortar every time; still reaches the goal"
        print(f"{name:38}{fmt(b['taken']):>22}{fmt(c['taken']):>22}{mean(b):>14.1f} | {mean(c):<9.1f}"
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
    if differ:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
