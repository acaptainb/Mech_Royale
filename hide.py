"""hide-spot: wait at a sheltered node near the zone centre instead of in the open."""
import math
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class HideSpot:
    """While the plain zone objective is active, walk to and hold the least exposed walkable
    node near the next circle's centre instead of the centre itself.

    Exposure comes from exposure.u8 (tools/build_exposure.py): for each navigation node, the
    share of 24 bearings x 40/100/180 m observer positions whose eye has a clear line to a mech
    standing there on the cover map. The spot is searched once per next circle, and only while
    no game mech is listed and none has hit us for QUIET_S. Candidates lie within SEARCH_M of
    the next centre and within WALK_LIMIT_M of it by the ground grid, ZONE_MARGIN_M inside the
    next circle. The best one (exposure plus a small distance tie-break) is used only when it
    is at least MIN_GAIN less exposed than the centre; otherwise normal movement stands. Once
    chosen, it stays the goal for that circle, including while an opponent is listed, because
    walking out of shelter toward the open centre in a fight is the opposite of the idea.
    Return, supply-drop and relocation modes keep priority (they are not "zone" mode).
    """
    SEARCH_M = 60.0         # candidates within this straight distance of the next centre
    WALK_LIMIT_M = 100.0    # ... and within this walking distance of it on the ground grid
    ZONE_MARGIN_M = 8.0     # ... and this far inside the next circle
    MIN_GAIN = 0.10         # the spot must be this much less exposed than the centre
    DISTANCE_WEIGHT = 0.05  # added per SEARCH_M of distance from the centre when ranking
    HOLD_M = 1.5            # within this of the spot the mech stands still
    QUIET_S = 5.0           # no game mech hit us for this long before a spot is searched
    ZONE_MARGIN_S = 8.0     # spare time before the shrink, as the pickup detour uses
    MIN_RADIUS_M = 8.0      # objectives.py switches to the zone return below this

    def __init__(self, hello, nav):
        self.nav = nav
        self.exposure = (ROOT / "exposure.u8").read_bytes()
        assert len(self.exposure) == nav.width * nav.height
        self.key = None             # the next circle the current search belongs to
        self.spot = None            # the chosen node's point, or None for normal movement
        self.spot_exposure = None
        self.centre_exposure = None
        self.last_hit = -math.inf   # last time a game mech damaged us
        # Counters for local reports; they never influence a decision.
        self.searches = 0
        self.decisions = 0          # decisions whose goal was the spot
        self.holds = 0              # decisions spent standing on the spot

    def exposure_at(self, point):
        k = self.nav.snap(point)
        return self.exposure[k] / 255

    def safe(self, zone, at):
        return (math.dist(at, zone["next_center"]) + self.ZONE_MARGIN_M <= zone["next_radius"]
                and math.dist(at, zone["center"]) + 3 <= zone["radius"])

    def search(self, zone):
        """Least exposed reachable node near the next centre, or None when none clearly beats it."""
        nav, centre = self.nav, zone["next_center"]
        start = nav.snap(centre)
        limit = int(self.WALK_LIMIT_M / nav.step)
        steps, queue = {start: 0}, deque([start])
        while queue:
            i = queue.popleft()
            if steps[i] >= limit:
                continue
            for j in (i - 1, i + 1, i - nav.width, i + nav.width):
                if 0 <= j < len(nav.free) and nav.free[j] and j not in steps:
                    steps[j] = steps[i] + 1
                    queue.append(j)
        best = None
        for k in steps:
            at = nav.point(k)
            distance = math.dist(at, centre)
            if distance > self.SEARCH_M or not self.safe(zone, at):
                continue
            score = self.exposure[k] / 255 + self.DISTANCE_WEIGHT * distance / self.SEARCH_M
            if best is None or score < best[0]:
                best = (score, k)
        self.searches += 1
        self.centre_exposure = self.exposure[start] / 255
        self.spot = self.spot_exposure = None
        if best is not None and self.exposure[best[1]] / 255 <= self.centre_exposure - self.MIN_GAIN:
            self.spot = list(nav.point(best[1]))
            self.spot_exposure = self.exposure[best[1]] / 255

    def in_time(self, obs):
        """Outside the next circle, walking to the spot must leave the pickup detour's margin."""
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        pos = me["pos"][:2]
        if math.dist(pos, zone["next_center"]) - zone["next_radius"] <= -3:
            return True
        speed = max(1, me["stats"]["walk_speed"])
        route = 1.3 * math.dist(pos, self.spot) + 10
        return now + route / speed + 5 + self.ZONE_MARGIN_S < zone["shrink_start"]

    def choose(self, obs, mode):
        """The point to walk to instead of the zone objective's centre, or None."""
        zone, now = obs["zone"], obs["t"]
        for event in obs.get("events") or ():
            by = event.get("by")
            if event.get("type") == "damaged" and isinstance(by, int) and 0 <= by < 100:
                self.last_hit = now
        if mode != "zone" or zone["next_radius"] < self.MIN_RADIUS_M or not obs["self"]["in_zone"]:
            return None
        key = (round(zone["next_center"][0], 1), round(zone["next_center"][1], 1),
               round(zone["next_radius"], 1))
        if key != self.key:
            self.spot = None
            quiet = (not any(other.get("kind") == "mech" for other in obs.get("mechs") or ())
                     and now - self.last_hit >= self.QUIET_S)
            if not quiet:
                return None
            self.search(zone)
            self.key = key
        if self.spot is None or not self.safe(zone, self.spot) or not self.in_time(obs):
            return None
        self.decisions += 1
        return self.spot
