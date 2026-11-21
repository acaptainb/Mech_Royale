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
        """Visit every crossed grid cell, including both sides of a corner."""
        ax = (start[0] - self.ox) / self.step + 0.5
        ay = (start[1] - self.oy) / self.step + 0.5
        bx = (end[0] - self.ox) / self.step + 0.5
        by = (end[1] - self.oy) / self.step + 0.5
        x, y = math.floor(ax), math.floor(ay)
        ex, ey = math.floor(bx), math.floor(by)
        dx, dy = bx - ax, by - ay
        sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
        stepx = abs(1 / dx) if dx else math.inf
        stepy = abs(1 / dy) if dy else math.inf
        tx = ((x + (sx > 0)) - ax) / dx if dx else math.inf
        ty = ((y + (sy > 0)) - ay) / dy if dy else math.inf
        def open_cell(i, j):
            return 0 <= i < self.width and 0 <= j < self.height and self.free[j*self.width+i]
        while open_cell(x, y):
            if (x, y) == (ex, ey):
                return True
            if abs(tx-ty) < 1e-10 and x != ex and y != ey:
                if not open_cell(x+sx,y) or not open_cell(x,y+sy):
                    return False
                x, y = x+sx, y+sy
                tx, ty = tx+stepx, ty+stepy
            elif y == ey or (x != ex and tx < ty):
                x += sx
                tx += stepx
            else:
                y += sy
                ty += stepy
        return False

    def waypoint(self, pos, destination):
        if self.clear_segment(pos, destination):
            return destination
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
        # Skip bends only when the whole shortcut fits inside the clear corridor.
        chain = [self.toward[start]]
        for _ in range(11):
            following = self.toward[chain[-1]]
            if following == chain[-1]:
                break
            chain.append(following)
        for node in reversed(chain):
            candidate = self.point(node)
            if self.clear_segment(pos, candidate):
                return candidate
        return self.point(chain[0])
