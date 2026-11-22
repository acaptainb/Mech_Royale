"""duel-strafe: walk sideways to the selected opponent during a clear one-on-one encounter."""
import math
import random


class DuelStrafe:
    """Eligible only while all of these hold:
    - ordinary zone movement (the plain zone objective: no return, supply drop, relocation
      after damage or pickup detour), inside the zone, the return not urgent, not in the
      obstacle recovery;
    - v6's engagement decision has selected a game mech, it is the only game mech listed,
      the line of fire to it is clear (v6's cover check) and it is within our weapon reach.

    The mech then walks, at normal walk speed, perpendicular to the bearing toward that
    opponent. One side is kept for an interval drawn from MIN_S to MAX_S seconds of match
    time (a generator seeded with the slot seed, so it is deterministic and varies), then the
    other side. If the current side would cross a wall on the ground grid (the navigation
    clearance check) or leave the safe circle within LOOKAHEAD_M, the other side is tried; if
    neither is safe, the normal waypoint stands.
    """
    MIN_S, MAX_S = 0.75, 1.15
    LOOKAHEAD_M = 4.0
    ZONE_MARGIN_M = 3.0

    def __init__(self, hello, nav):
        self.nav = nav
        self.rng = random.Random(hello.get("seed", 0))
        self.side = self.rng.choice((-1, 1))
        self.until = -1.0
        self.last = -1e9        # match time of the last decision this rule steered
        self.active = False
        self.counts = {}        # outcome -> count, for local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def blocker(self, obs, engage, mode, urgent, recovering, reach):
        me = obs["self"]
        if mode != "zone":
            return "not ordinary zone movement"
        if not me.get("in_zone"):
            return "outside the zone"
        if urgent:
            return "urgent zone return"
        if recovering:
            return "obstacle recovery"
        target = engage.get("target")
        if target is None:
            return "no opponent selected"
        mechs = [other for other in obs.get("mechs") or () if other.get("kind") == "mech"]
        chosen = next((other for other in mechs if other.get("id") == target), None)
        if chosen is None:
            return "selected opponent is not a mech"
        if len(mechs) > 1:
            return "more than one mech"
        if not engage.get("clear"):
            return "no clear shot line"
        if engage.get("distance", math.inf) > reach:
            return "beyond weapon reach"
        return None

    def safe(self, obs, end):
        me, zone = obs["self"], obs["zone"]
        pos = me["pos"]
        if not self.nav.clear_segment(pos, end):
            return False
        if math.dist(end, zone["center"]) + self.ZONE_MARGIN_M > zone["radius"]:
            return False
        inside_next = math.dist(pos[:2], zone["next_center"]) <= zone["next_radius"]
        return not inside_next or math.dist(end, zone["next_center"]) <= zone["next_radius"]

    def steer(self, obs, action, engage, mode, urgent, recovering, reach):
        """Call after the decision's move and boost are set and before the dodge.
        Returns True when this decision walks sideways."""
        self.active = False
        reason = self.blocker(obs, engage, mode, urgent, recovering, reach)
        if reason:
            self.count("skipped: " + reason)
            return False
        self.count("eligible")
        now = obs["t"]
        if now - self.last > 0.15 + 1e-9:
            self.until = -1.0  # a fresh encounter: start a new interval
        if now >= self.until - 1e-9:
            self.side = -self.side
            self.until = now + self.rng.uniform(self.MIN_S, self.MAX_S)
        me = obs["self"]
        pos = me["pos"]
        tx, ty = engage["centre"][:2]
        bearing = math.atan2(ty - pos[1], tx - pos[0])
        left = (-math.sin(bearing), math.cos(bearing))
        for sign in (self.side, -self.side):
            step = (sign * left[0], sign * left[1])
            end = (pos[0] + step[0] * self.LOOKAHEAD_M, pos[1] + step[1] * self.LOOKAHEAD_M)
            if not self.safe(obs, end):
                continue
            if sign != self.side:
                self.side = sign
                self.until = now + self.rng.uniform(self.MIN_S, self.MAX_S)
                self.count("switched side: lookahead blocked")
            before = list(action.get("move") or [0, 0])
            action["move"] = [step[0], step[1]]
            action["boost"] = False
            action["jump"] = False
            self.active = True
            self.last = now
            if any(abs(a - b) > 1e-9 for a, b in zip(before, action["move"])):
                self.count("changed movement")
            return True
        self.count("skipped: both sides unsafe")
        return False
