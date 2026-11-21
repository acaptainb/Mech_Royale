"""Deterministic opponent-selection scenario: nearest-mech rule against the stable-target rule.

Two game mechs stand at almost the same distance and their ordering alternates slightly over
several decisions. Later phases check that the candidate still switches for a clearly closer
mech, switches after a slightly closer mech persists, and releases at once when its opponent
is no longer listed. This counts switches only. It says nothing about placement.
Standard library only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from targeting import StableTarget, SwitchCounter, nearest_mech

A, B = 3, 7


def mech(key, distance):
    return dict(id=key, kind="mech", pos=[distance, 0.0, 0.0])


def decision(tick, mechs):
    return dict(t=round(tick * 0.1, 1), self=dict(pos=[0.0, 0.0, 0.0]), mechs=mechs)


def scenario():
    """(phase, observation) pairs, 0.1 s apart."""
    frames, tick = [], 0

    def add(phase, count, make):
        nonlocal tick
        for k in range(count):
            frames.append((phase, decision(tick, make(k))))
            tick += 1

    drone = dict(id=104, kind="npc", pos=[20.0, 0.0, 0.0])
    # 1. A and B trade the lead by 0.8 m every decision for four seconds. A drone stands
    #    closer than either and must never be selected.
    add("alternating", 40, lambda k: [mech(A, 60.0 + (0.4 if k % 2 else -0.4)),
                                      mech(B, 60.0 - (0.4 if k % 2 else -0.4)), drone])
    # 2. B closes to 35 m: clearly closer, the candidate must follow on the first decision.
    add("clearly closer", 10, lambda k: [mech(A, 60.0), mech(B, 35.0)])
    # 3. A returns to 33 m, only 2 m closer than B, and stays there: a small but persistent
    #    lead must win after the hold time.
    add("persistent small lead", 20, lambda k: [mech(A, 33.0), mech(B, 35.0)])
    # 4. The held opponent (A) is no longer listed: release to B on the same decision.
    add("opponent disappears", 5, lambda k: [mech(B, 35.0)])
    # 5. Nothing listed, then both again: a new engagement, history cleared.
    add("gap", 5, lambda k: [])
    add("after gap", 5, lambda k: [mech(A, 50.0), mech(B, 50.5)])
    return frames


def run(rule, frames):
    counter, chosen = SwitchCounter(), []
    for phase, obs in frames:
        target = rule(obs)
        counter.record(obs, target)
        chosen.append((phase, obs["t"], target))
    return counter, chosen


def main():
    frames = scenario()
    baseline, picks_baseline = run(nearest_mech, frames)
    selector = StableTarget()
    candidate, picks = run(selector.select, frames)

    def in_phase(sequence, phase):
        return [target for name, _, target in sequence if name == phase]

    def changes(sequence, phase):
        ids = in_phase(sequence, phase)
        return sum(a != b for a, b in zip(ids, ids[1:]))

    print(f"{'phase':24}{'decisions':>10}{'baseline changes':>18}{'candidate changes':>19}")
    for phase in dict.fromkeys(name for name, _ in frames):
        print(f"{phase:24}{len(in_phase(picks, phase)):>10}{changes(picks_baseline, phase):>18}"
              f"{changes(picks, phase):>19}")
    print()
    for name, counter in (("baseline (nearest mech)", baseline), ("candidate (stable target)", candidate)):
        s = counter.summary()
        print(f"{name:27} switches {s['switches']:>3}   A-B-A reversals {s['reversals']:>3}   "
              f"forced by disappearance {s['forced']}   engagements {s['engagements']}")

    hold = round(StableTarget.HOLD_S / 0.1)
    lead = in_phase(picks, "persistent small lead")
    checks = [
        ("baseline flips every decision while the order alternates", changes(picks_baseline, "alternating") == 39),
        ("candidate holds one id while the order alternates", changes(picks, "alternating") == 0),
        ("neither rule ever selects the drone", all(t != 104 for _, _, t in picks + picks_baseline)),
        ("candidate follows a clearly closer mech at once", in_phase(picks, "clearly closer")[0] == B),
        ("candidate keeps B through a small lead for the hold time", lead[:hold] == [B] * hold),
        ("candidate takes the persistent small lead after the hold time", lead[hold] == A and lead[-1] == A),
        ("candidate releases on the decision its opponent disappears", in_phase(picks, "opponent disappears")[0] == B),
        ("disappearance is counted as forced, not as a switch", candidate.forced == 1 and baseline.forced == 1),
        ("no target while nothing is listed", set(in_phase(picks, "gap")) == {None}),
        ("the gap starts a new engagement", candidate.engagements == 2 and baseline.engagements == 2),
        ("candidate makes fewer switches and no reversals", candidate.switches < baseline.switches and candidate.reversals == 0),
    ]
    print()
    failed = [text for text, ok in checks if not ok]
    for text, ok in checks:
        print(("  ok    " if ok else "  FAIL  ") + text)
    if failed:
        sys.exit(1)
    print(f"\nPASS: {len(checks)} checks")


if __name__ == "__main__":
    main()
