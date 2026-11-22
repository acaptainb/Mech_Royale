"""laser-cover: step behind cover while a visible mech charges a laser at us."""
import math


class LaserCover:
    """Trigger: a visible game mech is charging (`charging` true), its torso aim is within
    AIM_DEG of the bearing to us and we are within laser range. Lasers are hitscan, so walking
    sideways cannot beat them; only a solid line of sight does.

    While triggered (and for HOLD_S after the last charging decision), in the zone with the
    return not urgent, the mech moves to the nearest point within SEARCH_RADII that is
    reachable on the ground grid (`nav.clear_segment`), inside the current circle with
    ZONE_MARGIN_M to spare, and hidden from the shooter's eye by solid matter anywhere on the
    line (`cover.py`). After a search that finds nothing, the next waits RETRY_S.
    If its own position is already hidden, it holds still. With no such point, normal
    movement stands. It boosts toward cover while energy stays above ENERGY_RESERVE.
    """
    AIM_DEG = 12.0
    HOLD_S = 0.5
    SEARCH_RADII = (3.0, 5.0, 7.0, 10.0)
    DIRECTIONS = 12
    RETRY_S = 0.3          # after finding no cover, search again this much later
    ZONE_MARGIN_M = 3.0
    ENERGY_RESERVE = 20.0
    EYE_M = 8.0
    BODY_M = 4.5

    def __init__(self, hello, nav, cover):
        self.nav = nav
        self.cover = cover
        self.range = hello["config"].get("weapons", {}).get("laser", {}).get("range", 280.0)
        self.until = -1.0
        self.shooter = None    # position of the last charging shooter
        self.point = None      # the hiding point being walked to
        self.reached = False
        self.retry = -1.0      # no search before this time (after one that found nothing)
        self.active = False
        self.counts = {}       # outcome -> count, for local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def ground(self, x, y):
        c = self.cover
        i = min(c.nx - 1, max(0, int((x - c.ox) / c.cell)))
        j = min(c.ny - 1, max(0, int((y - c.oy) / c.cell)))
        return c.ground[j * c.nx + i] / 100

    def charging_at_us(self, obs):
        me = obs["self"]["pos"]
        best = None
        for other in obs.get("mechs") or ():
            if other.get("kind") != "mech" or not other.get("charging"):
                continue
            distance = math.dist(other["pos"][:2], me[:2])
            if distance > self.range:
                continue
            aim = (other.get("aim") or [None])[0]
            if aim is None:
                continue
            bearing = math.atan2(me[1] - other["pos"][1], me[0] - other["pos"][0])
            if abs((aim - bearing + math.pi) % math.tau - math.pi) > math.radians(self.AIM_DEG):
                continue
            if best is None or distance < best[0]:
                best = (distance, other)
        return best[1] if best else None

    def hidden(self, point):
        """Is a body standing at `point` hidden from the shooter's eye by solid matter near it?"""
        sx, sy, sz = self.shooter
        body = (point[0], point[1], self.ground(point[0], point[1]) + self.BODY_M)
        return not self.cover.clear((sx, sy, sz + self.EYE_M), body, skip_start=3.0, skip_end=2.5)

    def usable(self, obs, point):
        zone = obs["zone"]
        if math.dist(point, zone["center"]) + self.ZONE_MARGIN_M > zone["radius"]:
            return False
        return self.nav.clear_segment(obs["self"]["pos"], point)

    def search(self, obs):
        pos = obs["self"]["pos"]
        for radius in self.SEARCH_RADII:
            options = []
            for k in range(self.DIRECTIONS):
                a = k * math.tau / self.DIRECTIONS
                point = (pos[0] + radius * math.cos(a), pos[1] + radius * math.sin(a))
                if self.usable(obs, point) and self.hidden(point):
                    options.append(point)
            if options:
                # among equally near points, prefer the one most directly away from the shooter
                sx, sy = self.shooter[:2]
                return max(options, key=lambda p: math.dist(p, (sx, sy)))
        return None

    def steer(self, obs, action, urgent):
        """Call after the move and boost are set, before the dodge. Returns True while it steers."""
        self.active = False
        now = obs["t"]
        me = obs["self"]
        threat = self.charging_at_us(obs)
        if threat is not None:
            self.count("triggers")
            if now >= self.until:
                self.point, self.reached = None, False
            self.shooter = tuple(threat["pos"])
            self.until = now + self.HOLD_S
        elif now >= self.until - 1e-9:
            self.point = None
            return False
        if urgent or not me.get("in_zone"):
            self.count("skipped: zone return urgent")
            return False
        pos = me["pos"]
        if self.hidden(pos[:2]):
            target = (pos[0], pos[1])
        else:
            if self.point is None or not self.hidden(self.point) or not self.usable(obs, self.point):
                self.point = self.search(obs) if now >= self.retry - 1e-9 else None
                if self.point is None:
                    if now >= self.retry - 1e-9:
                        self.retry = now + self.RETRY_S
                    self.count("no cover found")
                    return False
                self.count("cover moves started")
            target = self.point
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        length = math.hypot(dx, dy)
        if length < 1.0:
            action["move"], action["boost"] = [0, 0], False
            if not self.reached:
                self.reached = True
                self.count("cover reached")
        else:
            action["move"] = [dx / length, dy / length]
            action["boost"] = me.get("energy", 0) > self.ENERGY_RESERVE
        action["jump"] = False
        self.active = True
        return True
