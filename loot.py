"""Early-loot objective: one short, stable detour to a ground weapon while slot 1 is empty."""
import math
import sys
from array import array
from pathlib import Path

from navigation import Navigator

ROOT = Path(__file__).resolve().parent
FOREVER = math.inf


class PickupDetour:
    MAX_ROUTE = 70.0        # metres of walking to the pickup
    MAX_EXTRA = 80.0        # metres the detour may add to the trip to the zone goal
    GROUND_TOLERANCE = 2.5  # pickup height above or below the terrain
    MECH_PRESSURE = 60.0    # an opponent this close to us or to the pickup cancels the detour
    ROUTE_TICKS = 3         # decisions allowed for the route search before giving up
    STALL_S = 2.5           # seconds without getting closer before the pickup is dropped
    # Spare time on top of the zone-return rule's own five seconds. Zone return has no stuck
    # recovery, so a detour must end early enough for ordinary movement to free a jammed mech.
    ZONE_MARGIN_S = 8.0
    UNSEEN_S = 5.0          # seconds a hidden pickup is trusted before it is set aside

    def __init__(self, hello):
        config = hello["config"]
        self.reach = config["loot"]["pickup_radius"]
        self.near_range = config.get("vision", {}).get("near_range", 45)
        self.npc_range = config.get("npc", {}).get("aggro_range", 45)
        # A second planner keeps the zone route intact while a pickup route is searched.
        self.nav = Navigator()
        self.heights = array("h")
        self.heights.frombytes((ROOT / "heights.i16").read_bytes())
        if sys.byteorder == "big":
            self.heights.byteswap()
        self.target = None      # id, pos, at, since, seen, initial, best, closest, best_at
        self.pending = None     # id and decision count of a route search in progress
        self.skip = {}          # pickup id -> match time until which it is ignored
        self.stand = {}         # pickup id -> stand point, or None when off the ground map
        self.strikes = {}       # pickup id -> times dropped for lack of progress
        # Counters for the local reports; they never influence a decision.
        self.pursued = []       # distinct pickup ids chosen, in order
        self.abandoned = {}     # reason -> count
        self.pursuit_ticks = 0
        self.acquired = 0

    # --- geometry -----------------------------------------------------------------------

    def ground(self, point):
        """Terrain height in metres, bilinear on the navigation grid."""
        nav = self.nav
        u = min(nav.width - 1.001, max(0.0, (point[0] - nav.ox) / nav.step))
        v = min(nav.height - 1.001, max(0.0, (point[1] - nav.oy) / nav.step))
        i, j = int(u), int(v)
        fu, fv = u - i, v - j
        k = j * nav.width + i
        h = self.heights
        low = h[k] * (1 - fu) + h[k + 1] * fu
        high = h[k + nav.width] * (1 - fu) + h[k + nav.width + 1] * fu
        return (low * (1 - fv) + high * fv) / 100

    def stand_point(self, pickup):
        """Where to walk for this pickup, or None when it is off the walkable ground."""
        key = pickup["id"]
        if key not in self.stand:
            self.stand[key] = self.locate(pickup["pos"])
        return self.stand[key]

    def locate(self, pos):
        if abs(pos[2] - self.ground(pos)) > self.GROUND_TOLERANCE:
            return None  # rooftop or bridge deck
        nav = self.nav
        cell = nav.snap(pos)
        if cell is None:
            return None
        centre = nav.point(cell)
        if abs(pos[0] - centre[0]) <= nav.step / 2 and abs(pos[1] - centre[1]) <= nav.step / 2:
            return [pos[0], pos[1]]
        # Next to a wall: stand on the nearest walkable node if the pickup is still in reach.
        return list(centre) if math.dist(pos[:2], centre) <= self.reach - 1 else None

    def route_cost(self, pos, at):
        """Walking distance to `at`: the straight line when clear, else the planner's path.
        Returns None while the search has not reached us, inf when no path exists."""
        nav = self.nav
        if nav.clear_segment(pos, at):
            return math.dist(pos[:2], at)
        nav.waypoint(pos, at)
        node = nav.snap(pos)
        if node not in nav.toward:
            return FOREVER if not nav.queue else None
        steps = 0
        while nav.toward[node] != node and steps < 400:
            node = nav.toward[node]
            steps += 1
        return steps * nav.step + math.dist(pos[:2], nav.point(nav.snap(pos)))

    # --- rules --------------------------------------------------------------------------

    def candidates(self, obs):
        """Compatible ground pickups in range while slot 1 is empty: (distance, id, pickup, at)."""
        me = obs["self"]
        if me["weapons"][1] is not None:
            return []
        pos = me["pos"][:2]
        held = {weapon["kind"] for weapon in me["weapons"] if weapon}
        found = []
        for pickup in obs["pickups"]:
            distance = math.dist(pos, pickup["pos"][:2])
            if pickup["kind"] in held or distance > self.MAX_ROUTE:
                continue
            at = self.stand_point(pickup)
            if at is not None:
                found.append((distance, pickup["id"], pickup, at))
        return sorted(found, key=lambda item: item[:2])

    def zone_allows(self, obs, at, cost):
        """True when walking `cost` metres to `at` still leaves time to be inside the zone."""
        zone, now = obs["zone"], obs["t"]
        speed = max(1, obs["self"]["stats"]["walk_speed"])
        if zone["next_radius"] < 8:
            return False
        if math.dist(at, zone["center"]) + 3 > zone["radius"]:
            return False
        gap = math.dist(at, zone["next_center"]) - zone["next_radius"]
        if gap + 3 <= 0:
            return True
        arrive = now + cost / speed + 1
        return arrive + max(0, gap) / speed + 5 + self.ZONE_MARGIN_S < zone["shrink_start"]

    def pressure(self, obs, pos, at=None):
        """Opponents close to us or the pickup. Distant drones and mechs are not pressure."""
        for other in obs["mechs"]:
            where = other["pos"][:2]
            if other["kind"] == "mech":
                if math.dist(where, pos) < self.MECH_PRESSURE:
                    return True
                if at is not None and math.dist(where, at) < self.MECH_PRESSURE:
                    return True
            elif at is not None and math.dist(where, at) < self.npc_range + 5:
                return True
        return False

    def blocker(self, obs, objectives):
        """Why no pickup may be pursued right now, or None."""
        me = obs["self"]
        if objectives.mode != "zone" or not me["in_zone"]:
            return {"drop": "supply_drop", "relocate": "under_fire"}.get(objectives.mode, "zone_return")
        if obs["t"] < objectives.relocate_until:
            return "under_fire"
        if abs(me["pos"][2] - self.ground(me["pos"])) > 4:
            return "off_ground"
        return None

    def drop(self, until, reason):
        self.skip[self.target["id"]] = until
        self.abandoned[reason] = self.abandoned.get(reason, 0) + 1
        self.target = None

    # --- per-decision entry point -------------------------------------------------------

    def choose(self, obs, objectives, zone_goal):
        """Return the point to walk to for a pickup, or None to keep the zone objective."""
        me, now = obs["self"], obs["t"]
        pos = me["pos"][:2]
        if me["weapons"][1] is not None:
            if self.target is not None:
                self.acquired += 1
            self.target = self.pending = None
            return None
        blocked = self.blocker(obs, objectives)
        if blocked:
            self.pending = None
            if self.target is not None:
                self.drop(now + 5, blocked)
            return None
        if self.target is not None:
            self.follow(obs, pos)
        if self.target is None:
            self.search(obs, pos, zone_goal)
        if self.target is None:
            return None
        self.pursuit_ticks += 1
        return self.target["at"]

    def follow(self, obs, pos):
        target, now = self.target, obs["t"]
        at = target["at"]
        for event in obs.get("events") or ():
            if (event.get("type") == "take_failed" and event.get("id") == target["id"]
                    and event.get("reason") != "range"):
                return self.drop(FOREVER, "take_failed_" + str(event.get("reason")))
        if any(pickup["id"] == target["id"] for pickup in obs["pickups"]):
            target["seen"] = now
        else:
            unseen = now - target["seen"]
            in_plain_view = (math.dist(pos, target["pos"][:2]) <= self.near_range - 5
                             and self.nav.clear_segment(pos, at))
            if in_plain_view and unseen >= 0.25:
                return self.drop(FOREVER, "disappeared")
            if unseen >= self.UNSEEN_S:
                return self.drop(now + 15, "out_of_sight")
        if self.pressure(obs, pos, at):
            return self.drop(now + 5, "opponent_pressure")
        cost = self.route_cost(pos, at)
        if cost == FOREVER:
            return self.drop(FOREVER, "unreachable")
        distance = math.dist(pos, at)
        remaining = distance if cost is None else cost
        if not self.zone_allows(obs, at, remaining):
            return self.drop(now + 20, "zone_deadline")
        if remaining < target["best"] - 1 or distance < target["closest"] - 1:
            target["best"] = min(target["best"], remaining)
            target["closest"] = min(target["closest"], distance)
            target["best_at"] = now
        speed = max(1, obs["self"]["stats"]["walk_speed"])
        if (now - target["best_at"] > self.STALL_S
                or now - target["since"] > 2 * target["initial"] / speed + 4):
            strikes = self.strikes[target["id"]] = self.strikes.get(target["id"], 0) + 1
            return self.drop(FOREVER if strikes >= 2 else now + 15, "no_progress")

    def search(self, obs, pos, zone_goal):
        now = obs["t"]
        if self.pressure(obs, pos):
            self.pending = None
            return
        searching = self.pending[0] if self.pending else None
        options = [item for item in self.candidates(obs) if self.skip.get(item[1], -1) <= now]
        # Keep evaluating the pickup whose route search is already running.
        # prefer-mortar: among the rest, mortars come first, then the usual distance order.
        options.sort(key=lambda item: (item[1] != searching, item[2]["kind"] != "mortar", item[0], item[1]))
        for _, key, pickup, at in options:
            if self.pressure(obs, pos, at):
                continue
            cost = self.route_cost(pos, at)
            if cost is None:
                # The planner expands a bounded number of cells per decision.
                if searching != key:
                    self.pending = [key, 0]
                self.pending[1] += 1
                if self.pending[1] >= self.ROUTE_TICKS:
                    self.pending = None
                    self.skip[key] = now + 10
                return
            if searching == key:
                self.pending = searching = None
            extra = cost + math.dist(at, zone_goal) - math.dist(pos, zone_goal)
            if cost > self.MAX_ROUTE or extra > self.MAX_EXTRA:
                self.skip[key] = FOREVER if cost == FOREVER else now + 10
                continue
            if not self.zone_allows(obs, at, cost):
                self.skip[key] = now + 20
                continue
            self.pending = None
            self.target = dict(id=key, kind=pickup["kind"], pos=pickup["pos"], at=at, since=now, seen=now,
                               initial=cost, best=cost, closest=math.dist(pos, at), best_at=now)
            if key not in self.pursued:
                self.pursued.append(key)
            return
        self.pending = None
