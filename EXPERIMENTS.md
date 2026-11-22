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
| no-mortar | `no-mortar` | `df1be152ba1bee40a368979ccb01eef1b7f9b347` | `3b290b0` (2.63) | pending | pending |
| lead-shots | `lead-shots` | `4d8a32d3c453d3efb430baddb4bd141678417d77` | `3b290b0` (2.63) | **2.90** | +0.27 |
| offense-upgrades | `offense-upgrades` | this commit (tag `offense-upgrades-candidate`) | `4d8a32d` (2.90) | pending | pending |

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
| lead-shots | `3b290b0` | this commit (tag `lead-shots-candidate`) | aiming the gun where a moving opponent will be when the bullet arrives lands more hits, so we kill more of the house bots that hunt us before we die | every decision with a moving opponent: aim led on 169 of 300 recording decisions | hits 56 to 109 of 130 shots (43% to 84%) in a closed-loop gunfight; never fewer; laser still released onto a moving target; only the aim changes | **2.90 (+0.27)** | **keep: best score** |
| offense-upgrades | `4d8a32d` | this commit (tag `offense-upgrades-candidate`) | taking gun and held-weapon upgrades before defensive ones raises damage output, and kills are placement points | only when an upgrade offer appears (at 1, 3, 6, 10 ... cubes); 0 offers on the recording | picks the offense upgrade in all 4 crafted offers that contain one, identical in the 2 that do not; gun dps after three offers 215.6 vs 187.5 | pending | pending your score |
| no-mortar | `3b290b0` | `df1be15` (tag `no-mortar-candidate`) | never carrying a mortar helps: we cannot aim it, and holding one makes every laser hit on us cook off for +60% | whenever v5 would detour for or walk over a mortar (a third of floor weapons); 0 on the recording (no mortar within 70 m) | never carries a mortar in any layout; takes a laser instead when one is near; control identical | pending | pending your score |

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

## offense-upgrades (on `4d8a32d`, the 2.90 commit)

The bot answers upgrade offers with a priority list. The old order was armor, plating, nanites, servos, gun_rate, sensors. The new order:

1. gun: gun_rate, gun_damage, gun_velocity, gun_mag;
2. the held weapons' own upgrades: laser_damage, laser_charge, laser_pierce, lightning_chain, lightning_efficiency, lightning_range, mortar_reload, mortar_splash, mortar_velocity;
3. the old order: armor, plating, nanites, servos, sensors.

Offers only list weapon upgrades for weapons we hold (protocol section 10). Upgrades on neither list (capacitor, reactor, jets, gyros) still fall back to the first choice, as before. Nothing else changes.

Evidence (`py tools/upgrade_trial.py`, against `4d8a32d`, both as real bot processes):

| Offer | Baseline picks | offense-upgrades picks |
| --- | --- | --- |
| armor, gun_rate, sensors | armor | gun_rate |
| plating, nanites, gun_damage | plating | gun_damage |
| armor, servos, sensors (no offense upgrade) | armor | armor |
| capacitor, armor, laser_damage (laser held) | armor | laser_damage |
| laser_damage, plating, gun_mag (laser held) | plating | gun_mag |
| reactor, jets, gyros (on neither list) | reactor | reactor |

- **Three offers from one seeded draw:** the baseline takes nanites, plating, nanites (gun 187.5 dps, 1,610 max HP). offense-upgrades takes nanites, plating, gun_damage (gun 215.6 dps, 1,610 max HP).
- **Activation:** the recording has no offers (no cubes held), so this acts only in matches where we collect cubes, from kills (2 plus the victim's), drones (2) or crates (1).
- **Other checks:** the lead trial against `3b290b0`, the laser trial against v8, the engagement trial and both held-out seeds, objective checks, route, pickup and target trials, the probe and `verify.py` all pass.

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
