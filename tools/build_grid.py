"""Regenerate the bundled ground navigation grid. Offline only: pillow, numpy, scipy."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, label

root = Path(__file__).resolve().parents[1]
arena = root / "arena/v2"
world = json.loads((arena / "world.json").read_text())
t = world["terrain"]
ground = np.fromfile(arena / t["file"], dtype="<i2").reshape(t["ny"], t["nx"]) * t["scale"]
origin = (t["minX"], t["minY"])
def pixels(ring):
    return [(x-origin[0], y-origin[1]) for x,y in zip(ring[::2], ring[1::2])]

blocked = np.zeros(ground.shape, dtype=bool)
for prism in world["prisms"]:
    image = Image.new("1", (t["nx"], t["ny"]))
    draw = ImageDraw.Draw(image)
    draw.polygon(pixels(prism["ring"]), fill=1)
    for hole in prism["holes"]:
        draw.polygon(pixels(hole), fill=0)
    blocked |= np.asarray(image) & (ground + 9 > prism["base"]) & (ground + 1.2 < prism["top"])
dy, dx = np.gradient(ground)
blocked |= np.hypot(dx, dy) > np.tan(np.radians(50))
blocked[[0,-1],:] = True
blocked[:,[0,-1]] = True
# Clearance includes the starter mech radius and half a four-metre grid edge.
free = (distance_transform_edt(~blocked) > 4.6)[::4, ::4]
components, _ = label(free)
sizes = np.bincount(components.ravel())
sizes[0] = 0
free = components == sizes.argmax()
(root / "ground.grid").write_bytes(free.astype("uint8").tobytes())
(root / "grid.json").write_text(json.dumps(dict(origin=origin, width=free.shape[1], height=free.shape[0], step=4)))
