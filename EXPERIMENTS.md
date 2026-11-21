# Experiment log

One row per version we submit. Each row names the exact commit, the scored version it was branched from, and the one behaviour it changes. A score is entered only after the Buildathon page reports it. Practice scoring is 48 matches against 15 house bots, mean of (16 - place); the track page lists the kit's starter bot at 1.15.

| Version | Commit SHA | Tag | Parent baseline | Single behaviour changed | Official practice score |
| --- | --- | --- | --- | --- | --- |
| zone-runner-v4 | `124101fe2402a13451921e0d97582adc5b3aab17` | `v4-scored` | none scored before it (first submission) | health-aware objectives on v3 navigation: supply drop when damaged, relocation after damage | 1.56 |
| zone-runner-v5 | `dbc4cc2da927ddcc3a48e5191c3c070294e2ab72` | `v5-candidate` | v4 `124101f` (1.56) | detour for one reachable ground weapon while slot 1 is empty | not submitted yet |

## Local evidence for v5 (`dbc4cc2`)

None of this is a placement result.

- Official replay checker: 300 of 300 answered in time on Windows and in the linux/amd64 match container ([run 44957396563](https://github.com/acaptainb/Mech_Royale/actions/runs/44957396563), both jobs passed).
- Objective checks: 12 passed. Route regression: v3 and v5 both reach 150 of 150, median 40.5 s, the same as v4.
- Closed-loop pickup trial (`tools/pickup_trial.py`, 10 seeded instances per scenario, identical starts):

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

  Takes in rows with zero detours are v4's existing take action firing because the zone route itself passed within reach.
- Recorded stream (`tools/replay_report.py`): no pickup ever comes within 70 m on the ground map (closest is 81.2 m, off the ground map), so v4 and v5 behave identically on it: 0 pursued, 0 take requests. The recording cannot exercise the new behaviour.

## Known limits

- v4 and v5: zone return has no stuck recovery. With v5's zone margin at 2 s, one of ten "deadline closes mid-route" runs ended jammed outside the zone; the margin is 8 s in `dbc4cc2` and all ten runs reach the zone. The underlying gap is unchanged and would be its own single-change experiment.
- No match feedback or replays were available for the v4 submission without signing in to the Buildathon site, so nothing here is drawn from official matches beyond the score.

## Stable opponent selection (measurement only, branch `exp/stable-target`)

No bot behaviour changes on this branch: `bot.py` is byte-identical to the v5 candidate. `targeting.py` holds the rule under test and the counter, `tools/target_trial.py` the scenario, and `tools/replay_report.py` gained an opponent section.

Observed on the supplied recording (300 decisions, 36.8 s): a game mech is listed in 169 decisions and it is always the same single mech (three separate engagements). No decision lists two or more, so the nearest-mech rule has nothing to choose between: 0 switches, 0 A-B-A reversals, 0 forced changes, for the baseline and for the candidate rule alike. The recording shows no switching, so no candidate bot was built from it.

Deterministic two-mech scenario (`py tools/target_trial.py`, 85 decisions): the nearest-mech rule switches 40 times with 38 A-B-A reversals; the stable-target rule switches twice with none. The candidate follows a clearly closer mech on the first decision, takes a small persistent lead after its 1 s hold, and releases on the same decision its opponent stops being listed. All 11 checks pass.

These are switch counts. They say nothing about placement.
