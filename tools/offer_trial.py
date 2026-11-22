"""plating-first: crossing-fire (c120041, official 2.94) and candidate as real bot processes.

    py tools/offer_trial.py [--baseline <git revision>]

The standard recording has no upgrade offer, so this replays it with offers injected on
two consecutive decisions each (an unresolved offer stays listed). Activating offers hold
both plating and armor; the candidate picks plating where crossing-fire picks armor.
Controls hold one of them, neither, or nanites on top: the pick must be identical. Every
other command must be identical on all decisions. Standard library only.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
from harness import BotProcess, export, plain

BASELINE = "c1200411b37163ea2496aefbb861a496d2bcea12"  # crossing-fire, official 2.94

UPGRADES = {u["id"]: u for u in et.HELLO["config"]["upgrades"]}

# name, choice ids, expectation
CASES = [
    ("armor, plating, sensors", ("armor", "plating", "sensors"), "activates"),
    ("plating, armor, gun_rate", ("plating", "armor", "gun_rate"), "activates"),
    ("gun_rate, armor, plating", ("gun_rate", "armor", "plating"), "activates"),
    ("servos, plating, armor", ("servos", "plating", "armor"), "activates"),
    ("armor, servos, gun_rate (control)", ("armor", "servos", "gun_rate"), "identical"),
    ("sensors, plating, gyros (control)", ("sensors", "plating", "gyros"), "identical"),
    ("gun_rate, sensors, capacitor (control)", ("gun_rate", "sensors", "capacitor"), "identical"),
    ("nanites, servos, gun_rate (control)", ("nanites", "servos", "gun_rate"), "identical"),
    ("gyros, capacitor, reactor (control)", ("gyros", "capacitor", "reactor"), "identical"),
]
FIRST, SPACING = 20, 30   # decision index of the first offer, decisions between offers


def offer(index, ids, t):
    choices = [{k: UPGRADES[i][k] for k in ("id", "name", "desc")} for i in ids]
    return {"id": index + 1, "expires": round(t + 5.0, 2), "choices": choices}


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    at = {}
    for k, (_, ids, _) in enumerate(CASES):
        for step in (0, 1):
            at[FIRST + k * SPACING + step] = k
    base, cand = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    picks = {k: [] for k in range(len(CASES))}
    other_diff, pick_diff_outside = 0, 0
    for n, obs in enumerate(et.STREAM):
        obs = copy.deepcopy(obs)
        if n in at:
            k = at[n]
            obs["offer"] = offer(k, CASES[k][1], obs["t"])
        a, c = base.act(copy.deepcopy(obs)), cand.act(copy.deepcopy(obs))
        if n in at:
            picks[at[n]].append((a.get("pick"), c.get("pick")))
        elif a.get("pick") != c.get("pick"):
            pick_diff_outside += 1
        rest = lambda x: {key: v for key, v in plain(x).items() if key != "pick"}
        other_diff += rest(a) != rest(c)
    print(f"names: {base.name} | {cand.name}")
    base.close()
    cand.close()

    failures = []
    print(f"\n{'offer (choices 0, 1, 2)':42}{'pick base | cand':>18}  {'taken base | cand':28}check")
    for k, (name, ids, expect) in enumerate(CASES):
        pairs = picks[k]
        b, c = pairs[0]
        steady = all(p == pairs[0] for p in pairs)
        if expect == "activates":
            ok = steady and ids[b] == "armor" and ids[c] == "plating"
            text = "picks plating where crossing-fire picks armor"
        else:
            ok = steady and b == c
            text = "identical"
        taken = f"{ids[b]} | {ids[c]}"
        print(f"{name:42}{b:>8} | {c:<7}  {taken:28}{'ok  ' if ok else 'FAIL'} {text}")
        if not ok:
            failures.append(name)
    print(f"\nrecording with offers injected: {len(et.STREAM)} decisions, {len(at)} with an offer listed")
    print(f"  pick differs outside offer decisions: {pick_diff_outside}; any other command differs: {other_diff}")
    if other_diff or pick_diff_outside:
        failures.append("a command other than the offer pick changed")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
