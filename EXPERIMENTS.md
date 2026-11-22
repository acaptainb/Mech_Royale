# Experiment log

Practice scoring is 48 matches against 15 house bots, mean of (16 - place); the track page lists the kit's starter bot at 1.15. Local tests catch mistakes; only official practice scores judge placement. A score is entered only after you report it from the Buildathon page.

## Scoreboard

Official practice scores as you report them. V7 to V12 each branch from the 2.08 baseline (`1a0ca39`) and change one behaviour, so each delta below is measured against that same parent.

| Version | Branch | Candidate SHA | Parent SHA | Official score | Delta vs parent |
| --- | --- | --- | --- | --- | --- |
| v4 | `main` | `124101fe2402a13451921e0d97582adc5b3aab17` | none | 1.56 | n/a |
| v5 | `v5-early-loot` | `dbc4cc2da927ddcc3a48e5191c3c070294e2ab72` | `124101f` | 1.75 | +0.19 |
| v6 | `v6-selective-engagement` | `1a0ca394d26fe5e97c60dbac2ded343a2694b114` | `dbc4cc2` | 2.08 (baseline for v7-v12) | +0.33 |
| v7 | `v7-laser-release` | `f69d39c2c32f92e533568ce27854cf5efd0e04ca` | `1a0ca39` | 2.19 | +0.11 |
| v8 | `v8-bullet-dodge` | `4588e6b826e3ea923ab10697160e5c7658a64179` | `1a0ca39` | **2.50** | +0.42 |
| v9 | `v9-return-recovery` | this commit (tag `v9-candidate`) | `1a0ca39` | pending | pending |

## Log

| Version | Parent SHA | Candidate SHA | Hypothesis (the one change) | Activation (local) | Local result | Official score | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v4 | none | `124101f` (tag `v4-scored`) | health-aware objectives: supply drop when damaged, relocation after damage | not measured | replay 300/300; 12 objective checks | 1.56 | superseded by v5 |
| v5 | `124101f` | `dbc4cc2` (tag `v5-candidate`) | detouring for one reachable ground weapon while slot 1 is empty improves placement | 40 detours in 110 closed-loop runs; 0 on the recording | acquired 40/40 where intended; no extra zone misses | 1.75 (+0.19) | kept; superseded by v6 |
| stable target (measurement) | `dbc4cc2` | `97d49a9` (PR #2) | the nearest-mech rule oscillates between opponents | 0: the recording never lists two mechs | 0 switches on the recording; 40 vs 2 in the two-mech scenario | not submitted | rule reused inside v6 |
| no drop pursuit (parked) | `dbc4cc2` | `0733dd7` (branch `exp/no-drop-pursuit`) | travelling to or waiting at supply drops costs placement | objective checks only | not container-checked | not submitted | parked |
| v6 | `dbc4cc2` | `1a0ca39` (tag `v6-candidate`) | facing the opponent that is fighting us and holding fire when shots cannot land improves placement | aim or fire differs on 556 of 965 scripted decisions | 30/30 scenarios; held-out rules pass; movement identical to v5 | 2.08 (+0.33) | keep: baseline for v7-v12 |
| v7 | `1a0ca39` | `f69d39c` (tag `v7-candidate`) | releasing a full laser charge the moment the beam is on target improves placement | 4 of 7 entrypoint scenarios; 0 on the recording | first beam on target 0.0-0.8 s vs 1.9-2.7 s | 2.19 (+0.11) | keep |
| v8 | `1a0ca39` | `4588e6b` (tag `v8-candidate`) | one brief sideways step from a bullet on course cuts hits taken | 1 dodge on the recording | hits -8% / -7% in the reactive trial; 0 zone exits | **2.50 (+0.42)** | **keep: best score so far** |
| v9 | `1a0ca39` | this commit (tag `v9-candidate`) | one cooled-down recovery attempt when the zone return stops gaining ground gets a jammed mech back to safety | 0 on the recording and on every control; 1-2 attempts per stuck episode | stuck episodes reach safety in 5-12 s where the baseline stays out 30 s; controls identical | pending | pending your score |

## v6: selective engagement

The change replaces the inherited nearest-mech rule (fire both triggers at whichever mech is closest) with `targeting.Engagement`, wired in at the end of `bot.py`'s `act()`. Movement, pickup routing and how the triggers are pressed are v5's.

- **Choice of opponent:** each listed mech scores its distance, 35 m closer if it hit us in the last 5 s, 15 m closer if its torso pointed at us in the last 1 s, 20 m farther if solid cover blocks our line. A shootable mech that is fighting us ranks ahead of everything else. A drone is a candidate only after it hits us, and then 60 m farther. `StableTarget` keeps the current choice through small changes and switches after a 1 s persistent lead, at once for a clear lead, and on the same decision the opponent stops being listed.
- **Shooting:** only at the chosen opponent, only with a clear line (`cover.py` on the 2 m `cover.i16` raster built from `arena/v2`) and within weapon range, and only when it is fighting us, is within 45 m, or unled bullets would land. A charging laser is kept held through a hold, so it is never released into a wall.
- **Unseen attacker:** when a recent attacker is not listed and the chosen opponent is neither fighting us nor within 45 m, the torso turns toward the damage bearing, without firing, except during a pickup detour. Zone damage has no attacker. Mortar damage keeps its attacker id but not its bearing, which is the blast point. A kill clears the victim's evidence.

Evidence (`py tools/engagement_trial.py`, `--heldout`, `py tools/engagement_probe.py`):

- The independent review raised 26 findings and confirmed 20. All were fixed or turned into checks; the 6 refuted ones are documented in the review run.
- Recording: no pickup is pursued and only one mech is ever listed. v6 holds fire on 54 decisions where the raster says a building blocks the line (no shot landed by either side in that window) and on 8 where a crossing mech at about 147 m would dodge unled bullets. The raster calls all 37 lines before a landed shot clear.
- Timing: 0 late answers, p99 1.1 ms on Windows; worst case with 15 opponents at 200 m is 2.5 ms. The CI conformance job runs the restricted linux/amd64 container, and the probe asserts that the container's bot aims at an attacker rather than a closer passive mech.

## v9: zone-return recovery (single change on `1a0ca39`)

**The known case:** since v4, `bot.py` replaces `first_run`'s obstacle recovery with the straight waypoint direction whenever the zone return is active. A mech pressed against an obstacle the ground grid does not contain keeps pushing into it. The v5 pickup trial jammed this way, with the mech held at (475.7, -75.8) and outside the zone. The baseline reproduces it from that position: 30 s outside, never safe.

**The change:** `recovery.py` measures progress during zone return. Progress is the remaining walking distance to the zone centre from the same planner that steers the return: the straight line when it is clear, otherwise the planner's path length. One recovery attempt runs when all of these hold:

- the remaining distance shrinks by less than 2 m over 2 s;
- the mech moved less than 3 m in that time, so it is jammed rather than sliding round something;
- the planner already has a route, so its warm-up never counts.

The attempt is the existing obstacle-recovery manoeuvre: a sideways step with a jump for 1.5 s, to a side whose step is clear on the ground grid. Sides go A, A, B, B. The next attempt waits 3 s after the previous one ends.

How the rules were chosen (each step tested on episodes that were not used again for judging):

- **A, A, B, B order:** a plain alternation, inherited from `first_run`, paced back and forth along a 44 m wall and never cleared it.
- **First held-out set (seed 31337):** 23 of 24 passed. In the failing case the baseline slid round slowly on its own and the retry reversed the slide, costing 2.1 s. This led to the 3 m movement gate.
- **Follow-the-slide rule (rejected):** making the retry follow the slide broke three wide-wall cases on seed 90210, because after a sideways step the mech slides back toward the middle of a long wall.
- **Choosing the variant:** four variants were compared on all seen episodes. With the movement gate, a 1.5 s step had 1 failure in 77 episodes against 5 for 1.0 s. Results barely changed with gates of 2 to 4 m.

Evidence (`py tools/zone_return_trial.py`; baseline exported from `1a0ca39`; both bots as `python -u bot.py`; every episode starts outside the zone, cap 30 s):

| Episode set | Stuck for the baseline | v9 reaches safety | Baseline got round unaided (v9 no slower) | Unsolved by both | Controls (clear and corner routes) |
| --- | --- | --- | --- | --- | --- |
| designed: known case, unmapped wall, wide unmapped wall | 3 | 3 (5.2 s, 7.6 s, 7.6 s) | 0 | 0 | 2, identical actions, 0 retries |
| seeds 31337, 90210, 4711 (tuning) | 40 | 39 | 8 | 1 | 24, identical actions, 0 retries |
| seed 2718 (fresh, generated after all rules were fixed) | 15 | 15 (about 9.2 s each) | 1 | 0 | 8, identical actions, 0 retries |
| standard recording | | | | | 0 retries, 0 of 300 decisions differ |

The unsolved episode is a 32 m unmapped wall across a corridor between mapped buildings. The only way round is about 19 m to one side, and from there the route bends. Both bots stay outside the zone for 30 s.

The trial world has no jumps, so a step can only walk round an obstacle; in a match the jump-and-boost of the attempt may also clear low ledges.

## Next experiment: laser trigger discipline (#3)

Selected because v5 started picking up second weapons and the inherited trigger mishandles all of them. Measured with each weapon placed in slot 1 over the recording (v6 trigger rule):

| Slot 1 | What the trigger does | Measured |
| --- | --- | --- |
| laser | held whenever v6 fires: the mech walks at half speed while charging, and a full charge auto-fires after 2 s wherever the torso points | 107 of 300 decisions (10.7 s) at half speed |
| lightning | fired at any range: every arc beyond 45 m hits nothing and costs 3 energy | 107 of 107 trigger decisions beyond range, up to about 128 energy |
| mortar | fired with the gun's pitch | shells land short on 103 of 107 trigger decisions |

Lasers did 1,260 of the 1,665 damage taken in the recording. The challenger changes only the laser trigger:

- charge only on a clear line within laser range;
- release when fully charged and our actual torso aim is within the target's angular radius;
- never charge while returning to the zone.

Measures: half-speed decisions during zone return, released beams on target, wasted releases. Cases where it should activate: a duel at 60-200 m. Cases where it would hurt: a close fight where holding is worse than an early partial shot. Lightning range gating and mortar elevation follow as separate single changes.

## Loop for every later round

1. Branch from the strongest officially scored commit with a known SHA.
2. Name one observed weakness and the measurable behaviour that should improve.
3. Build one challenger; compare both bots through `bot.act()` on identical starting conditions, including cases where the feature should activate and cases where activating would hurt.
4. After tuning, run fresh held-out cases on unseen seeds. If a rule never changes an action, diagnose why before spending a submission.
5. Run the container check, then log parent, candidate, hypothesis, activation, local result. Record the official score and the keep/revert decision when it comes back. A losing challenger stays logged, and the next hypothesis starts from the stronger parent. Two promising changes get a separate combined test.

## Earlier detail

### v5 closed-loop pickup trial (`tools/pickup_trial.py`, 10 seeded instances per scenario)

| Scenario | v4 acquired | v5 acquired | v5 detours | Runs outside the zone (v4 / v5) |
| --- | --- | --- | --- | --- |
| easy nearby pickup | 0 | 10 | 10 | 0 / 0 |
| off-route pickup (path around an obstacle) | 3 | 10 | 10 | 0 / 0 |
| distant NPC in view | 0 | 10 | 10 | 0 / 0 |
| roomy zone (control for the next row) | 0 | 10 | 10 | 0 / 0 |
| expiring zone | 0 | 0 | 0 | 0 / 0 |
| rooftop pickup | 0 | 0 | 0 | 0 / 0 |
| bridge-deck pickup | 0 | 0 | 0 | 0 / 0 |
| pickup disappears mid-route | 0 | 0 | 10, all abandoned as disappeared | 0 / 0 |
| opponent beside pickup | 1 | 1 | 0 | 0 / 0 |
| blocked approach (obstacle the map does not know) | 0 | 0 | 10, all abandoned for no progress | 0 / 0 |
| deadline closes mid-route | 0 | 0 | 10, all abandoned for the zone deadline | 0 / 0 |

v6 reproduces the v5 column exactly.

### Known limits

- Zone return has no stuck recovery (v4 onward). v5's 8 s zone margin exists so an abandoned detour still leaves time for ordinary movement.
- No match feedback or replays were available without signing in to the Buildathon site, so nothing here comes from official matches beyond the scores.
- The recording never lists two mechs, never shows a pickup within reach, and does not react to the bot. The scripted and closed-loop trials cover those cases, but they measure decisions, not placements.
