"""Regenerate cover.i16: a 2 m raster of what stops a shot, from arena/v2. Standard library only.

Four int16 planes in centimetres, each `ny * nx` cells, row-major from the terrain origin:
  0 ground      terrain height at the cell centre
  1 solid top   top of the highest prism that rises from (near) the ground, or NONE
  2 lift low    lowest base of a raised prism (bridge deck, overhang), or NONE
  3 lift high   highest top among those raised prisms, or NONE
A point at height h is inside solid matter when h < ground, h <= solid top, or
lift low <= h <= lift high. Trees are left out because they do not stop shots.
"""
import json
import struct
import sys
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CELL = 2.0
NONE = -32768
RAISED_M = 1.5  # a prism whose base is this far above the ground under it is a deck, not a wall


def main():
    world = json.loads((ROOT / "arena/v2/world.json").read_text())
    terrain = world["terrain"]
    source = array("h")
    source.frombytes((ROOT / "arena/v2" / terrain["file"]).read_bytes())
    if sys.byteorder == "big":
        source.byteswap()
    tnx, tny, scale = terrain["nx"], terrain["ny"], terrain["scale"]
    ox, oy = terrain["minX"], terrain["minY"]
    nx, ny = int((tnx - 1) // CELL), int((tny - 1) // CELL)

    def height(x, y):
        u = min(tnx - 1.001, max(0.0, x - ox))
        v = min(tny - 1.001, max(0.0, y - oy))
        i, j = int(u), int(v)
        fu, fv = u - i, v - j
        k = j * tnx + i
        low = source[k] * (1 - fu) + source[k + 1] * fu
        high = source[k + tnx] * (1 - fu) + source[k + tnx + 1] * fu
        return (low * (1 - fv) + high * fv) * scale

    ground = array("h", [0]) * (nx * ny)
    for j in range(ny):
        for i in range(nx):
            ground[j * nx + i] = round(100 * height(ox + (i + 0.5) * CELL, oy + (j + 0.5) * CELL))
    top = array("h", [NONE]) * (nx * ny)
    lift_low = array("h", [NONE]) * (nx * ny)
    lift_high = array("h", [NONE]) * (nx * ny)

    def edges(flat):
        points = list(zip(flat[::2], flat[1::2]))
        return [(points[k], points[(k + 1) % len(points)]) for k in range(len(points))]

    for prism in world["prisms"]:
        rings = [edges(prism["ring"])] + [edges(hole) for hole in prism["holes"]]
        xs, ys = prism["ring"][::2], prism["ring"][1::2]
        j0 = max(0, int((min(ys) - oy) / CELL) - 1)
        j1 = min(ny - 1, int((max(ys) - oy) / CELL) + 1)
        i0 = max(0, int((min(xs) - ox) / CELL) - 1)
        i1 = min(nx - 1, int((max(xs) - ox) / CELL) + 1)
        base, peak = round(prism["base"] * 100), round(prism["top"] * 100)

        def spans(y):
            """Even-odd scanline over the ring and its holes at height y."""
            crossings = []
            for ring in rings:
                for (ax, ay), (bx, by) in ring:
                    if (ay > y) != (by > y):
                        crossings.append(ax + (y - ay) * (bx - ax) / (by - ay))
            crossings.sort()
            return list(zip(crossings[::2], crossings[1::2]))

        for j in range(j0, j1 + 1):
            # Walls and buildings: a cell is solid when its centre is inside.
            for a, b in spans(oy + (j + 0.5) * CELL):
                for i in range(max(i0, int((a - ox) / CELL - 0.5) + 1), min(i1, int((b - ox) / CELL - 0.5)) + 1):
                    k = j * nx + i
                    if base <= ground[k] + RAISED_M * 100:
                        top[k] = max(top[k], peak)
            # Raised decks are narrow strips that cell centres can miss entirely, so a deck
            # marks every cell it touches on any of four sub-rows.
            touched = set()
            for sub in (0.05, 0.35, 0.65, 0.95):
                for a, b in spans(oy + (j + sub) * CELL):
                    touched.update(range(max(i0, int((a - ox) / CELL)), min(i1, int((b - ox) / CELL)) + 1))
            for i in touched:
                k = j * nx + i
                if base > ground[k] + RAISED_M * 100:
                    lift_low[k] = base if lift_low[k] == NONE else min(lift_low[k], base)
                    lift_high[k] = max(lift_high[k], peak)
    header = struct.pack("<4sHHfff", b"CVR1", nx, ny, ox, oy, CELL)
    body = array("h")
    for plane in (ground, top, lift_low, lift_high):
        body.extend(plane)
    if sys.byteorder == "big":
        body.byteswap()
    (ROOT / "cover.i16").write_bytes(header + body.tobytes())
    covered = sum(1 for v in top if v != NONE)
    raised = sum(1 for v in lift_low if v != NONE)
    print(f"cover.i16: {nx} x {ny} cells of {CELL} m; {covered} solid, {raised} under a raised deck")


if __name__ == "__main__":
    main()
