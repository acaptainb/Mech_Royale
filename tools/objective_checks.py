"""Regression cases for game decisions using the full bot and a real observation."""
import copy
import gzip
import json
import math
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot import Bot

with gzip.open(ROOT/"check/stream.jsonl.gz","rt") as f:
    hello, template = json.loads(next(f)), json.loads(next(f))
nav = Bot(hello).nav
cell = next(i for i in range(nav.width*10,len(nav.free)-nav.width*10)
            if all(nav.free[i+nav.width*y+x] for x in range(-5,6) for y in range(-5,6)))
x,y = nav.point(cell)
passed = 0

def scenario(change, expected, movement=None, damage=False):
    global passed
    b = Bot(hello)
    o = copy.deepcopy(template)
    o.update(mechs=[],cubes=[],pickups=[],drops=[],offer=None,t=1)
    o["self"].update(pos=[x,y,0], hp=500,max_hp=1000,in_zone=True)
    o["zone"].update(center=[x,y],next_center=[x,y],radius=100,next_radius=75,shrink_start=60)
    d = dict(id=20,pos=[x+12,y,0],radius=8,lands_in=0,capture_s=4,progress=0,holder=None)
    o["drops"]=[d]
    if damage:
        b.act(o)
        o["self"]["hp"] -= 10
        o["t"] += 0.1
    change(o,d)
    a = b.act(o)
    assert b.objectives.mode == expected,(expected,b.objectives.mode)
    if movement is not None:
        assert (math.hypot(*a["move"]) > 0.5) == movement
    passed += 1

scenario(lambda o,d: None,"drop",True)
scenario(lambda o,d:d.update(pos=[x+2,y,0],holder=o["self"]["id"],progress=2),"drop",False)
scenario(lambda o,d:d.update(holder=99),"zone")
# drop-always: a drop still falling is worth walking to while the capture finishes within
# 30 s (was 10 s); past that window the plain zone objective stands.
scenario(lambda o,d:d.update(lands_in=20),"drop",True)
scenario(lambda o,d:d.update(lands_in=25),"drop",True)
scenario(lambda o,d:d.update(lands_in=27),"zone")
scenario(lambda o,d:d.update(pos=[x+12,y,20]),"zone")
# drop-always: no HP gate (was below 80% HP only).
scenario(lambda o,d:o["self"].update(hp=990),"drop",True)
scenario(lambda o,d:o["self"].update(hp=1000),"drop",True)
scenario(lambda o,d:o["self"].update(in_zone=False),"return")
scenario(lambda o,d:o["zone"].update(next_radius=0),"return")
scenario(lambda o,d:o.update(drops=[]),"relocate",True,damage=True)
scenario(lambda o,d:o.update(drops=[]),"zone",False)
scenario(lambda o,d:o["zone"].update(next_center=[x+200,y],shrink_start=0),"return",damage=True)
scenario(lambda o,d:o.update(mechs=[dict(kind="mech",id=98,pos=d["pos"])]),"zone")
print(passed,"objective checks passed")
