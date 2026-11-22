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
| mortar-arc | `mortar-arc` | `8670353ea471e3156f988b13b46c7ad01daea128` | `4d8a32d` (2.90) | 2.90 | +0.00 (probably never fired; an exact tie can also come from small changes cancelling) |
| mortar-dodge | `mortar-dodge` | `1645c22576e99d0afe6cb9ce8ec37ad0d9bae616` | `4d8a32d` (2.90) | 3.00 | +0.10 |
| mortar-dodge + crossing-fire | `combo-mortar-dodge-crossing-fire` | `4f4596e12bf916fe76039a7e75652cf4036d35f4` | `1645c22` (3.00) | 3.04 | +0.04 (exactly crossing-fire's own gain) |
| plating-first | `plating-first` | `4ec3f8a664f39b2d0922f00b21a44ff3a7336575` | `c120041` (2.94) | 2.94 | +0.00 (an offer listing both plating and armor is rare, about 1 in 25 offers) |
| dodge-tuned | `dodge-tuned` | `dd9b7313b69aa7a9ab655d731acd3774ba4467fc` | `1645c22` (3.00) | 3.10 | +0.10 |
| dodge-tuned + mortar-dodge + crossing-fire | `dodge-tuned-on-combo` | `3ddcb13c5da09ee0bfa5b8a0228c053f4c343278` | `4f4596e` (3.04) | 2.94 | -0.10 (and -0.16 vs dodge-tuned without crossing-fire: the two did not add; crossing-fire's +0.04s look like luck) |
| dodge-margin | `dodge-margin` | `c5a5c7e6a2ec47fed99e4323c53450357c8d0418` | `dd9b731` (3.10) | 3.06 | -0.04 |
| kite-on-dodge-tuned | `kite-on-dodge-tuned` | `da522cddee7fdd5a824c3fc05bcbe60ea0af16ad` | `dd9b731` (3.10) | 3.10 | +0.00 |
| stealth | `stealth` | `80b6727383925685a77a08d847273d63f2973bf6` | `d62b1b5` (hide-spot on dodge-tuned) | 2.85 | -0.25 vs dodge-tuned: hiding and holding fire cost kills, and practice points are our kills |
| farm-power | `farm-power` | `8064167d11936561991186bf35261946ffbec33d` | `dd9b731` (3.10) | 3.25 | +0.15 |
| squad-fire | `squad-fire` | `90d298b7fc7ac7a79dd7d596133926a0d6ba1dc2` | `8064167` (3.25) | **3.65** (best) | +0.40 |
| squad-move | `squad-move` | `35a0bdd5c4c7be51b5b1d6620e454958e3bf4cd3` | `8064167` (3.25) | 3.52 | +0.27 |
| squad-econ | `squad-econ` | `f8dc9bfdf039c6ebd3978b203a34df0a9e0ef26c` | `8064167` (3.25) | 3.29 | +0.04 (within the noise) |
| squad-fire-move | `squad-fire-move` | `8805ed6c2b3365f31784f767a099cdd6a3edfef8` | `90d298b` (3.65), with squad-move `35a0bdd` (3.52) | pending | pending |
| squad-all | `squad-all` | `9399d0de1b55b29f64462d9926c132529f060e8d` (tag `squad-all-candidate`) | `8805ed6` (squad-fire-move), with squad-econ `f8dc9bf` (3.29) | pending | pending |
| squad-all-sticky | `squad-all-sticky` | `076bec93c96f3181c6080f0fbefb26a9af3b9f63` | `9399d0d` (squad-all) | pending | pending |
| squad-all-fixed | `squad-all-fixed` | `fea757a8d484bae92c488810c00f0c401a5911a5` (tag `squad-all-fixed-candidate`) | `076bec9` (squad-all-sticky) | pending | pending |
| squad-all-zone | `squad-all-zone` | this commit (tag `squad-all-zone-candidate`) | `fea757a` (squad-all-fixed) | pending | pending |

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
| mortar-dodge | `4d8a32d` | `1645c22` (tag `mortar-dodge-candidate`) | stepping out of the blast of a visible mortar shell that would land on our route cuts the damage taken (200 direct + 160 splash per shell) | only while a mortar shell is visible and would hit our route within 2.5 s; 0 on the recording (no shell listed) | closed-loop shell damage 10,240 to 0 (tuning) and 12,040 to 360 (held-out); every route finished, 0 zone exits; 4 controls identical on every decision | **3.00 (+0.10)** | **keep: best score; parent of the dodge tuning** |
| dodge-tuned | `1645c22` | `dd9b731` (tag `dodge-tuned-candidate`) | dodging bullets more often (one dodge per 0.5 s instead of 2 s, each 0.2 s instead of 0.3 s) cuts the hits a leading gun shooter lands | every on-course bullet outside the cooldown, as v8; on the recording 1 dodge and 1 skip inside the cooldown (v8: 1 dodge, 3 skips) | parameters chosen by `tools/dodge_sweep.py` on the 12 tuning routes and confirmed on the 16 held-out routes: 369 vs 404 hits (tuning), 517 vs 554 (held-out); hits per second of route 2.69 vs 3.03 and 2.90 vs 3.25; arrival +0.3 and +0.5 s; 0 zone exits, every route finished | 3.10 (+0.10) | keep: parent of farm-power, dodge-margin (3.06), kite (3.10) and stealth (2.85) |
| farm-power | `dd9b731` | `8064167` (tag `farm-power-candidate`) | in the first 180 s of a match, with no game mech listed and no mech hitting us, shooting passive drones (2 cubes each) and crates (1 cube, a weapon half the time) within 150 m and walking to cubes within 120 m makes the bot stronger (+4% HP and damage per cube, upgrade offers at 1, 3, 6 and 10 cubes) before the hunters arrive | 8 of 300 recording decisions (crate shots at a crate in view with nothing else listed); every match with drones, crates or cubes in reach while nobody is around in the first 3 minutes | tools/farm_trial.py against dd9b731: drone kills 0 to 3 (60, 120, 145 m), crates destroyed 0 to 2 (60, 120 m), cubes collected 0 to 2 (50 m in 4.0 s, 110 m in 9.2 s); 11 controls identical (beyond range, behind cover, a mech listed, a recent hit, after 180 s, an urgent zone return) | 3.25 (+0.15) | keep: parent of squad-fire (3.65), squad-move (3.52) and squad-econ (3.29) |
| squad-fire | `8064167` | `90d298b` (tag `squad-fire-candidate`) | in practice matches (after 20 s, while every death so far is one of our kills) shooting only mechs that are engaging us or easy to finish, focusing the weakest of them, releasing the laser early when the shot already kills, firing the gun only when the torso can reach the lead point, gating lightning to its range and cone, preferring a laser (sought from 240 m, swapped in for lightning, never a mortar) and a laser-first upgrade order turns more fights into kills | every practice match from 20 s on (the mode needs no event to fire); 0 of 300 on the recording, where a mech dies to someone else at 18 s | `tools/squad_fire_trial.py` against 8064167: 18/18 engagement cases, target choice and stickiness, lethal release at 0.30 s on a 150 HP target (parent 0.75 s), full charge held below 0.9 of the target's angular radius, 7/7 loot cases, 60/60 upgrade picks, identical to the parent before 20 s and after a death we did not cause; closed-loop hunter: gun only 6 kills vs 4 in 6 fights, gun + laser 6 vs 6 but 1.2 s slower (engages at 190 m, not 200 m) | **3.65 (+0.40)** | **keep: best score; parent of squad-fire-move** |
| squad-move | `8064167` | `35a0bdd` (tag `squad-move-candidate`) | in practice the house mechs hunt us as one squad, so choosing where to stand in a fight (range kept per weapon, a line of fire when a shot is ready, out of the other hunters' sight, a random strafe), retreating briefly to cover only when outnumbered and hurt, and sidestepping aimed laser charges lets us kill more of them before we die | practice mode only (from 20 s, while every death is one of our kills): every decision with a mech target, plus LoseRule retreats and laser sidesteps; 0 of 300 on the recording (an outside death at 18 s switches it off) | tools/squad_move_trial.py against 8064167: 24/24 scripted checks (range 85/85/119/120 m from gun and laser starts, line of fire, hidden from a second hunter, strafe with 17 flips in 10 s, cube grab, finish mode closes to 19 m, 1.5 s LoseRule pulse, hidden cell 21 m away after 1.3 s, laser sidestep; identical before 20 s, after an outside death and on an urgent return); 9 closed-loop fights: damage 9,788 to 9,676, kills 5 to 6, deaths 5 to 4 | 3.52 (+0.27) | keep: its fight movement joins squad-fire in squad-fire-move |
| squad-econ | `8064167` | `f8dc9bf` (tag `squad-econ-candidate`) | in practice mode (after 20 s, while every death so far was our kill) gathering power all match (cubes always; crates and drones above 50 % HP with no danger), camping still on an inner zone circle between fights and scanning all round wins more of the fights the hunting squad brings | every practice match from 20 s until a house bot dies to something other than us; 0 of 300 recording decisions (a death we did not cause at 18 s switches the mode off) | `tools/squad_econ_trial.py` against 8064167: after 180 s a crate at 100 m, a drone at 120 m and a cube at 90 m are farmed (farm-power: none); no crate or drone farming at 45 % HP, with an engaged mech listed, or within 4 s of a mech hit; hysteresis, the 30 s give-up and 60 s ban, zone camping, zone must over loot, idle spin and sweep and the stuck rule behave as designed; identical to farm-power before 20 s, after a death we did not cause, and on the recording | 3.29 (+0.04) | within the noise; joins squad-fire-move as the third practice part in squad-all |
| squad-fire-move | `90d298b` (squad-fire) with `35a0bdd` (squad-move) | `8805ed6` (tag `squad-fire-move-candidate`) | the two practice parts that scored best on their own act on different parts of the action (squad-fire: whom to shoot and how; squad-move: where to stand), so together they keep both gains: the move part fights the mech the fire part shoots | practice mode (from 20 s while every death is one of our kills), as both parts: fire decisions on every practice decision, fight movement while an engaged mech is listed; 0 of 300 on the recording | `tools/squad_fire_trial.py` all checks (fights: gun only 4 to 6 kills, gun + laser 6 to 6); `tools/squad_move_trial.py` 24/24 (one check now compares only movement on the urgent zone return), 9 closed-loop fights: kills 5 to 6, deaths 5 to 3; `tools/practice_trial.py`: identical to farm-power before 20 s, after an outside death and on the recording, decision time p99 3.9 ms through stdin/stdout with the cover search running, 6,000-decision fuzz clean | pending | pending your score |
| squad-all | `8805ed6` (squad-fire-move) with `f8dc9bf` (squad-econ) | `9399d0d` (tag `squad-all-candidate`) | the economy part (power all match, camping on an inner zone circle, the idle scan, the stuck rule) adds to the two fight parts when it only moves us while there is nobody to fight and never takes the aim or the triggers from the fire part | practice mode, as all three parts: fire decisions on every practice decision, fight movement while an engaged mech is listed, the economy plan otherwise; 0 of 300 on the recording | the three trials pass (fire: all, two expectations adjusted for the idle scan and the timing line p99 3.4 ms; move 24/24 with the urgent-return check adjusted; econ 24/24 unchanged); `tools/practice_trial.py`: identical to farm-power before 20 s, after an outside death and on the recording, 12/12 priority checks, decision time p99 3.7 ms through stdin/stdout with every part busy, fuzz clean | pending | pending your score |
| squad-all-fixed | `076bec9` (squad-all-sticky) | `fea757a` (tag `squad-all-fixed-candidate`) | seven corrections to the practice design, each where it acted against its own intent: fight only a mech we can shoot, keep a laser pursuit alive, grab only cubes we can reach, ignore supply drops and the relocate hop, keep collecting cubes under threat, never fire a mortar, and turn the torso onto a lethal laser shot one decision earlier | practice mode only: the target-only fight on every decision with an engaged mech out of sight or beyond 240 m; the laser pursuit whenever a laser is wanted and in reach; the others when their situation arises; the recording stays identical to farm-power up to 20 s | every fix has a check that fails on `076bec9` and passes here (see below); the four practice trials pass apart from the mode-switch checks that already failed on `076bec9`; identical to farm-power before 20 s | pending | pending your score |
| squad-all-zone | `fea757a` (squad-all-fixed) | this commit (tag `squad-all-zone-candidate`) | in practice mode the zone should take the movement only on a deadline: outside the next circle with time to spare, and in the last phase, the bot keeps fighting, retreating, sidestepping and dodging; on a zone-must walk the shell dodge still acts and the bullet dodge is blended into the walk; only hurry (outside the current circle, or the walk ends at or after the deadline) is the old straight run home with boost and no dodge | practice mode only, whenever the bot is outside the next circle within about 4-5 s of walking plus the time to the shrink, or the next radius is below 8 m, and zone must does not hold (the parent's urgent return); 0 of 300 recording answers differ from the parent (it ends at 36.8 s, before any shrink) | zone trial: 10/10 scripted checks and both zone-run checks; closed-loop zone run under a gun hunter at 100 m: hits 248 to 206 (comfortable deadline) and 248 to 225 (tight), deaths 4 to 0 of 8 in both, 0 decisions outside the circle for either build, the circle reached at 29.5 s and 21.3 s instead of 11.0 s; the five practice-part and dodge trials give the parent's results exactly; identical to farm-power before 20 s | pending | pending your score |

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

## dodge-tuned (on `1645c22`, the 3.00 commit)

One change to the v8 bullet dodge in `dodge.py`: `COOLDOWN_S` 0.5 (was 2.0) and `DODGE_S` 0.2 (was 0.3, so each dodge steers for 2 decisions instead of 3). Everything else, including the shell dodge, is unchanged.

**Why:** the bullet dodge is the largest single gain so far (v8, +0.42). In the dodge trial a gun shooter that leads every bullet at our current velocity fires every 0.25 s; with a 2 s cooldown most of its bullets arrive while the dodge is waiting. Shorter, more frequent steps keep changing our velocity, so a leading shooter's aim is wrong more often.

**How the values were chosen** (`py tools/dodge_sweep.py`, each variant a real bot process on the trial's reactive episodes): 46 settings on the 12 tuning routes (cooldown 0.25-2.0 s, dodge 0.1-0.5 s, horizon 1.0/1.5 s; the horizon made no difference), then the best 6 and the current setting on the 16 held-out routes.

| Setting | Tuning: hits, hits/s, arrival | Held-out: hits, hits/s, arrival |
| --- | --- | --- |
| v8 (cooldown 2.0, dodge 0.3) | 404, 3.03, 11.1 s | 554, 3.25, 10.6 s |
| cooldown 1.0, dodge 0.3 | 374, 2.67, 11.7 s | 532, 2.96, 11.2 s |
| **cooldown 0.5, dodge 0.2 (dodge-tuned)** | 369, 2.69, 11.4 s | 517, 2.90, 11.1 s |
| cooldown 0.35, dodge 0.2 | 370, 2.69, 11.5 s | 524, 2.90, 11.3 s |
| **cooldown 0.25, dodge 0.2 (dodge-rapid)** | 351, 2.33, 12.5 s | 518, 2.69, 12.0 s |
| cooldown 0.5, dodge 0.3 | 349, 1.90, 15.3 s | 526, 2.17, 15.1 s |
| cooldown 0.25, dodge 0.3 | 407, 1.43, 23.8 s (7 routes unfinished, 3 zone exits) | not run |

dodge-tuned takes the setting that lowers both total hits and the hit rate with the least delay; dodge-rapid takes the lowest hit rate under fire at about 13% more route time. Longer dodges (0.3 s and up) with short cooldowns stall the route. The shooter model is ours: house bots' aim is unknown, which only the official score can judge.

| Check | Result |
| --- | --- |
| `py tools/dodge_trial.py` (against v6) | 9/9 scripted checks; reactive hits 441 to 369 (tuning) and 596 to 517 (held-out), 0 zone exits, every route finished |
| `py tools/shell_dodge_trial.py --baseline 1645c22` | every shell episode identical to mortar-dodge (0 and 360 damage, same routes and energy): the shell dodge is unchanged. Its gun-only control differs by design (damage 1,620 to 1,440 against a 100 m gun shooter), and its shell checks expect a baseline without the shell dodge, so they report no gain |
| `py tools/lead_trial.py --baseline 3b290b0` | led aims as before; narrowed so that move, boost and jump are not compared on the 3 recording decisions around the candidate's bullet dodges (the baseline's dodge lasts one decision longer); any other difference still fails |
| regressions | engagement trial and `--heldout`, `entrypoint_trial --baseline 4588e6b`, combo check, objective checks (12), route (150/150), pickup and target (11) trials, engagement probe and `verify.py` pass |

## farm-power (on `dd9b731`, dodge-tuned, official 3.10)

**Why:** practice points come from house bots we kill before we die, and that happens early in a match. Cubes make every later fight easier: each is +4% max HP and +4% damage, and the cube count brings upgrade offers at 1, 3, 6 and 10 cubes. A passive drone drops 2 cubes, a crate drops 1 and a weapon half the time. So the bot gathers power while nobody is hunting it yet.

**The change** (only before 180 s of match time, with no game mech listed and no game mech hitting us within the engagement's 5 s attack memory; a listed mech or a hit hands control straight back to the normal engagement and the dodges):
- `targeting.py`: passive NPC drones within 150 m with a clear line become targets (drone-hunt's rule, `160361c`, with a 150 m range), and with no opponent to face the gun aims at the nearest crate within 150 m with a clear line (crate-shoot's rule, `27b9d89`, with a 150 m range). Only the gun fires at crates; crates are skipped during a pickup detour.
- `farm.py` (new): during ordinary zone movement inside the zone, walk to the nearest cube within 120 m that is within 4 m of our height, inside the next circle with 4 m to spare, reachable (straight line or its own planner's path) and leaves the pickup detour's zone timing margin. The inherited 16 m cube rule applies otherwise.
- After 180 s the bot behaves exactly as dodge-tuned.

| Check | Result |
| --- | --- |
| `py tools/farm_trial.py` (against dd9b731) | drones: killed at 60 m (1.9 s), 120 m (2.4 s) and 145 m (2.8 s), dodge-tuned never shoots them; crates: destroyed at 60 m and 120 m (the 120 m one also left a weapon), the 145 m crate is shot at (21 shots) but survives 12 s; cubes: collected at 50 m (4.0 s) and 110 m (9.2 s). Controls identical: drone or crate at 170 m, after 180 s, with a mech listed, behind cover, after an unseen mortar hit; cube at 140 m, after 180 s, with a mech listed, during an urgent zone return |
| recording | 8 of 300 answers differ, all crate shots (no drone or cube farming happens there) |
| regressions | engagement trial (the scripted "distant passive NPC" at 120 m is now shot, as intended; a new copy of it after 180 s is ignored as before) and `--heldout` (R1 allows a passive drone within 150 m in the first 180 s with no mech listed and no mech hit in 5 s), `lead_trial --baseline 3b290b0` and `entrypoint_trial --baseline 4588e6b` (both leave out the 8 recording decisions spent on a crate), dodge trial (369 and 517 hits, unchanged), combo check, objective checks, route (150/150), pickup and target trials, engagement probe and `verify.py` pass. `shell_dodge_trial --baseline dd9b731` reports no shell gain because the baseline already dodges shells (every shell episode identical); its recording differs on the 8 crate shots |

## squad-fire (on `8064167`, farm-power, official 3.25)

**Why:** in practice the 15 house bots hunt us together and the score is the number we kill before we die. The bot already shoots at whoever fights it; this change makes every shot count in that setting: it ignores mechs that are neither threatening us nor easy to finish, focuses the weakest engaged one, and handles each weapon so damage is not wasted (no gun shots while the torso is still turning, no lightning arcs out of range, a laser released the moment its charge kills). It also wants the laser more than any other weapon and upgrades it first.

**When it applies:** practice mode, which starts after 20 s of match time and lasts while every death so far is one of our kills (start count from the first observation, minus `alive`, minus our `kill` events). Five decisions in a row with a death we did not cause end it for the rest of the match; the wait covers a decision of lag between `alive` and our `kill` event. Outside practice mode the bot is farm-power exactly. Movement and the dodges are untouched.

**The change** (`squad.py`, new; `bot.py` applies it; `loot.py` and a line-of-fire cache in `targeting.py`):
- Engagement. A listed mech is engaged when it is within 60 m, hit us in the last 6 s, the match is late (next circle radius 70 m or less, or 3 or fewer mechs alive), it closes on us faster than 3 m/s within 180 m, it is under 40% HP within 160 m, or its torso points within 0.22 rad of us within 190 m. Any other mech is never shot and never looked at.
- Target. Engaged, with a clear line (body centre, or 85% of the height over low cover), within 240 m. Lowest score wins: distance + 0.2 x HP, minus 100 at 30% HP or less, minus 120 if it was the target in the last 2 s, minus 40 if it hit us in the last 4 s, minus 15 if it is closing faster than 3 m/s. With no target the torso faces the nearest engaged mech (or one that hit us in the last 6 s and was listed in the last 2.5 s), else the bearing of a drone hit, else of any hit, in the last 2.5 s, all at pitch 0; with only unengaged mechs listed it looks where it would with nobody listed.
- Drones: shot back at in self-defence (a drone hit us in the last 3 s: the visible drone within 150 m that hit us, or the one closest to the hit's bearing within 0.7 rad). farm-power's farming shots (passive drones and crates in the first 180 s) are kept as they were.
- Gun. Aims at lead-shots' intercept point and fires when the target is within 0.96 of gun range, rounds are loaded, and the lead point is within reach of the torso this tick (yaw and pitch errors less one tick of turning, under atan(0.75 r / d) and atan(0.4 h / d)). Early reload only with nothing to shoot, at 60% of the magazine or after 3 s without a threat.
- Laser. Held while a target is within 0.97 of laser range. Between the minimum charge and full, it is let go as soon as 80% of the charge's damage (damage x (0.35 + 0.65 x charge / full) x (1 + 0.04 per cube, up to 10), x1.6 against a mortar carrier) covers the target's HP and the torso is on the direct aim point. Past 45% of a full charge the torso moves from the gun's lead point to the direct point (body centre plus 0.125 s of the target's motion, seen from our muzzle 0.075 s ahead). A full charge goes only when the torso is within 0.9 x atan(0.75 r / d) in yaw and atan(0.4 h / d) in pitch. Never charged at a drone or crate; a charge in progress stays held while any mech is listed.
- Lightning: only within its range less 1.5 m, inside its cone less 0.05 rad, with energy for the shot.
- Weapons: laser over lightning, never a mortar. A wanted pickup within 3.7 m (3.6 m in height) is taken, with `drop` = slot 1 when both slots are full, but not while the laser charges. The pickup detour also runs to replace lightning or a mortar, reaches lasers within 240 m and other weapons within 150 m, ranks them by value per metre (laser 150, otherwise 130 with slot 1 empty or 60), and keeps the zone-timing checks; the 80 m added-trip cap is dropped in this mode, and a far route search may take up to 12 decisions.
- Upgrades: plating, armor, laser_damage, laser_charge, nanites, gun_damage, gun_rate, lightning_efficiency, lightning_range, servos, gun_mag, gun_velocity, gyros, lightning_chain, reactor, capacitor, mortar_reload, mortar_splash, mortar_velocity, sensors, jets, laser_pierce.

**Evidence** (`py tools/squad_fire_trial.py`, parent and candidate as real bot processes; scripted scenarios at t = 30 s on the open lawn, the torso slewing at the configured rates and the laser charging, firing and cooling as the protocol says):

| Check | Result |
| --- | --- |
| engagement | each of the six rules engages just inside its limit (aim on the mech, gun firing) and not just outside it (55/65 m; hit 6.0/6.1 s ago; next radius 70/71 m and 3/4 alive; closing 3.5/2.5 m/s at 150 m and 3.5 m/s at 185 m; 500/600 HP at 150 m and 500 HP at 165 m; torso 0.20/0.25 rad off at 150 m and 0.20 rad at 195 m). A passive mech at 120 m: never aimed at, never shot (the parent aims and fires on 30/30) |
| target choice | a 400 HP mech at 200 m (score 180) beats a full one at 50 m (330); it stays the target when it heals to 450 HP and the near one drops to 1000 (290 - 120 vs 250), and gives way when the near one drops to 500 (150). The same middle phase without the history picks the near one. The parent faces the near mech throughout |
| laser | 150 HP target: released at 0.30 s of charge (threshold 0.283 s), on the body; parent 0.75 s. 240 HP mortar carrier: 0.30 s. 150 HP with our 10 cubes: 0.20 s. 1400 HP control: no early release; released at full charge (0.70 s, which is within 0.051 s of full and counts as full). Full charge with the torso held still 0, 0.010, 0.016 rad off a mech at 100 m: released; 0.020 and 0.040 rad: held (the parent releases at 0.020). Torso 40 degrees off and turning: held, then 2/2 beams on the body. Never charged at a drone that hit us; the gun shoots it |
| loot (closed loop: we walk where the bot steers) | laser taken over a closer lightning; laser chosen over lightning at equal distance (60 m); laser fetched from 200 m (16.9 s); holding lightning, a laser 100 m away is fetched and swapped in with `drop` 1; lightning ignored while holding a laser; a mortar 20 m away ignored (the parent takes it); holding a mortar, lightning 40 m away swapped in |
| upgrades | 60 random offers: the earliest choice in the list on 60/60 (the parent's pick differs on 28) |
| mode switch | identical to the parent on all 965 decisions of the engagement trial's scenarios (before 20 s), on a three-mech scenario before 20 s (200/200), on the same run to 45 s after a death we did not cause at 10 s (450/450), from 35.5 s on after such a death at 35 s (95/95; it differs on 149/149 decisions before it), and on the recording (300/300). A death whose `kill` event arrives one decision late keeps practice mode on |
| timing | p99 2.6 ms over 6,350 candidate answers through stdin/stdout, 3.2 ms with 15 engaged mechs and a charging laser (this machine) |
| fuzz | 4,800 random in-process decisions (2,217 in practice mode): no exception, every action valid JSON with two boolean triggers and a finite aim |

Closed-loop fight (one 1400 HP hunter with a gun walks in from 200 m aiming at us and shooting; we stand still; three paths, two seeds each; 25 s limit):

| Loadout | Kills (parent / squad-fire) | Mean kill time | Gun hits / shots | Beams on target | Damage taken |
| --- | --- | --- | --- | --- | --- |
| gun only | 4 / 6 | 18.9 / 18.7 s (25 s if none) | 186/277 / 192/257 | - | 11,700 / 11,340 |
| gun + laser | 6 / 6 | 6.5 / 7.7 s | 66/107 / 72/103 | 18 / 18 | 4,140 / 5,040 |

With the gun alone, holding fire while the torso turns saves rounds: the hunter strafing at 150 m dies in 23-24 s instead of surviving. With the laser, squad-fire is 1.2 s slower: the hunter is engaged when it aims at us within 190 m, about 0.9 s after the parent (which shoots any mech pointing a weapon at us from 280 m) starts charging, and a full charge counts from 0.70 s (301 damage instead of 315).

**Regressions:**

| Trial | Result |
| --- | --- |
| `engagement_trial.py` and `--heldout` | pass (every scenario and held-out encounter is before 20 s; the 200 s drone scenario is unchanged) |
| `lead_trial.py --baseline 3b290b0` | pass |
| `entrypoint_trial.py --baseline 4588e6b` | 4 of 7 scenarios fail, all from the intended change: the trial's frames start at t = 100 s, so practice mode is on. Partial charge 0.4 s at 30 m: released at 0.70 s, which this mode counts as full, and the trial counts as early. Full charge behind a wall: the same triggers (laser held), but the torso faces the hidden mech at pitch 0. Full charge with the torso 40 degrees off: the gun waits for the torso (the parent fires at once); every release lands, the first 0.2 s in vs 1.9 s. Full charge at 300 m: the mech aims at us but is beyond 190 m, so it is not engaged and not looked at; the triggers match. The other three pass (empty laser 90 degrees off: first beam on target 0.7 s vs 2.7 s), and the recording control matches on 300/300 |
| `dodge_trial.py` | pass; 369 and 517 hits, unchanged (movement is untouched) |
| `farm_trial.py` | pass (its cases run before 20 s or after 180 s, where farming is the parent's) |
| `engagement_probe.py` and `verify.py` | pass. The probe's crafted frames are at t = 50 s, so they are practice mode; they now start with the torso facing the attacker, because the gun fires only once the torso is on target |

**Judgement calls and what is not here:**
- A laser charge in progress stays held while any mech is listed and there is no target, so a lost line of fire does not spend it into a wall; it still fires on its own after 2 s at full charge.
- Mortar hits are not faced: their bearing points at the blast, not the shooter.
- farm-power's farming shots keep their rules (no added HP condition); the gun fires at them as before and lightning only inside its range and cone.
- No vertical lead on airborne targets; the gun keeps lead-shots' horizontal intercept, aimed at the body centre.
- A mortar already carried at 20 s fires with the gun at a mech target until it is swapped out.
- Fight movement, retreat and cover, where the bot stands, a scan when idle, mid-fight cube grabs and farming after 180 s are separate pieces; nothing here moves the mech.

## squad-move (on `8064167`, farm-power, official 3.25)

**Why:** in practice the 15 house mechs hunt us together, and the score is only the mechs we kill before we die. The bot already chooses well whom to shoot (v6, lead-shots); this changes where it stands while it shoots. The aim is to meet hunters one at a time at the range our weapons like, with a line of fire when a shot is ready and out of sight while it is not, out of view of the other hunters, and to step back to cover only when the fight is clearly lost.

**The change** (`squad.py`, new). Practice mode: from 20 s of match time while every death so far is one of our kills, counted as alive at the first observation minus alive now minus our kill events; five decisions in a row with a death we did not cause switch it off for the rest of the match. Outside practice mode, during an urgent zone return, and whenever the bullet dodge or the shell dodge steers, the bot behaves exactly as farm-power. Target choice and firing are unchanged (`targeting.py`); `bot.py` only asks the engagement for its decision before movement instead of after it.

- **Fight movement:** while the engagement has a mech target, score staying put and 16 points 6 m away whose straight line is walkable on the ground grid: -1.1 x |distance to the target - preferred range|, -0.4 x step, +45 x w for a clear line of fire from the point (Cover.clear, sampled every 2 m), -30 for each of the 3 nearest other hunters listed in the last 2.5 s (within 170 m of the point) whose eye sees the point's body, - the zone penalty, +1.5 x metres gained toward a cube within 40 m, -2.5 per metre of wall clearance under 4 m (2 m cover raster), +9 x the strafe component when w > 0, and -8 for staying (+14 back when w < 0 and the target cannot be shot from here). Walk at full speed toward the best point. Line tests are skipped once a point cannot beat the best so far, so the choice is exact and usually costs a few rays.
  - Preferred range: 28 m with lightning and energy > 12, 120 m with a laser, else 85 m; without lightning, at least 64 m from a lightning holder and 80 m from a mortar holder; 20 m (with the same floors) when the target is under 38% HP, we are over 42% and at most 2 mechs are listed within 150 m.
  - w = +1 with a laser or lightning, or a loaded gun (reload at most 0.25 s) within range - 10 m; otherwise -1.
  - Strafe: perpendicular to the target's bearing; when its timer runs out the side flips with probability 0.6 and a new 0.3-1.0 s timer starts (seeded from `hello.seed`, so the bot stays deterministic). A dropped point within 26 degrees of the strafe direction flips the side and holds it 0.5 s.
  - Cube grab: a remembered cube within 40 m (22.8 m at or below half HP) and 4 m of our height is walked to instead.
- **Short retreats (LoseRule):** near = mechs listed within 160 m; losing = (near >= 2 and HP < 55%) or (near >= 3 and HP < 80%) or (HP < 35% and the target's HP fraction more than 0.10 above ours), cancelled when the target is under 25%, we are over 20% and near <= 2. The retreat lasts 1.5 s after the last losing decision, except when finishing (target under 120 m with HP < 200 or under half ours) or late (next radius <= 70 or alive <= 3).
  - Cover: breadth-first search outward on the 2 m cover raster (passable where the 4 m ground grid is free) for a cell hidden from the 4 nearest hunters within 230 m (both the eye-to-head and eye-to-mid-body lines blocked), scored 2 x steps + zone penalty - 0.25 x min(distance to the nearest hunter, 80); at most 350 tested cells per search and 60 (or 4,000 ray samples) per decision, so a search spans a few decisions; a found cell is kept 0.4 s. Boost while energy > 10.
  - Without cover: the fight move with w = +1 ("cornered"); with no target, walk to the zone goal ("flee").
- **Laser sidestep:** each listed mech charging a laser aimed within 0.15 rad of us adds a 1.5 m step along the strafe side; the move becomes 0.4 x plan + 0.9 x the unit sidestep (normalised), boosting when energy > 25.

| Check | Result |
| --- | --- |
| `py tools/squad_move_trial.py` (against 8064167) | 24/24 scripted checks: range held at 85 m from 160 m and 50 m gun-only starts, 119 m and 120 m from 60 m and 170 m laser starts (farm-power stays put); moves to a point with a line of fire to a foe behind cover; moves to a point the second hunter cannot see; strafes (mean along-bearing 0.15, 17 flips in 10 s, a repeat run identical); collects a cube 25 m away mid-fight; at 43% HP a cube 30 m away only pulls until it is within 22.8 m; finish mode closes from 60 m to 19 m; the LoseRule retreat runs from 30.0 to 32.3 s after the last losing decision at 30.9 s; finishing, next radius 60 and alive 3 each cancel it; a cell hidden from both mechs (80 and 120 m) found 21 m away, hidden after 1.3 s (farm-power stays exposed); laser sidestep only for a charge aimed within 0.15 rad; identical to farm-power before 20 s, after an outside death at 16 s and on an urgent zone return, with the same hunters fought from 30 s (control); our own kill keeps practice mode on |
| closed-loop fights (simplified world, hunters with perfect lead) | 3 starts x (1 gun hunter from 200 m, 2 gun hunters, 1 lightning hunter), 60 s each: damage taken 9,788 to 9,676, kills 5 to 6, mean first kill 35.3 to 32.4 s, deaths 5 to 4. Two perfect gun hunters still kill either build in 8-39 s |
| recording | 0 of 300 answers differ (practice mode is switched off by the death at 18 s) |
| timing | candidate round trip p50 0.5 ms, p99 2.7 ms, max 4.8 ms over 6,401 trial decisions; worst case (6 hunters within 170 m, retreat with the cover search and the cornered fight move) act() p99 3.4 ms, max 3.7 ms, of which squad.py p99 2.9 ms |
| fuzz | 1,500 random observations (random positions, mechs, weapons, zone, kills): 0 exceptions, none swallowed by squad.py's guard |
| regressions | `verify.py`, engagement probe, engagement trial and `--heldout`, `lead_trial --baseline 3b290b0`, dodge trial (369 and 517 hits, unchanged) and `farm_trial` pass. `shell_dodge_trial --baseline 8064167` reports no shell gain because farm-power already dodges shells; every shell episode and control is identical |

## squad-econ (on `8064167`, farm-power, official 3.25)

**Why:** in practice the 15 house bots hunt us as one squad and only our kills before we die count. farm-power gathered power in the first 180 s and gained +0.15. squad-econ keeps gathering all match, and between fights it waits still on an inner circle of the zone (silent, regenerating HP) with its torso scanning all round, so hunters arrive where we see them first.

**When it applies (practice mode):** after 20 s of match time while every death so far was our own kill (the first `alive` minus the current `alive` minus our `kill` events). Five decisions in a row with a death we did not cause switch it off for the rest of the match. Outside practice mode every decision is farm-power's, including its first-180 s farming. Practice seeds are fixed, so a match where the mode switches off before 20 s plays exactly as it did for farm-power.

**The change** (`squad.py`, wired into `bot.py`; `Engagement.decide` gets a `farm` switch that turns its own drone hunt and crate shot off in practice mode; `Dockerfile` and `.dockerignore` include `squad.py`):
- **Economy all match.** The loot target maximises value / (distance + 18), x1.35 for the current target. Every candidate is within 260 m, inside the current circle with 6 m to spare, reachable before its zone deadline (now + 1.4 x distance / walk speed + 5 s), at most 3.2 m above the terrain (no roofs or decks) and within 12 m of a walkable grid cell.
  - Cubes within 105 m: value 75, or 25 from 10 cubes. No HP or danger condition.
  - Crates within 150 m (0.6 x the cube value, so 45) and drones seen in the last 12 s within 150 m (85, under 10 cubes): only above 50 % HP and with no danger (an engaged mech seen in the last 2.5 s, or any hit in the last 4 s).
  - Items are remembered by id and forgotten when they should be in view but are not (within 40 m, or within 80 m inside the vision wedge, on a clear line, unseen for 0.35 s).
  - After following one item for 30 s it is banned for 60 s.
- **Approach.** A drone with a clear line within 75 m: hold 52-64 m from it and shoot it with the gun. A crate within 50 m with a clear shot: stand (step back inside 12 m) and shoot it with the gun. Otherwise walk to the item: straight inside 12 m, else on its own grid planner. The laser never fires at loot, and loot is only shot when the engagement has nothing to face.
- **Who stops loot.** A listed mech that is hunting us (within 60 m; hit us in the last 6 s; closing faster than 3 m/s within 180 m; under 40 % HP within 160 m; aiming at us within 0.22 rad and 190 m; every listed mech once the next radius is 70 m or less or 3 mechs are left), a mech hit in the last 4 s, or a mech the engagement is shooting hands control back to the normal engagement at once. Zone must and zone should also come first. The pickup detour is kept as it was.
- **Zone goal and camping.** The goal is the next centre when the next radius is 30 m or less; otherwise the nearest point on a circle of next radius - clamp(0.3 x next radius, 3, 30) - 5, moved onto the walkable grid, or our own position once inside that circle. Deadlines sample the shrink 25 times (8 m pad for us, 6 m for loot). Zone must (outside the zone, or the walk to the goal x1.45 + 4 s ends within 3 s of our deadline) outranks everything but the stuck recovery and boosts when it is tight; zone should (within 14 s) comes after the inherited supply-drop and relocate-after-damage objectives. With nothing to loot the bot walks to the goal and stands still within 3 m.
- **Idle aim** (nothing to face or shoot): the bearing of a hit in the last 2.5 s; moving: heading + 1.15 sin(1.3 t); standing: torso yaw + 0.35 rad per decision, a full turn in 1.8 s. Pitch 0.
- **Stuck rule.** A commanded move, under 1.2 m/s on the ground for 0.7 s: a random direction (RNG seeded from `hello.seed`, so matches stay deterministic) for 0.5 s with a jump, and the cached routes are dropped. It replaces the inherited side-step recovery in practice mode.
- The bullet dodge and the shell dodge keep the final word on the move.

| Check | Result |
| --- | --- |
| `py tools/squad_econ_trial.py` (against 8064167; both as real bot processes in a closed loop with vision, our gun, crates, drones that fire back, cubes and the zone) | 24/24. After 180 s: the crate at 100 m is destroyed at 6.3 s (7 shots) and the drone at 120 m killed at 6.2 s (10 shots), then their cubes are collected; the cube at 90 m is collected at 7.4 s; farm-power does none of it. No crate or drone shots at 45 % HP (a cube is still collected), none with an engaged mech listed, first loot 4.1 s after an unseen mech hit. Hysteresis keeps a cube 37.5 m away when one appears 29.7 m away (utility 1.57 against 1.35 x 1.35) and switches for one 12.8 m away. Give-up after 30.0 s, chosen again 60.1 s later. Camps 66.7 m from the centre of a 100 m next circle (inner circle 65 m) and stands still, where farm-power walks to the centre. Zone must: 13 decisions toward the goal (8 boosted) before loot, which resumes only 8 m inside the next circle. Idle spin (+0.35 rad on every standing decision, a full turn in 1.8 s), sweep (60/60 walking decisions) and the turn to a hit from the last 2.5 s. Stuck recovery on decision 8, five decisions each, one jump each, two runs identical. Identical to farm-power on every decision before 20 s (195), after a death we did not cause at 10 s (600) and on the standard recording (300); our own kill keeps the mode on; a death we did not cause at 30 s ends it at 30.4 s |
| timing | process round trip over 5,460 trial decisions: p99 0.72 ms, max 1.2 ms; in-process `act()` on 1,500 busy practice decisions (up to 12 drones, 6 mechs, 20 crates, 25 cubes, 4 pickups, 6 projectiles): p99 2.7 ms, max 3.3 ms; `verify.py` p99 1.0 ms |
| fuzz | 6 x 700 random decisions, with deaths with and without our kill events: no exceptions, no non-finite move or aim |
| `verify.py`, `tools/engagement_probe.py` | pass (ready name `zone-runner-squad-econ`) |
| regressions | engagement trial `--heldout`, objective checks (12), target trial (11) and the dodge trial (369 and 517 hits, unchanged: its routes end before 20 s) pass. Failures the change causes, left as they are: the engagement trial's "distant passive NPC after 180 s" (at 200 s practice mode walks toward that drone as loot); `farm_trial`'s two "after 180 s" controls (practice mode farms there); the pickup trial's "reached the zone goal" counts (pickups are still acquired as before, but after 20 s the bot camps on the inner circle instead of walking to the centre); the route trial (30/150 reach the centre; the rest camp after 20 s) |

## squad-fire-move (on `90d298b`, squad-fire, official 3.65; with squad-move `35a0bdd`, official 3.52)

**Why:** squad-fire (whom to shoot and how) and squad-move (where to stand in a fight) were the two practice parts that beat farm-power on their own, and they act on different parts of the action: the triggers and the aim, and the legs. Put together as one practice design, the move part fights exactly the mech the fire part shoots, so both gains should hold.

**Practice mode** (`practice.py`, one detector read by both parts): after 20 s of match time while every death so far is one of our kills (the first `alive` minus `alive` now minus our distinct `kill` targets); five decisions in a row with a death we did not cause end it for the rest of the match. Outside it every decision is farm-power's.

**The design** (`squad_fire.py` and `squad_move.py`, the two parts; `bot.py` runs them):
- Fire part: as squad-fire. It now decides first on each practice decision (it only reads the observation), before the dodges, so the move part knows the target; aim, triggers, reload, weapon take and swap and upgrades are applied at the end of the decision as before. Its decision also names the nearest engaged mech.
- Move part: as squad-move, against the fire part's target, or, while no target has a line of fire, the nearest engaged mech (the one the fire part faces), so the fight move still walks to a line of fire. A mech the fire part ignores (not engaged) is not fought; the parent's movement applies.
- Movement priority: the bullet dodge and the shell dodge keep the last word; during the urgent zone return the parent moves us (the move part, laser sidestep included, stands aside); then the LoseRule retreat (unless finishing or late); then the fight move with the mid-fight cube grab; the laser sidestep is blended into whichever move was chosen; otherwise the parent's movement (zone, the laser-first pickup detour, the cube farm and its stuck recovery). As in squad-move, the parent's stuck recovery steers only the parent's movement: its detector measures displacement alone, so it would also fire while we hold still in cover, wait hidden for a reload, or strafe back and forth.
- The v6 engagement is asked before the dodges in every mode. It only reads the observation, and the cube farm still sees the previous decision's attackers, so farm-power's decisions are unchanged.
- `Cover.clear` now runs `solid()` inside its loop: the same arithmetic on every sample (identical answers on 300,000 random lines, both step sizes), in about half the time, which keeps the decision time low with many hunters listed.

| Check | Result |
| --- | --- |
| `py tools/squad_fire_trial.py` (against 8064167) | pass: 18/18 engagement cases, target choice and stickiness, laser (0.30 s lethal release on a 150 HP target, full charge held from 0.020 rad off), 7/7 loot, 60/60 upgrades, mode switch identical before 20 s (965/965, 200/200), after an outside death (450/450; 95/95 after one at 35 s), recording 300/300. Closed-loop hunter (we stand still): gun only 4 to 6 kills, gun + laser 6 to 6, the same as squad-fire. Timing p99 3.3 ms over 6,350 answers, 3.9 ms with 15 engaged mechs; fuzz 4,800 decisions clean |
| `py tools/squad_move_trial.py` (against 8064167) | 24/24: range held at 85/85/119/120 m, a spot with a line of fire, hidden from a second hunter, strafe (17 flips in 10 s, repeat identical), cube grab, 22.8 m hurt grab, finish mode to 19 m, the 1.5 s LoseRule pulse (30.0-32.3 s), finishing and late cancel it, cover found 21 m away in 1.3 s, laser sidestep only for an aimed charge, identical before 20 s and after an outside death, our own kill keeps the mode on. 9 closed-loop fights: damage 9,788 to 10,125, kills 5 to 6, mean first kill 35.3 to 32.7 s, deaths 5 to 3; recording 0/300 differ; round trip p99 2.4 ms |
| changed expectation | the move trial's urgent-zone-return control compared whole answers; in practice mode the aim and triggers are the fire part's even then, so it now compares move, boost and jump, which stay identical (80/80). The two trials only follow the module renames otherwise (`squad_fire.UPGRADES`, `bot.squad_move.errors`) |
| `py tools/practice_trial.py` (new; against 8064167) | identical to farm-power on the engagement scenarios before 20 s (965/965), a rich scenario 0-19.9 s (200/200), the same with a death we did not cause at 10 s run to 60 s (600/600) and the recording (300/300); the same scenario from 20.05 s differs on 200/200. Busy closed loop near buildings (hunters aiming at us, HP 45% so the cover search runs, crates, cubes, drones and pickups in view, bullets, a charging laser, then 15 engaged mechs): act() p99 4.9 ms, max 5.6 ms; through stdin/stdout p99 3.9 ms, max 5.1 ms. Fuzz: 6,000 random decisions (3,019 in practice mode), 0 exceptions, 0 malformed or non-finite actions, 0 errors swallowed |
| regressions | `engagement_trial.py` and `--heldout` (R0-R9), `lead_trial.py --baseline 3b290b0` (hits 56 to 109 of 130), `dodge_trial.py` (369 and 517 hits, unchanged), `farm_trial.py`, `verify.py` (p99 1.8 ms) and `engagement_probe.py` (ready name `zone-runner-squad-fire-move`) pass; none fails |

## squad-all (on `8805ed6`, squad-fire-move; with squad-econ `f8dc9bf`, official 3.29)

**Why:** the practice design so far fights well (squad-fire 3.65, squad-move 3.52) but between fights it walks to the zone centre and looks where it walks. The economy part keeps gathering power all match, camps still on an inner circle of the zone, scans all round, and frees the mech when it is stuck. Alone it scored 3.29 (within the noise of farm-power's 3.25), so here it only moves us when there is nobody to fight, and never takes the aim or the triggers from the fire part.

**Practice mode** (`practice.py`, one detector read by all three parts): after 20 s of match time while every death so far is one of our kills; five decisions in a row with a death we did not cause end it for the rest of the match. Outside it every decision is farm-power's.

**The design: one practice mode, three parts.**
- `squad_fire.py`, the fire part: whom to face and shoot, every trigger, the early reload, the weapon wishes (laser first, swapped in, never a mortar) and the upgrade order. It decides first on every practice decision.
- `squad_move.py`, the move part: the fight move with the mid-fight cube grab against the fire part's target (or the nearest engaged mech while no target has a line of fire), the LoseRule retreat to cover, the laser sidestep.
- `squad_econ.py`, the economy part: the zone goal and its must/should deadlines, loot (cubes, crates, drones) by value per metre, the loot shot, camping, the idle aim, the stuck rule. It runs the movement plan and calls the move part at its place in it.

**Movement in practice mode, highest first:**
1. the stuck recovery (economy part: a commanded move but under 1.2 m/s on the ground for 0.7 s; a random 0.5 s run with a jump, and every planner's cached route, the move part's included, is dropped);
2. the bullet dodge and the shell dodge keep the final word on the move, exactly as before (they run after the plan, with the parent's urgency rule plus zone must's hurry);
3. zone must;
4. the LoseRule retreat, unless finishing or late;
5. the fight move with the mid-fight cube grab, while there is a mech to fight. The move part (4 and 5, and the laser sidestep) stands aside during the parent's urgent zone return, as it does in squad-move and squad-fire-move;
6. the inherited supply-drop and relocate-after-damage objectives (between the fight and zone should, which keeps both parts' own order: the fight outranked them in the move part, and they outranked zone should in the economy part);
7. zone should;
8. the weapon pickup detour the fire part chose (a laser, or lightning to replace an empty slot or a mortar), then loot (only with no mech hunting us, no mech hit in 4 s and no mech target);
9. camp still at the zone goal, or walk to it.
The laser sidestep is blended into any move from 4 down.

**Aim and triggers:** the fire part's. The economy part's crate and drone shots apply only when the fire part has nothing to shoot (no mech target and no drone to shoot back at): its aim and the gun's trigger once the torso is within 0.2 rad, while the laser keeps the fire part's rule (a charge in progress stays held while a mech is listed, none is started), and no early reload is ordered between loot shots. The idle aim (spin while standing, sweep while walking, the bearing of a hit in the last 2.5 s) applies only when there is no target and no engaged enemy to face; with only unengaged mechs listed the bot looks where it would with nobody listed (the idle aim, or the pickup during its detour). In practice mode the engagement's own farming shots (farm-power's first-180 s drone hunt and crate shot) and farm.py's cube walk are off, since loot belongs to the economy part; the engagement is still asked every decision for its memory and its line-of-fire cache.

**Weapon pickups:** the fire part's laser-first seek (the detour) and take-and-swap rule own them; the economy part handles cubes, crates and drones. When both want to move us, the detour wins.

| Check | Result |
| --- | --- |
| `py tools/squad_fire_trial.py` (against 8064167) | pass: the engagement rules (engaged mechs faced and shot; ignored ones never shot and never held in the aim, see the changed expectations), target choice and stickiness, the laser (0.30 s lethal release on a 150 HP target, full charge held from 0.020 rad off), 7/7 loot, 60/60 upgrades, mode switch identical before 20 s (965/965, 200/200), after an outside death (450/450; 95/95 after one at 35 s) and on the recording (300/300). Closed-loop hunter (we stand still): gun only 4 to 5 kills (squad-fire alone: 6), gun + laser 6 to 6; the first trigger comes 0.3-0.5 s later because the idle scan has turned the torso away before the hunter engages. Timing p99 3.4 ms (max 4.4 ms) over 6,326 answers, 4.3 ms with 15 engaged mechs; fuzz 4,800 decisions clean |
| `py tools/squad_move_trial.py` (against 8064167) | 24/24, the same checks as in squad-fire-move (range 85/85/119/120 m, a spot with a line of fire, hidden from a second hunter, strafe, cube grab, the hurt grab limit, finish mode to 19 m, the 1.5 s LoseRule pulse, finishing and late cancel it, cover 21 m away in 1.3 s, laser sidestep only for an aimed charge, identical before 20 s and after an outside death, our own kill keeps the mode on). 9 closed-loop fights: damage 9,788 to 10,305, kills 5 to 5, mean first kill 35.3 to 34.9 s, deaths 5 to 4 (squad-fire-move: 6 kills, 3 deaths; between hunters the economy part now walks to cubes and camps); recording 0/300 differ; round trip p99 2.7 ms, max 4.4 ms |
| `py tools/squad_econ_trial.py` (against 8064167) | 24/24, unchanged: after 180 s the crate at 100 m, the drone at 120 m and the cube at 90 m are farmed; no crate or drone at 45% HP, with an engaged mech listed (the fight move runs instead) or within 4 s of a mech hit; hysteresis, the 30 s give-up and 60 s ban, camping on the inner circle, zone must over loot, the idle spin, sweep and turn to a recent hit, the stuck rule (from decision 8, five decisions, one jump, deterministic); identical to farm-power before 20 s (195), after an outside death (600) and on the recording (300). Round trip p99 2.1 ms; in-process p99 3.9 ms on 1,500 busy decisions; fuzz 4,200 decisions clean |
| changed expectations | two, both from the parts now meeting. (1) squad_fire_trial's engagement cases: an ignored mech was never to come within 10 degrees of the aim; with nothing to face, the economy part's idle scan now turns the torso all round, so it passes over the mech on one decision (1/15). The check is now: never shot, and never within 10 degrees on two decisions in a row. (2) squad_move_trial's urgent-zone-return control (movement only since squad-fire-move): the zone plan now walks us back (zone must on 80/80), so the check is that the move part stands aside (no fight, grab, retreat or sidestep decision). squad_econ_trial needed no change |
| `py tools/practice_trial.py` (against 8064167) | identical to farm-power on the engagement scenarios before 20 s (965/965), the rich scenario 0-19.9 s (200/200), the same with a death we did not cause at 10 s run to 60 s (600/600) and the recording (300/300); from 20.05 s it differs on 200/200. Busy closed loop near buildings (hunters aiming at us, HP 45% so the cover search runs, 10 crates, 15 cubes, 6 drones and 3 pickups in view, bullets, a charging laser, then 15 engaged mechs; moves: cover, cornered, fight with the sidestep, loot, unstuck): act() p99 5.0 ms, max 5.3 ms; through stdin/stdout p99 3.7 ms, max 4.7 ms. Fuzz: 6,000 random decisions (3,019 in practice mode), 0 exceptions, 0 malformed or non-finite actions. Movement priority, 12/12 scripted checks: stuck over fight, zone must over retreat, retreat over fight, fight over the laser detour and loot, zone should over loot, the laser detour over loot, loot, camp, no fight and no stare at an unengaged mech, the loot shot only without a mech target, and the bullet dodge still having the last word |
| regressions | `engagement_trial.py --heldout` (R0-R9), `lead_trial.py --baseline 3b290b0` (hits 56 to 109 of 130), `dodge_trial.py` (369 and 517 hits, unchanged), `verify.py` and `engagement_probe.py` (ready name `zone-runner-squad-all`) pass. Failures from the intended change, the same ones squad-econ reported: `engagement_trial.py`'s "distant passive NPC after 180 s" (at 200 s practice mode walks toward the drone as loot with the idle scan, so the aim is no longer v5's on 20/20; it never fires) and `farm_trial.py`'s "passive drone 60 m, after 180 s" and "cube at 50 m, after 180 s" (practice mode keeps farming after 180 s: the drone dies in 2.0 s, the cube is collected in 4.0 s). Everything else in both passes |

## squad-all-sticky (on `9399d0d`, squad-all)

squad-all with squad-sticky's detector change (`65a5a5c`): practice mode switches off only after three mechs have died to something other than us, so a house bot lost to a drone or the zone no longer drops the practice design for the rest of the match. `py tools/practice_trial.py`: identical to farm-power before 20 s and after three outside deaths; practice mode after two outside deaths and on the recording after 20 s; 6,000 random decisions with no errors; in-process p99 4.6 ms, max 5.6 ms.

## squad-all-fixed (on `076bec9`, squad-all-sticky)

**Why:** a review of the practice design found seven places where it worked against its own rules. Each fix below is ours and stays inside practice mode; before 20 s, and after three deaths we did not cause, every decision is still farm-power's. The zone urgency and the dodge gating are unchanged, so the bullet dodge, the shell dodge and the urgent zone return behave exactly as before.

**The fixes, by expected impact:**
1. **Fight only the target.** The move part fought the fire part's target or, with no target, the nearest engaged mech at any distance, so the bot left its camp to walk toward mechs it could not see or that stood far away. Now it fights only the target (engaged, with a line of fire, within 240 m). An engaged mech without one is faced by the idle aim and never walked to; the LoseRule's target terms and the finishing check also read the target only.
2. **A laser pursuit that survives a fight nearby.** Any HP loss started the relocate timer, which cancelled the pursuit and set the laser aside for 5 s; a mech within 60 m cancelled it too; only listed pickups could be chosen; a pickup unseen for 5 s was dropped; and the pursuit ranked below zone should, supply drops and the relocate hop. In practice mode the damage and nearby-mech cancels are gone, pickups are remembered where they were last seen and forgotten only when one should be in view and is not (within 40 m all round, or within 80 m inside the vision wedge with a clear line from our eyes, as the economy part forgets items), and a laser pursuit ranks just below the fight move, above zone should. Zone must and the pursuit's own zone-timing rule still bring us back in time; a detour to lightning keeps its place below zone should.
3. **Cube grabs we can finish.** The mid-fight grab walked to any remembered cube within 40 m, even one on a roof that no walkable cell reaches, and could hold the move on it for the rest of the fight. A cube now qualifies when it passes the loot rules' ground checks (at most 3.2 m above the terrain, a walkable cell within 12 m) or a walkable cell lies within 3.5 m of it. Grabbing a cube for 3 s without getting 1 m closer bans it for 30 s. Only qualifying cubes pull the fight move's points as well.
4. **No supply drops or relocate hop in practice mode.** The design keeps its own movement rules; the inherited drop pursuit and the 12 m hop after damage are skipped while practice mode is on.
5. **Cubes still count under threat.** With an engaged mech listed, a mech hit in the last 4 s or a target, the economy part chose nothing. It now chooses among cubes only (crates and drones still wait for calm). The fight move keeps priority whenever there is a target, so this acts while there is a threat but nothing to shoot.
6. **A held mortar never fires in practice mode.** The mortar slot followed the gun trigger along the gun's flat aim, so close in its splash hit us too. Its trigger is now always off in practice mode (farm-power can pick one up before 20 s; practice mode never takes one).
7. **The torso reaches a lethal laser shot sooner.** The torso moved from the gun's lead point to the direct aim only past 0.45 of a full charge, so against a moving target the lethal release waited for the turn. It now moves as soon as the charge on the next decision would already be lethal by the release rule; the release rule itself is unchanged.

**Review experiments, before (`076bec9`) and after:**

| Fix | Experiment | Before | After |
| --- | --- | --- | --- |
| 1 | engaged mech behind cover, 80 m | fight move toward it (`[-1, 0]`, no line of fire from the chosen point) | camp, move `[0, 0]`, torso faces it |
| 1 | a mech hits us from 262 m | fight move toward it (heading 112 deg, bearing 105 deg) | camp, move `[0, 0]`, torso faces it |
| 2, 4 | laser 110 m away, a drone hit at 1 s | pickup x10, relocate x25, camp x5 (laser set aside as `under_fire`); 110 m left after 4 s | pickup x40; 63 m left |
| 1, 2 | laser 110 m away, a passive mech 68 m from it with no line of fire | pickup x1, then fight x39; 97 m left | pickup x40; 63 m left |
| 3 | cube on a low roof 24 m away (2.7 m up, no walkable cell within 3.5 m) during a fight | grab x58, fight x42 | fight x100, no grab |
| 6 | gun + mortar, engaged mech at 8 m | fire `[True, True]` | fire `[True, False]` |
| 7 | 150 HP target strafing at 8 m/s, 120 m, torso slewing (closed loop) | releases at 0.5, 0.5, 0.5 s of charge | 0.5 (the first, limited by the torso's initial turn), then 0.3, 0.3 s |
| timing | busy closed loop (E2) | p99 3.3 / 1.1 / 0.5 / 2.2 ms per phase | p99 3.5 / 1.0 / 0.4 / 2.4 ms |

| Check | Result |
| --- | --- |
| new checks (each fails on `076bec9`) | practice_trial: engaged mech behind cover faced not walked to (before: fight x10); attacker at 262 m faced (fight x10); the laser detour outranks zone should (zone should x10); the laser detour holds through a drone hit (relocate x25); a laser listed only on its first 3 decisions is followed 60/60 (dropped after 5 s); no supply-drop move (drop x10); no relocate hop (relocate x8); a cube collected under threat (before: grab x10, inside the fight move against the hidden mech); a crate under the same threat left alone (fight x10). squad_fire_trial: lethal release on a strafing 150 HP target at 0.30 s (before 0.50 s); a held mortar never fired at 8 and 100 m (before 10/10). squad_move_trial: no grab of the roof cube (before grab x50); a grab that gets no closer gives the cube up after 26 grab decisions (before: 64 grabs, never given up). squad_econ_trial: under a mech hit, the first loot decision is a cube at 190.0 s (before 194.1 s, after the threat) and the crate waits until 197.8 s |
| changed expectations (intended) | squad_move_trial: "prefers a spot with a line of fire" becomes "no fight move toward a foe with no line of fire" (fix 1: a foe behind cover is not fought, so no step toward a line); the LoseRule pulse check now asks that the decision after the pulse is not a retreat instead of a fight (fix 1: we stand hidden in the cover the pulse found, so the foe is no target and the bot camps). practice_trial's priority list in its docstring now reads fight > the laser detour > zone should |
| `py tools/squad_fire_trial.py` | pass except the three mode-switch checks that fail identically on `076bec9` (they expect one outside death to end practice mode, which squad-all-sticky changed on purpose). Closed-loop gun + laser: kills 6 to 6, the same; timing p99 3.2 ms over 6,368 answers, 4.3 ms with 15 engaged mechs; fuzz 4,800 decisions clean |
| `py tools/squad_move_trial.py` | 25/26 scripted checks; the one failure ("identical to the baseline outside death at 16 s") and the recording comparison fail identically on `076bec9` for the same detector reason. 9 closed-loop fights: kills 5 to 5, deaths 5 to 4, damage taken 9,788 to 9,653 (`076bec9`: 10,305); no relocate decisions any more |
| `py tools/squad_econ_trial.py` | 22/25: the three mode checks fail identically on `076bec9` (the detector); everything else passes, the new cube-under-threat case included |
| `py tools/practice_trial.py` | pass: identical to farm-power before 20 s (965/965 and 200/200), with three outside deaths (600/600) and on the recording up to 20 s; practice mode with two outside deaths; 21/21 priority checks. Busy closed loop: act() p99 5.2 ms, round trip p99 3.5 ms; fuzz 6,000 decisions clean |
| regressions | `verify.py` pass (p99 2.2 ms, ready name `zone-runner-squad-all-fixed`), `engagement_probe.py` pass, `dodge_trial.py` 369 and 517 hits (unchanged), `lead_trial.py --baseline 3b290b0` hits 56 to 109 of 130 (its recording check fails exactly as on `076bec9`: the recording's outside death at 18 s no longer ends practice mode) |

## squad-all-zone (on `fea757a`, squad-all-fixed)

**Why:** in practice mode the bot treated the whole shrink window as an urgent return. Once it stood outside the next circle and `t + walk time + 4 s` passed the shrink start, or the next radius fell below 8 m (the whole last phase), the fight move, the LoseRule retreat, the laser sidestep, the bullet dodge and the shell dodge all switched off. So it crossed open ground on zone moves without dodging or fighting back, even with plenty of time before the circle reached it.

**The change (practice mode only).** The zone takes the movement on a deadline instead, read from squad_econ.py's ZonePlan, which already computed it:
- **Zone must** (outside the zone, or the walk to the zone goal, x1.45 + 4 s, ends within 3 s of the deadline at our spot from the interpolated circle) is the urgent flag for movement priority: no fight move, retreat or laser sidestep. On that walk the shell dodge still steps out of a blast, and the bullet dodge is blended into the walk: final move = normalise(0.4 x walk + 0.9 x step). Each side's blended move is judged by how far it carries us across the bullet's path by the time it arrives; of the sides that clear the bullet, the one that keeps more of the walk goes first.
- **Hurry** (outside the current circle, or the walk ends at or after that deadline, which also covers the last 3 s before it): straight to the goal with boost and no dodge at all, exactly as before.
- **Otherwise**, even outside the next circle during a shrink or in the last phase, the fight move, the retreat, both dodges and the sidestep work as in the rest of practice play.

Outside practice mode, and before 20 s, nothing changes: every decision is farm-power's. objectives.py still reports "return" in the last phase and when the next circle is close in time, but in practice mode that now only keeps the weapon pickup detour off, as before.

**Scripted decisions** (`py tools/zone_urgency_trial.py`, both builds as `python -u bot.py`, practice mode at t = 30 s on the open lawn):

| Case | Parent `fea757a` | squad-all-zone |
| --- | --- | --- |
| outside the next circle, deadline 87.5 s away (must, should and hurry all off), a bullet on course 45 deg off the walk | camp walk `[+1, 0]`, no dodge | steps across the bullet `[-0.71, +0.71]` with boost |
| the same, an engaged hunter 100 m away | camp walk, never fights | fight move on every decision |
| the same, hunter and bullet | camp walk `[+1, 0]` | fight move, then the dodge `[+0.71, -0.71]` |
| tight deadline (must, not hurry: deadline 45.0 s, walk 14.3 s), nothing in the air | zone must, walks home | identical answers |
| tight deadline, a mortar shell landing on the route in 1.2 s | walks into it (predicted blast 360 HP) | steps out `[+0.92, +0.38]` with boost (predicted 0) |
| tight deadline, a bullet on course from the side | `[+1, 0]`, no boost | `[+1, 0]` with boost: the forward side clears the bullet, so the walk goes on at boost speed |
| tight deadline, a bullet from 30 deg off ahead | `[+1, 0]` | `[+0.74, -0.68]` with boost (progress +0.74, 0.95 across the bullet) |
| outside the current circle, a bullet and a shell on us | home with boost, no dodge | identical answers |
| inside it, but the walk ends after the deadline (hurry), a bullet and a shell on us | home with boost, no dodge | identical answers |
| control: hunter and bullet at t = 5 s | farm-power | identical answers |

**Closed-loop zone run** (`tools/zone_urgency_trial.py`, part 2; the world of `tools/squad_move_trial.py` with a shrinking circle and 60 HP/s zone damage). We walk 150 m to the goal of a new circle (next radius 60 m, the goal 37 m from its centre) while a gun hunter (1400 HP, leading its shots, 0.6 deg spread) holds 100 m from us and shoots; our gun can kill it. Four starts, two seeds each, 60 s from t = 30 s:

| Deadline | Hits taken (parent, cand) | Hits before entering the circle | Circle entered at (mean s) | Goal reached at (mean s) | Decisions outside the circle | Kills | Deaths |
| --- | --- | --- | --- | --- | --- | --- | --- |
| comfortable: about 40 s at the start for a 23 s walk by the plan's estimate | 248, 206 (-17%) | 192, 206 | 11.0, 29.5 | 30.2 (4 runs), 31.2 | 0, 0 | 6, 8 | 4, 0 |
| tight: zone must from the start, not hurry | 248, 225 (-9%) | 192, 225 | 11.0, 21.3 | 34.6 (4 runs), 23.1 | 0, 0 | 6, 8 | 4, 0 |

The parent walks straight in (camp walk, no dodges) and is inside the circle at 11 s, but the hunter follows and the parent dies on 4 of 8 runs (all seed 2) at 12.9-13.1 s, at the moment its own kill would land. The candidate stands and fights with its dodges, kills the hunter on every run at 12.5-12.9 s, and walks in afterwards (zone should, loot of the two kill cubes, camp walk), still well before the circle reaches it. In the tight case zone must held on 47 decisions and the deadline rule brought the bot in before the circle with no decision outside it.

**Existing trials**, run on `fea757a` and on this tree and compared line by line (timings aside):

| Trial | Result |
| --- | --- |
| `py tools/practice_trial.py` | identical to the parent's output: farm-power before 20 s (965/965, 200/200), with three outside deaths (600/600) and on the recording up to 20 s; 21/21 priority checks; fuzz 6,000 decisions clean. Quiet machine: act() p99 4.60 ms (parent 4.65), round trip p99 5.12 ms (parent 3.74), max 7.05 ms |
| `py tools/dodge_trial.py` | identical: 9/9 scripted checks, hits 441 to 369 (tuning) and 596 to 517 (held-out). Its zone-edge and urgent-return cases run before 20 s, so they are unchanged, and every reactive route finishes before 20 s |
| `py tools/squad_econ_trial.py` | identical, the same three mode checks failing as on the parent (the detector keeps practice mode after one outside death by design) |
| `py tools/squad_fire_trial.py` | identical, the same three mode-switch checks failing as on the parent; fuzz 4,800 clean |
| `py tools/squad_move_trial.py` | identical, the same two failures as on the parent (outside death at 16 s, recording); "the move part stands aside on an urgent zone return" still passes: that case starts outside the current circle, which is hurry |
| standard recording | 0 of 300 answers differ from the parent (it ends at 36.8 s, before the first shrink) |
| `py verify.py` | pass, ready name `zone-runner-squad-all-zone`, p99 4.6 ms |
| `py tools/engagement_probe.py` | pass |

No existing expectation changed. `tools/squad_move_trial.py`'s world now also accepts the zone as a function of match time, can apply zone damage, and records hit times and whether each decision was inside the circle; its existing calls behave as before.
