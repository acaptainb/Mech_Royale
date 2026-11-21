"""Choose a movement objective for one simulated game tick."""
import math


class Objectives:
    def __init__(self):
        self.last_hp = None
        self.relocate_until = -1
        self.refuge = None
        self.mode = "zone"

    def choose(self, obs, nav):
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        pos = me["pos"][:2]
        center = zone["next_center"]
        radius = zone["next_radius"]
        speed = max(1, me["stats"]["walk_speed"])
        gap = math.dist(pos, center) - radius
        self.mode = "zone"
        if self.last_hp is not None and me["hp"] < self.last_hp:
            self.relocate_until = now + 2.5
        self.last_hp = me["hp"]

        def safe(at):
            return (math.dist(at, center) + 3 <= radius and
                    math.dist(at, zone["center"]) + 3 <= zone["radius"])

        if not me["in_zone"] or radius < 8 or (gap > 0 and now + gap/speed + 5 >= zone["shrink_start"]):
            self.mode = "return"
            self.refuge = None
            return center

        # A destination safely inside both circles stays safe as the zone interpolates.
        if me["hp"] < 0.80 * me["max_hp"]:
            best, best_time = None, math.inf
            for drop in obs["drops"]:
                at = drop["pos"][:2]
                distance = math.dist(pos, at)
                ours = drop["holder"] == me["id"]
                inside = distance <= drop["radius"] - 1
                if (not safe(at) or abs(drop["pos"][2]-me["pos"][2]) > 4
                    or drop["holder"] not in (None, me["id"])
                    or any(a["kind"] == "mech" and math.dist(a["pos"][:2],at) < drop["radius"]+5 for a in obs["mechs"])):
                    continue
                finish = max(distance/speed, drop["lands_in"]) + drop["capture_s"] - (drop["progress"] if ours else 0)
                if finish <= 10 and finish < best_time and (inside or nav.clear_segment(pos, at)):
                    best, best_time = (pos if inside and safe(pos) else at), finish
            if best is not None:
                self.mode = "drop"
                return best

        if now < self.relocate_until and safe(pos):
            if self.refuge is None or not safe(self.refuge) or math.dist(pos,self.refuge) < 2:
                options = []
                for i in range(12):
                    angle = i * math.tau / 12
                    at = [pos[0]+12*math.cos(angle),pos[1]+12*math.sin(angle)]
                    if safe(at) and nav.clear_segment(pos, at):
                        separation = min((math.dist(a["pos"][:2], at) for a in obs["mechs"]), default=0)
                        options.append((separation - 0.1*math.dist(at,center),at))
                self.refuge = max(options, default=(0,None), key=lambda item:item[0])[1]
            if self.refuge is not None:
                self.mode = "relocate"
                return self.refuge
        else:
            self.refuge = None
        return center
