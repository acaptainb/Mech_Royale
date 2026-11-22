# Experiment log

Practice scoring is 48 matches against 15 house bots, mean of (16 - place); the track page lists the kit's starter bot at 1.15. Local tests catch mistakes; only official practice scores judge placement. A score is entered only after you report it from the Buildathon page.

## Scoreboard

Official practice scores as reported from the Buildathon submission rows. V7 to V12 each branch from the 2.08 baseline (`1a0ca39`) and change one behaviour, so each delta is measured against that same parent. Combinations of changes that scored well are separate candidates.

Practice seeds are fixed for the whole event and the bot is deterministic. A version whose new rule never fires in those 48 matches therefore reproduces its parent's score exactly, as v9 did.

| Version | Branch | Candidate SHA | Parent SHA | Official score | Delta vs parent |
| --- | --- | --- | --- | --- | --- |
| v4 | `main` | `124101fe2402a13451921e0d97582adc5b3aab17` | none | 1.56 | n/a |
| v5 | `v5-early-loot` | `dbc4cc2da927ddcc3a48e5191c3c070294e2ab72` | `124101f` | 1.75 | +0.19 |
| v6 | `v6-selective-engagement` | `1a0ca394d26fe5e97c60dbac2ded343a2694b114` | `dbc4cc2` | 2.08 (baseline for v7-v12) | +0.33 |
| v7 | `v7-laser-release` | `f69d39c2c32f92e533568ce27854cf5efd0e04ca` | `1a0ca39` | 2.19 | +0.11 |
| v8 | `v8-bullet-dodge` | `4588e6b826e3ea923ab10697160e5c7658a64179` | `1a0ca39` | **2.50** (entered in the final) | +0.42 |
| v9 | `v9-return-recovery` | `e287d238ed0cdf196c7e7a18595e9b293afd3360` | `1a0ca39` | 2.08 | +0.00 (its rule never fired in practice) |
| v8 + v7 | `combo-v8-v7` | `3b290b0b87bee98c418a74546671c82dd232c2d0` | `4588e6b` (v8) | pending | pending |
| v12 | `v12-hold-near-cover` | this commit (tag `v12-candidate`) | `1a0ca39` | pending | pending |

## Log

| Version | Parent SHA | Candidate SHA | Hypothesis (the one change) | Activation (local) | Local result | Official score | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v4 | none | `124101f` (tag `v4-scored`) | health-aware objectives: supply drop when damaged, relocation after damage | not measured | replay 300/300; 12 objective checks | 1.56 | superseded by v5 |
| v5 | `124101f` | `dbc4cc2` (tag `v5-candidate`) | detouring for one reachable ground weapon while slot 1 is empty improves placement | 40 detours in 110 closed-loop runs; 0 on the recording | acquired 40/40 where intended; no extra zone misses | 1.75 (+0.19) | superseded by v6 |
| stable target (measurement) | `dbc4cc2` | `97d49a9` (PR #2) | the nearest-mech rule oscillates between opponents | 0: the recording never lists two mechs | 0 switches on the recording; 40 vs 2 in the two-mech scenario | not submitted | rule reused inside v6 |
| no drop pursuit (parked) | `dbc4cc2` | `0733dd7` (branch `exp/no-drop-pursuit`) | travelling to or waiting at supply drops costs placement | objective checks only | not container-checked | not submitted | parked |
| v6 | `dbc4cc2` | `1a0ca39` (tag `v6-candidate`) | facing the opponent that is fighting us and holding fire when shots cannot land improves placement | aim or fire differs on 556 of 965 scripted decisions | 30/30 scenarios; held-out rules pass; movement identical to v5 | 2.08 (+0.33) | baseline for v7-v12 |
| v7 | `1a0ca39` | `f69d39c` (tag `v7-candidate`) | releasing a full laser charge the moment the beam is on target improves placement | 4 of 7 entrypoint scenarios; 0 on the recording | first beam on target 0.0-0.8 s vs 1.9-2.7 s | 2.19 (+0.11) | keep |
| v8 | `1a0ca39` | `4588e6b` (tag `v8-candidate`) | one brief sideways step from a bullet on course cuts hits taken | 1 dodge on the recording | hits -8% / -7% in the reactive trial; 0 zone exits | **2.50 (+0.42)** | best score so far |
| v9 | `1a0ca39` | `e287d23` (tag `v9-candidate`) | one cooled-down recovery attempt gets a jammed zone return back to safety | 0 on the recording and every control | stuck trial episodes reach safety in 5-12 s instead of never | 2.08 (+0.00) | neutral: never fired in practice |
| v12 | `1a0ca39` | this commit (tag `v12-candidate`) | holding position beside cover while comfortably safe, instead of walking to the zone centre, saves exposure without costing zone safety | 1 hold in every covered designed start; 11 of 20 randomized episodes on each seed; 0 on the recording | walking -28% (tuning) and -22% (held-out), 0 late seconds for either bot, release on the exact decision of every change | pending | pending your score |

## v6: selective engagement

The change replaces the inherited nearest-mech rule (fire both triggers at whichever mech is closest) with `targeting.Engagement`, wired in at the end of `bot.py`'s `act()`. Movement, pickup routing and how the triggers are pressed are v5's.

- **Choice of opponent:** each listed mech scores its distance, 35 m closer if it hit us in the last 5 s, 15 m closer if its torso pointed at us in the last 1 s, 20 m farther if solid cover blocks our line. A shootable mech that is fighting us ranks ahead of everything else. A drone is a candidate only after it hits us, and then 60 m farther. `StableTarget` keeps the current choice through small changes and switches after a 1 s persistent lead, at once for a clear lead, and on the same decision the opponent stops being listed.
- **Shooting:** only at the chosen opponent, only with a clear line (`cover.py` on the 2 m `cover.i16` raster built from `arena/v2`) and within weapon range, and only when it is fighting us, is within 45 m, or unled bullets would land. A charging laser is kept held through a hold, so it is never released into a wall.
- **Unseen attacker:** when a recent attacker is not listed and the chosen opponent is neither fighting us nor within 45 m, the torso turns toward the damage bearing, without firing, except during a pickup detour. Zone damage has no attacker. Mortar damage keeps its attacker id but not its bearing, which is the blast point. A kill clears the victim's evidence.

Evidence (`py tools/engagement_trial.py`, `--heldout`, `py tools/engagement_probe.py`):

- The independent review raised 26 findings and confirmed 20. All were fixed or turned into checks; the 6 refuted ones are documented in the review run.
- Recording: no pickup is pursued and only one mech is ever listed. v6 holds fire on 54 decisions where the raster says a building blocks the line (no shot landed by either side in that window) and on 8 where a crossing mech at about 147 m would dodge unled bullets. The raster calls all 37 lines before a landed shot clear.
- Timing: 0 late answers, p99 1.1 ms on Windows; worst case with 15 opponents at 200 m is 2.5 ms. The CI conformance job runs the restricted linux/amd64 container, and the probe asserts that the container's bot aims at an attacker rather than a closer passive mech.

## v12: hold position beside cover (single change on `1a0ca39`)

Before this change the bot always walks to the next circle's centre and only stops within 2 m of it. `hold.py` adds a hold, applied in `bot.py` after the decision's move and boost are set. While every condition below is true, the bot sends move `[0, 0]` and boost off; aim and fire stay v6's.

- **Objective:** the plain zone objective. No zone return, supply drop, relocation after damage or pickup detour (including a pending pickup route search), no cube being chased, and not in the obstacle recovery.
- **Safety:** inside the current circle by 5 m, and inside the next circle by max(8 m, 15% of its radius). The next circle lies inside every circle the zone passes through while shrinking toward it, so the spot stays safe until a new next circle is announced, which releases the hold.
- **Cover:** a ground-anchored solid at least 4.5 m tall (a mech's centre height) within 8 m, read from `cover.i16`. That raster records what stops shots; the navigation grid also blocks slopes and clearance, so it is not cover.
- **Quiet:** no game mech listed, no damage from a mech or drone this decision, and no recent attacker evidence in v6's engagement memory.

The first decision any condition fails, that decision's normal move stands. While holding, `first_run`'s stuck sampling is restarted, so deliberate stillness is not mistaken for a jam.

Evidence (`py tools/hold_trial.py`; baseline exported from `1a0ca39`; both bots as `python -u bot.py`; closed-loop movement on the navigation grid with a multi-phase shrinking zone):

| Case | Metres walked (base / v12) | Late seconds (base / v12) | Hold |
| --- | --- | --- | --- |
| quiet covered start (45 s) | 317.5 / 0.0 | 0 / 0 | held all 450 decisions |
| exposed start | 317.5 / 317.5 | 0 / 0 | no hold, identical moves |
| opponent appears at t=5.0 | 171.8 / 142.0 | 0 / 0 | held through decision 49, moving at decision 50 (the change) |
| unseen attacker hits at t=5.0 | 111.1 / 111.1 | 0 / 0 | held through decision 49, moving at decision 50 |
| next circle moves away at t=15.0 | 317.5 / 110.4 | 0 / 0 | held through decision 149, moving at decision 150; arrived in time |
| 20 randomized three-phase starts, seed 5150 (tuning) | 4,424 / 3,167 (-28%) | 0 / 0 | 11 of 20 episodes held (16 holds) |
| 20 randomized three-phase starts, seed 8086 (held out) | 4,178 / 3,249 (-22%) | 0 / 0 | 11 of 20 episodes held (14 holds) |
| standard recording | 0 of 300 decisions differ | n/a | 0 holds: the recorded mech is never inside the next circle |

Part of the baseline's walking in the covered cases is jitter near a zone centre it cannot quite reach (the v4 finding), which v12 avoids by not going there.

The trade-off shows in held-out episode #11: v12 walked more (312 m vs 214 m). It held at its covered start through the first phase, and the next small circle was then announced about 180 m away; the baseline was already at the old centre, about 90 m from it. Both arrived in time.

**Regressions:** with the hold on, `tools/route_trial.py` (24 of 150) and `tools/pickup_trial.py` report fewer arrivals at the zone centre. Those trials define success as reaching the centre, and their next circles (380 m and 330 m) contain the start, which is exactly when v12 stops short on purpose. Zone misses stay 0 in every pickup scenario and every pickup is still acquired. With only the hold switched off (`py tools/no_hold.py route_trial.py`, `pickup_trial.py`, `objective_checks.py`) all three match the baseline exactly. The objective checks pass with the hold on, because their test location has no cover within 8 m.

**Not measured here:** standing still is silent (no step sounds) but makes a stationary target. Holding beside cover also means not being at the circle's centre when the next circle is announced.

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
