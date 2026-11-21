"""Line-of-fire test against terrain, buildings, the stadium and bridges (cover.i16)."""
import math
import struct
import sys
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NONE = -32768


class Cover:
    STEP_M = 1.0
    # A line must pass through this much solid matter to count as blocked. The raster is 2 m,
    # so a shot grazing a corner can touch up to about 3 m of cells that are really open air;
    # walls and buildings put far more than that across any line through them.
    MIN_SOLID_M = 4.0

    def __init__(self, path=ROOT / "cover.i16"):
        data = path.read_bytes()
        size = struct.calcsize("<4sHHfff")
        magic, self.nx, self.ny, self.ox, self.oy, self.cell = struct.unpack("<4sHHfff", data[:size])
        assert magic == b"CVR1"
        planes = array("h")
        planes.frombytes(data[size:])
        if sys.byteorder == "big":
            planes.byteswap()
        n = self.nx * self.ny
        self.ground, self.top = planes[:n], planes[n:2 * n]
        self.lift_low, self.lift_high = planes[2 * n:3 * n], planes[3 * n:]

    def solid(self, x, y, z):
        """0 for open air, 1 inside terrain or a wall, 2 inside a raised deck (2 m thick)."""
        i = int((x - self.ox) / self.cell)
        j = int((y - self.oy) / self.cell)
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return 1  # the map edge is a wall
        k = j * self.nx + i
        h = z * 100
        if h < self.ground[k] or h <= self.top[k]:
            return 1
        low = self.lift_low[k]
        return 2 if low != NONE and low <= h <= self.lift_high[k] else 0

    def clear(self, start, end, skip_start=3.0, skip_end=2.5):
        """True unless at least MIN_SOLID_M of solid matter lies on the segment, ignoring the
        first `skip_start` metres (a shot leaves 3 m out from the mech) and the last `skip_end`
        (the target's own body)."""
        length = math.dist(start, end)
        if length <= skip_start + skip_end:
            return True
        steps = int((length - skip_start - skip_end) / self.STEP_M) + 1
        spacing = (length - skip_start - skip_end) / steps
        limit = max(1, round(self.MIN_SOLID_M / spacing))
        blocked = 0
        for k in range(steps + 1):
            f = (skip_start + k * spacing) / length
            hit = self.solid(start[0] + f * (end[0] - start[0]), start[1] + f * (end[1] - start[1]),
                             start[2] + f * (end[2] - start[2]))
            if hit == 2:
                return False  # bridge decks are thinner than the threshold; any crossing blocks
            if hit:
                blocked += 1
                if blocked >= limit:
                    return False
        return True
