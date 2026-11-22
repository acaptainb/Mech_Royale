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
| v8 + v7 | `combo-v8-v7` | `3b290b0b87bee98c418a74546671c82dd232c2d0` | `4588e6b` (v8) | **2.63** (entered in the final) | +0.13 |
| v10 | `v10-pickup-tiebreak` | `7c3605fdcc0d7bf0c3c813258b3cb746093830b9` | `1a0ca39` | not submitted | n/a |
| v11 | `v11-kill-cube-detour` | `63b62ff5c20eec473719e2e87061d07a0a834380` | `1a0ca39` | not submitted | n/a |
| v12 | `v12-hold-near-cover` | `3bc1f4734b8a2c7aecda3b89a6f62f74d712cf46` | `1a0ca39` | not submitted | n/a |
| combo A: v8 + v7 + v10 + v11 | `combo-a` | `f0a59c7d1f94f9fab441fe4cdd6167aa07670219` | `3b290b0` | 2.60 | -0.03 |
| combo B: combo A + v12 | `combo-b` | `32259f0dc1c7edf7b5241f18c62fc2632749564c` | `f0a59c7` | 2.58 | -0.02 (-0.05 vs 2.63) |
| duel-strafe | `duel-strafe` | `2b8e620b618581f267189f12ca46d12b5be28588` | `3b290b0` (2.63) | 2.46 (submission row SHA still to be matched to `2b8e620`) | -0.17 |
| duel-weave | `duel-weave` | not a candidate: failed its pre-submission gate | `3b290b0` (2.63) | not submitted | n/a |
| no-mortar | `no-mortar` | `df1be152ba1bee40a368979ccb01eef1b7f9b347` | `3b290b0` (2.63) | 2.58 | -0.05 |
| lead-shots | `lead-shots` | `4d8a32d3c453d3efb430baddb4bd141678417d77` | `3b290b0` (2.63) | 2.90 (parent of the batch candidates) | +0.27 |
| crossing-fire | `crossing-fire` | `c1200411b37163ea2496aefbb861a496d2bcea12` | `4d8a32d` (2.90) | 2.94 | +0.04 |
| offense-upgrades | `offense-upgrades` | `bb0e5e0dc51f8f75356a726230ca080da66706d3` | `4d8a32d` (2.90) | 2.85 | -0.05 |
| laser-cover | `laser-cover` | `1961af48491445c4d10d88c767f901d163a98668` | `4d8a32d` (2.90) | 2.90 | +0.00 (probably never fired in practice) |
| chase-wounded | `chase-wounded` | `ef880813566961c48504d37db14e2e8234a8f3ef` | `4d8a32d` (2.90) | 2.75 | -0.15 (walking toward opponents lost) |
| mortar-arc | `mortar-arc` | `8670353ea471e3156f988b13b46c7ad01daea128` | `4d8a32d` (2.90) | 2.90 | +0.00 (exactly the parent: probably never fired, so we rarely or never shoot while holding a ready mortar; an exact tie can also come from small changes cancelling) |
| mortar-dodge | `mortar-dodge` | `1645c22576e99d0afe6cb9ce8ec37ad0d9bae616` | `4d8a32d` (2.90) | 3.00 | +0.10 |
| mortar-dodge + crossing-fire | `combo-mortar-dodge-crossing-fire` | `4f4596e12bf916fe76039a7e75652cf4036d35f4` | `1645c22` (3.00) | **3.04** (best; entered in the final) | +0.04 (exactly additive: +0.10 and +0.04 over 2.90) |
| hide-spot | `hide-spot` | `c08eef931025c4ca3b129514e63d21c11b8519ad` | `c120041` (2.94) | pending | pending |
| hide-spot on the combination | `hide-spot-on-combo` | this commit (tag `hide-spot-on-combo-candidate`) | `4f4596e` (3.04) | pending | pending |

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
| v8 + v7 | `4588e6b` | this commit (tag `combo-v8-v7-candidate`) | the two changes that scored above 2.08 on their own add up | the dodge as in v8 (1 on the recording); the laser release as in v7 (0 on the recording) | moves exactly as v8 and fires exactly as v7 on every checked decision; recording identical to v8 | **2.63 (+0.13 over v8)** | **keep: best score; parent of duel-strafe** |
| combos A and B | `3b290b0` | `f0a59c7`, `32259f0` | v10 + v11, then v12, add to v8 + v7 | v10, v11 and v12 as on their own branches | each trial reproduced its standalone result | 2.60 and 2.58 | revert: both below 2.63, so v10 or v11 fired in practice and cost placements, and v12 cost more |
| duel-strafe | `3b290b0` | this commit (tag `duel-strafe-candidate`) | walking sideways to the only, clearly visible opponent during ordinary zone movement helps survive the exchange | eligible on 115 of 300 recording decisions; the move changed on all 115 | hit rate under a leading shooter -17% and -11%, but routes stall while the opponent stays in view (see below) | 2.46 (-0.17) | revert: it fired at about 150 m, mostly against a laser user (hitscan, not dodgeable by walking), and replaced progress toward the zone |
| duel-weave | `3b290b0` | not a candidate | angling the waypoint 20 degrees, alternating sides, in a clear duel keeps progress and cuts hits | eligible on 115 of 300 recording decisions; the move changed on all 115 | 16 held-out routes: 16/16 finished, but 570 hits vs 554 for 2.63 and safety 0.8 s later | not submitted | gate not passed: more hits than 2.63 |
| lead-shots | `3b290b0` | this commit (tag `lead-shots-candidate`) | aiming the gun where a moving opponent will be when the bullet arrives lands more hits, so we kill more of the house bots that hunt us before we die | every decision with a moving opponent: aim led on 169 of 300 recording decisions | hits 56 to 109 of 130 shots (43% to 84%) in a closed-loop gunfight; never fewer; laser still released onto a moving target; only the aim changes | **2.90 (+0.27)** | **keep: best score; parent of the next candidates** |
| no-mortar | `3b290b0` | `df1be15` (tag `no-mortar-candidate`) | never carrying a mortar helps: we cannot aim it, and holding one makes every laser hit on us cook off for +60% | whenever v5 would detour for or walk over a mortar (a third of floor weapons); 0 on the recording (no mortar within 70 m) | never carries a mortar in any layout; takes a laser instead when one is near; control identical | 2.58 (-0.05) | revert: carrying the mortar is worth more than the cook-off risk |
| mortar-dodge | `4d8a32d` | `1645c22` (tag `mortar-dodge-candidate`) | stepping out of the blast of a visible mortar shell that would land on our route cuts the damage taken (200 direct + 160 splash per shell) | only while a mortar shell is visible and would hit our route within 2.5 s; 0 on the recording (no shell listed) | closed-loop shell damage 10,240 to 0 (tuning) and 12,040 to 360 (held-out); every route finished, 0 zone exits; 4 controls identical on every decision | **3.00 (+0.10)** | **keep: best score; parent of the combination** |
| mortar-dodge + crossing-fire | `1645c22` | `4f4596e` (tag `combo-mortar-dodge-crossing-fire-candidate`) | the two changes that scored above lead-shots (2.90) on their own add up | the shell dodge as in mortar-dodge (0 on the recording); crossing-fire's led fire as in `c120041` (fire differs from mortar-dodge on 8 of 300 recording decisions) | moves exactly as mortar-dodge and fires exactly as crossing-fire on every checked decision; 32 shell routes and 9 gunfights identical to the parent whose change is active | **3.04 (+0.04)** | **keep: best score; parent of the rebased candidates** |
| hide-spot on the combination | `4f4596e` | this commit (tag `hide-spot-on-combo-candidate`) | hide-spot's one change (wait at the least exposed walkable node near the next centre instead of in the open on the centre) also helps on top of the 3.04 combination | as hide-spot (`c08eef9`): plain zone mode with nobody listed and nobody hitting us for 5 s, in most circles (a spot at 185 of 300 sampled centres); 0 on the recording | see the section below | pending | pending your score |

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

## duel-strafe (on `3b290b0`, the 2.63 commit; parent score 2.63)

`strafe.py`, applied in `bot.py`. V6's engagement decision is now computed once, before movement, and the same decision drives aiming, firing and the laser release.

**When it is eligible:**
- local mode is the plain zone objective, so no return, supply drop, relocation or pickup detour;
- the mech is in the zone, the return is not urgent (`late` is false) and the obstacle recovery is not running;
- the selected opponent is a game mech and the only game mech listed;
- its line of fire is clear by the existing cover check, and it is within weapon reach.

**What it does:**
- walks, at walk speed with boost off, perpendicular to the bearing toward that opponent;
- keeps one side for an interval drawn from 0.75-1.15 s of match time (a generator seeded with the slot seed), then switches;
- if a 4 m lookahead on the current side crosses a wall on the ground grid, or ends within 3 m of the current circle's edge (or outside the next circle when we are inside it), it tries the other side; if neither is safe, the normal waypoint stands.

It runs before the v8 dodge, so a bullet on course still has the last word.

Evidence (`py tools/strafe_trial.py`; baseline exported from `3b290b0`; both as `python -u bot.py`; identical starts):

| Check | Baseline | duel-strafe |
| --- | --- | --- |
| open duel before any damage | walks `[1, 0]` | `[0.87, -0.50]`, perpendicular to the opponent, boost off |
| one side blocked by a wall | stands | switches to the open side `[-1, 0]` |
| both sides blocked, a second opponent listed, urgent zone return | | identical to the baseline |
| bullet on course during the duel | dodges `[-1, 0]`, boost on | same: the dodge has the final say |
| side intervals in a static duel | | runs of 10, 9, 12, 9 and 11 decisions (all 0.75-1.15 s) |
| aim and fire, all scripted cases and the recording | | identical to the baseline |
| standard recording (300 decisions) | | eligible 115, move changed 115, side switched for a blocked lookahead 2; skipped: no opponent selected 131, no clear shot line 54; move or boost differs from the baseline on 112 (the dodge overrides 3) |

The reactive duel uses the v8 dodge trial's world: a stationary shooter leading every bullet, the episode ending on arrival or at 30 s. It is a measurement, not a pass/fail.

| Episodes | Hits (base / strafe) | Hits per 10 s | Routes unfinished |
| --- | --- | --- | --- |
| 12 tuning | 404 / 807 | 30.3 / 25.0 | 0 / 10 |
| 16 held-out | 554 / 1,323 | 32.5 / 28.8 | 0 / 15 |

Sideways walking cuts the hit rate by 11-17%. But while a single clear opponent stays in view, the strafe replaces progress toward the zone, so total exposure and total hits roughly double in this world. In a match the zone's own timing eventually makes the return urgent and switches the strafe off.

The same effect shows in the older tools:

- **`tools/dodge_trial.py`:** routes unfinished. There were also 6 and 34 decisions outside the zone, after relocations near the edge during the longer exposure; the strafe itself was not steering on the decisions that crossed.
- **`tools/pickup_trial.py`:** "opponent beside pickup" never reaches the zone centre, because a passive mech stays listed the whole episode.
- **`tools/combo_check.py`:** case 2 (a single clear opponent) now strafes instead of moving as v8.

These checks are left unedited and reported here. `tools/engagement_trial.py` (now excluding strafe decisions from its movement check: 115) and `tools/entrypoint_trial.py` (controls now compare fire and aim) pass.

**Official result: 2.46** (-0.17 against 2.63; to be matched to the submission row's SHA). On the recording the strafe fired on 115 decisions:

- **Range:** the opponent was a median 148 m away, and only 4 decisions were within 60 m.
- **Damage:** we took 1,260 laser and 360 gun damage on those decisions. A laser hits the instant it is released, so walking sideways cannot make it miss.
- **Progress:** the strafe replaced the walk toward the zone.

The pre-submission trial showed the stalled routes and the doubled exposure. The official score confirms the cost.

## duel-weave (on `3b290b0`, the 2.63 commit): gate not passed, not submitted

`weave.py` reuses duel-strafe's eligibility and side timer (`strafe.py`). When eligible, it turns the normal waypoint direction 20 degrees to the current side, at the same speed. If a 4 m lookahead on that heading crosses a wall or leaves the safe circle, it tries the other side, then keeps the original direction. The v8 dodge stays the final override.

The submission gate, set in advance: finish every route and take fewer total hits than 2.63 on the same 16 held-out routes (`py tools/weave_compare.py`; the v8 dodge trial's world, with a shooter leading every bullet, both bots as real processes):

| Build | Routes finished | Mean time to safety | Total hits | Decisions outside the zone |
| --- | --- | --- | --- | --- |
| 2.63 (`3b290b0`) | 16/16 | 10.6 s | 554 | 0 |
| full strafe (`2b8e620`, official 2.46) | 1/16 | 10.1 s (the one route) | 1,323 | 34 |
| duel-weave | 16/16 | 11.4 s | 570 | 0 |

The weave fixes the strafe's stall: every route finishes and nothing leaves the zone. But it takes 16 more hits than 2.63 (+2.9%) and arrives 0.8 s later. It cut hits on 3 routes (9, 11, 14), tied on 2 (routes 2 and 3) and added them on 11. A leading shooter re-aims within a fraction of a second of each turn, and the zigzag lengthens the time under fire. The gate was not passed, so no submission SHA was prepared; this commit is a record only.

## no-mortar (on `3b290b0`, the 2.63 commit)

Why, from the evidence:

- **We cannot use a mortar:** with our aim, shells land short on 96% of trigger decisions (measured after v6).
- **Holding one is dangerous:** the protocol's cook-off rule adds +60% to every laser hit on a mortar carrier, so 315 becomes 504.
- **Lasers are what hurt us:** the recorded opponent held a gun and a laser on all 169 decisions it was listed, and lasers did 1,260 of the 1,665 damage we took.

The change, two lines:

- the pickup detour (`loot.py` `candidates`) skips mortars;
- the take-on-the-way rule in `bot.py` no longer takes them.

Nothing else changes.

Evidence (`py tools/no_mortar_trial.py`: the pickup trial's closed-loop world, both bots as real processes from the same starts, 8 layouts per case):

| Case | Baseline carries away | no-mortar carries away | Goal reached (base / cand) |
| --- | --- | --- | --- |
| lone mortar nearby | mortar 8 | nothing 8 | 22.2 s / 22.6 s |
| mortar, laser 10 m farther | mortar 8 | laser 8 | 22.2 s / 22.3 s |
| mortar lying on the route | mortar 8 | nothing 8 | 22.1 s / 22.6 s |
| lone laser (control) | laser 8 | laser 8 | identical |

- **Recording:** 2 mortar sightings, none within 70 m, and 0 of 300 decisions differ.
- **Laser trial against v8 (`4588e6b`):** every v7 row passes, so the laser release is intact.
- **Other checks:** the dodge trial, combo check, engagement trial (both held-out seeds), objective checks, route, pickup and target trials, the probe and `verify.py` all pass.

## lead-shots (on `3b290b0`, the 2.63 commit)

**Why:** the practice house bots share vision, never fight each other and hunt us. Placement is the order of deaths, so every house bot we kill before dying is about one more placement point. On the recording, an unled bullet at the moving opponent would pass more than 2.5 m wide on 67% of decisions (median 3.8 m). The inherited aim point was the opponent's current position.

**The change:**

- `Engagement.lead_point` solves the intercept for a gun bullet: the gun's own speed and range, the opponent's current horizontal velocity, from our muzzle.
- `decide` aims at that point instead of at the opponent, keeping the inherited pitch rule.
- **Laser exception:** while a laser is fully charged the aim stays direct, because a beam is instant and v7's release must line up.
- **Unchanged:** opponents slower than 0.5 m/s, decisions with no gun, and every other command (fire, movement, pickups).

Evidence (`py tools/lead_trial.py`: a closed-loop gunfight against `3b290b0`, both as real bot processes, the same spread draws per scenario):

| Opponent (6 s, aiming at us) | Hits base / lead (of 15 shots, 10 at 150 m) |
| --- | --- |
| stationary, 100 m (control) | 14 / 14 (identical) |
| walking across, 60 m | 9 / 14 |
| walking across, 100 m | 2 / 14 |
| walking across, 150 m | 0 / 10 |
| boosting across, 100 m | 0 / 12 |
| walking at 45 deg, 100 m | 6 / 13 |
| walking straight at us, 150 m | 13 / 13 |
| zigzag every 1 s, 100 m | 3 / 10 |
| zigzag every 0.5 s, 60 m | 9 / 9 |
| **all** | **56 / 109 (43% to 84%)** |

- **Laser:** with a full laser against an opponent walking across at 60 m, both builds land 2 of 2 beams, and the lead build adds 12 gun hits against 7.
- **Recording:** the aim is led on all 169 decisions with an opponent listed, and no command other than aim differs. The first led decision is at t=4.9, 140 m away: yaw +0.850 against +0.807.
- **Narrowed checks:** the laser trial's recording control now compares fire commands, and the engagement held-out rule R3 also accepts a lead bearing, computed independently in the trial.
- **Other checks:** the dodge trial, combo check, objective checks, route, pickup and target trials, the probe and `verify.py` all pass.

## mortar-dodge (on `4d8a32d`, the 2.90 commit)

**Why:** the v8 dodge only answers straight bullets (`BULLETS = ("gun", "npc")`) and walks straight on under a mortar shell. A shell does 200 on a direct hit plus 160 splash, falling to 30% at 7 m, and its concussion throws us and drains 45 energy. Shells fly at 72 m/s under 22 m/s2 gravity, so most of them are visible long enough to step out of. v8's bullet dodge alone was worth +0.42.

**The change** (`ShellDodge` in `dodge.py`, one call in `bot.py` right after the v8 dodge):

- **Prediction:** each decision, every visible `mortar` projectile is integrated from its position and velocity (gravity from `hello.config.weapons.mortar`) in 25 ms steps for up to 2.5 s, until it meets terrain, a wall or a deck on the cover raster. A shell whose path passes through our body counts as a direct hit.
- **Trigger:** our own path for the next 2.5 s is simulated from the current velocity and the route's move command (ground acceleration, walk or boost cap). The rule acts only when that path would take damage: a direct hit, or a burst within 7 m of our body plus a 1 m margin.
- **The step:** 16 directions are scored by the same prediction, each with the first 4-12 m clear on the ground grid and ending 3 m inside the zone. It takes the least damage and, among near-equal options, the direction closest to the route, so it often just boosts on along the route. A step must cut the predicted damage by at least 10 HP. Steps are judged against shells that threaten the route or land within 25 m of it.
- **Gates as in v8:** never during an urgent zone return (`mode == "return"`, late, or outside the zone). After a shell dodge ends, a dodge for a new shell waits 1 s. Boost is used only while more than 20 energy remains.
- **Unchanged:** bullets keep the v8 behaviour, and aim, fire, pickups and every other command are untouched.
- **Counters:** `ShellDodge.decisions` and `ShellDodge.counts`.

Evidence (`py tools/shell_dodge_trial.py`: the exported `4d8a32d` and this tree as real bot processes from identical starts). A stationary mortar mech lobs shells at where we will be (low or high arc, 1.5 m aim spread, one every 2.6 s) while we walk a 120 m route. A shell is shown only while it is visible: within 45 m, or within 200 m and 60 deg of our aim. It bursts on the terrain or our body. Knock-back and energy drain are applied.

| Check | lead-shots (2.90) | mortar-dodge |
| --- | --- | --- |
| shell landing on our route in 1.2 s | walks on `[1, 0]` | `[0.92, 0.38]`, boosting |
| shell landing 25 m to the side; shell on us during an urgent zone return; shell landing after the 2.5 s horizon | | identical |
| 16 tuning episodes (shooter 60-200 m, abeam or oblique, low or high arc) | 10,240 damage: 23 direct hits, 16 splashes; route time 160.1 s | 0 damage; route time 141.4 s; 609 boost energy; 0 zone exits; every route finished |
| 16 held-out episodes on fresh routes | 12,040 damage: 27 direct, 19 splashes; 158.8 s | 360 damage (1 direct hit at 62 m, low arc); 137.9 s; 764 energy; 0 zone exits |
| controls: shells aimed 30 m wide (low and high arc), a gun shooter only, shells on us while outside the zone | | identical commands on every decision (100, 100, 103, 67) |
| standard recording (no shell listed) | | 0 of 300 answers differ, debug included |
| decision time with shells in flight (this machine) | p99 0.8 ms | p99 2.7 ms, max 3.3 ms; 10 shells at once max 7.7 ms |

**Trace** (100 m abeam, low arc; shells fired at 0.3 s and 2.9 s):

- **First shell:** visible at 0.4 s. lead-shots walks on and the shell bursts on its body at 1.75 s (360 damage). mortar-dodge keeps the route direction but boosts from 0.4 to 1.6 s, and the shell bursts 11.8 m behind it (0 damage).
- **Second shell:** visible at 3.0 s. lead-shots takes a direct hit at 4.25 s (360). mortar-dodge steers `[0.92, 0.38]`, boosting, for 0.5 s, then boosts on along the route until 4.2 s; the burst is 11.9 m away (0 damage).

**What the trial cannot show:**

- **The shooter model:** the trial shooter leads our current velocity, as a simple house bot might. A shooter that anticipates the dodge, or shells hidden behind buildings until late, would make it harder.
- **Buildings:** the trial has no buildings for shells, though the bot's own prediction uses the cover raster.
- **The splash rule:** the trial assumes splash is measured from our centre; the bot plans with our body radius plus a 1 m margin.
- **Activation:** if no house bot fires a mortar at us in the 48 practice matches, the score reproduces 2.90 exactly.

**Narrowed check:** `tools/dodge_trial.py`'s scripted "mortar shell on course" case expected the bot to ignore the shell entirely. It now requires only the non-movement commands to be identical. That shell is on course for a direct hit, and the new rule boosts on out of it; the v8 bullet dodge itself still ignores shells.

**Other checks:** all pass.

- the dodge trial (tuning 441 to 404 hits, held-out 596 to 554, as before);
- the engagement trial and `--heldout`;
- `lead_trial --baseline 3b290b0`;
- `entrypoint_trial --baseline 4588e6b`;
- combo check, objective checks, route, pickup and target trials;
- the probe and `verify.py`.

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

## Combination: mortar-dodge + crossing-fire (on `1645c22`, the 3.00 commit)

Both changes scored above their shared parent, lead-shots (`4d8a32d`, 2.90), on their own: mortar-dodge 3.00 (+0.10) and crossing-fire 2.94 (+0.04). This branch is mortar-dodge with crossing-fire's change applied unchanged (the four lines in `targeting.py`, plus crossing-fire's trial and the three trial narrowings it made). The shell dodge only sets move and boost, and crossing-fire only changes the fire decision for a passive opponent when the aim is led, so the two never write the same command. Ready name `zone-runner-md-crossing-fire` (names are cut at 32 characters).

| Check | Result |
| --- | --- |
| `py tools/combo_md_cf_check.py` (against the exported mortar-dodge and crossing-fire) | recording: commands other than fire identical to mortar-dodge on 300 of 300, fire identical to crossing-fire on 300 of 300 (it differs from mortar-dodge on crossing-fire's 8); 4 scripted shell decisions move as mortar-dodge and fire as crossing-fire; 32 closed-loop shell routes identical to mortar-dodge (360 damage in total, the same single direct hit); 9 crossing-fire gunfights identical to crossing-fire |
| `py tools/shell_dodge_trial.py --baseline c120041` | identical to mortar-dodge's own run: shell damage 10,240 to 0 (tuning) and 12,040 to 360 (held-out), every route finished, 0 zone exits; scripted checks and controls pass; 0 of 300 recording answers differ from crossing-fire |
| `py tools/crossing_fire_trial.py --baseline 1645c22` | fires where mortar-dodge held on the passive crossing opponents and lands hits; controls identical; only fire differs on the recording |
| regressions | engagement trial and `--heldout`, `lead_trial --baseline 3b290b0`, `entrypoint_trial --baseline 4588e6b`, dodge trial, combo check, objective checks (12), route (150/150), pickup and target (11) trials, engagement probe and `verify.py` all pass |

## hide-spot on the combination (on `4f4596e`, the 3.04 commit)

The one change of hide-spot (`c08eef9`, built on crossing-fire `c120041` and still pending there) moved unchanged onto the 3.04 combination of mortar-dodge and crossing-fire. In plain zone mode, with no mech listed and no mech hitting us for 5 s, the goal becomes the least exposed walkable node within 60 m of the next centre (and within 100 m on foot, 8 m inside the next circle), used only when it is at least 0.10 less exposed than the centre; on the spot the bot holds still. Exposure comes from `exposure.u8` (byte-identical to `c08eef9`'s, 48,508 bytes; `.gitattributes` keeps `*.u8` binary), built by `tools/build_exposure.py`. Files: `hide.py`, `exposure.u8`, `.gitattributes`, the `bot.py` hook, the Dockerfile and `.dockerignore` lines, `tools/build_exposure.py`, `tools/hide_trial.py` (baseline now `4f4596e`), and hide-spot's narrowings of `objective_checks.py`, `route_trial.py` and `pickup_trial.py` (they accept standing on the hide spot as reaching the zone goal). Ready name `zone-runner-md-cf-hide-spot`.

| Check (`py tools/hide_trial.py`, against the exported `4f4596e`) | Baseline | hide-spot on the combination |
| --- | --- | --- |
| exposure where it stands, 18 zones with a spot | 0.58 | 0.34 (lower in 18 of 18) |
| same, 6 zones with no clearly better spot (control) | 0.33 | 0.33 (identical actions) |
| 3 patrolling hunters, 12 x 90 s: median first seen, damage, deaths | 0.45 s, 15,885, 9 of 12 | 2.75 s, 15,030, 10 of 12 |
| 3 hunters walking at our true position, 12 x 90 s | 3.35 s, 11,385, 7 of 12 | 46.65 s, 8,572, 5 of 12 |
| controls: urgent zone return (while it lasts), opponent listed, supply drop at 60% HP | | identical on every decision |
| recording | | 0 of 299 decisions differ |

These are the same numbers as hide-spot against crossing-fire: the hunter trial has no shells and no passive opponent, so the combination's two changes do not act there.

| Other check | Result |
| --- | --- |
| `py tools/combo_md_cf_check.py` | PASS unchanged: the recording, the scripted shell decisions, the 32 shell routes and the 9 gunfights never trigger the hide spot (an opponent or shell shooter is listed, or no spot is clearly better) |
| `py tools/shell_dodge_trial.py --baseline c120041` | shell damage 10,240 to 0 and 12,040 to 360 as for mortar-dodge; 0 of 300 recording answers differ from crossing-fire. With the default baseline (lead-shots) the recording check reports crossing-fire's own 8 fire changes, exactly as for `4f4596e` itself |
| regressions | engagement trial and `--heldout`, crossing-fire trial, `lead_trial --baseline 3b290b0`, `entrypoint_trial --baseline 4588e6b`, dodge trial, combo check, objective checks (12), route (150/150; median 42.2 s against 40.5 s, standing on the spot counts as arrival), pickup and target (11) trials, engagement probe and `verify.py` pass |
