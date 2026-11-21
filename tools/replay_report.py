"""Run v4 and v5 over the same recorded observation stream: pickup decisions and opponent switching.

    py tools/replay_report.py [stream.jsonl or stream.jsonl.gz]

The recording does not react to our bot: the position, the pickups and the weapon slots are
whatever the recorded mech experienced. A take request here is therefore only a request.
Confirmed acquisitions are measured in tools/pickup_trial.py, where the world responds.
Standard library only.
"""
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mechfight as mf
from bot import Bot as V5
from bot_v4 import Bot as V4
from loot import PickupDetour
from targeting import StableTarget, SwitchCounter, game_mechs, nearest_mech

# Debug drawing has no consumer in a direct controller call.
mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None


def load(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    hello, observations = None, []
    with opener(path, "rt") as f:
        for line in f:
            message = json.loads(line)
            if message.get("type") == "hello":
                hello = message
            elif message.get("type") == "obs":
                observations.append(message)
    return hello, observations


def stream_facts(hello, observations):
    """What the recording itself contains, independent of either bot."""
    probe = PickupDetour(hello)
    eligible_ticks, eligible_ids, visible_ticks = 0, set(), 0
    nearest = None
    for obs in observations:
        visible_ticks += bool(obs["pickups"])
        for pickup in obs["pickups"]:
            distance = math.dist(obs["self"]["pos"][:2], pickup["pos"][:2])
            if nearest is None or distance < nearest[0]:
                nearest = (round(distance, 1), pickup["id"], pickup["kind"],
                           "ground" if probe.stand_point(pickup) else "off the ground map")
        found = probe.candidates(obs)
        eligible_ticks += bool(found)
        eligible_ids.update(key for _, key, _, _ in found)
    recorded_takes = [event for obs in observations for event in obs.get("events") or ()
                      if event.get("type") == "took"]
    return dict(decisions=len(observations), seconds=round(observations[-1]["t"] - observations[0]["t"], 1),
                visible_ticks=visible_ticks, eligible_ticks=eligible_ticks,
                eligible_ids=sorted(eligible_ids), recorded_takes=len(recorded_takes), nearest=nearest)


def replay(controller, hello, observations):
    bot = controller(hello)
    take_requests, requested = 0, set()
    for obs in observations:
        action = bot.act(obs)
        if action.get("take") is not None:
            take_requests += 1
            requested.add(action["take"])
    loot = getattr(bot, "loot", None)
    step = (observations[-1]["t"] - observations[0]["t"]) / max(1, len(observations) - 1)
    return dict(name=controller.name, take_requests=take_requests, requested_ids=sorted(requested),
                pursued=list(loot.pursued) if loot else [],
                pursuit_s=round(loot.pursuit_ticks * step, 1) if loot else 0.0,
                abandoned=dict(sorted(loot.abandoned.items())) if loot else {})


def opponent_report(observations):
    """How often each selection rule changes opponent on this stream. Both v4 and v5 use the
    nearest-mech rule, so this depends on the rule and the recording, not on the bot."""
    listed = [len(game_mechs(obs)) for obs in observations]
    print("opponent selection on this stream")
    print(f"  decisions with 0 / 1 / 2+ game mechs listed: "
          f"{listed.count(0)} / {listed.count(1)} / {sum(n >= 2 for n in listed)}")
    selector = StableTarget()
    for name, rule in (("nearest mech (v4, v5)", nearest_mech), ("stable target (candidate)", selector.select)):
        counter = SwitchCounter()
        for obs in observations:
            counter.record(obs, rule(obs))
        s = counter.summary()
        print(f"  {name:27} engagements {s['engagements']}  decisions engaged {s['engaged']}  "
              f"switches with previous still listed {s['switches']}  "
              f"A-B-A reversals within {SwitchCounter.REVERSAL_S:.0f} s {s['reversals']}  "
              f"changes forced by disappearance {s['forced']}")
    print("  Counts restart after every decision with no game mech listed.")
    print()


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "check/stream.jsonl.gz"
    hello, observations = load(path)
    facts = stream_facts(hello, observations)
    print(f"stream: {path.name}  {facts['decisions']} decisions over {facts['seconds']} s of match time")
    print(f"  decisions with any pickup listed:        {facts['visible_ticks']}")
    print(f"  decisions with an eligible pickup:       {facts['eligible_ticks']}"
          f"   (slot 1 empty, compatible, on the ground map, within {PickupDetour.MAX_ROUTE:.0f} m)")
    print(f"  distinct eligible pickup ids:            {facts['eligible_ids'] or 'none'}")
    if facts["nearest"]:
        distance, key, kind, where = facts["nearest"]
        print(f"  closest any listed pickup ever came:     {distance} m (id {key}, {kind}, {where})")
    print(f"  takes confirmed for the RECORDED mech:   {facts['recorded_takes']}   (not ours)")
    print()
    for controller in (V4, V5):
        row = replay(controller, hello, observations)
        print(row["name"])
        print(f"  distinct pickup ids pursued:             {len(row['pursued'])} {row['pursued'] or ''}")
        print(f"  time spent pursuing:                     {row['pursuit_s']} s")
        print(f"  take REQUESTS sent (unconfirmed):        {row['take_requests']} {row['requested_ids'] or ''}")
        print(f"  detours abandoned by reason:             "
              f"{', '.join(f'{k} {v}' for k, v in row['abandoned'].items()) or 'none'}")
    print()
    opponent_report(observations)
    print("Confirmed acquisitions: not measurable on a recording. See tools/pickup_trial.py.")


if __name__ == "__main__":
    main()
