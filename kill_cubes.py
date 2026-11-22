"""v11: after a confirmed kill, one short detour window for nearby visible cubes."""
import math


class KillCubeDetour:
    """A `kill` event opens one window of WINDOW_S seconds. While it is open, the bot's existing
    cube choice may look REACH_M far instead of 16 m and may run while other mechs are listed,
    as long as none of them threatens us and zone timing is comfortable. The window closes when
    it runs out, when its cubes are collected or gone, or on the first threat; each kill opens at
    most one window."""
    WINDOW_S = 6.0            # how long after the kill a detour may run
    REACH_M = 40.0            # how far a cube may be during the window
    THREAT_M = 60.0           # a game mech this close cancels the detour
    MECH_IDS = range(0, 16)   # protocol id range for mechs (NPCs are 100+)

    def __init__(self, hello):
        self.until = -1.0
        self.killed = set()
        self.targeted = False
        self.owns_move = False
        self.counts = {}      # outcome -> count, for local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def threat(self, obs, engagement):
        me = obs["self"]["pos"]
        for event in obs.get("events") or ():
            if (event.get("type") == "damaged" and event.get("by") in self.MECH_IDS
                    and event.get("by") not in self.killed):
                return "damage from a mech"
        for other in obs.get("mechs") or ():
            if other.get("kind") != "mech" or other.get("id") in self.killed:
                continue
            if math.dist(other["pos"][:2], me[:2]) <= self.THREAT_M:
                return f"mech within {self.THREAT_M:.0f} m"
            if engagement.aiming_at(other, me):
                return "mech aiming at us"
        return None

    def comfortable(self, obs, mode):
        """Zone timing as the bot itself judges it: no return, inside the circle, not late."""
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        if mode == "return" or not me["in_zone"]:
            return False
        x, y = me["pos"][:2]
        gap = math.dist((x, y), zone["next_center"]) - zone["next_radius"]
        walk = max(0.0, gap) / max(1, me["stats"]["walk_speed"])
        return not (gap > 0 and now + walk + 4 > zone["shrink_start"])

    def window(self, obs, mode, engagement):
        """Called before the cube choice. Returns the reach to use, or None for the usual rule."""
        now = obs["t"]
        self.owns_move = False
        for event in obs.get("events") or ():
            if event.get("type") == "kill":
                self.killed.add(event.get("target"))
                if now >= self.until:
                    self.until, self.targeted = now + self.WINDOW_S, False
                    self.count("kills that opened a window")
        if now >= self.until - 1e-9:
            return None
        reason = self.threat(obs, engagement) or (None if self.comfortable(obs, mode) else "zone timing")
        if reason:
            self.until = -1.0
            self.count("cancelled: " + reason)
            return None
        return self.REACH_M

    def chose(self, obs, cube, reach):
        """Called after the cube choice with the cube taken (or None) during an open window."""
        if reach is None:
            return
        if cube is None:
            if self.targeted:
                self.until = -1.0
                self.count("ended: cubes collected or gone")
            return
        me = obs["self"]["pos"]
        if not self.targeted:
            self.count("detours started")
            self.targeted = True
        self.count("detour decisions")
        # The detour owns this move only where the usual rule would not have taken this cube.
        self.owns_move = bool(obs["mechs"]) or math.dist(cube["pos"][:2], me[:2]) > 16
        if self.owns_move:
            self.count("decisions steered beyond the usual cube rule")
