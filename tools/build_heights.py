"""Regenerate heights.i16: terrain height at every navigation grid node. Standard library only."""
import json
import sys
from array import array
from pathlib import Path

root = Path(__file__).resolve().parents[1]
grid = json.loads((root / "grid.json").read_text())
terrain = json.loads((root / "arena/v2/world.json").read_text())["terrain"]
source = array("h")
source.frombytes((root / "arena/v2" / terrain["file"]).read_bytes())
if sys.byteorder == "big":
    source.byteswap()
assert terrain["step"] == 1 and terrain["scale"] == 0.01
assert grid["origin"] == [terrain["minX"], terrain["minY"]]
step = grid["step"]
# Grid node (i, j) sits on terrain vertex (i*step, j*step); values stay in centimetres.
heights = array("h", (source[j * step * terrain["nx"] + i * step]
                      for j in range(grid["height"]) for i in range(grid["width"])))
if sys.byteorder == "big":
    heights.byteswap()
(root / "heights.i16").write_bytes(heights.tobytes())
print(len(heights), "heights written")
