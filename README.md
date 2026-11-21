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
