"""sensors-first: dodge-tuned (dd9b731, official 3.10) and candidate as real bot processes.

    py tools/offer_trial.py [--baseline <git revision>]

The standard recording carries no upgrade offer, so offers are written into it: one case every
20 decisions, in the documented format (3 distinct choices, expires 5 s later). Both bots get
the identical stream. Activating cases offer the Sensor suite next to an upgrade the old order
ranks first; controls offer no sensors (none drawn, or both stacks already taken) or offer it
where the old order already picks it. Every other command must be identical on all decisions.
Standard library only.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et
from harness import BotProcess, export, plain

BASELINE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"  # dodge-tuned, official 3.10

# choices, expectation
CASES = [
    (("sensors", "armor", "plating"), "sensors"),
    (("armor", "sensors", "gun_rate"), "sensors"),
    (("plating", "nanites", "sensors"), "sensors"),
    (("servos", "sensors", "capacitor"), "sensors"),
    (("nanites", "gyros", "sensors"), "sensors"),
    (("gun_rate", "sensors", "reactor"), "sensors"),
    (("sensors", "gyros", "jets"), "identical"),            # the old order already takes sensors
    (("armor", "plating", "nanites"), "identical"),          # no sensors drawn
    (("capacitor", "gyros", "gun_damage"), "identical"),     # nothing either order ranks
    (("gun_damage", "servos", "plating"), "identical"),
    (("reactor", "jets", "gun_rate"), "identical"),
    (("plating", "armor", "gyros"), "identical"),            # sensors maxed, so not offered
    (("servos", "nanites", "gun_velocity"), "identical"),    # sensors maxed, so not offered
]
FIRST, EVERY = 10, 20


def offers():
    names = {u["id"]: u for u in et.HELLO["config"]["upgrades"]}
    stream = copy.deepcopy(et.STREAM)
    placed = {}
    for k, (choices, expect) in enumerate(CASES):
        i = FIRST + EVERY * k
        obs = stream[i]
        obs["offer"] = {"id": k + 1, "expires": round(obs["t"] + 5.0, 2),
                        "choices": [{"id": c, "name": names[c]["name"], "desc": names[c]["desc"]}
                                    for c in choices]}
        placed[i] = (choices, expect)
    return stream, placed


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    stream, placed = offers()
    base, cand = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    print(f"baseline {revision[:12]} ({base.name}) vs this working tree ({cand.name}), both as `python -u bot.py`\n")
    print(f"{'t':>6}  {'offered':40}{'baseline picks':>16}{'candidate picks':>17}  check")
    failures, other_diff, pick_diff, trace = [], 0, 0, None
    for i, obs in enumerate(stream):
        a, c = base.act(copy.deepcopy(obs)), cand.act(copy.deepcopy(obs))
        rest = lambda x: {k: v for k, v in plain(x).items() if k != "pick"}
        if rest(a) != rest(c):
            other_diff += 1
        if a.get("pick") != c.get("pick"):
            pick_diff += 1
        if i in placed:
            choices, expect = placed[i]
            got = lambda x: choices[x["pick"]] if isinstance(x.get("pick"), int) else "none (choice 0 at expiry)"
            pa, pc = got(a), got(c)
            if expect == "identical":
                ok, text = pa == pc, "identical"
            else:
                ok, text = pc == expect and pa != pc, f"switches to {expect}"
            print(f"{obs['t']:6.1f}  {', '.join(choices):40}{pa:>16}{pc:>17}  {'ok  ' if ok else 'FAIL'} {text}")
            if not ok:
                failures.append(", ".join(choices))
            if trace is None and expect == "sensors" and ok:
                trace = (obs["t"], choices, a, c)
        elif "pick" in a or "pick" in c:
            failures.append(f"pick sent without an offer at t={obs['t']}")
    base.close()
    cand.close()
    print(f"\n{len(stream)} decisions, {len(placed)} with an offer: pick differs on {pick_diff}; "
          f"any other command differs on {other_diff}")
    if trace:
        t, choices, a, c = trace
        print(f"\ntrace at t={t:.1f}, offer {list(choices)}:")
        print(f"  baseline  pick {a.get('pick')} -> {choices[a['pick']]}   move {a.get('move')}  fire {a.get('fire')}")
        print(f"  candidate pick {c.get('pick')} -> {choices[c['pick']]}   move {c.get('move')}  fire {c.get('fire')}")
    base, cand = BotProcess(folder, et.HELLO), BotProcess(ROOT, et.HELLO)
    plain_diff = sum(plain(base.act(copy.deepcopy(obs))) != plain(cand.act(copy.deepcopy(obs)))
                     for obs in et.STREAM)
    base.close()
    cand.close()
    listed = sum(1 for obs in et.STREAM if obs.get("offer"))
    print(f"\nplain recording: an offer is listed on {listed} of {len(et.STREAM)} decisions; "
          f"answers differ on {plain_diff}")
    if plain_diff:
        failures.append("plain recording: answers differ")
    expected_switches = sum(1 for _, e in CASES if e != "identical")
    if pick_diff != expected_switches:
        failures.append(f"pick differs on {pick_diff} decisions, expected {expected_switches}")
    if other_diff:
        failures.append("a command other than pick changed")
    if failures:
        print("\nFAIL:", "; ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
