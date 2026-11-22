"""offense-upgrades: lead-shots (4d8a32d, official 2.90) and candidate as real bot processes.

    py tools/upgrade_trial.py [--baseline <git revision>]

1. Crafted upgrade offers (protocol section 10: three distinct choices, weapon upgrades only for
   weapons held): the emitted `pick` for each bot.
2. A three-offer sequence drawn from the configured upgrade list with one seeded generator,
   applying each bot's picks with the configured effects: gun damage per second, max HP and
   armor after three picks.
3. Offers on the standard recording.
Standard library only.
"""
import copy
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
from harness import BotProcess, export

BASELINE = "4d8a32d3c453d3efb430baddb4bd141678417d77"  # lead-shots, official 2.90
UPGRADES = {u["id"]: u for u in et.HELLO["config"]["upgrades"]}


def offer_obs(tick, choices, weapons=None):
    obs = et.frame(tick, [], weapons=weapons)
    obs["offer"] = dict(id=tick, expires=obs["t"] + 5,
                        choices=[dict(id=c, name=UPGRADES[c]["name"], desc=UPGRADES[c]["desc"]) for c in choices])
    return obs


def laser_held():
    return [et.gun(), et.laser(0.0)]


CASES = [
    ("gun upgrade beside defence", ["armor", "gun_rate", "sensors"], None, "differs"),
    ("gun damage last in the list", ["plating", "nanites", "gun_damage"], None, "differs"),
    ("no offense upgrade offered", ["armor", "servos", "sensors"], None, "identical"),
    ("held laser: laser upgrade offered", ["capacitor", "armor", "laser_damage"], laser_held(), "differs"),
    ("held laser: gun and laser upgrades", ["laser_damage", "plating", "gun_mag"], laser_held(), "differs"),
    ("neither list: energy and aim upgrades", ["reactor", "jets", "gyros"], None, "identical"),
]


def pick(folder, obs):
    bot = BotProcess(folder, et.HELLO)
    action = bot.act(copy.deepcopy(obs))
    bot.close()
    return action.get("pick")


def apply_stats(stats, upgrade):
    for effect in upgrade["effects"]:
        key = effect["path"]
        if "mul" in effect:
            stats[key] = stats.get(key, 0) * effect["mul"]
        if "add" in effect:
            stats[key] = stats.get(key, 0) + effect["add"]


def sequence(folder, seed=11, offers=3):
    """Offers drawn from upgrades the bot can still take (gun held only)."""
    rng = random.Random(seed)
    cfg = et.HELLO["config"]
    stats = {"weapons.gun.damage": cfg["weapons"]["gun"]["damage"], "weapons.gun.cooldown": cfg["weapons"]["gun"]["cooldown"],
             "mech.hp": cfg["mech"]["hp"], "mech.armor": cfg["mech"]["armor"]}
    taken, picks = {}, []
    bot = BotProcess(folder, et.HELLO)
    for k in range(offers):
        eligible = sorted(u for u, spec in UPGRADES.items()
                          if taken.get(u, 0) < spec.get("max", 1) and spec.get("requires") in (None, "gun"))
        choices = rng.sample(eligible, 3)
        action = bot.act(offer_obs(k, choices))
        chosen = choices[action.get("pick", 0)]
        taken[chosen] = taken.get(chosen, 0) + 1
        apply_stats(stats, UPGRADES[chosen])
        picks.append((choices, chosen))
    bot.close()
    dps = stats["weapons.gun.damage"] / stats["weapons.gun.cooldown"]
    return picks, dps, stats["mech.hp"], stats["mech.armor"]


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"baseline {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    print(f"{'offer':40}{'choices':48}{'base pick':>14}{'cand pick':>16}  check")
    failures = []
    for k, (name, choices, weapons, expect) in enumerate(CASES):
        obs = offer_obs(k, choices, weapons)
        a, b = pick(folder, obs), pick(ROOT, obs)
        ok = (a == b) if expect == "identical" else (a != b)
        print(f"{name:40}{', '.join(choices):48}{choices[a]:>14}{choices[b]:>16}  {'ok  ' if ok else 'FAIL'}"
              f" {'identical' if expect == 'identical' else 'offense first'}")
        if not ok:
            failures.append(name)

    print("\nthree offers from one seeded draw (gun only), each bot's own picks applied:")
    for label, path in (("baseline", folder), ("offense", ROOT)):
        picks, dps, hp, armor = sequence(path)
        chosen = ", ".join(c for _, c in picks)
        print(f"  {label:9} picks {chosen:40} gun dps {dps:6.1f}   max hp {hp:6.0f}   armor {armor:.2f}")
    base_dps = et.HELLO["config"]["weapons"]["gun"]["damage"] / et.HELLO["config"]["weapons"]["gun"]["cooldown"]
    print(f"  (no upgrades: gun dps {base_dps:.1f}, max hp {et.HELLO['config']['mech']['hp']}, armor 0.00)")

    offers = sum(1 for obs in et.STREAM if obs.get("offer"))
    cubes = max(obs["self"].get("cubes", 0) for obs in et.STREAM)
    print(f"\nrecording: {offers} decisions with an offer (most cubes held: {cubes}); the rule only acts when an"
          f" offer appears, at 1, 3, 6, 10 ... cubes")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
