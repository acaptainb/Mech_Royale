"""break-sight: when we are losing a fight, break line of sight and regenerate."""
import math


class BreakSight:
    """Trigger: a game mech damaged us within TRIGGER_S, and either our HP is below HP_FRAC
    of max or at least MIN_MECHS game mechs are listed.

    An episode then runs (in the zone, with the return not urgent) until HP is back to
    max(RESUME_FRAC of max, HP when the episode started), the zone return becomes urgent, or
    MAX_HIDE_S pass. Regeneration only starts after 5 s without dealing or taking damage, so
    standing hidden is what brings HP back.

    During an episode the mech moves to the nearest point (SEARCH_RADII, DIRECTIONS) that is
    reachable on the ground grid, inside the current and next circle with ZONE_MARGIN_M to
    spare, and hidden by solid matter (cover.py) from the eye of every listed game mech and
    of each recent attacker that is no longer listed (its last known position, or a point
    GUESS_M along the damage bearing when it was never seen). It boosts there while energy
    stays above ENERGY_RESERVE. Once hidden it stands still. If the spot stops being hidden
    it searches again. One decision examines at most RADII_PER_DECISION rings (a fixed count,
    so the answer time stays bounded and the result deterministic); a longer search resumes on
    the next decision. After a search that finds nothing the next waits RETRY_S, and normal
    movement stands meanwhile. Aim and fire are not touched.
    """
    TRIGGER_S = 1.5
    HP_FRAC = 0.55
    MIN_MECHS = 2
    RESUME_FRAC = 0.85
    MAX_HIDE_S = 20.0
    SEARCH_RADII = (3.0, 5.0, 7.0, 10.0, 14.0, 18.0, 24.0)
    DIRECTIONS = 16
    RADII_PER_DECISION = 2
    RETRY_S = 0.3
    ZONE_MARGIN_M = 3.0
    ENERGY_RESERVE = 20.0
    ATTACKER_MEMORY_S = 10.0
    GUESS_M = 100.0
    EYE_M = 8.0
    BODY_M = 4.5

    def __init__(self, hello, nav, cover):
        self.nav = nav
        self.cover = cover
        self.last_pos = {}       # game mech id -> last position we saw it at
        self.attacked = {}       # game mech id -> (time it last damaged us, bearing)
        self.last_damage = -1e9  # time a game mech last damaged us
        self.started = None      # start time of the current episode, None when idle
        self.target_hp = 0.0
        self.point = None        # the hiding point being walked to
        self.reached = False
        self.retry = -1.0
        self.resume = 0          # index into SEARCH_RADII where an unfinished search resumes
        self.active = False      # this decision's move came from this rule
        self.counts = {}         # outcome -> count, for local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    @staticmethod
    def game_mech(key):
        return isinstance(key, int) and not isinstance(key, bool) and 0 <= key < 100

    def ground(self, x, y):
        c = self.cover
        i = min(c.nx - 1, max(0, int((x - c.ox) / c.cell)))
        j = min(c.ny - 1, max(0, int((y - c.oy) / c.cell)))
        return c.ground[j * c.nx + i] / 100

    def observe(self, obs):
        now = obs["t"]
        for other in obs.get("mechs") or ():
            if other.get("kind") == "mech":
                self.last_pos[other.get("id")] = tuple(other["pos"])
        for event in obs.get("events") or ():
            if event.get("type") == "damaged" and self.game_mech(event.get("by")):
                self.last_damage = now
                bearing = None if event.get("weapon") == "mortar" else event.get("bearing")
                self.attacked[event["by"]] = (now, bearing)
            elif event.get("type") == "kill":
                self.attacked.pop(event.get("target"), None)
                self.last_pos.pop(event.get("target"), None)
        self.attacked = {key: seen for key, seen in self.attacked.items()
                         if now - seen[0] <= self.ATTACKER_MEMORY_S}

    def observers(self, obs):
        """Eye positions we must be hidden from."""
        me = obs["self"]["pos"]
        listed = {}
        for other in obs.get("mechs") or ():
            if other.get("kind") == "mech":
                listed[other.get("id")] = other["pos"]
        eyes = [(p[0], p[1], p[2] + self.EYE_M) for p in listed.values()]
        for key, (_, bearing) in self.attacked.items():
            if key in listed:
                continue
            if key in self.last_pos:
                p = self.last_pos[key]
                eyes.append((p[0], p[1], p[2] + self.EYE_M))
            elif bearing is not None:
                x, y = me[0] + self.GUESS_M * math.cos(bearing), me[1] + self.GUESS_M * math.sin(bearing)
                eyes.append((x, y, self.ground(x, y) + self.EYE_M))
        return eyes

    def hidden(self, point, eyes):
        body = (point[0], point[1], self.ground(point[0], point[1]) + self.BODY_M)
        return all(not self.cover.clear(eye, body, skip_start=3.0, skip_end=2.5) for eye in eyes)

    def usable(self, obs, point):
        zone = obs["zone"]
        if math.dist(point, zone["center"]) + self.ZONE_MARGIN_M > zone["radius"]:
            return False
        if math.dist(point, zone["next_center"]) + self.ZONE_MARGIN_M > zone["next_radius"]:
            return False
        return self.nav.clear_segment(obs["self"]["pos"], point)

    def search(self, obs, eyes):
        """Returns a point, None when nothing was found, or False to continue next decision."""
        pos = obs["self"]["pos"]
        for index in range(self.resume, len(self.SEARCH_RADII)):
            if index - self.resume >= self.RADII_PER_DECISION:
                self.resume = index
                return False
            radius = self.SEARCH_RADII[index]
            options = []
            for k in range(self.DIRECTIONS):
                a = k * math.tau / self.DIRECTIONS
                point = (pos[0] + radius * math.cos(a), pos[1] + radius * math.sin(a))
                if self.usable(obs, point) and self.hidden(point, eyes):
                    options.append(point)
            if options:
                self.resume = 0
                # among equally near points, prefer the one farthest from the nearest observer
                return max(options, key=lambda p: min(math.dist(p, e[:2]) for e in eyes))
        self.resume = 0
        return None

    def end(self, outcome):
        self.count(outcome)
        self.started, self.point, self.reached, self.resume = None, None, False, 0

    def steer(self, obs, action, urgent):
        """Call after the move and boost are set, before the dodge. Returns True while it steers."""
        self.active = False
        self.observe(obs)
        now, me = obs["t"], obs["self"]
        max_hp = me.get("max_hp") or 1400
        mechs = sum(1 for other in obs.get("mechs") or () if other.get("kind") == "mech")
        triggered = (now - self.last_damage <= self.TRIGGER_S + 1e-9
                     and (me["hp"] < self.HP_FRAC * max_hp or mechs >= self.MIN_MECHS))
        if self.started is None:
            if not triggered:
                return False
            self.started = now
            self.target_hp = min(max_hp, max(self.RESUME_FRAC * max_hp, me["hp"]))
            self.point, self.reached, self.resume = None, False, 0
            self.count("episodes")
        if me["hp"] >= self.target_hp - 1e-6 and not triggered:
            self.end("ended: healed")
            return False
        if urgent or not me.get("in_zone"):
            self.end("ended: zone return urgent")
            return False
        if now - self.started > self.MAX_HIDE_S:
            self.end("ended: 20 s limit")
            return False
        eyes = self.observers(obs)
        pos = me["pos"]
        if self.hidden(pos[:2], eyes):
            target = (pos[0], pos[1])
            self.point = None
        else:
            if self.point is None or not self.hidden(self.point, eyes) or not self.usable(obs, self.point):
                self.point = None
                if now < self.retry - 1e-9:
                    return False
                found = self.search(obs, eyes)
                if found is False:
                    self.count("search continues next decision")
                    return False
                if found is None:
                    self.retry = now + self.RETRY_S
                    self.count("no cover found")
                    return False
                self.point, self.reached = found, False
                self.count("cover moves started")
            target = self.point
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        length = math.hypot(dx, dy)
        if length < 1.0:
            action["move"], action["boost"] = [0, 0], False
            if not self.reached:
                self.reached = True
                self.count("hidden")
        else:
            action["move"] = [dx / length, dy / length]
            action["boost"] = me.get("energy", 0) > self.ENERGY_RESERVE
        action["jump"] = False
        self.active = True
        self.count("decisions steered")
        return True
