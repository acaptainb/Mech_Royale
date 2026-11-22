"""chase-wounded: close in on a nearly dead opponent to finish the kill."""
import math

from navigation import Navigator


class WoundedChase:
    """Steers the normal move toward v6's selected opponent while all of these hold:
    - ordinary zone movement (the plain zone objective: no return, supply drop, relocation or
      pickup detour), inside the zone, the return not urgent, not in the obstacle recovery;
    - the selected opponent is a game mech, the only game mech listed, below HP_FRAC of its
      max HP, with a clear line of fire, and farther than CLOSE_M;
    - our own HP is at least OWN_HP_FRAC of our max;
    - walking to it still leaves time to be safe before the zone shrinks (as loot.zone_allows:
      arrival plus the walk to the next circle plus ZONE_MARGIN_S before shrink_start);
    - at most MAX_S seconds per opponent.
    A separate planner (as the pickup detour does) routes toward a point up to LEG_M along the
    line to the opponent, so the zone route is left intact; a decision whose route is not ready
    keeps the ordinary move. Aim and fire stay with v6 and lead-shots; the v8 dodge keeps the
    final say."""
    HP_FRAC = 0.35
    CLOSE_M = 35.0
    MAX_S = 4.0
    OWN_HP_FRAC = 0.40
    ZONE_MARGIN_S = 8.0
    REPLAN_M = 8.0          # keep the planner's destination until the wanted point moves this far
    LEG_M = 30.0            # plan toward a point this far along the line to the opponent

    def __init__(self, hello):
        self.nav = Navigator()
        self.goal = None        # planner destination on the way to the chased opponent
        self.first = {}         # id -> time its chase first began
        self.spent = set()      # ids whose chase time ran out
        self.active = False
        self.counts = {}        # outcome -> count, for local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def blocker(self, obs, engage, mode, urgent, recovering):
        me = obs["self"]
        if mode != "zone":
            return "not ordinary zone movement"
        if not me.get("in_zone"):
            return "outside the zone"
        if urgent:
            return "urgent zone return"
        if recovering:
            return "obstacle recovery"
        if me.get("hp", 0) < self.OWN_HP_FRAC * max(1, me.get("max_hp", 1)):
            return "own HP low"
        target = engage.get("target")
        mechs = [m for m in obs.get("mechs") or () if m.get("kind") == "mech"]
        chosen = next((m for m in mechs if m.get("id") == target), None)
        if chosen is None:
            return "no mech selected"
        if len(mechs) > 1:
            return "another mech listed"
        if chosen.get("hp") is None or chosen["hp"] >= self.HP_FRAC * max(1, chosen.get("max_hp", 1)):
            return "opponent not wounded"
        if not engage.get("clear"):
            return "no clear line"
        if engage.get("distance", 0) <= self.CLOSE_M:
            return "already close"
        if target in self.spent:
            return "time limit"
        if not self.zone_allows(obs, chosen["pos"][:2]):
            return "zone timing"
        return None

    def zone_allows(self, obs, at):
        zone, now, me = obs["zone"], obs["t"], obs["self"]
        speed = max(1, (me.get("stats") or {}).get("walk_speed", 11.7))
        if math.dist(at, zone["center"]) + 3 > zone["radius"]:
            return False
        gap = math.dist(at, zone["next_center"]) - zone["next_radius"]
        if gap + 3 <= 0:
            return True
        arrive = now + math.dist(me["pos"][:2], at) / speed
        return arrive + max(0, gap) / speed + 5 + self.ZONE_MARGIN_S < zone["shrink_start"]

    def steer(self, obs, action, engage, mode, urgent, recovering):
        """Call after the decision's move and boost are set and before the dodge.
        Returns True when this decision moves toward the wounded opponent."""
        was = self.active
        self.active = False
        now = obs["t"]
        reason = self.blocker(obs, engage, mode, urgent, recovering)
        if reason is None:
            target = engage["target"]
            self.first.setdefault(target, now)
            if now - self.first[target] > self.MAX_S + 1e-9:
                self.spent.add(target)
                reason = "time limit"
        move = None
        if reason is None:
            move = self.toward(obs, engage, was)
            if move is None:
                reason = "no route yet"
        if reason is not None:
            if was:
                self.count("ended: " + reason)
            return False
        action["move"] = move
        action["jump"] = False
        self.active = True
        if not was:
            self.count("chases started")
        self.count("chase decisions")
        return True

    def toward(self, obs, engage, was):
        """Unit move along a walkable route toward a point up to LEG_M along the line to the
        opponent, or None while the planner has not reached our position yet."""
        pos = obs["self"]["pos"]
        other = next(m for m in obs["mechs"] if m.get("id") == engage["target"])
        dx, dy = other["pos"][0] - pos[0], other["pos"][1] - pos[1]
        distance = math.hypot(dx, dy)
        leg = min(self.LEG_M, distance)
        desired = [pos[0] + dx / distance * leg, pos[1] + dy / distance * leg]
        # The planner restarts its search whenever the destination changes, so keep one
        # destination until the wanted point has moved REPLAN_M away from it.
        if not was or self.goal is None or math.dist(self.goal, desired) > self.REPLAN_M:
            self.goal = desired
        waypoint = self.nav.waypoint(pos, self.goal)
        if waypoint != self.goal and self.nav.snap(pos) not in self.nav.toward:
            return None
        mx, my = waypoint[0] - pos[0], waypoint[1] - pos[1]
        length = math.hypot(mx, my)
        if length < 0.6:
            return None
        return [mx / length, my / length]
