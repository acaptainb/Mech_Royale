# Mech Royale v4

Extract the ZIP into the root of a new public repository. Include the hidden .github folder. Push the files and open Actions → Match container check. The workflow runs a native Windows Python replay and a restricted linux/amd64 Docker replay. Once the checks pass, submit the repository and commit at https://www.joinbuilders.org/buildathon/tracks/builders.

## Windows PowerShell

Open a terminal in the extracted folder (the one containing bot.py). If you have Python 3.13 or newer available through the Windows Python launcher:

```powershell
py verify.py
py tools/route_trial.py
```

These commands use only the Python standard library. The first checks the official protocol replay. The second compares v3 and v4 on a seeded navigation benchmark. To test the match container locally with Docker Desktop in Linux-container mode, use WSL with Python and run python3 verify.py --docker. GitHub Actions can perform that check for you.

## Changes and measurements

V3 first checks whether a direct route crosses any blocked grid cells. On obstructed routes it uses incremental breadth-first search and checks shortcuts along the resulting path. Crossing a grid corner requires clearance in both adjacent cells. Pickup and zone decisions follow v2.

The earlier v2-to-v3 paired benchmark moves each controller over the same 150 sampled routes at a fixed speed on the navigation grid. Both reached 150 destinations. Median simulated arrival time was 45.6 seconds for v2 and 40.5 for v3. The trial excludes combat, acceleration, jumping, and dynamic opponents. Rooftops and stacked bridges are approximated by a ground-only map. For a placement score, submit to the official practice matches.

## Files and attribution

bot.py and navigation.py are the current controller and planner. bot_v2.py and navigation_v2.py preserve the comparison version. The map-derived travel grid is bundled and ready to use. Its optional offline generator uses NumPy, SciPy and Pillow. Builders supplied the arena, schema, protocol, replay, checker, Python wrapper and example bot. The example has an import guard for reuse. The runtime image contains the current bot and its dependencies only.

## Version 4 practice entry

V4 adds health-aware movement objectives. A damaged mech can select a nearby reachable supply drop, stay inside its capture ring, or choose among twelve nearby positions following damage. Returning from outside the zone, an imminent shrink, and the final small circle take precedence. Ground navigation and ordinary starter game actions carry forward from v3.

From PowerShell run `py tools/objective_checks.py` for the decision regressions, `py verify.py` for the official replay and `py tools/route_trial.py` for a v3/v4 navigation comparison. Official practice is required to measure placement. The active Docker entrypoint runs bot.py (v4).

## Version 5 early-loot experiment

V5 changes one behaviour relative to v4 (commit 124101fe2402a13451921e0d97582adc5b3aab17, tag `v4-scored`): while the second weapon slot is empty and the plain zone objective is active, the mech may leave its zone route for one nearby weapon pickup. Zone return, supply drops and relocation after damage keep priority, and the take itself is v4's existing take action. `loot.py` holds the rule:

- A pickup qualifies when it is a kind we do not hold, lies within 2.5 m of the terrain height (`heights.i16`, so rooftops and bridge decks are excluded), sits on or next to the walkable grid, and is at most 70 m of walking away with at most 80 m added to the trip to the zone goal. The cost is the straight line when it is clear, otherwise the planner's path.
- The zone must allow it: the pickup is inside the current circle, and either inside the next one or reachable with 8 s to spare before v4's zone-return rule would fire.
- Opponent pressure cancels it: a game mech within 60 m of us or the pickup, or a drone within its 45 m aggro range of the pickup. A distant drone in `obs["mechs"]` does not.
- The chosen pickup is kept across decisions and dropped when it disappears in plain view, stays hidden for 5 s, becomes unreachable, threatens the zone deadline, or stops getting closer for 2.5 s. Zone movement resumes on the same decision.

`bot_v4.py` preserves the scored controller for comparison. From PowerShell:

```powershell
py tools/pickup_trial.py    # closed loop: v4 and v5 from identical starts, pickups actually acquired
py tools/replay_report.py   # both bots over the recorded stream: pursuit and take requests only
```

The closed-loop trial moves the mech where the bot steers it on the navigation grid and removes a pickup only after a valid take. It does not model combat, buildings blocking sight, or real match physics. The recorded stream does not react to our bot, so the replay report labels takes as requests. `tools/build_heights.py` regenerates `heights.i16` with the standard library.

Known limit carried over from v4: zone return has no stuck recovery. The 8 s margin exists so that a detour abandoned beside an obstacle the grid does not know still leaves ordinary movement time to free the mech.

## Version 6 selective engagement

V6 changes one behaviour relative to v5 (`dbc4cc2`): which opponent to face and whether to shoot, in `targeting.py` (`Engagement`) with a line-of-fire raster (`cover.py`, `cover.i16`, rebuilt by `tools/build_cover.py`). Movement, pickups and the trigger handling stay v5's. `bot_v5.py` keeps the v5 controller for comparison, and `EXPERIMENTS.md` holds the log and the next experiment.

```powershell
py tools/engagement_trial.py            # v5 and v6 on identical observations, judged by emitted aim and fire
py tools/engagement_trial.py --heldout  # randomized encounters checked against rules with exact map geometry
py tools/engagement_probe.py            # the running bot (or --docker: the match container) uses v6
```

## Version 7 laser release

V7 changes one behaviour on the 2.08 baseline (`1a0ca39`). A fully charged laser is released on the decision its beam would hit the chosen opponent, where V6 held it until the game fired it on its own. `py tools/entrypoint_trial.py` runs the exported baseline and this tree as real bot processes from identical starting conditions.

## Version 8 bullet dodge

V8 changes one behaviour on the 2.08 baseline (`1a0ca39`). When a visible bullet is on course to hit us, the mech takes one brief sideways step (`dodge.py`). It skips the step when the step is blocked, would leave the zone, cannot clear the bullet in time, or would delay an urgent zone return, and it dodges at most once every 2 s. `py tools/dodge_trial.py` compares the exported baseline and this tree as real bot processes. `tools/harness.py` holds the shared process and baseline-export helpers.

## Combination: V8 + V7

This branch is V8 (`4588e6b`, official 2.50) with V7's laser release (`f69d39c`, official 2.19) added unchanged. Both changes scored above their shared 2.08 parent on their own. The dodge only sets move and boost, and the laser release only sets the laser slot's trigger, so the two never write the same command.

## lead-shots

Built on the 2.63 commit (`3b290b0`). The gun aims where a moving opponent will be when the bullet arrives; a fully charged laser is still aimed straight at the body. Run `py tools/lead_trial.py` for a closed-loop gunfight against the exported baseline.

## reload-lull

Built on the lead-shots commit (`4d8a32d`, official 2.90). While v6 holds fire (opponent behind cover, out of range, passive and unhittable, or none listed) and the gun has fewer than 8 rounds and is not reloading, the bot sends `reload`, so the next exchange starts on a full magazine. Nothing but the reload command changes. Run `py tools/reload_trial.py` for a closed-loop gunfight in which the opponent passes behind a building, against the exported baseline.
