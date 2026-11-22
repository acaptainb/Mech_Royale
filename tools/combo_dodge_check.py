"""Tuned dodge on the 3.04 combination, against the two scored versions it combines.

    py tools/combo_dodge_check.py [--quick]

The tuned bullet dodge (MOVE_PARENT: mortar-dodge with the dodge tuned) owns move and boost;
the 3.04 combination (FIRE_PARENT: mortar-dodge + crossing-fire) adds crossing-fire's led fire.
On the recording and the scripted dodge and shell decisions the candidate must move exactly as
MOVE_PARENT and fire exactly as FIRE_PARENT; closed-loop bullet and shell routes must match
MOVE_PARENT and closed-loop gunfights must match FIRE_PARENT. --quick skips the held-out routes.
Standard library only.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import crossing_fire_trial as cft
import dodge_trial as dt
import engagement_trial as et
import lead_trial as lt
import shell_dodge_trial as sdt
from harness import BotProcess, export

MOVE_PARENT = "a75bb3b4ceb798dcb10bfd2064bfb58be4854810"   # dodge-rapid (pending)
FIRE_PARENT = "4f4596e12bf916fe76039a7e75652cf4036d35f4"   # mortar-dodge + crossing-fire, official 3.04


def strip(action, *keys):
    return {k: v for k, v in action.items() if k not in ("tick", "debug") + keys}


def main():
    quick = "--quick" in sys.argv
    folders = {"move": export(MOVE_PARENT), "fire": export(FIRE_PARENT), "cand": ROOT}
    failures = []

    bots = {k: BotProcess(f, et.HELLO) for k, f in folders.items()}
    other_vs_move = fire_vs_fire = fire_vs_move = 0
    for obs in et.STREAM:
        a = {k: b.act(copy.deepcopy(obs)) for k, b in bots.items()}
        other_vs_move += strip(a["cand"], "fire") != strip(a["move"], "fire")
        fire_vs_fire += a["cand"].get("fire") != a["fire"].get("fire")
        fire_vs_move += a["cand"].get("fire") != a["move"].get("fire")
    for b in bots.values():
        b.close()
    print(f"recording ({len(et.STREAM)} decisions): commands other than fire differ from the move parent on "
          f"{other_vs_move}; fire differs from the fire parent on {fire_vs_fire}; fire differs from the move parent "
          f"on {fire_vs_move} (crossing-fire's own change)")
    if other_vs_move or fire_vs_fire:
        failures.append("recording")

    scripted = [(case[0], case[2]) for case in dt.scripted()]
    shell_cases, _ = sdt.scripted()
    cases = [(name, obs) for name, _, obs in shell_cases] + scripted
    print(f"\n{'scripted decision':52}  check")
    for name, obs in cases:
        a = {}
        for label, folder in folders.items():
            bot = BotProcess(folder, et.HELLO)
            a[label] = bot.act(copy.deepcopy(obs))
            bot.close()
        ok = (strip(a["cand"], "fire") == strip(a["move"], "fire") and a["cand"].get("fire") == a["fire"].get("fire"))
        print(f"{name:52}  {'ok  moves as the move parent, fires as the fire parent' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    for title, eps, react, keys in (
            ("bullet route", dt.episodes() + ([] if quick else dt.heldout_episodes()), dt.react,
             ("hits", "spent", "outside", "reached")),
            ("shell route", sdt.episodes() + ([] if quick else sdt.heldout_episodes()), sdt.react,
             ("damage", "direct", "splashed", "spent", "outside", "reached", "fired"))):
        print(f"\n{title + 's':40}{'move parent | candidate':>26}  check")
        for ep in eps:
            m, c = react(folders["move"], ep), react(ROOT, ep)
            ok = all(m[k] == c[k] for k in keys)
            key = keys[0]
            print(f"{ep['name']:40}{m[key]:>12.0f} | {c[key]:<11.0f}  {'ok  identical' if ok else 'FAIL'}")
            if not ok:
                failures.append(f"{title}: {ep['name']}")

    print(f"\n{'gunfight (crossing-fire trial)':50}{'shots fire parent | cand':>26}  check")
    for k, (name, motion, passive, _) in enumerate(cft.SCENARIOS):
        f = lt.gunfight(folders["fire"], motion, seed=300 + k, passive=passive)
        c = lt.gunfight(ROOT, motion, seed=300 + k, passive=passive)
        ok = f == c
        print(f"{name:50}{f['shots']:>12} | {c['shots']:<11}  {'ok  identical' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS: moves as the tuned dodge, fires as the 3.04 combination")


if __name__ == "__main__":
    main()
