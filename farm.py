"""farm-power: walk to power cubes up to RANGE_M away in the first FARM_S of the match."""
import math

from navigation import Navigator


class CubeFarm:
    """In the first FARM_S of the match, during ordinary zone movement inside the zone, with no
    game mech listed and no game mech (ids 0-99) hitting us in the engagement's attack memory,
    walk to the nearest power cube within RANGE_M (straight-line distance) that sits within
    HEIGHT_M of our height, is inside the next circle with EDGE_M to spare, has a walkable route
    (straight when the line is clear, else its own planner's path) and leaves the same zone
    timing margin as the pickup detour (loot.py ZONE_MARGIN_S). Each cube is +4% max HP and
    damage, and the cube count drives the upgrade offers (1, 3, 6, 10 cubes).
    Returns the waypoint to steer to, or None to leave the existing cube and zone rules alone."""
    FARM_S = 180.0
    RANGE_M = 120.0
    HEIGHT_M = 4.0
    EDGE_M = 4.0
    ZONE_MARGIN_S = 8.0
    SKIP_S = 10.0          # a cube with no route is ignored this long

    def __init__(self, hello):
        self.nav = Navigator()  # its own planner, so the zone and pickup routes stay intact
        self.skip = {}          # cube id -> match time until which it is ignored
        self.walks = 0          # decisions this rule set the waypoint, for local reports
        self.targets = set()    # distinct cube ids steered to

    @staticmethod
    def game_mech(key):
        return isinstance(key, int) and not isinstance(key, bool) and 0 <= key < 100

    def zone_allows(self, obs, at, cost):
        zone, now = obs["zone"], obs["t"]
        speed = max(1, obs["self"]["stats"]["walk_speed"])
        if zone["next_radius"] < 8:
            return False
        gap = math.dist(at, zone["next_center"]) - zone["next_radius"]
        if gap + 3 <= 0:
            return now + cost / speed + 5 + self.ZONE_MARGIN_S < zone["shrink_end"]
        return now + cost / speed + 1 + max(0, gap) / speed + 5 + self.ZONE_MARGIN_S < zone["shrink_start"]

    def route(self, pos, at):
        """(waypoint, cost): cost None while the search runs, inf when there is no path."""
        nav = self.nav
        if nav.clear_segment(pos, at):
            return at, math.dist(pos[:2], at)
        waypoint = nav.waypoint(pos, at)
        node = nav.snap(pos)
        if node not in nav.toward:
            return None, (math.inf if not nav.queue else None)
        steps = 0
        while nav.toward[node] != node and steps < 400:
            node = nav.toward[node]
            steps += 1
        return waypoint, steps * nav.step + math.dist(pos[:2], nav.point(nav.snap(pos)))

    def choose(self, obs, attackers):
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        if now >= self.FARM_S or not me.get("in_zone"):
            return None
        if any(other.get("kind") == "mech" for other in obs.get("mechs") or ()):
            return None
        if any(self.game_mech(key) for key in attackers):
            return None
        pos = me["pos"]
        options = []
        for cube in obs.get("cubes") or ():
            at = cube["pos"]
            distance = math.dist(at[:2], pos[:2])
            if (distance > self.RANGE_M or abs(at[2] - pos[2]) > self.HEIGHT_M
                    or self.skip.get(cube["id"], -1) > now
                    or math.dist(at[:2], zone["next_center"]) + self.EDGE_M >= zone["next_radius"]):
                continue
            options.append((distance, cube["id"], at))
        for distance, key, at in sorted(options)[:1]:
            waypoint, cost = self.route(pos, at[:2])
            if cost is None:
                return None              # the search continues next decision
            if cost == math.inf or not self.zone_allows(obs, at[:2], cost):
                self.skip[key] = now + self.SKIP_S
                return None
            self.walks += 1
            self.targets.add(key)
            return list(waypoint[:2])
        return None
