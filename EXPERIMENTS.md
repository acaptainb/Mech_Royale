# Experiment log

Practice scoring is 48 matches against 15 house bots, mean of (16 - place); the track page lists the kit's starter bot at 1.15. Local tests catch mistakes; only official practice scores judge placement. A score is entered only after you report it from the Buildathon page.

## Scoreboard

Official practice scores as you report them; the submitted SHAs were confirmed from the Buildathon submission rows. V7 to V12 each branch from the 2.08 baseline (`1a0ca39`) and change one behaviour, so each delta is measured against that same parent. Combinations of changes that scored well are separate candidates.

Practice seeds are fixed for the whole event and the bot is deterministic. A version whose new rule never fires in those 48 matches therefore reproduces its parent's score exactly, as v9 did.

| Version | Branch | Candidate SHA | Parent SHA | Official score | Delta vs parent |
| --- | --- | --- | --- | --- | --- |
| v4 | `main` | `124101fe2402a13451921e0d97582adc5b3aab17` | none | 1.56 | n/a |
| v5 | `v5-early-loot` | `dbc4cc2da927ddcc3a48e5191c3c070294e2ab72` | `124101f` | 1.75 | +0.19 |
| v6 | `v6-selective-engagement` | `1a0ca394d26fe5e97c60dbac2ded343a2694b114` | `dbc4cc2` | 2.08 (baseline for v7-v12) | +0.33 |
| v7 | `v7-laser-release` | `f69d39c2c32f92e533568ce27854cf5efd0e04ca` | `1a0ca39` | 2.19 | +0.11 |
| v8 | `v8-bullet-dodge` | `4588e6b826e3ea923ab10697160e5c7658a64179` | `1a0ca39` | **2.50** (entered in the final) | +0.42 |
| v9 | `v9-return-recovery` | `e287d238ed0cdf196c7e7a18595e9b293afd3360` | `1a0ca39` | 2.08 | +0.00 (the recovery never fired in practice) |
| v8 + v7 | `combo-v8-v7` | `3b290b0b87bee98c418a74546671c82dd232c2d0` | `4588e6b` (v8) | **2.63** | +0.13 |
| v10 | `v10-pickup-tiebreak` | `7c3605fdcc0d7bf0c3c813258b3cb746093830b9` | `1a0ca39` | pending | pending |
| v11 | `v11-kill-cube-detour` | `63b62ff5c20eec473719e2e87061d07a0a834380` | `1a0ca39` | pending | pending |
| v12 | `v12-hold-near-cover` | `3bc1f4734b8a2c7aecda3b89a6f62f74d712cf46` | `1a0ca39` | pending | pending |
| combo A: v8 + v7 + v10 + v11 | `combo-a` | `f0a59c7d1f94f9fab441fe4cdd6167aa07670219` | `3b290b0` (v8 + v7) | pending | pending |
| combo B: combo A + v12 | `combo-b` | this commit (tag `combo-b-candidate`) | `f0a59c7` (combo A) | pending | pending |

## Log

| Version | Parent SHA | Candidate SHA | Hypothesis (the one change) | Activation (local) | Local result | Official score | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v4 | none | `124101f` (tag `v4-scored`) | health-aware objectives: supply drop when damaged, relocation after damage | not measured | replay 300/300; 12 objective checks | 1.56 | superseded by v5 |
| v5 | `124101f` | `dbc4cc2` (tag `v5-candidate`) | detouring for one reachable ground weapon while slot 1 is empty improves placement | 40 detours in 110 closed-loop runs; 0 on the recording (no pickup within 70 m) | acquired 40/40 where intended, none where it should not; no extra zone misses | 1.75 (+0.19) | kept; superseded by v6 |
| stable target (measurement) | `dbc4cc2` | `97d49a9` (PR #2) | the nearest-mech rule oscillates between opponents | 0: the recording never lists two mechs | 0 switches on the recording; 40 vs 2 switches in the two-mech scenario | not submitted (no bot change) | rule reused inside v6 |
| no drop pursuit (parked) | `dbc4cc2` | `0733dd7` (branch `exp/no-drop-pursuit`) | travelling to or waiting at supply drops costs placement | objective checks only | not container-checked | not submitted | parked |
| v6 | `dbc4cc2` (git parent `cdfa00f`, identical match files) | `1a0ca39` (tag `v6-candidate`) | facing the opponent that is actually fighting us and holding fire when shots cannot land improves placement | aim or fire differs on 556 of 965 scripted decisions; on the recording, fire differs on 62 and aim on 40 of 300 | 30/30 scenarios; held-out rules pass on 2 x 400 encounters; 10 of 11 mutants caught; movement identical to v5 on 1,265 decisions | 2.08 (+0.33) | keep: baseline for v7-v12 |
| v7 | `1a0ca39` | `f69d39c` (tag `v7-candidate`) | releasing a full laser charge the moment the beam is on the chosen opponent improves placement | 4 of 7 entrypoint scenarios; 0 on the recording (no laser held) | first beam on target 0.0-0.8 s vs 1.9-2.7 s; half-speed charging roughly halved; controls identical | 2.19 (+0.11) | keep: combined with v8 |
| v8 | `1a0ca39` | `4588e6b` (tag `v8-candidate`) | one brief sideways step away from a visible bullet on course to hit us cuts hits taken | 1 dodge on the recording (9 bullets on course: 5 too close to clear, 3 inside the 2 s cooldown) | 9/9 scripted checks; hits -8% (tuning) and -7% (held-out) in the reactive trial, 0 zone exits, every route finished | **2.50 (+0.42)** | **keep: best score; parent of the combination** |
| v9 | `1a0ca39` | `e287d23` (tag `v9-candidate`) | one cooled-down recovery attempt when the zone return stops gaining ground gets a jammed mech back to safety | 0 on the recording and every control; 1-2 attempts per stuck trial episode | stuck episodes reach safety in 5-12 s where the baseline stays out 30 s | 2.08 (+0.00) | neutral: the rule never fired in the fixed practice matches; harmless, not combined |
| v8 + v7 | `4588e6b` | this commit (tag `combo-v8-v7-candidate`) | the two changes that scored above 2.08 on their own add up | the dodge as in v8 (1 on the recording); the laser release as in v7 (0 on the recording) | moves exactly as v8 and fires exactly as v7 on every checked decision; recording identical to v8 | **2.63 (+0.13 over v8)** | **keep: best score; parent of combo A** |
| v10 | `1a0ca39` | `7c3605f` (tag `v10-candidate`) | on a near tie between two eligible pickups, preferring the one with a clear onward line to the next circle saves time | 1 crafted layout; 3 of 150 random two-pickup layouts (2%); 0 in 110 pickup-trial episodes; 0 on the recording | courtyard vs open: reaches safety 1.3 s sooner; faster pickup and shared doorway identical | pending | rarely fires; likely reproduces its parent's score |
| v11 | `1a0ca39` | `63b62ff` (tag `v11-candidate`) | one short cube detour after a confirmed kill turns kills into HP | 3 of 7 crafted episodes; 0 on the recording (it has no kill events) | collects 3 cubes (HP 1568 vs 1400 at the next encounter) for a 3-5 s later arrival inside the zone; cancels on the decision a threat appears | pending | fires only after our kills |
| v12 | `1a0ca39` | `3bc1f47` (tag `v12-candidate`) | holding still beside cover while comfortably safe and quiet cuts exposure | held in 11 of 20 random starts on each of two seeds; 0 on the recording | walks 22-28% less, 0 late arrivals, releases on the same decision anything changes | pending | the one new rule likely to fire in practice; effect uncertain |
| combo B | `f0a59c7` | this commit (tag `combo-b-candidate`) | holding still beside cover adds to everything that scored well | as in v12: holds in 11 of 20 random starts per seed; 0 on the recording | v12's trial against combo A reproduces v12's own numbers (22-28% less walking, 0 late arrivals, same-decision release); a hold gives way to a dodge on the decision a bullet is on course | pending | pending your score |
| combo A | `3b290b0` | `f0a59c7` (tag `combo-a-candidate`) | v10 and v11 add to v8 + v7 without harm | as in v10 and v11 | each trial against `3b290b0` reproduces its standalone result; laser, dodge and interaction checks unchanged | pending | pending your score |

## v6: selective engagement

The change replaces the inherited nearest-mech rule (fire both triggers at whichever mech is closest) with `targeting.Engagement`, wired in at the end of `bot.py`'s `act()`. Movement, pickup routing and how the triggers are pressed are v5's.

- **Choice of opponent:** each listed mech scores its distance, 35 m closer if it hit us in the last 5 s, 15 m closer if its torso pointed at us in the last 1 s, 20 m farther if solid cover blocks our line. A shootable mech that is fighting us ranks ahead of everything else. A drone is a candidate only after it hits us, and then 60 m farther. `StableTarget` keeps the current choice through small changes and switches after a 1 s persistent lead, at once for a clear lead, and on the same decision the opponent stops being listed.
- **Shooting:** only at the chosen opponent, only with a clear line (`cover.py` on the 2 m `cover.i16` raster built from `arena/v2`) and within weapon range, and only when it is fighting us, is within 45 m, or unled bullets would land. A charging laser is kept held through a hold, so it is never released into a wall.
- **Unseen attacker:** when a recent attacker is not listed and the chosen opponent is neither fighting us nor within 45 m, the torso turns toward the damage bearing, without firing, except during a pickup detour. Zone damage has no attacker. Mortar damage keeps its attacker id but not its bearing, which is the blast point. A kill clears the victim's evidence.

Evidence (`py tools/engagement_trial.py`, `--heldout`, `py tools/engagement_probe.py`):

- The independent review raised 26 findings and confirmed 20. All were fixed or turned into checks; the 6 refuted ones are documented in the review run.
- Recording: no pickup is pursued and only one mech is ever listed. v6 holds fire on 54 decisions where the raster says a building blocks the line (no shot landed by either side in that window) and on 8 where a crossing mech at about 147 m would dodge unled bullets. The raster calls all 37 lines before a landed shot clear.
- Timing: 0 late answers, p99 1.1 ms on Windows; worst case with 15 opponents at 200 m is 2.5 ms. The CI conformance job runs the restricted linux/amd64 container, and the probe asserts that the container's bot aims at an attacker rather than a closer passive mech.

## v8: brief sideways dodge (single change on `1a0ca39`)

`dodge.py`, applied in `bot.py` right after v6's move and boost are set. When a visible gun or NPC bullet is on course, `Dodge.steer` overrides move and boost with one sideways step:

- **On course:** its straight path meets our body (radius + bullet radius + 0.5 m) at the point our current velocity carries us to, within 1 s.
- **The step:** perpendicular to the bullet, boosted while energy stays above 20, held for 0.3 s.
- **Side:** whichever side leaves the bullet farthest from us when it arrives, given our velocity, ground acceleration and speed cap.
- **Skipped when any of these hold:**
  - the zone return is urgent (return mode, the boost-when-late rule, or outside the zone);
  - the 4 m step is blocked on the ground grid on both sides;
  - the step would end within 3 m of the current circle's edge;
  - the step cannot clear the bullet in time;
  - another dodge started less than 2 s ago.

Mortar shells are ignored. Each bullet is answered at most once.

Two rules were added after the first reactive run:

- **Feasibility gate:** a dodge that cannot clear the bullet in time is skipped.
- **2 s cooldown:** at most one dodge per 2 s.

As first written, the rule stepped sideways at nearly every bullet under sustained fire (one every 0.25 s). It never finished a route in 12 episodes, spent 1,749 boost energy and took 694 hits against the baseline's 441. Both refinements keep "one brief dodge" literal. The held-out episodes were generated only after these values were fixed.

Evidence (`py tools/dodge_trial.py`; baseline exported from `1a0ca39`, both bots as `python -u bot.py`):

| Check | Baseline | v8 |
| --- | --- | --- |
| direct incoming bullet, 150 m | walks on | steps sideways, boosting |
| harmless near miss (8 m wide), bullet moving away, mortar shell, bullet too close to clear (40 m) | | identical to baseline |
| wall on one side | | steps to the open side |
| walls on both sides, urgent zone return | | identical to baseline |
| zone edge 2 m away | | steps inward |
| reactive, 12 tuning episodes (shooter 60-150 m, leads every bullet) | 441 hits, 0 boost energy, 0 decisions outside | 404 hits, 230 energy, 0 outside; arrival +0.9 s on average |
| reactive, 16 held-out episodes on fresh routes | 596 hits, 0 energy, 0 outside | 554 hits, 214 energy, 0 outside; arrival +0.6 s on average |
| standard recording | | 1 dodge, 3 decisions differ |

The gain comes almost entirely from shooters beyond about 100 m. Closer bullets arrive before a 2.8 m sideways shift is possible, and the feasibility gate skips them. The reactive world has no walls for bullets, no return fire and a perfectly leading shooter, so these are first-order effects, not placements.

## Combination: v8 + v7 (on `4588e6b`, the 2.50 commit)

V7's commit (`f69d39c`) applied unchanged on top of v8. The only conflicts were the bot's name, the README sections and this log; no code line overlaps. The dodge sets move and boost, and the laser release sets only the laser slot's trigger, so they never write the same command.

Evidence (all as real bot processes):

| Check | Result |
| --- | --- |
| `py tools/entrypoint_trial.py --baseline 4588e6b` (laser scenarios against v8) | every row matches v7's run against its own parent; the recording is identical to v8 (0 of 300 decisions differ) |
| `py tools/dodge_trial.py` (against v6) | identical to v8's own run: 9/9 scripted checks, hits 441 to 404 (tuning) and 596 to 554 (held-out), 0 zone exits, 1 dodge on the recording |
| `py tools/combo_check.py` (against the exported v7 and v8) | with a full laser and a bullet on course at once, the combination steps sideways and boosts like v8 and sends `[true, false]` like v7; each change alone also matches its parent |

## Combo A: v8 + v7 + v10 + v11 (on `3b290b0`, the 2.63 commit)

V10's commit (`7c3605f`) and V11's (`63b62ff`) applied on top of v8 + v7.

- **Conflicts:** the bot's name, the Dockerfile and `.dockerignore` lines (both `dodge.py` and `kill_cubes.py` ship now), and the docs.
- **Rules and the commands they own:**
  - the pickup tie-break owns only which pickup is chosen;
  - the cube detour owns only which cube becomes the waypoint;
  - the dodge owns move and boost;
  - the laser release owns the laser trigger.

Evidence (all as real bot processes):

| Check | Result |
| --- | --- |
| `py tools/pickup_tiebreak_trial.py --baseline 3b290b0` | identical to v10 against its own parent: courtyard vs open taken open, safety 12.2 s vs 13.5 s; 2% activation on random layouts; 0 on the recording |
| `py tools/kill_cube_trial.py --baseline 3b290b0` | identical to v11 against its own parent: 3 cubes, HP 1568 vs 1400 at the next encounter, cancel on the threat's first decision, 0 zone exits |
| `py tools/entrypoint_trial.py --baseline 4588e6b` | laser rows as in v7; recording identical to v8 |
| `py tools/dodge_trial.py` | identical to v8 (441 to 404 and 596 to 554 hits, 0 zone exits) |
| `py tools/combo_check.py` | moves as v8 and fires as v7 in all three cases |

V10 and V11 rarely activate: twice in a combined 260 crafted and random cases, and never on the recording. Combo A will most likely score exactly 2.63 unless our bot gets kills or meets near-tied pickups in practice.

## Combo B: combo A + v12 (on `f0a59c7`)

V12's commit (`3bc1f47`) applied on combo A. V12 was written against the old cube block, so in the merged `bot.py` the hold is told about a cube chase through v11's `nearest_cube` result. The hold runs before the dodge, so a bullet on course still moves a holding mech.

Evidence (all as real bot processes):

| Check | Result |
| --- | --- |
| `py tools/hold_trial.py --baseline f0a59c7` (against combo A) | identical to v12 against its own parent: seed 5150 4,424 to 3,167 m walked, seed 8086 4,178 to 3,249 m, 0 late seconds, releases on the decision an opponent appears or the circle moves |
| quiet covered start, then a bullet on course 0.1 s later | combo A walks `[0.17, 0.98]` then dodges `[-0.5, 0.87]` with boost; combo B holds `[0, 0]` then dodges `[-0.5, 0.87]` with boost |
| v10 and v11 trials against `3b290b0`; laser trial against `4588e6b`; dodge trial; `combo_check.py` | all identical to combo A |
| route and pickup trials | fewer arrivals at the zone centre (route 24 of 150) because the hold stops short of the centre on purpose; 0 zone misses and every pickup still taken. `py tools/no_hold.py route_trial.py` and `pickup_trial.py` match the baseline exactly |

Submitting combo A and combo B together separates their effects. Combo A minus 2.63 is what v10 and v11 add; combo B minus combo A is what v12 adds on top of the best build.

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
