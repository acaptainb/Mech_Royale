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

## mortar-dodge

Built on lead-shots (`4d8a32d`, official 2.90). The bot steps out of the blast of a visible mortar shell that would land on its route (`ShellDodge` in `dodge.py`). It predicts each shell's flight against the cover raster, checks where the route would put us when the shell lands, and picks the clear direction with the least predicted damage, preferring the route direction. It never acts during an urgent zone return. Run `py tools/shell_dodge_trial.py` for the closed-loop shell trial against the exported baseline.

## dodge-tuned

Built on mortar-dodge (`1645c22`, official 3.00). The v8 bullet dodge steps aside at most once per 0.5 s (was 2 s), for 0.2 s (was 0.3 s). The values come from `py tools/dodge_sweep.py`, which runs dodge settings through the dodge trial's tuning and held-out routes.

## farm-power

Built on dodge-tuned (`dd9b731`, official 3.10). In the first 180 s, with nobody around, the bot shoots passive drones and crates within 150 m and walks to cubes within 120 m, so it is stronger when the hunters come (`farm.py`, `targeting.py`). Run `py tools/farm_trial.py`.

## squad-fire

Built on farm-power (`8064167`, official 3.25). In practice matches, where the 15 house bots hunt us together and only our kills score, it changes what the bot shoots and how it pulls each trigger (`squad.py`, now `squad_fire.py`). Practice mode starts after 20 s of match time and lasts while every death so far is one of our kills; outside it the bot is farm-power exactly, and movement and the dodges never change.

- Only engaged mechs are shot or looked at: within 60 m, hit us in the last 6 s, late in the match, closing faster than 3 m/s within 180 m, under 40% HP within 160 m, or aiming at us within 190 m.
- The target is the engaged mech in clear view within 240 m with the lowest distance + 0.2 x HP, with bonuses for low HP, for being the current target, for hitting us and for closing.
- The laser is released early when the charge already kills, and a full charge only with the torso on the body; the gun fires when the torso can reach the lead point; lightning only inside its range and cone.
- Laser over lightning (sought from 240 m, swapped in for lightning), never a mortar, and a laser-first upgrade order.

Run `py tools/squad_fire_trial.py` (scenarios against the exported parent, a closed-loop fight, timing and a fuzz pass; `--quick` skips the fight).

## squad-move

Built on farm-power (`8064167`, official 3.25). In practice mode the bot chooses where to stand in a fight: a 17-point scorer keeps the range its weapons like, a line of fire when a shot is ready, and out of sight of the other hunters, with a random strafe. It retreats to cover in 1.5 s pulses only when outnumbered and hurt, and sidesteps aimed laser charges. Official 3.52.

## squad-econ

Built on farm-power (`8064167`, official 3.25). In practice mode the bot gathers cubes, crates and drones all match, camps still on an inner circle of the zone between fights, scans all round with the torso when there is nothing to face, and frees itself when it stops moving against an obstacle. Official 3.29.

## squad-fire-move

Built on squad-fire (`90d298b`, official 3.65) with squad-move (`35a0bdd`, official 3.52). Practice mode is one design in two parts, both reading one detector (`practice.py`: after 20 s, while every death so far is one of our kills):

- `squad_fire.py`, the fire part: which mech to face and shoot, how each trigger is pulled, the weapon wishes and the upgrade order. It decides first on every practice decision.
- `squad_move.py`, the move part: where to stand while fighting the fire part's target (or the nearest engaged mech while no target has a line of fire), the short LoseRule retreats to cover and the laser sidestep.

Movement, highest first: the bullet and shell dodges; the parent's urgent zone return; the LoseRule retreat; the fight move with the mid-fight cube grab; otherwise farm-power's movement. Outside practice mode every decision is farm-power's. Run `py tools/squad_fire_trial.py`, `py tools/squad_move_trial.py` and `py tools/practice_trial.py` (mode switch against farm-power, decision time with the parts busy, fuzz).

## squad-all

Built on squad-fire-move (`8805ed6`) with squad-econ (`f8dc9bf`, official 3.29). Practice mode is one design in three parts, all reading one detector (`practice.py`: after 20 s, while every death so far is one of our kills):

- `squad_fire.py`, the fire part: which mech to face and shoot, every trigger, the weapon wishes and the upgrade order. It decides first, and owns the aim and the triggers.
- `squad_move.py`, the move part: where to stand while fighting, the short LoseRule retreats to cover and the laser sidestep.
- `squad_econ.py`, the economy part: loot all match, camping on an inner zone circle, the idle scan and the stuck rule. Its crate and drone shots apply only when the fire part has nothing to shoot, its idle aim only when there is no enemy to face.

Movement, highest first: the stuck recovery; the bullet and shell dodges (the final word); zone must; the LoseRule retreat; the fight move with the mid-fight cube grab; supply drops and relocation; zone should; the fire part's weapon detour; loot; camp or walk to the zone goal. Outside practice mode every decision is farm-power's. Run the three part trials (`py tools/squad_fire_trial.py`, `py tools/squad_move_trial.py`, `py tools/squad_econ_trial.py`) and `py tools/practice_trial.py` (mode switch, decision time with every part busy, fuzz, the movement priority).

## squad-all-sticky

squad-all (`9399d0d`) with practice mode kept on until three mechs have died to something other than us.
