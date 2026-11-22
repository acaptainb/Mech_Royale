"""Regenerate exposure.u8: how exposed a mech standing on each navigation node is.

    py tools/build_exposure.py

For every walkable node of the navigation grid (grid.json, 4 m), observers stand at
DIRECTIONS bearings x RANGES distances around it. An observer counts only where a mech can
stand (a walkable node); its eye is ground + 8 m. It sees us when the cover map (cover.py,
the same line test the bot uses for shots) leaves a clear line to our centre (ground + 4.5 m)
or our top (ground + 9 m). The byte is round(255 * seen / (DIRECTIONS * len(RANGES))); 255
for nodes that are not walkable. Trees are not in the cover map, so this over-counts what a
real mech sees through canopy. Standard library only; uses every CPU core.
"""
import math
import sys
from array import array
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DIRECTIONS = 24
RANGES = (40.0, 100.0, 180.0)
EYE_M, CENTRE_M, TOP_M = 8.0, 4.5, 9.0

_nav = _cover = _heights = None


def _setup():
    global _nav, _cover, _heights
    from cover import Cover
    from navigation import Navigator
    _nav, _cover = Navigator(), Cover()
    _heights = array("h")
    _heights.frombytes((ROOT / "heights.i16").read_bytes())
    if sys.byteorder == "big":
        _heights.byteswap()


def node(x, y):
    i = round((x - _nav.ox) / _nav.step)
    j = round((y - _nav.oy) / _nav.step)
    if 0 <= i < _nav.width and 0 <= j < _nav.height:
        return j * _nav.width + i
    return None


def exposure(k):
    """Observers (of DIRECTIONS * len(RANGES)) that see a mech standing on node k."""
    px, py = _nav.point(k)
    gz = _heights[k] / 100
    centre, top = (px, py, gz + CENTRE_M), (px, py, gz + TOP_M)
    seen = 0
    for d in range(DIRECTIONS):
        angle = d * math.tau / DIRECTIONS
        ux, uy = math.cos(angle), math.sin(angle)
        for r in RANGES:
            o = node(px + r * ux, py + r * uy)
            if o is None or not _nav.free[o]:
                continue
            ox, oy = _nav.point(o)
            eye = (ox, oy, _heights[o] / 100 + EYE_M)
            if (_cover.clear(eye, top, skip_start=0.5, skip_end=2.5)
                    or _cover.clear(eye, centre, skip_start=0.5, skip_end=2.5)):
                seen += 1
    return seen


def row(j):
    out = bytearray(_nav.width)
    total = DIRECTIONS * len(RANGES)
    for i in range(_nav.width):
        k = j * _nav.width + i
        out[i] = round(255 * exposure(k) / total) if _nav.free[k] else 255
    return j, bytes(out)


def main():
    _setup()
    rows = {}
    with Pool(initializer=_setup) as pool:
        for done, (j, data) in enumerate(pool.imap_unordered(row, range(_nav.height)), 1):
            rows[j] = data
            if done % 20 == 0:
                print(f"{done}/{_nav.height} rows", flush=True)
    blob = b"".join(rows[j] for j in range(_nav.height))
    (ROOT / "exposure.u8").write_bytes(blob)
    free = [blob[k] for k in range(len(blob)) if _nav.free[k]]
    free.sort()
    print(f"exposure.u8: {len(blob)} bytes, {len(free)} walkable nodes; exposure quartiles "
          f"{free[len(free)//4]/255:.2f} {free[len(free)//2]/255:.2f} {free[3*len(free)//4]/255:.2f}")


if __name__ == "__main__":
    main()
