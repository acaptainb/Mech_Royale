"""2.63 vs full strafe vs duel-weave on the same 16 held-out routes, as real bot processes.

    py tools/weave_compare.py

Uses the v8 dodge trial's reactive world: our mech walks a 120 m route to the next circle's
centre while a stationary mech leads a gun bullet at it every 0.25 s (it is listed and aiming
at us, so the duel rules are eligible). Each episode ends on arrival or at 30 s. Reports route
completion, time to safety (arrival at the next circle's centre) and total hits, then applies
the submission gate: the weave must finish every route and take fewer total hits than 2.63.
Standard library only.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
from harness import export

BOTS = [("2.63 (3b290b0)", "3b290b0b87bee98c418a74546671c82dd232c2d0"),
        ("full strafe (2b8e620)", "2b8e620b618581f267189f12ca46d12b5be28588"),
        ("duel-weave (this tree)", None)]


def arrive(r):
    return "-" if r["reached"] is None else f"{r['reached']:.1f}"


def main():
    episodes = dt.heldout_episodes()
    folders = {name: (export(rev) if rev else ROOT) for name, rev in BOTS}
    results = {name: [dt.react(folder, ep) for ep in episodes] for name, folder in folders.items()}
    print(f"{len(episodes)} held-out routes (seed 70411), shooter leading every bullet\n")
    print(f"{'route':28}" + "".join(f"{name.split(' (')[0]:>22}" for name, _ in BOTS))
    print(f"{'':28}" + "".join(f"{'hits / arrival s':>22}" for _ in BOTS))
    for k, ep in enumerate(episodes):
        cells = []
        for name, _ in BOTS:
            r = results[name][k]
            cells.append(f"{r['hits']:>4} / {arrive(r):>5}")
        print(f"{ep['name']:28}" + "".join(f"{c:>22}" for c in cells))
    print()
    summary = {}
    for name, _ in BOTS:
        runs = results[name]
        done = [r["reached"] for r in runs if r["reached"] is not None]
        summary[name] = dict(done=len(done), hits=sum(r["hits"] for r in runs),
                             mean=sum(done) / len(done) if done else float("nan"),
                             outside=sum(r["outside"] for r in runs))
        s = summary[name]
        print(f"{name:26} routes finished {s['done']:>2}/{len(runs)}   mean time to safety {s['mean']:5.1f} s"
              f"   total hits {s['hits']:>5}   decisions outside the zone {s['outside']}")
    base, weave = summary[BOTS[0][0]], summary[BOTS[2][0]]
    finishes = weave["done"] == len(episodes)
    fewer = weave["hits"] < base["hits"]
    print(f"\ngate: weave finishes every route: {'yes' if finishes else 'NO'};"
          f" fewer total hits than 2.63 ({weave['hits']} vs {base['hits']}): {'yes' if fewer else 'NO'}")
    print("GATE PASSED: prepare a submission SHA" if finishes and fewer else "GATE NOT PASSED: do not submit")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    bot = Bot(et.HELLO)
    for obs in et.STREAM:
        bot.act(copy.deepcopy(obs))
    counts = bot.weave.counts
    skips = {k[len("skipped: "):]: v for k, v in counts.items() if k.startswith("skipped: ")}
    print(f"\nrecording: eligible {counts.get('eligible', 0)}, move changed {counts.get('changed movement', 0)};"
          f" skipped: {', '.join(f'{k} {v}' for k, v in sorted(skips.items(), key=lambda kv: -kv[1]))}")
    sys.exit(0 if finishes and fewer else 2)


if __name__ == "__main__":
    main()
