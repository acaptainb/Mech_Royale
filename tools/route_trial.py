"""Paired navigation-only trial. Uses the controller's simplified ground grid as collision geometry."""
import gzip
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot import Bot
from bot_v3 import Bot as Original
from navigation import Navigator

def trial(controller, start, goal, grid, hello, template):
    import copy
    obs = copy.deepcopy(template)
    bot = controller(hello)
    me = obs["self"]
    me.update(pos=[*start,0], grounded=True, in_zone=True)
    obs.update(mechs=[],offer=None,pickups=[],zone=dict(template["zone"],next_center=list(goal)))
    for i in range(1400):
        obs.update(t=i/10,tick=2*i)
        dx,dy = bot.act(obs)["move"]
        x,y = me["pos"][:2]
        for axis,delta in enumerate((dx,dy)):
            candidate = me["pos"][:2]
            candidate[axis] += delta*1.17
            gx = round((candidate[0]-grid.ox)/grid.step)
            gy = round((candidate[1]-grid.oy)/grid.step)
            if 0 <= gx < grid.width and 0 <= gy < grid.height and grid.free[gy*grid.width+gx]:
                me["pos"][axis] = candidate[axis]
        if math.dist(me["pos"][:2],goal) <= 4:
            return i+1
    return None

if __name__ == "__main__":
    import mechfight as mf
    # Debug drawing has no consumer in a direct controller call.
    mf.draw.line = mf.draw.point = mf.draw.label = lambda *args: None
    with gzip.open(ROOT/"check/stream.jsonl.gz","rt") as f:
        hello,template = json.loads(next(f)),json.loads(next(f))
    grid = Navigator()
    rng = random.Random(51739)
    cells = [i for i,free in enumerate(grid.free) if free]
    pairs = []
    while len(pairs)<150:
        start,goal = [grid.point(i) for i in rng.sample(cells,2)]
        if 80 <= math.dist(start,goal) <= 650:
            pairs.append((start,goal))
    for cls in [Original,Bot]:
        import statistics
        times = [trial(cls,a,b,grid,hello,template) for a,b in pairs]
        finished = [steps / 10 for steps in times if steps is not None]
        print(cls.name, len(finished), "/", len(pairs), "reached;",
              "median simulated seconds", round(statistics.median(finished), 1))
