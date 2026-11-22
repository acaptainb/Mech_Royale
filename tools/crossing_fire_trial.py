"""crossing-fire: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/crossing_fire_trial.py [--baseline <git revision>]

The closed-loop gunfight of tools/lead_trial.py, with opponents that are not fighting us
(torso turned 90 degrees away). v6 holds fire on such an opponent when unled shots would miss;
the candidate fires whenever its aim is led. Controls are opponents both bots already fire on.
Also checks the standard recording: only fire commands may differ. Standard library only.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
import lead_trial as lt
from harness import BotProcess, export

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90

# name, motion, passive, expectation
SCENARIOS = [
    ("passive, walking across, 60 m", lt.path(60, 11.7, 0), True, "activates"),
    ("passive, walking across, 100 m", lt.path(100, 11.7, 0), True, "activates"),
    ("passive, walking across, 150 m", lt.path(150, 11.7, 0), True, "activates"),
    ("passive, boosting across, 100 m", lt.path(100, 19.5, 0), True, "activates"),
    ("passive, zigzag every 1 s, 100 m", lt.path(100, 11.7, 0, flip_s=1.0), True, "measure"),
    ("passive, zigzag every 0.5 s, 60 m", lt.path(60, 11.7, 0, flip_s=0.5), True, "measure"),
    ("passive, standing, 100 m (control)", lt.path(100, 0.0, 0), True, "identical"),
    ("passive, walking straight at us, 150 m (control)", lt.path(150, 11.7, 90), True, "identical"),
    ("aiming at us, walking across, 100 m (control)", lt.path(100, 11.7, 0), False, "identical"),
]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    print(f"{'opponent (6 s)':50}{'shots':>12}{'hits':>12}{'hit rate':>16}  check")
    print(f"{'':50}{'base | cand':>12}{'base | cand':>12}{'base | cand':>16}")
    failures = []
    totals = {"base": [0, 0], "cand": [0, 0]}
    for k, (name, motion, passive, expect) in enumerate(SCENARIOS):
        base = lt.gunfight(folder, motion, seed=300 + k, passive=passive)
        cand = lt.gunfight(ROOT, motion, seed=300 + k, passive=passive)
        for key, r in (("base", base), ("cand", cand)):
            totals[key][0] += r["shots"]
            totals[key][1] += r["hits"]
        rate = lambda r: f"{100 * r['hits'] / r['shots']:.0f}%" if r["shots"] else "-"
        if expect == "identical":
            ok, text = base == cand, "identical (lead-shots already fires)"
        elif expect == "activates":
            ok, text = cand["shots"] > base["shots"] and cand["hits"] > base["hits"], "fires where lead-shots held, and lands hits"
        else:
            ok, text = True, "measurement: the lead assumes steady motion"
        print(f"{name:50}{base['shots']:>5} | {cand['shots']:<5}{base['hits']:>5} | {cand['hits']:<5}"
              f"{rate(base):>8} | {rate(cand):<6}  {'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    b, c = totals["base"], totals["cand"]
    print(f"{'all scenarios':50}{b[0]:>5} | {c[0]:<5}{b[1]:>5} | {c[1]:<5}")

    import mechfight as mf
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    from bot import Bot
    local = Bot(et.HELLO)
    reasons, kiting = {}, set()
    for k, obs in enumerate(et.STREAM):
        local.act(copy.deepcopy(obs))
        r = local.engagement.decision.get("reason")
        if obs["mechs"]:
            reasons[r] = reasons.get(r, 0) + 1
        if getattr(local, "kite", None) is not None and local.kite.active:
            kiting.add(k)  # kite-distance: backing away owns move, boost and jump here
    base_bot, cand_bot = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    fire_diff = other_diff = 0
    for k, obs in enumerate(et.STREAM):
        a, c = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        fire_diff += a.get("fire") != c.get("fire")
        skip = ("fire", "tick", "debug") + (("move", "boost", "jump") if k in kiting else ())
        rest = lambda x: {key: v for key, v in x.items() if key not in skip}
        other_diff += rest(a) != rest(c)
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording: fire differs on {fire_diff} of {len(et.STREAM)} decisions; any other command differs on {other_diff}"
          f" (move, boost and jump not compared on the {len(kiting)} kite decisions)")
    print("  candidate reasons while a mech is listed:", ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    if other_diff:
        failures.append("recording: a command other than fire changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
