"""mortar-dodge + crossing-fire against the two scored versions it combines, as real bot processes.

    py tools/combo_md_cf_check.py [--quick]

mortar-dodge (1645c22, official 3.00) and crossing-fire (c120041, official 2.94) each change one
thing on lead-shots (4d8a32d, 2.90): the shell dodge owns move and boost when a mortar shell
threatens the route, and crossing-fire only changes the fire decision (firing at a passive
opponent when the aim is led). On every checked observation the combination must move exactly as
mortar-dodge and fire exactly as crossing-fire, and closed-loop runs must match the version whose
change is active. --quick skips the 16 held-out shell routes. Standard library only.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import crossing_fire_trial as cft
import engagement_trial as et
import lead_trial as lt
import shell_dodge_trial as sdt
from harness import BotProcess, export

MORTAR_DODGE = "1645c22576e99d0afe6cb9ce8ec37ad0d9bae616"   # official 3.00
CROSSING_FIRE = "c1200411b37163ea2496aefbb861a496d2bcea12"  # official 2.94


def strip(action, *keys):
    return {k: v for k, v in action.items() if k not in ("tick", "debug") + keys}


def answers(folders, obs):
    out = {}
    for label, folder in folders.items():
        bot = BotProcess(folder, et.HELLO)
        out[label] = bot.act(copy.deepcopy(obs))
        bot.close()
    return out


def main():
    quick = "--quick" in sys.argv
    folders = {"md": export(MORTAR_DODGE), "cf": export(CROSSING_FIRE), "combo": ROOT}
    failures = []

    # 1. The standard recording, one process per build fed the same stream.
    bots = {k: BotProcess(f, et.HELLO) for k, f in folders.items()}
    move_vs_md = fire_vs_cf = fire_vs_md = rest_vs_cf = 0
    for obs in et.STREAM:
        a = {k: b.act(copy.deepcopy(obs)) for k, b in bots.items()}
        move_vs_md += strip(a["combo"], "fire") != strip(a["md"], "fire")
        fire_vs_cf += a["combo"].get("fire") != a["cf"].get("fire")
        fire_vs_md += a["combo"].get("fire") != a["md"].get("fire")
        rest_vs_cf += strip(a["combo"]) != strip(a["cf"])
    for b in bots.values():
        b.close()
    n = len(et.STREAM)
    print(f"recording ({n} decisions): commands other than fire differ from mortar-dodge on {move_vs_md}; "
          f"fire differs from crossing-fire on {fire_vs_cf}; every command differs from crossing-fire on "
          f"{rest_vs_cf}; fire differs from mortar-dodge on {fire_vs_md} (crossing-fire's own change)")
    if move_vs_md or fire_vs_cf or rest_vs_cf:
        failures.append("recording")

    # 2. Scripted shell decisions: the dodge decides the move, crossing-fire the trigger.
    cases, _ = sdt.scripted()
    print(f"\n{'scripted shell decision':48}{'md move/boost':>22}{'combo move/boost':>22}  check")
    for name, _, obs in cases:
        a = answers(folders, obs)
        ok = (a["combo"]["move"] == a["md"]["move"] and a["combo"].get("boost") == a["md"].get("boost")
              and a["combo"].get("fire") == a["cf"].get("fire"))
        fmt = lambda act: f"[{act['move'][0]:+.2f},{act['move'][1]:+.2f}] {str(act.get('boost', False)):5}"
        print(f"{name:48}{fmt(a['md']):>22}{fmt(a['combo']):>22}  {'ok  moves as md, fires as cf' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    # 3. Closed-loop shell episodes: no passive opponent, so crossing-fire's rule never fires and
    #    the combination must play exactly as mortar-dodge.
    eps = sdt.episodes() + ([] if quick else sdt.heldout_episodes())
    keys = ("damage", "direct", "splashed", "spent", "outside", "reached", "fired")
    print(f"\n{'shell episode':34}{'damage md | combo':>20}{'arrival md | combo':>22}  check")
    totals = {"md": 0.0, "combo": 0.0}
    for ep in eps:
        md, combo = sdt.react(folders["md"], ep), sdt.react(ROOT, ep)
        totals["md"] += md["damage"]
        totals["combo"] += combo["damage"]
        ok = all(md[k] == combo[k] for k in keys) and md["log"] == combo["log"]
        print(f"{ep['name']:34}{md['damage']:>9.0f} | {combo['damage']:<8.0f}{str(md['reached']):>10} | "
              f"{str(combo['reached']):<9}  {'ok  identical' if ok else 'FAIL'}")
        if not ok:
            failures.append(ep["name"])
    print(f"{'all shell episodes':34}{totals['md']:>9.0f} | {totals['combo']:<8.0f}")

    # 4. Closed-loop gunfights from the crossing-fire trial: no shells, so the dodge never acts and
    #    the combination must play exactly as crossing-fire (including where it fires and lead-shots held).
    print(f"\n{'gunfight (crossing-fire trial)':50}{'shots cf | combo':>18}{'hits cf | combo':>18}  check")
    for k, (name, motion, passive, _) in enumerate(cft.SCENARIOS):
        cf = lt.gunfight(folders["cf"], motion, seed=300 + k, passive=passive)
        combo = lt.gunfight(ROOT, motion, seed=300 + k, passive=passive)
        ok = cf == combo
        print(f"{name:50}{cf['shots']:>8} | {combo['shots']:<7}{cf['hits']:>8} | {combo['hits']:<7}  "
              f"{'ok  identical' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS: moves as mortar-dodge, fires as crossing-fire")


if __name__ == "__main__":
    main()
