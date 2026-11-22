"""Run another trial with only the v12 hold switched off, to show nothing else changed.

    py tools/no_hold.py route_trial.py
    py tools/no_hold.py pickup_trial.py
    py tools/no_hold.py objective_checks.py

Those trials judge success by reaching the zone centre. V12 deliberately stops short of it
when it is already safe beside cover, so with the hold on they report fewer arrivals.
"""
import runpy
import sys
from pathlib import Path

root = str(Path(__file__).resolve().parents[1])
trial = sys.argv[1]
sys.path.insert(0, root); sys.path.insert(0, root + "/tools")
import hold
hold.Hold.steer = lambda self, obs, action, **state: False
sys.argv = [trial]
runpy.run_path(root + "/tools/" + trial, run_name="__main__")
