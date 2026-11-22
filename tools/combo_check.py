"""The V8 + V7 combination against the two scored versions it combines, as real bot processes.

    py tools/combo_check.py

On each observation the combination must move exactly as V8 (4588e6b) and fire exactly as
V7 (f69d39c): the dodge owns move and boost, the laser release owns the laser trigger.
Standard library only.
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
from harness import BotProcess, export

V7, V8 = "f69d39c2c32f92e533568ce27854cf5efd0e04ca", "4588e6b826e3ea923ab10697160e5c7658a64179"
LASER = et.HELLO["config"]["weapons"]["laser"]


def case(laser_full, bullet):
    home = list(et.HOME)
    heading, ahead = dt.clear_heading(home)
    h = math.radians(heading)
    walk = (dt.MECH["walk_speed"] * math.cos(h), dt.MECH["walk_speed"] * math.sin(h))
    target = et.mech(3, heading, 30, aim_at_us=True)
    projectiles = [dt.bullet_at(1, home, walk, 150, heading + 90)] if bullet else []
    obs = dt.observation(0, home, walk, ahead, projectiles, [target])
    obs["self"]["weapons"] = [et.gun(), dict(et.laser(LASER["charge"]), cooldown=0.0) if laser_full else None]
    obs["self"]["aim"] = [h, math.atan2(target["pos"][2] - obs["self"]["pos"][2] - 2.5, 30)]
    return obs


def main():
    folders = {"v7": export(V7), "v8": export(V8), "v8+v7": ROOT}
    cases = [("full laser, clear opponent 30 m, bullet on course", case(True, True)),
             ("full laser, clear opponent 30 m, no bullet", case(True, False)),
             ("gun only, clear opponent 30 m, bullet on course", case(False, True))]
    failures = []
    print(f"{'case':52}{'bot':8}{'move':>18}{'boost':>7}{'fire':>16}")
    for name, obs in cases:
        answers = {}
        for label, folder in folders.items():
            bot = BotProcess(folder, et.HELLO)
            answers[label] = bot.act(copy.deepcopy(obs))
            bot.close()
            a = answers[label]
            print(f"{name if label == 'v7' else '':52}{label:8}{str([round(v, 2) for v in a['move']]):>18}"
                  f"{str(a.get('boost')):>7}{str(a.get('fire')):>16}")
        combo = answers["v8+v7"]
        ok = (combo["move"] == answers["v8"]["move"] and combo.get("boost") == answers["v8"].get("boost")
              and combo.get("fire") == answers["v7"].get("fire"))
        print(f"{'':52}{'check':8}  {'ok: moves as v8, fires as v7' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
