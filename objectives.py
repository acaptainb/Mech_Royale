"""Choose a movement objective for one simulated game tick."""
import math


class Objectives:
    # drop-always: go for a supply drop whatever our HP, as long as the capture can finish
    # within this many seconds (a drop lands 25 s after it is called, so walking there
    # during the fall counts). The kit-era rule went only below 80% HP with 10 s.
    DROP_WINDOW_S = 30.0

    def __init__(self):
        self.last_hp = None
        self.relocate_until = -1
        self.refuge = None
        self.mode = "zone"
        self.drop_decisions = 0   # drop-always: decisions in drop mode, for local reports
        self.captures = 0         # drop-always: drops we were holding that were then taken
        self.holding = None       # id of the drop whose capture clock was ours last decision

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

        # drop-always: count a capture when the drop we were holding is no longer listed.
        listed = {drop["id"]: drop for drop in obs.get("drops") or ()}
        if self.holding is not None and self.holding not in listed:
            self.captures += 1
        self.holding = next((key for key, drop in listed.items()
                             if drop["holder"] == me["id"]), None)

        def safe(at):
            return (math.dist(at, center) + 3 <= radius and
                    math.dist(at, zone["center"]) + 3 <= zone["radius"])

        if not me["in_zone"] or radius < 8 or (gap > 0 and now + gap/speed + 5 >= zone["shrink_start"]):
            self.mode = "return"
            self.refuge = None
            return center

        # A destination safely inside both circles stays safe as the zone interpolates.
        # drop-always: no HP gate (was HP below 80%), and a DROP_WINDOW_S window (was 10 s).
        best, best_time = None, math.inf
        for drop in obs.get("drops") or ():
            at = drop["pos"][:2]
            distance = math.dist(pos, at)
            ours = drop["holder"] == me["id"]
            inside = distance <= drop["radius"] - 1
            if (not safe(at) or abs(drop["pos"][2]-me["pos"][2]) > 4
                or drop["holder"] not in (None, me["id"])
                or any(a["kind"] == "mech" and math.dist(a["pos"][:2],at) < drop["radius"]+5 for a in obs["mechs"])):
                continue
            finish = max(distance/speed, drop["lands_in"]) + drop["capture_s"] - (drop["progress"] if ours else 0)
            if finish <= self.DROP_WINDOW_S and finish < best_time and (inside or nav.clear_segment(pos, at)):
                best, best_time = (pos if inside and safe(pos) else at), finish
        if best is not None:
            self.mode = "drop"
            self.drop_decisions += 1
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
