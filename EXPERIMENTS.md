# Experiment log

Practice scoring is 48 matches against 15 house bots, mean of (16 - place); the track page lists the kit's starter bot at 1.15. Local tests catch mistakes; only official practice scores judge placement. A score is entered only after you report it from the Buildathon page.

## Scoreboard

Official practice scores as you report them. V7 to V12 each branch from the 2.08 baseline (`1a0ca39`) and change one behaviour.

| Version | Branch | Candidate SHA | Parent SHA | Official score | Delta vs parent |
| --- | --- | --- | --- | --- | --- |
| v4 | `main` | `124101fe2402a13451921e0d97582adc5b3aab17` | none | 1.56 | n/a |
| v5 | `v5-early-loot` | `dbc4cc2da927ddcc3a48e5191c3c070294e2ab72` | `124101f` | 1.75 | +0.19 |
| v6 | `v6-selective-engagement` | `1a0ca394d26fe5e97c60dbac2ded343a2694b114` | `dbc4cc2` | **2.08** (baseline) | +0.33 |
| v7 | `v7-laser-release` | this commit (tag `v7-candidate`) | `1a0ca39` | pending | pending |

## Log

| Version | Parent SHA | Candidate SHA | Hypothesis (the one change) | Activation (local) | Local result | Official score | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v4 | none | `124101f` (tag `v4-scored`) | health-aware objectives: supply drop when damaged, relocation after damage | not measured | replay 300/300; 12 objective checks | 1.56 | superseded by v5 |
| v5 | `124101f` | `dbc4cc2` (tag `v5-candidate`) | detouring for one reachable ground weapon while slot 1 is empty improves placement | 40 detours in 110 closed-loop runs; 0 on the recording (no pickup within 70 m) | acquired 40/40 where intended, none where it should not; no extra zone misses | 1.75 (+0.19) | kept; superseded by v6 |
| stable target (measurement) | `dbc4cc2` | `97d49a9` (PR #2) | the nearest-mech rule oscillates between opponents | 0: the recording never lists two mechs | 0 switches on the recording; 40 vs 2 switches in the two-mech scenario | not submitted (no bot change) | rule reused inside v6 |
| no drop pursuit (parked) | `dbc4cc2` | `0733dd7` (branch `exp/no-drop-pursuit`) | travelling to or waiting at supply drops costs placement | objective checks only | not container-checked | not submitted | parked |
| v6 | `dbc4cc2` (git parent `cdfa00f`, identical match files) | `1a0ca39` (tag `v6-candidate`) | facing the opponent that is actually fighting us and holding fire when shots cannot land improves placement | aim or fire differs on 556 of 965 scripted decisions; on the recording, fire differs on 62 and aim on 40 of 300 | 30/30 scenarios; held-out rules R0-R9 pass on 2 x 400 encounters; 10 of 11 mutants caught (the 11th is equivalent); movement, pickups, reloads identical to v5 on 1,265 decisions | **2.08 (+0.33)** | **keep: baseline for v7-v12** |
| v7 | `1a0ca39` | this commit (tag `v7-candidate`) | releasing a full laser charge the moment the beam is on the chosen opponent, instead of holding it until it fires on its own, improves placement | fires in 4 of 7 entrypoint scenarios; never on the standard recording (no laser held) | first beam on target 0.0-0.8 s vs 1.9-2.7 s; charging (half-speed) decisions roughly halved; controls identical; all regressions pass | pending | pending your score |

## v6: selective engagement

The change replaces the inherited nearest-mech rule (fire both triggers at whichever mech is closest) with `targeting.Engagement`, wired in at the end of `bot.py`'s `act()`. Movement, pickup routing and how the triggers are pressed are v5's.

- **Choice of opponent:** each listed mech scores its distance, 35 m closer if it hit us in the last 5 s, 15 m closer if its torso pointed at us in the last 1 s, 20 m farther if solid cover blocks our line. A shootable mech that is fighting us ranks ahead of everything else. A drone is a candidate only after it hits us, and then 60 m farther. `StableTarget` keeps the current choice through small changes and switches after a 1 s persistent lead, at once for a clear lead, and on the same decision the opponent stops being listed.
- **Shooting:** only at the chosen opponent, only with a clear line (`cover.py` on the 2 m `cover.i16` raster built from `arena/v2`) and within weapon range, and only when it is fighting us, is within 45 m, or unled bullets would land. A charging laser is kept held through a hold, so it is never released into a wall.
- **Unseen attacker:** when a recent attacker is not listed and the chosen opponent is neither fighting us nor within 45 m, the torso turns toward the damage bearing, without firing, except during a pickup detour. Zone damage has no attacker. Mortar damage keeps its attacker id but not its bearing, which is the blast point. A kill clears the victim's evidence.

Evidence (`py tools/engagement_trial.py`, `--heldout`, `py tools/engagement_probe.py`):

- The independent review raised 26 findings and confirmed 20. All were fixed or turned into checks; the 6 refuted ones are documented in the review run.
- Recording: no pickup is pursued and only one mech is ever listed. v6 holds fire on 54 decisions where the raster says a building blocks the line (no shot landed by either side in that window) and on 8 where a crossing mech at about 147 m would dodge unled bullets. The raster calls all 37 lines before a landed shot clear.
- Timing: 0 late answers, p99 1.1 ms on Windows; worst case with 15 opponents at 200 m is 2.5 ms. The CI conformance job runs the restricted linux/amd64 container, and the probe asserts that the container's bot aims at an attacker rather than a closer passive mech.

## v7: release a full, aligned laser charge

One change on the 2.08 baseline:

- **The rule:** on a decision where the laser's charge has reached the configured charge time (`self.weapons[i].stats.charge`, falling back to `config.weapons.laser.charge`), the change applies when all of these hold:
  - v6 has chosen an opponent;
  - that opponent is within laser range;
  - the line to it is clear;
  - our actual torso aim (`obs.self.aim`) points inside its body.

  The bot then sends `false` for the laser slot. The other slot's command is unchanged.
- **Where:** `Engagement.release_laser` in `targeting.py`, applied at the end of `bot.py`.

Evidence (`py tools/entrypoint_trial.py`: the baseline exported from `1a0ca39` and the candidate both run as `python -u bot.py` over stdin/stdout, from identical starting conditions):

| Scenario | First decision's fire (base / v7) | Beams on target (base / v7) | First beam on target (base / v7) | Charging decisions (base / v7) |
| --- | --- | --- | --- | --- |
| full charge, clear, 30 m | `[true, true]` / `[true, false]` | 1/1, 2/2 | 1.9 s / 0.0 s | 23 / 10 |
| partial charge (0.4 s), clear, 30 m | `[true, true]` / `[true, true]` | 1/1, 2/2 | 2.3 s / 0.4 s | 24 / 14 |
| full charge, torso 40 deg off | `[true, true]` / `[true, true]` | 1/1, 2/2 | 1.9 s / 0.2 s | 23 / 12 |
| empty laser, torso 90 deg off, 60 m | `[true, true]` / `[true, true]` | 1/1, 2/2 | 2.7 s / 0.8 s | 43 / 26 |
| full charge, blocked view (control) | identical on every decision | 0/1, 0/1 | none | 20 / 20 |
| beyond laser range, 300 m (control) | identical on every decision | 0/1, 0/1 | none | 20 / 20 |
| gun-only loadout (control) | identical on every decision | none | none | 0 / 0 |
| standard recording (control) | 0 of 300 decisions differ | n/a | n/a | n/a |

The first four rows run over 4 s (6 s for the empty-laser row). Baseline beams are the game's own auto-fire after `hold_s`.

## Selected after v6: laser trigger discipline (#3)

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
