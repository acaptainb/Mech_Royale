"""kite-distance: back away from a house mech that is fighting us or closing in at short range."""
import math


class Kite:
    """Trigger: a listed game mech within RANGE_M that is an attacker (it damaged us within
    the engagement's memory), aims at us (the engagement's threat test), or walks at us (speed
    above CLOSING_MPS with its velocity within CLOSING_DEG of the bearing to us).

    While triggered, outside an urgent zone return, a supply-drop capture and obstacle
    recovery, the move becomes the direction away from the threat-weighted centroid of those
    mechs, blended with GOAL_WEIGHT of the heading to the current waypoint. A leg of LEG_M must
    be clear on the ground grid, stay ZONE_MARGIN_M inside the current circle and, when we are
    inside the next circle, inside it too (otherwise it must not lose ground toward it). When
    the straight-away leg fails, directions turned up to 90 degrees to either side are tried.
    No passing leg: the normal move stands. Boosts only while energy is above BOOST_ENERGY.
    Aim and fire stay as the engagement decides; the v8 dodge runs afterwards and keeps the
    final say.
    """
    RANGE_M = 70.0
    CLOSING_MPS = 2.0
    CLOSING_DEG = 30.0
    GOAL_WEIGHT = 0.35
    LEG_M = 8.0
    ZONE_MARGIN_M = 5.0
    TURNS_DEG = (0, 30, -30, 60, -60, 90, -90)
    BOOST_ENERGY = 50.0

    def __init__(self, hello, nav):
        self.nav = nav
        self.decisions = 0      # decisions whose move this rule set, for local reports
        self.counts = {}        # outcome -> count, for local reports
        self.active = False

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def threats(self, obs, engagement):
        """[(mech, weight)] for listed game mechs that trigger the rule."""
        me = obs["self"]["pos"]
        out = []
        for other in obs.get("mechs") or ():
            if other.get("kind") != "mech":
                continue
            distance = math.dist(other["pos"][:2], me[:2])
            if distance > self.RANGE_M:
                continue
            key = other.get("id")
            attacker = key in engagement.attackers
            aiming = key in engagement.threats
            vx, vy = (other.get("vel") or [0, 0, 0])[:2]
            speed = math.hypot(vx, vy)
            closing = False
            if speed > self.CLOSING_MPS and distance > 1e-6:
                bx, by = me[0] - other["pos"][0], me[1] - other["pos"][1]
                cos = (vx * bx + vy * by) / (speed * distance)
                closing = cos >= math.cos(math.radians(self.CLOSING_DEG))
            if not (attacker or aiming or closing):
                continue
            weight = (self.RANGE_M + 10.0 - distance) * (2.0 if attacker or aiming else 1.0)
            out.append((other, weight))
        return out

    def leg_ok(self, pos, end, zone):
        if not self.nav.clear_segment(pos, end):
            return False
        if math.dist(end, zone["center"]) + self.ZONE_MARGIN_M > zone["radius"]:
            return False
        centre, radius = zone["next_center"], zone["next_radius"]
        if math.dist(pos, centre) + self.ZONE_MARGIN_M <= radius:
            return math.dist(end, centre) + self.ZONE_MARGIN_M <= radius
        return math.dist(end, centre) <= math.dist(pos, centre) + 0.5

    def steer(self, obs, action, engagement, heading, mode, urgent, recovering):
        """Override move (and boost) with a retreat leg; returns True while it does."""
        self.active = False
        found = self.threats(obs, engagement)
        if not found:
            return False
        if urgent:
            self.count("skipped: urgent zone return")
            return False
        if mode == "drop" or recovering:
            self.count("skipped: drop capture or obstacle recovery")
            return False
        me, zone = obs["self"], obs["zone"]
        pos = me["pos"][:2]
        total = sum(w for _, w in found)
        cx = sum(o["pos"][0] * w for o, w in found) / total
        cy = sum(o["pos"][1] * w for o, w in found) / total
        ax, ay = pos[0] - cx, pos[1] - cy
        norm = math.hypot(ax, ay)
        if norm < 1e-6:
            self.count("skipped: on top of the threat")
            return False
        ax, ay = ax / norm, ay / norm
        hx, hy = heading
        dx, dy = ax + self.GOAL_WEIGHT * hx, ay + self.GOAL_WEIGHT * hy
        norm = math.hypot(dx, dy)
        if norm < 1e-6:
            dx, dy = ax, ay
        else:
            dx, dy = dx / norm, dy / norm
        base = math.atan2(dy, dx)
        for turn in self.TURNS_DEG:
            a = base + math.radians(turn)
            side = (math.cos(a), math.sin(a))
            end = (pos[0] + side[0] * self.LEG_M, pos[1] + side[1] * self.LEG_M)
            if self.leg_ok(pos, end, zone):
                action["move"] = [side[0], side[1]]
                action["boost"] = me.get("energy", 0) > self.BOOST_ENERGY
                action["jump"] = False
                self.active = True
                self.decisions += 1
                self.count("kited" if turn == 0 else "kited sideways")
                return True
        self.count("skipped: no clear leg inside the zone")
        return False
