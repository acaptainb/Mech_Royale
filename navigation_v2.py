"""Incremental reverse breadth-first search on the arena's connected ground grid."""
import json
import math
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class Navigator:
    def __init__(self):
        meta = json.loads((ROOT / "grid.json").read_text())
        self.width, self.height = meta["width"], meta["height"]
        self.ox, self.oy = meta["origin"]
        self.step = meta["step"]
        self.free = (ROOT / "ground.grid").read_bytes()
        self.goal = None
        self.toward = {}
        self.queue = deque()

    def point(self, i):
        return self.ox + i % self.width * self.step, self.oy + i // self.width * self.step

    def snap(self, point):
        x = min(self.width-1, max(0, round((point[0]-self.ox)/self.step)))
        y = min(self.height-1, max(0, round((point[1]-self.oy)/self.step)))
        i = y*self.width+x
        if self.free[i]:
            return i
        # Find the nearest accessible ring, including for rooftop spawns.
        for r in range(1,max(self.width,self.height)):
            candidates = []
            for yy in range(max(0,y-r),min(self.height,y+r+1)):
                xs = range(max(0,x-r),min(self.width,x+r+1)) if abs(yy-y)==r else (x-r,x+r)
                for xx in xs:
                    if 0 <= xx < self.width and self.free[yy*self.width+xx]:
                        candidates.append(yy*self.width+xx)
            if candidates:
                return min(candidates,key=lambda j: math.dist(point[:2],self.point(j)))

    def clear_segment(self, start, end):
        count = max(1, math.ceil(math.dist(start[:2],end[:2])/2))
        for k in range(count+1):
            fraction = k/count
            x = round((start[0] + fraction*(end[0]-start[0]) - self.ox)/self.step)
            y = round((start[1] + fraction*(end[1]-start[1]) - self.oy)/self.step)
            if not (0 <= x < self.width and 0 <= y < self.height and self.free[y*self.width+x]):
                return False
        return True

    def waypoint(self, pos, destination):
        if destination != self.goal:
            self.goal = list(destination)
            target = self.snap(destination)
            self.toward = {target:target}
            self.queue = deque([target])
        start = self.snap(pos)
        for _ in range(1000):
            if start in self.toward or not self.queue:
                break
            i = self.queue.popleft()
            for j in (i-1,i+1,i-self.width,i+self.width):
                # Map edges are blocked during grid generation.
                if self.free[j] and j not in self.toward:
                    self.toward[j] = i
                    self.queue.append(j)
        if math.dist(pos[:2],self.point(start)) > 3 or start not in self.toward:
            return self.point(start)
        nxt = self.toward[start]
        # Look ahead along straight runs without cutting building corners.
        stride = nxt-start
        for _ in range(3):
            further = self.toward[nxt]
            if further-nxt != stride:
                break
            nxt = further
        return self.point(nxt)
