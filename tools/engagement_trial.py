"""v5 and v6 on identical scripted observations, judged by the aim and fire each bot.act() emits.

    py tools/engagement_trial.py            scenarios, trace, recording comparison
    py tools/engagement_trial.py --heldout  fresh randomized encounters checked against rules

Each scenario is a fixed sequence of full observations built from the recorded template, so
the world does not react to either bot: this measures decisions, not outcomes. The opponent a
bot faces is read back from its emitted aim yaw (the listed opponent whose bearing matches
within 3 degrees). The held-out rules judge lines of fire with an exact test against the
prisms and terrain in arena/v2, independent of the bot's own cover raster. Standard library.
"""
import copy
import gzip
import json
import math
import random
import sys
import time
import traceback
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mechfight as mf
from bot import Bot as V6
from bot_v5 import Bot as V5
from cover import Cover

mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None

with gzip.open(ROOT / "check/stream.jsonl.gz", "rt") as f:
    HELLO = json.loads(next(f))
    STREAM = [json.loads(line) for line in f if '"obs"' in line]
TEMPLATE = STREAM[0]
WEAPONS = HELLO["config"]["weapons"]
COVER = Cover()
HOME = (-353.0, -158.0)  # open lawn: clear lines of fire in almost every direction
DT = 0.1


def ground(x, y):
    i = int((x - COVER.ox) / COVER.cell)
    j = int((y - COVER.oy) / COVER.cell)
    return COVER.ground[j * COVER.nx + i] / 100


def at(bearing_deg, distance, origin=HOME):
    a = math.radians(bearing_deg)
    x, y = origin[0] + distance * math.cos(a), origin[1] + distance * math.sin(a)
    return [round(x, 2), round(y, 2), round(ground(x, y), 2)]


def mech(key, bearing_deg, distance, aim_at_us=False, vel=(0.0, 0.0), charging=False,
         origin=HOME, aim_off_deg=90.0):
    pos = at(bearing_deg, distance, origin)
    toward_us = math.atan2(origin[1] - pos[1], origin[0] - pos[0])
    aim = toward_us if aim_at_us else toward_us + math.radians(aim_off_deg)
    return dict(id=key, kind="mech", pos=pos, vel=[vel[0], vel[1], 0.0], aim=[aim, 0.0], hp=1400,
                max_hp=1400, cubes=0, weapons=["gun"], charging=charging)


def npc(key, bearing_deg, distance):
    return dict(id=key, kind="npc", pos=at(bearing_deg, distance), vel=[0.0, 0.0, 0.0],
                aim=[0.0, 0.0], hp=350, max_hp=350)


def damaged(by, bearing_deg, weapon="gun", amount=45):
    return dict(type="damaged", amount=amount, weapon=weapon, by=by,
                bearing=None if bearing_deg is None else math.radians(bearing_deg))


def gun():
    return copy.deepcopy(TEMPLATE["self"]["weapons"][0])


def laser(charge):
    return dict(kind="laser", cooldown=0, charge=charge, stats=copy.deepcopy(WEAPONS["laser"]))


def frame(tick, mechs=(), events=(), in_zone=True, hp=1400, origin=HOME, weapons=None,
          pickups=()):
    obs = copy.deepcopy(TEMPLATE)
    obs.update(tick=2 * tick, t=round(tick * DT, 2), mechs=copy.deepcopy(list(mechs)),
               events=copy.deepcopy(list(events)), projectiles=[], crates=[], cubes=[],
               pickups=copy.deepcopy(list(pickups)), sounds=[], beams=[], drops=[], offer=None)
    obs["self"].update(pos=[origin[0], origin[1], ground(*origin)], vel=[0.0, 0.0, 0.0],
                       aim=[0.0, 0.0], hp=hp, max_hp=1400, grounded=True, in_zone=in_zone,
                       weapons=copy.deepcopy(weapons) if weapons else [gun(), None])
    obs["zone"].update(center=list(origin), radius=400 if in_zone else 50,
                       next_center=list(origin) if in_zone else [origin[0] + 300, origin[1]],
                       next_radius=250 if in_zone else 40, shrink_start=200, shrink_end=250)
    return obs


def clear_from(origin, bearing_deg, distance):
    spot = at(bearing_deg, distance, origin)
    return COVER.clear([origin[0], origin[1], ground(*origin) + 7], [spot[0], spot[1], spot[2] + 4.5])


def find_cover_spot():
    """An origin with a mech spot 40-80 m away behind solid cover, and a clear bearing
    from the same origin at 80-130 m for a second opponent."""
    from navigation import Navigator
    grid = Navigator()
    for index in range(0, len(grid.free), 7):
        if not grid.free[index]:
            continue
        origin = grid.point(index)
        for bearing in range(0, 360, 15):
            for distance in (40, 60, 80):
                spot = at(bearing, distance, origin)
                cell = grid.snap(spot)
                if cell is None or math.dist(grid.point(cell), spot[:2]) > 2:
                    continue
                if clear_from(origin, bearing, distance):
                    continue
                for other in range(0, 360, 10):
                    if abs((other - bearing + 180) % 360 - 180) < 30:
                        continue
                    if all(clear_from(origin, other, d) for d in (distance + 3, 120)):
                        return origin, bearing, distance, other
    raise RuntimeError("no cover spot")


COVER_SPOT = find_cover_spot()


# --- scenarios -----------------------------------------------------------------------------

def passive_beside_attacker():
    """A passive mech at 30 m, an attacker at 45 m hitting us every 0.4 s."""
    return [frame(k, [mech(3, 20, 30), mech(5, 120, 45, aim_at_us=True)],
                  [damaged(5, 120)] if k % 4 == 0 else [], hp=1400 - 45 * (k // 4 + 1))
            for k in range(30)]


def attacker_appears_while_holding():
    """v6 holds a passive mech at 30 m; from t=1.0 a mech at 45 m aims and hits every 0.4 s."""
    frames = []
    for k in range(30):
        listed = [mech(3, 20, 30)] + ([mech(5, 120, 45, aim_at_us=True)] if k >= 10 else [])
        frames.append(frame(k, listed, [damaged(5, 120)] if k >= 10 and (k - 10) % 4 == 0 else []))
    return frames


def trading_nearest():
    """Two passive mechs 60 m out whose distances swap by 0.8 m every decision."""
    return [frame(k, [mech(3, 30, 60.4 if k % 2 else 59.6), mech(7, 150, 59.6 if k % 2 else 60.4)])
            for k in range(40)]


def short_then_persistent_lead():
    """Held mech 3 at 60 m. Mech 7 (62 m) is 2.5 m closer for 0.5 s and falls back; later it
    is 2.5 m closer for good."""
    def distance_7(k):
        return 57.5 if 10 <= k < 15 or k >= 30 else 62.0
    return [frame(k, [mech(3, 30, 60.0), mech(7, 150, distance_7(k))]) for k in range(50)]


def disappearing_target():
    """We are on the attacker; after 1.5 s it is no longer listed; a passive mech at 40 m remains."""
    frames = []
    for k in range(30):
        listed = [mech(3, 200, 40)] + ([mech(5, 60, 50, aim_at_us=True)] if k < 15 else [])
        frames.append(frame(k, listed, [damaged(5, 60)] if k in (0, 4, 8, 12) else []))
    return frames


def attacker_killed():
    """The attacker at 40 m hits us until t=0.9; at t=1.0 we kill it. Nothing else is listed."""
    frames = []
    for k in range(30):
        listed = [mech(5, 120, 40, aim_at_us=True)] if k < 10 else []
        events = [damaged(5, 120)] if k < 10 and k % 3 == 0 else []
        if k == 10:
            events = [dict(type="hit", target=5, amount=45, weapon="gun"), dict(type="kill", target=5)]
        frames.append(frame(k, listed, events))
    return frames


def zone_damage_only():
    """Outside the zone, taking zone damage, nobody in sight."""
    return [frame(k, [], [damaged(None, None, weapon="zone", amount=2)], in_zone=False,
                  hp=1400 - 2 * k) for k in range(20)]


def zone_damage_with_far_passive():
    """Zone damage while a passive mech walks across our view 150 m away."""
    return [frame(k, [mech(3, 75, 150, vel=(11.0, 0.0))],
                  [damaged(None, None, weapon="zone", amount=2)], in_zone=False, hp=1400 - 2 * k)
            for k in range(20)]


def zone_damage_with_unseen_attacker():
    """An unseen mech hits us once from 250 deg while zone damage ticks on every decision."""
    return [frame(k, [], ([damaged(9, 250)] if k == 0 else []) + [damaged(None, None, weapon="zone", amount=2)],
                  in_zone=False, hp=1400 - 2 * k) for k in range(60)]


def first_encounter_far_crossing():
    """One mech appears 150 m away walking across our line of fire, not aiming at us."""
    return [frame(k, [mech(3, 75, 150, vel=(11.0, 0.0))]) for k in range(20)]


def first_encounter_far_aiming():
    """One mech 150 m away walking across, but its weapon points at us."""
    return [frame(k, [mech(3, 75, 150, aim_at_us=True, vel=(11.0, 0.0))]) for k in range(20)]


def first_encounter_far_approaching():
    """One passive mech 150 m away walking straight at us: unled shots land."""
    a = math.radians(75)
    return [frame(k, [mech(3, 75, 150, vel=(-11.0 * math.cos(a), -11.0 * math.sin(a)))])
            for k in range(20)]


def first_encounter_close():
    """One passive mech 35 m away, inside proximity range."""
    return [frame(k, [mech(3, 75, 35, vel=(11.0, 0.0))]) for k in range(20)]


def charging_at_someone_else():
    """A mech 150 m away crossing, charging a laser with its torso 90 deg away from us."""
    return [frame(k, [mech(3, 75, 150, vel=(11.0, 0.0), charging=True)]) for k in range(20)]


def committed_after_hit():
    """A passive crossing mech 150 m away (unled shots would miss) that we hit at t=0."""
    return [frame(k, [mech(3, 75, 150, vel=(11.0, 0.0))],
                  [dict(type="hit", target=3, amount=45, weapon="gun")] if k == 0 else [])
            for k in range(50)]


def behind_cover():
    """A mech listed behind a building (tracked from memory)."""
    origin, bearing, distance, _ = COVER_SPOT
    return [frame(k, [mech(3, bearing, distance, origin=origin)], origin=origin) for k in range(20)]


def covered_passive_and_clear_attacker():
    """A passive mech behind cover, and a clear mech 120 m away aiming at us and hitting us."""
    origin, bearing, distance, other = COVER_SPOT
    return [frame(k, [mech(3, bearing, distance, origin=origin),
                      mech(5, other, 120, aim_at_us=True, origin=origin)],
                  [damaged(5, other)] if k % 4 == 0 else [], origin=origin) for k in range(30)]


def covered_passive_and_clear_passive():
    """A passive mech behind cover and a passive mech in the open 3 m farther away."""
    origin, bearing, distance, other = COVER_SPOT
    return [frame(k, [mech(3, bearing, distance, origin=origin),
                      mech(7, other, distance + 3, origin=origin)], origin=origin) for k in range(20)]


def laser_charging_into_cover():
    """We hold a laser at 0.4 s of charge when our opponent is only listed behind cover."""
    origin, bearing, distance, _ = COVER_SPOT
    return [frame(k, [mech(3, bearing, distance, origin=origin, aim_at_us=True)], origin=origin,
                  weapons=[gun(), laser(0.4)]) for k in range(10)]


def mech_on_bridge_deck():
    """We stand under the 6.6-8.6 m deck west of the Oval; a mech stands on it 4 m away,
    listed from memory. Our line to it crosses about 2 m of deck."""
    origin = (-112.2, -32.08)
    above = dict(mech(3, 180, 4, origin=origin, aim_at_us=True), pos=[-116.2, -32.1, 8.59])
    return [frame(k, [above], origin=origin) for k in range(10)]


def npc_attacker():
    """A drone 30 m away is shooting at us; no mech in sight."""
    return [frame(k, [npc(104, 300, 30)], [damaged(104, 300, weapon="npc", amount=25)] if k % 10 == 0 else [])
            for k in range(20)]


def drone_attacker_and_mech_aiming():
    """A drone 15 m away hit us once; a mech 60 m away aims at us."""
    return [frame(k, [npc(104, 0, 15), mech(3, 100, 60, aim_at_us=True)],
                  [damaged(104, 0, weapon="npc", amount=25)] if k == 0 else []) for k in range(20)]


def distant_passive_npc():
    """A passive drone 120 m away; nobody has hit us."""
    return [frame(k, [npc(104, 300, 120)]) for k in range(20)]


def unseen_attacker():
    """Hit from behind by a mech that is not listed; the evidence ages out after 5 s."""
    return [frame(k, [], [damaged(9, 250)] if k == 0 else [], hp=1355) for k in range(70)]


def unseen_attacker_with_far_passive():
    """An unseen mech hits us from 250 deg every 0.4 s while a passive mech crosses 150 m away."""
    return [frame(k, [mech(3, 75, 150, vel=(11.0, 0.0))], [damaged(9, 250)] if k % 4 == 0 else [])
            for k in range(30)]


def mortar_from_unseen_shooter():
    """A shell from an unseen shooter bursts beside us; its bearing is the blast point."""
    return [frame(k, [], [damaged(9, 0, weapon="mortar", amount=120)] if k == 0 else [])
            for k in range(20)]


def unseen_attacker_during_pickup():
    """Hit once from behind with a pickup 20 m ahead. v5 relocates, then walks to the pickup
    facing it; v6 must not take that facing away."""
    spot = at(0, 20)
    item = dict(id=8100, kind="laser", pos=[spot[0], spot[1], spot[2] + 0.1])
    return [frame(k, [], [damaged(9, 250)] if k == 0 else [], pickups=[item]) for k in range(60)]


def attacker_evidence_expires():
    """An attacker at 50 m hit us at t=0 only; a passive mech at 40 m. After 5 s the passive
    mech is closer by more than the margin and takes over."""
    return [frame(k, [mech(3, 20, 40), mech(5, 120, 50)], [damaged(5, 120)] if k == 0 else [])
            for k in range(80)]


OUT_OF_RANGE_BEARING = next(b for b in range(0, 360, 5) if clear_from(HOME, b, 240))


def out_of_range():
    """A remembered mech 240 m away on a clear line, beyond gun range, aiming at us."""
    return [frame(k, [mech(3, OUT_OF_RANGE_BEARING, 240, aim_at_us=True)]) for k in range(10)]


def existing_two_mech_scenario():
    """tools/target_trial.py's scenario rebuilt as full observations around HOME."""
    sys.path.insert(0, str(ROOT / "tools"))
    import target_trial
    frames = []
    for k, (_, obs) in enumerate(target_trial.scenario()):
        listed = []
        for other in obs["mechs"]:
            distance = other["pos"][0]
            if other["kind"] == "npc":
                listed.append(npc(other["id"], 0, distance))
            else:
                listed.append(mech(other["id"], 30 if other["id"] == 3 else 150, distance))
        frames.append(frame(k, listed))
    return frames


def yaw_is(row, bearing_deg):
    return row["aim"] is not None and abs((row["aim"][0] - math.radians(bearing_deg) + math.pi)
                                          % math.tau - math.pi) < 1e-6


# name -> (builder, check on the v6 rows, plain statement of the expectation)
SCENARIOS = {
    "passive beside attacker": (passive_beside_attacker,
        lambda r: all(row["target"] == 5 and row["fire"] for row in r), "shoots the attacker every decision"),
    "attacker appears while holding passive": (attacker_appears_while_holding,
        lambda r: all(row["target"] == 3 for row in r[:10]) and all(row["target"] == 5 and row["fire"] for row in r[10:]),
        "switches to the attacker on the decision its first hit lands"),
    "two opponents trading nearest": (trading_nearest,
        lambda r: switches(r) == 0, "holds one opponent"),
    "short lead, then persistent lead": (short_then_persistent_lead,
        lambda r: all(row["target"] == 3 for row in r[:40]) and all(row["target"] == 7 for row in r[40:]),
        "ignores a 0.5 s lead; takes a persistent one after exactly 1 s"),
    "disappearing target": (disappearing_target,
        lambda r: all(row["target"] == 5 for row in r[:15]) and r[15]["target"] == 3,
        "shoots the attacker, then the remaining close mech on the decision the attacker vanishes"),
    "attacker killed": (attacker_killed,
        lambda r: all(row["same_aim"] for row in r[10:]), "no lingering turn after the kill: v5's aim"),
    "zone damage only": (zone_damage_only,
        lambda r: not any(row["fire"] for row in r) and all(row["same_aim"] for row in r),
        "does nothing different from v5"),
    "zone damage, far passive crossing": (zone_damage_with_far_passive,
        lambda r: not any(row["fire"] for row in r) and all(row["target"] == 3 for row in r),
        "zone damage is not an attacker: faces the mech, holds fire"),
    "zone damage, unseen attacker": (zone_damage_with_unseen_attacker,
        lambda r: all(yaw_is(row, 250) for row in r[:50]) and all(row["same_aim"] for row in r[52:]),
        "zone ticks do not displace the turn toward the attacker"),
    "first encounter, far, crossing": (first_encounter_far_crossing,
        lambda r: not any(row["fire"] for row in r) and all(row["target"] == 3 for row in r),
        "faces it and keeps its magazine"),
    "first encounter, far, aiming at us": (first_encounter_far_aiming,
        lambda r: all(row["fire"] for row in r), "shoots first"),
    "first encounter, far, approaching": (first_encounter_far_approaching,
        lambda r: all(row["fire"] for row in r), "shoots: unled shots land"),
    "first encounter, close": (first_encounter_close,
        lambda r: all(row["fire"] for row in r), "shoots inside proximity range"),
    "charging at someone else": (charging_at_someone_else,
        lambda r: not any(row["fire"] for row in r) and "aiming at us" not in {row["reason"] for row in r},
        "a laser charging elsewhere is not a threat to us"),
    "committed after our hit": (committed_after_hit,
        lambda r: all(row["fire"] for row in r[:31]) and not any(row["fire"] for row in r[32:]),
        "keeps shooting for 3 s after hitting it, then holds"),
    "remembered behind cover": (behind_cover,
        lambda r: not any(row["fire"] for row in r) and all(row["target"] == 3 for row in r),
        "faces it, holds fire"),
    "covered passive, clear attacker": (covered_passive_and_clear_attacker,
        lambda r: all(row["target"] == 5 and row["fire"] for row in r),
        "the clear attacker wins over the hidden passive contact"),
    "covered passive, clear passive": (covered_passive_and_clear_passive,
        lambda r: all(row["target"] == 7 for row in r), "prefers the opponent it can shoot"),
    "laser charging into cover": (laser_charging_into_cover,
        lambda r: all(row["fire_raw"] == [False, True] for row in r),
        "keeps the charging laser held instead of releasing it into the wall"),
    "mech on a bridge deck above us": (mech_on_bridge_deck,
        lambda r: all(row["reason"] == "hold: behind cover" and not row["fire"] for row in r),
        "does not shoot into a 2 m bridge deck"),
    "NPC attacker": (npc_attacker,
        lambda r: all(row["target"] == 104 and row["fire"] for row in r), "shoots back"),
    "drone attacker, mech aiming at us": (drone_attacker_and_mech_aiming,
        lambda r: all(row["target"] == 3 and row["fire"] for row in r), "the mech outranks the drone"),
    "distant passive NPC": (distant_passive_npc,
        lambda r: not any(row["fire"] for row in r) and all(row["same_aim"] for row in r),
        "ignores it, like v5"),
    "unseen attacker behind us": (unseen_attacker,
        lambda r: all(yaw_is(row, 250) and not row["fire"] for row in r[:50])
        and all(row["same_aim"] for row in r[52:]),
        "turns toward the damage bearing for 5 s, then v5's aim"),
    "unseen attacker, far passive listed": (unseen_attacker_with_far_passive,
        lambda r: all(yaw_is(row, 250) and not row["fire"] for row in r),
        "a passive contact does not cancel the turn toward the attacker"),
    "mortar from unseen shooter": (mortar_from_unseen_shooter,
        lambda r: all(row["same_aim"] for row in r), "a blast bearing is not a direction to turn"),
    "unseen attacker during pickup": (unseen_attacker_during_pickup,
        lambda r: any(row["detour"] for row in r) and all(row["same_aim"] for row in r if row["detour"]),
        "keeps v5's face-the-pickup aim during the detour"),
    "attacker evidence expires": (attacker_evidence_expires,
        lambda r: all(row["target"] == 5 for row in r[:50]) and r[-1]["target"] == 3,
        "stays on the attacker for 5 s, then the closer passive mech"),
    "out of range": (out_of_range,
        lambda r: all(not row["fire"] and row["reason"] == "hold: out of range" for row in r),
        "holds fire beyond gun range (clear line, aiming at us)"),
    "existing two-mech scenario": (existing_two_mech_scenario,
        lambda r: switches(r) <= 3, "switches as rarely as the stable-target rule"),
}


def identify(action, obs):
    """Which listed opponent the emitted aim points at, or None."""
    me = obs["self"]["pos"]
    yaw = (action.get("aim") or [None])[0]
    if yaw is None:
        return None
    best = None
    for other in obs["mechs"]:
        bearing = math.atan2(other["pos"][1] - me[1], other["pos"][0] - me[0])
        off = abs((yaw - bearing + math.pi) % math.tau - math.pi)
        if off < math.radians(3) and (best is None or off < best[0]):
            best = (off, other["id"])
    return best[1] if best else None


def switches(rows):
    ids = [row["target"] for row in rows]
    return sum(1 for a, b in zip(ids, ids[1:]) if a is not None and b is not None and a != b)


def play(controller, frames):
    bot = controller(HELLO)
    rows = []
    for obs in frames:
        action = bot.act(copy.deepcopy(obs))
        raw = list(action.get("fire") or [False, False])
        engagement = getattr(bot, "engagement", None)
        dodge = getattr(bot, "dodge", None)  # v8 onward: a sideways step may own the move
        rows.append(dict(t=obs["t"], target=identify(action, obs), fire=any(raw), fire_raw=raw,
                         aim=action.get("aim"), detour=bot.loot.target is not None,
                         dodging=bool(dodge and dodge.active),
                         rest={key: action.get(key) for key in UNCHANGED},
                         reason=engagement.decision.get("reason") if engagement else None))
    return rows


# Everything a v6 action must share with v5: only aim and fire may differ.
UNCHANGED = ("move", "boost", "jump", "take", "reload", "pick", "drop")


def compare(frames):
    old, new = play(V5, frames), play(V6, frames)
    for a, b in zip(old, new):
        b["same_aim"] = (a["aim"] is not None and b["aim"] is not None
                         and all(abs(p - q) < 1e-9 for p, q in zip(a["aim"], b["aim"])))
        b["differs"] = a["target"] != b["target"] or a["fire_raw"] != b["fire_raw"] or not b["same_aim"]
        # Movement may differ only while a later version's dodge owns the move.
        b["moved_differently"] = a["rest"] != b["rest"] and not b["dodging"]
    return old, new


def scenarios():
    failures, total, differing, reasons, moved = [], 0, 0, {}, 0
    print(f"{'scenario':40}{'decisions':>9}{'v5 fire':>8}{'v6 fire':>8}{'v5 sw':>6}{'v6 sw':>6}"
          f"{'differ':>7}  v6 expectation")
    for name, (build, check, expectation) in SCENARIOS.items():
        frames = build()
        old, new = compare(frames)
        moved_here = sum(row["moved_differently"] for row in new)
        moved += moved_here
        ok = check(new) and not moved_here
        diff = sum(row["differs"] for row in new)
        total += len(frames)
        differing += diff
        for row in new:
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
        print(f"{name:40}{len(frames):>9}{sum(r['fire'] for r in old):>8}{sum(r['fire'] for r in new):>8}"
              f"{switches(old):>6}{switches(new):>6}{diff:>7}  {'ok  ' if ok else 'FAIL'} {expectation}")
        if not ok:
            failures.append(name)
    print(f"\nv6 made a different aim or fire decision on {differing} of {total} scripted decisions;"
          f" move, boost, jump, take, reload, pick or drop differed on {moved}.")
    print("v6 decision reasons across all scenarios:",
          ", ".join(f"{k} {v}" for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])))
    return failures


def recording():
    old, new = compare(STREAM)
    listed = [k for k, obs in enumerate(STREAM) if obs["mechs"]]
    moved = sum(row["moved_differently"] for row in new)
    diff_fire = sum(old[k]["fire_raw"] != new[k]["fire_raw"] for k in range(len(STREAM)))
    diff_aim = sum(old[k]["aim"] != new[k]["aim"] for k in range(len(STREAM)))
    reasons = {}
    for k in listed:
        reasons[new[k]["reason"]] = reasons.get(new[k]["reason"], 0) + 1
    print(f"\nrecording: {len(STREAM)} decisions, a mech listed in {len(listed)} (always the same one)")
    print(f"  fire decisions v5 {sum(r['fire'] for r in old)}  v6 {sum(r['fire'] for r in new)};"
          f"  decisions with a different fire command {diff_fire}, different aim {diff_aim},"
          f" anything else different {moved} (dodge decisions excluded: {sum(r['dodging'] for r in new)})")
    print("  v6 reasons while the mech is listed:", ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())))
    bot, worst, t0 = V6(HELLO), 0.0, time.perf_counter()
    for obs in STREAM:
        start = time.perf_counter()
        bot.act(copy.deepcopy(obs))
        worst = max(worst, time.perf_counter() - start)
    print(f"  v6 decision time on this machine: mean {(time.perf_counter() - t0) / len(STREAM) * 1e3:.2f} ms,"
          f" worst {worst * 1e3:.2f} ms")
    return moved


def trace():
    frames = attacker_appears_while_holding()
    old, new = compare(frames)
    print("\ntrace: passive mech 3 at 30 m; from t=1.0 mech 5 at 45 m aims at us and hits every 0.4 s")
    print("    t   event      v5 faces / fires      v6 faces / fires   v6 reason")
    for k in range(8, 13):
        event = "5 hits us" if frames[k]["events"] else ""
        print(f"  {frames[k]['t']:4.1f}   {event:9}  mech {old[k]['target']} / {str(old[k]['fire']):5}"
              f"         mech {new[k]['target']} / {str(new[k]['fire']):5}   {new[k]['reason']}")


# --- exact line-of-fire oracle for the held-out rules ---------------------------------------

class Exact:
    """Point-in-polygon against every prism plus bilinear terrain, sampled every 0.5 m."""

    def __init__(self):
        world = json.loads((ROOT / "arena/v2/world.json").read_text())
        terrain = world["terrain"]
        self.t = terrain
        self.heights = array("h")
        self.heights.frombytes((ROOT / "arena/v2" / terrain["file"]).read_bytes())
        if sys.byteorder == "big":
            self.heights.byteswap()
        self.prisms = []
        for prism in world["prisms"]:
            xs, ys = prism["ring"][::2], prism["ring"][1::2]
            rings = [list(zip(xs, ys))] + [list(zip(h[::2], h[1::2])) for h in prism["holes"]]
            self.prisms.append((min(xs), max(xs), min(ys), max(ys), prism["base"], prism["top"],
                                prism["kind"], rings))

    def terrain(self, x, y):
        t = self.t
        u = min(t["nx"] - 1.001, max(0.0, x - t["minX"]))
        v = min(t["ny"] - 1.001, max(0.0, y - t["minY"]))
        i, j = int(u), int(v)
        fu, fv = u - i, v - j
        k = j * t["nx"] + i
        h = self.heights
        low = h[k] * (1 - fu) + h[k + 1] * fu
        high = h[k + t["nx"]] * (1 - fu) + h[k + t["nx"] + 1] * fu
        return (low * (1 - fv) + high * fv) * t["scale"]

    @staticmethod
    def inside(rings, x, y):
        hit = False
        for ring in rings:
            for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
                if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                    hit = not hit
        return hit

    def solid(self, start, end):
        """Metres of solid matter between a muzzle and a target centre, and whether a bridge is hit."""
        length = math.dist(start, end)
        metres, bridge, s = 0.0, False, 3.0
        while s <= length - 2.5:
            f = s / length
            x, y, z = (start[i] + f * (end[i] - start[i]) for i in range(3))
            blocked = z < self.terrain(x, y)
            if not blocked:
                for x0, x1, y0, y1, base, top, kind, rings in self.prisms:
                    if x0 <= x <= x1 and y0 <= y <= y1 and base <= z <= top and self.inside(rings, x, y):
                        blocked = True
                        bridge = bridge or kind == "bridge"
                        break
            metres += 0.5 if blocked else 0.0
            s += 0.5
        return metres, bridge

    def category(self, origin, other):
        me = [origin[0], origin[1], ground(*origin) + 7]
        metres, bridge = self.solid(me, [other["pos"][0], other["pos"][1], other["pos"][2] + 4.5])
        if metres == 0 and not bridge:
            return "clear"
        if metres >= 6.0 or bridge:
            return "blocked"
        return "ambiguous"


RULES = [
    "R0 act() never raises and the action is valid JSON",
    "R1 never shoot a drone that has not hit us",
    "R2 a recent clear attacker beats passive mechs at most 25 m closer",
    "R3 the emitted aim matches the chosen opponent",
    "R4 prompt release: never the vanished opponent, and a listed one or the attacker bearing next",
    "R5 no fire without a chosen opponent",
    "R6 shoot a chosen mech within proximity range on a clear line",
    "R7 never shoot through solid cover",
    "R8 a clear passive mech beats a blocked passive one at most 10 m closer",
    "R9 never shoot beyond gun range",
]


def heldout(seed, cases=400):
    """Random encounters around HOME, on seeds not used while choosing any constant."""
    rng = random.Random(seed)
    exact = Exact()
    failures, counts, worst, categories = {}, {}, 0.0, {}

    def fail(rule, detail):
        failures.setdefault(rule, []).append(detail)

    for case in range(cases):
        others = []
        for key in range(rng.randint(1, 3)):
            speed = rng.choice([0.0, 6.0, 11.7])
            heading = rng.uniform(0, math.tau)
            others.append(mech(10 + key, rng.uniform(0, 360), rng.uniform(15, 260),
                               aim_at_us=rng.random() < 0.3,
                               vel=(speed * math.cos(heading), speed * math.sin(heading)),
                               charging=rng.random() < 0.1, aim_off_deg=rng.uniform(25, 180)))
        if rng.random() < 0.3:
            others.append(npc(100 + case % 50, rng.uniform(0, 360), rng.uniform(20, 120)))
        truth = {o["id"]: exact.category(HOME, o) for o in others}
        aiming = {o["id"] for o in others if o["kind"] == "mech"
                  and abs((o["aim"][0] - math.atan2(HOME[1] - o["pos"][1], HOME[0] - o["pos"][0]) + math.pi)
                          % math.tau - math.pi) < 1e-9}
        for value in truth.values():
            categories[value] = categories.get(value, 0) + 1
        attacker = rng.choice(others + [None, None])
        hit_ticks = sorted(rng.sample(range(0, 20), rng.randint(1, 4))) if attacker else []
        vanish = rng.choice([None, 10, 15])
        gone = rng.choice(others)["id"] if vanish is not None else None
        bot, last_hit, first_hit = V6(HELLO), None, None
        for k in range(25):
            listed = [o for o in others if not (gone == o["id"] and k >= vanish)]
            events = []
            if attacker and k in hit_ticks:
                b = math.degrees(math.atan2(attacker["pos"][1] - HOME[1], attacker["pos"][0] - HOME[0]))
                events.append(damaged(attacker["id"], b, weapon="npc" if attacker["kind"] == "npc" else "gun"))
                last_hit = k * DT
                first_hit = first_hit if first_hit is not None else k * DT
            if rng.random() < 0.05:
                events.append(damaged(None, None, weapon="zone", amount=2))
            obs = frame(k, listed, events)
            start = time.perf_counter()
            try:
                action = bot.act(copy.deepcopy(obs))
                json.dumps(action)
            except Exception:
                fail(RULES[0], (case, k, traceback.format_exc(limit=1)))
                break
            worst = max(worst, time.perf_counter() - start)
            decision = bot.engagement.decision
            chosen = decision["target"]
            fired = any(action.get("fire") or [])
            counts[decision["reason"]] = counts.get(decision["reason"], 0) + 1
            listed_ids = {o["id"] for o in listed}
            me = obs["self"]["pos"]
            target = next((o for o in listed if o["id"] == chosen), None)
            distance = math.dist(target["pos"], me) if target else None
            recent_attack = attacker is not None and last_hit is not None and obs["t"] - last_hit <= 5.0
            # R1
            if target and target["kind"] == "npc" and fired and not (
                    recent_attack and attacker["id"] == target["id"]):
                fail(RULES[1], (case, k))
            # R2
            if (attacker and attacker["kind"] == "mech" and last_hit is not None
                    and obs["t"] - last_hit <= 4.0 and obs["t"] - first_hit >= 1.05
                    and attacker["id"] in listed_ids and truth[attacker["id"]] == "clear"
                    and math.dist(attacker["pos"], me) <= 230):
                d_att = math.dist(attacker["pos"], me)
                rest = [o for o in listed if o["kind"] == "mech" and o["id"] != attacker["id"]]
                closer = [o for o in rest if math.dist(o["pos"], me) < d_att]
                if (rest and not (aiming & {o["id"] for o in rest})
                        and all(d_att - math.dist(o["pos"], me) <= 25 for o in closer)
                        and chosen != attacker["id"]):
                    fail(RULES[2], (case, k, chosen))
            # R3
            if chosen is not None and (chosen not in listed_ids or identify(action, obs) != chosen):
                fail(RULES[3], (case, k))
            # R4
            if vanish is not None and k == vanish:
                if chosen == gone:
                    fail(RULES[4], (case, k, "kept"))
                elif chosen is None and decision["reason"] != "turn toward unseen attacker" and any(
                        o["kind"] == "mech" or (recent_attack and o["id"] == attacker["id"]) for o in listed):
                    fail(RULES[4], (case, k, decision["reason"]))
            # R5
            if fired and chosen is None:
                fail(RULES[5], (case, k))
            # R6
            if (target and target["kind"] == "mech" and distance <= 45 and truth[chosen] == "clear"
                    and not fired):
                fail(RULES[6], (case, k))
            # R7
            if target and fired and truth[chosen] == "blocked":
                fail(RULES[7], (case, k, chosen))
            # R8
            mechs_now = [o for o in listed if o["kind"] == "mech"]
            calm = not recent_attack and not (aiming & {o["id"] for o in mechs_now})
            if calm and (vanish is None or k < vanish):
                for blocked in (o for o in mechs_now if truth[o["id"]] == "blocked"):
                    for open_ in (o for o in mechs_now if truth[o["id"]] == "clear"):
                        gap = math.dist(open_["pos"], me) - math.dist(blocked["pos"], me)
                        if gap <= 10 and math.dist(open_["pos"], me) <= 230 and chosen == blocked["id"]:
                            fail(RULES[8], (case, k))
            # R9
            if target and fired and distance > 230:
                fail(RULES[9], (case, k))
    print(f"held-out: {cases} randomized encounters, seed {seed}; worst decision {worst * 1e3:.2f} ms;"
          f" exact lines of fire: {', '.join(f'{k} {v}' for k, v in sorted(categories.items()))}")
    print("  v6 reasons:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    for rule in RULES:
        bad = failures.get(rule, [])
        print(f"  {'ok  ' if not bad else 'FAIL'} {rule}" + (f": {len(bad)} decisions, e.g. {bad[:3]}" if bad else ""))
    return sum(len(v) for v in failures.values())


def main():
    if "--heldout" in sys.argv:
        bad = heldout(902117) + heldout(55313)
        sys.exit(1 if bad else 0)
    failures = scenarios()
    trace()
    if recording():
        failures.append("recording: v6 changed something besides aim and fire")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS: every scenario matched its v6 expectation.")


if __name__ == "__main__":
    main()
