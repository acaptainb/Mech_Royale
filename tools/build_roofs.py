"""Regenerate roofs.json: flat roofs a mech can jet onto, with a camp spot and climb points.

    py tools/build_roofs.py

From cover.i16 (2 m raster of ground, solid tops and raised decks), the navigation grid and
the arena's fences, cars and tree trunks. Standard library only. For every flat roof 8-45 m
above the ground beside it:
  camp   the roof cell farthest from the roof's edge (at least CAMP_DEPTH_M in)
  runs   the roof's cells as [row, first column, last column] runs of the 2 m raster
  feet   climb points on a straight wall: a stage point on open ground (STAGE_M out from the
         wall), the contact point (the mech touching the wall), the landing point on the roof,
         the unit direction into the roof and the wall height. The approach corridor is open,
         flat ground with no overhang; the strip behind the wall is this roof; the landing
         point has a straight walk on the roof to the camp spot; a navigation grid node near
         the stage point has a straight, open line to it.
"""
import heapq
import json
import math
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cover import NONE, Cover
from navigation import Navigator

MIN_H, MAX_H = 8.0, 45.0     # roof height above the ground at the foot of the wall
FLAT_CM = 30                 # neighbouring roof cells within this much count as one roof
MIN_CELLS = 36               # 144 m2
CAMP_DEPTH_M = 5.0
STAGE_M = 7.0                # stage point: mech centre this far out from the wall face
CONTACT_M = 2.9              # mech radius 2.5 plus a little
LAND_M = 3.5                 # landing point: centre this far in from the edge
WALK_DEPTH_M = 3.0           # the walk to the camp spot keeps this far in from the edge
RADIUS = 2.5
SPACING_M = 6.0              # climb points on one roof at least this far apart
MAX_FEET = 32


def main():
    cover = Cover()
    nav = Navigator()
    world = json.loads((ROOT / "arena/v2/world.json").read_text())
    nx, ny, cell = cover.nx, cover.ny, cover.cell

    def index(x, y):
        i, j = int((x - cover.ox) / cell), int((y - cover.oy) / cell)
        return j * nx + i if 0 <= i < nx and 0 <= j < ny else None

    def centre(k):
        return cover.ox + (k % nx + 0.5) * cell, cover.oy + (k // nx + 0.5) * cell

    def open_ground(k, level):
        """Walkable ground cell near `level` (cm) with nothing solid or raised over it."""
        if k is None or cover.lift_low[k] != NONE:
            return False
        top = cover.top[k]
        if top != NONE and top - cover.ground[k] > 50:
            return False
        return abs(cover.ground[k] - level) <= 100

    # Obstacles the cover raster leaves out: fences (taller than a step), cars, tree trunks.
    segments = [b["line"] for b in world["barriers"] if b.get("blocks", True) and b.get("height", 2) > 1.2]
    fields = world["cars"]["fields"]
    cars = [dict(zip(fields, world["cars"]["data"][n:n + len(fields)]))
            for n in range(0, len(world["cars"]["data"]), len(fields))]
    tfields = world["trees"]["fields"]
    trees = [dict(zip(tfields, world["trees"]["data"][n:n + len(tfields)]))
             for n in range(0, len(world["trees"]["data"]), len(tfields))]
    circles = [(c["x"], c["y"], max(c["length"], c["width"]) / 2) for c in cars]
    circles += [(t["x"], t["y"], t["trunkR"]) for t in trees]

    def seg_dist(p, a, b):
        ax, ay, bx, by = a[0], a[1], b[0], b[1]
        dx, dy = bx - ax, by - ay
        f = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        return math.dist(p, (ax + f * dx, ay + f * dy))

    def seg_seg(a, b, c, d):
        def orient(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
        if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
            return True
        return min(seg_dist(c, a, b), seg_dist(d, a, b), seg_dist(a, c, d), seg_dist(b, c, d)) < 1e-6

    def corridor_clear(a, b, width):
        """No fence, car or trunk within `width` of the segment a-b."""
        for line in segments:
            pts = list(zip(line[::2], line[1::2]))
            for p, q in zip(pts, pts[1:]):
                if seg_seg(a, b, p, q) or seg_dist(p, a, b) < width or seg_dist(q, a, b) < width \
                        or seg_dist(a, p, q) < width or seg_dist(b, p, q) < width:
                    return False
        for x, y, r in circles:
            if seg_dist((x, y), a, b) < width + r:
                return False
        return True

    # --- roof cells and flat components ------------------------------------------------
    roofish = bytearray(nx * ny)
    for k in range(nx * ny):
        top = cover.top[k]
        if top != NONE and cover.lift_low[k] == NONE and top - cover.ground[k] >= 600:
            roofish[k] = 1
    label = [-1] * (nx * ny)
    components = []
    for k0 in range(nx * ny):
        if not roofish[k0] or label[k0] >= 0:
            continue
        members, queue = [], deque([k0])
        label[k0] = len(components)
        while queue:
            k = queue.popleft()
            members.append(k)
            i, j = k % nx, k // nx
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ii, jj = i + di, j + dj
                if 0 <= ii < nx and 0 <= jj < ny:
                    q = jj * nx + ii
                    if roofish[q] and label[q] < 0 and abs(cover.top[q] - cover.top[k]) <= FLAT_CM:
                        label[q] = label[k0]
                        queue.append(q)
        components.append(members)

    roofs = []
    for cid, members in enumerate(components):
        if len(members) < MIN_CELLS:
            continue
        inside = set(members)
        top_cm = sorted(cover.top[k] for k in members)[len(members) // 2]
        # Depth: chamfer distance from the roof's edge, in metres.
        depth = {}
        heap = []
        for k in members:
            i, j = k % nx, k // nx
            edge = any(not (0 <= i + di < nx and 0 <= j + dj < ny) or (j + dj) * nx + i + di not in inside
                       for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj)
            if edge:
                depth[k] = cell / 2
                heapq.heappush(heap, (cell / 2, k))
        while heap:
            d, k = heapq.heappop(heap)
            if d > depth.get(k, math.inf):
                continue
            i, j = k % nx, k // nx
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if not (di or dj):
                        continue
                    q = (j + dj) * nx + i + di
                    if q in inside:
                        nd = d + cell * (1.4142 if di and dj else 1.0)
                        if nd < depth.get(q, math.inf):
                            depth[q] = nd
                            heapq.heappush(heap, (nd, q))
        camp_k = max(members, key=lambda k: (depth[k], -k))
        if depth[camp_k] < CAMP_DEPTH_M:
            continue
        camp = centre(camp_k)

        def on_roof(x, y):
            return index(x, y) in inside

        feet = []
        for k in sorted(members):
            if depth[k] > cell:
                continue
            i, j = k % nx, k // nx
            bx, by = centre(k)
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ii, jj = i + di, j + dj
                if not (0 <= ii < nx and 0 <= jj < ny):
                    continue
                o = jj * nx + ii
                level = cover.ground[o]
                if not open_ground(o, level):
                    continue
                height = (top_cm - level) / 100
                if not MIN_H <= height <= MAX_H:
                    continue
                ux, uy = -di, -dj                        # into the roof
                px, py = uy, -ux                         # along the wall
                fx, fy = bx + di * cell / 2, by + dj * cell / 2   # wall face
                stage = (fx + di * STAGE_M, fy + dj * STAGE_M)
                contact = (fx + di * CONTACT_M, fy + dj * CONTACT_M)
                land = (fx - di * LAND_M, fy - dj * LAND_M)
                ok = True
                # Approach corridor: open, flat ground, no overhang, the full mech width.
                s = 0.6
                while ok and s <= STAGE_M + 0.01:
                    for w in (-3.0, -1.5, 0.0, 1.5, 3.0):
                        if not open_ground(index(fx + di * s + px * w, fy + dj * s + py * w), level):
                            ok = False
                            break
                    s += 0.8
                # No eave or deck anywhere near the climb column.
                for ddx in (-4, -2, 0, 2, 4):
                    for ddy in (-4, -2, 0, 2, 4):
                        q = index(contact[0] + ddx, contact[1] + ddy)
                        if q is None or cover.lift_low[q] != NONE:
                            ok = False
                # Behind the face: this roof, the full width, deep enough to land.
                s = 0.6
                while ok and s <= LAND_M + RADIUS + 0.01:
                    for w in (-2.0, 0.0, 2.0):
                        if not on_roof(fx - di * s + px * w, fy - dj * s + py * w):
                            ok = False
                            break
                    s += 0.8
                # A straight walk on the roof from the landing point to the camp spot, with room
                # for the mech's width (every point at least WALK_DEPTH_M in from the roof's edge).
                if ok:
                    span = math.dist(land, camp)
                    steps = max(1, int(span))
                    for n in range(steps + 1):
                        f = n / steps
                        q = index(land[0] + f * (camp[0] - land[0]), land[1] + f * (camp[1] - land[1]))
                        if q not in inside or depth[q] < WALK_DEPTH_M:
                            ok = False
                            break
                # Fences, cars and trunks in the corridor.
                if ok and not corridor_clear(stage, (fx, fy), RADIUS + 0.3):
                    ok = False
                # A navigation node near the stage point with an open, straight line to it.
                if ok:
                    node = nav.snap(stage)
                    at = nav.point(node)
                    if math.dist(at, stage) > 9.0 or not nav.free[node]:
                        ok = False
                    else:
                        span = math.dist(at, stage)
                        steps = max(1, int(span / 0.8))
                        for n in range(steps + 1):
                            f = n / steps
                            for w in (-2.0, 0.0, 2.0):
                                q = index(at[0] + f * (stage[0] - at[0]) + px * w, at[1] + f * (stage[1] - at[1]) + py * w)
                                if q is None or cover.lift_low[q] != NONE or (
                                        cover.top[q] != NONE and cover.top[q] - cover.ground[q] > 50):
                                    ok = False
                        if ok and not corridor_clear(at, stage, RADIUS):
                            ok = False
                if not ok:
                    continue
                if any(math.dist(contact, f["contact"]) < SPACING_M for f in feet):
                    continue
                feet.append(dict(stage=[round(v, 2) for v in stage], contact=[round(v, 2) for v in contact],
                                 land=[round(v, 2) for v in land], dir=[ux, uy], h=round(height, 2),
                                 ground=round(level / 100, 2)))
                if len(feet) >= MAX_FEET:
                    break
            if len(feet) >= MAX_FEET:
                break
        if not feet:
            continue
        runs = []
        for k in sorted(members):
            i, j = k % nx, k // nx
            if runs and runs[-1][0] == j and runs[-1][2] == i - 1:
                runs[-1][2] = i
            else:
                runs.append([j, i, i])
        roofs.append(dict(id=len(roofs), top=round(top_cm / 100, 2), camp=[round(v, 2) for v in camp],
                          depth=round(depth[camp_k], 2), cells=len(members), runs=runs, feet=feet))
    out = dict(cell=cell, origin=[cover.ox, cover.oy], nx=nx, roofs=roofs)
    (ROOT / "roofs.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(roofs)} roofs, {sum(len(r['feet']) for r in roofs)} climb points, "
          f"heights {min((f['h'] for r in roofs for f in r['feet']), default=0)}-"
          f"{max((f['h'] for r in roofs for f in r['feet']), default=0)} m")


if __name__ == "__main__":
    main()
