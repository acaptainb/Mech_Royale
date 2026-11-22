"""Early-loot objective: one short, stable detour to a ground weapon while slot 1 is empty.

squad-fire (practice mode, `choose(..., squad=True)`): the detour also runs to swap slot 1 for a
better weapon (laser over lightning, never a mortar), reaches lasers within 240 m and other
weapons within 150 m, and ranks them by value per metre. `swap_take` is the matching take rule.

Practice mode also keeps the pursuit going through a fight nearby: damage and mechs near us or
the pickup do not end it, and pickups are remembered where they were last seen, forgotten only
when one should be in view and is not (close by, or a little farther inside the vision wedge,
with a clear line from our eyes)."""
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
    # squad-fire: weapon wishes in practice mode. A kind is wanted when it outranks slot 1;
    # a mortar is never wanted, and a held kind never is.
    RANK = {"laser": 4, "lightning": 3, "mortar": 1}
    WANTED = ("laser", "lightning")
    SQUAD_LASER_M = 240.0   # how far a laser is sought
    SQUAD_OTHER_M = 150.0   # how far any other wanted weapon is sought
    TAKE_FLAT_M = 3.7       # take reach: pickup radius 4 less a margin
    TAKE_HEIGHT_M = 3.6
    # Practice mode: a remembered pickup is forgotten when it should be in view and is not.
    GONE_S = 0.35           # not listed for longer than this
    GONE_NEAR_M = 40.0      # within this, all round (inside the near vision range)
    GONE_VIEW_M = 80.0      # within this, inside the vision wedge less GONE_VIEW_MARGIN_RAD
    GONE_VIEW_MARGIN_RAD = math.radians(8)
    GONE_LIFT_M = 1.5       # the line from our eyes ends this far above the pickup

    def __init__(self, hello, cover=None):
        config = hello["config"]
        self.reach = config["loot"]["pickup_radius"]
        self.near_range = config.get("vision", {}).get("near_range", 45)
        self.npc_range = config.get("npc", {}).get("aggro_range", 45)
        self.fov = math.radians(config.get("vision", {}).get("fov_deg", 120))
        self.cover = cover      # line tests for the pickup memory; without it, the walkable grid
        self.memory = {}        # practice mode: pickup id -> {"id", "kind", "pos", "seen"}
        # A second planner keeps the zone route intact while a pickup route is searched.
        self.nav = Navigator()
        self.heights = array("h")
        self.heights.frombytes((ROOT / "heights.i16").read_bytes())
        if sys.byteorder == "big":
            self.heights.byteswap()
        self.target = None      # id, pos, at, since, seen, initial, best, closest, best_at
        self.squad = False      # squad-fire: practice mode on this decision
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

    def slot1_rank(self, me):
        held = me["weapons"][1]
        return self.RANK.get(held.get("kind"), 0) if held else 0

    def wanted(self, me, kind):
        """squad-fire: this kind outranks slot 1 and is not held already."""
        held = {weapon["kind"] for weapon in me["weapons"] if weapon}
        return kind in self.WANTED and kind not in held and self.RANK[kind] > self.slot1_rank(me)

    def seeking(self, me):
        """A detour may run: slot 1 is empty, or (practice mode) holds less than a laser."""
        if me["weapons"][1] is None:
            return True
        return self.squad and self.slot1_rank(me) < self.RANK["laser"]

    def reach_for(self, kind):
        """squad-fire: walking limit for a pickup of this kind."""
        return self.SQUAD_LASER_M if kind == "laser" else self.SQUAD_OTHER_M

    @staticmethod
    def value(me, kind):
        """squad-fire: worth of a pickup; a laser is worth at least 150."""
        worth = 130.0 if me["weapons"][1] is None else 60.0
        return max(worth, 150.0) if kind == "laser" else worth

    def remember(self, obs, prune):
        """Note every listed pickup (read only in practice mode) and, with `prune`, forget
        remembered ones that should be in view but are not."""
        now, me = obs["t"], obs["self"]
        for pickup in obs["pickups"]:
            self.memory[pickup["id"]] = dict(id=pickup["id"], kind=pickup["kind"], pos=list(pickup["pos"]), seen=now)
        if not prune:
            return
        pos = me["pos"]
        eye = [pos[0], pos[1], pos[2] + (me.get("stats") or {}).get("eye_height", 8)]
        facing = (me.get("aim") or [None])[0]
        for key in [k for k, item in self.memory.items() if self.gone(item, eye, facing, now)]:
            del self.memory[key]

    def gone(self, item, eye, facing, now):
        """Not listed although it should be in view: close by (all-round sensors), or a little
        farther inside the vision wedge, with nothing solid on the line from our eyes."""
        if now - item["seen"] <= self.GONE_S:
            return False
        at = item["pos"]
        d = math.hypot(at[0] - eye[0], at[1] - eye[1])
        if d > self.GONE_VIEW_M:
            return False
        if d > self.GONE_NEAR_M:
            if facing is None:
                return False
            off = abs((math.atan2(at[1] - eye[1], at[0] - eye[0]) - facing + math.pi) % math.tau - math.pi)
            if off > self.fov / 2 - self.GONE_VIEW_MARGIN_RAD:
                return False
        if self.cover is None:
            return self.nav.clear_segment(eye[:2], at[:2])
        return self.cover.clear(eye, [at[0], at[1], at[2] + self.GONE_LIFT_M], skip_start=0.5, skip_end=0.5)

    def squad_candidates(self, obs):
        """Wanted ground pickups within their seek range, best value per metre first:
        (distance, id, pickup, at). Remembered pickups count, seen or not."""
        me = obs["self"]
        pos = me["pos"][:2]
        found = []
        for pickup in self.memory.values():
            if not self.wanted(me, pickup["kind"]):
                continue
            distance = math.dist(pos, pickup["pos"][:2])
            if distance > self.reach_for(pickup["kind"]):
                continue
            at = self.stand_point(pickup)
            if at is not None:
                utility = self.value(me, pickup["kind"]) / (distance + 18.0)
                found.append((-utility, distance, pickup["id"], pickup, at))
        return [item[1:] for item in sorted(found, key=lambda item: item[:3])]

    def swap_take(self, me, pickups):
        """squad-fire take rule: (pickup id, slot to drop or None) for the best wanted visible
        pickup within reach, or None. Nothing is taken while the slot-1 laser is charging."""
        held = me["weapons"][1]
        if held and held.get("kind") == "laser" and (held.get("charge") or 0) > 0:
            return None
        pos = me["pos"]
        best = None
        for pickup in pickups:
            kind = pickup["kind"]
            if kind == "gun":
                if me["weapons"][0] is not None:
                    continue
                rank = 5
            elif self.wanted(me, kind):
                rank = self.RANK[kind]
            else:
                continue
            flat = math.dist(pos[:2], pickup["pos"][:2])
            if flat > self.TAKE_FLAT_M or abs(pickup["pos"][2] - pos[2]) > self.TAKE_HEIGHT_M:
                continue
            if best is None or (-rank, flat, pickup["id"]) < best[0]:
                best = ((-rank, flat, pickup["id"]), pickup["id"])
        if best is None:
            return None
        full = all(weapon is not None for weapon in me["weapons"][:2])
        return best[1], (1 if full else None)

    def candidates(self, obs):
        """Compatible ground pickups in range while slot 1 is empty: (distance, id, pickup, at)."""
        me = obs["self"]
        if self.squad:
            return self.squad_candidates(obs)
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
        """Opponents close to us or the pickup. Distant drones and mechs are not pressure.
        Practice mode has none: the fight rules decide when a fight outranks the pickup."""
        if self.squad:
            return False
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
        if obs["t"] < objectives.relocate_until and not self.squad:
            # Practice mode keeps the pursuit through damage (a drone's shot, a far hunter's).
            return "under_fire"
        if abs(me["pos"][2] - self.ground(me["pos"])) > 4:
            return "off_ground"
        return None

    def drop(self, until, reason):
        self.skip[self.target["id"]] = until
        self.abandoned[reason] = self.abandoned.get(reason, 0) + 1
        self.target = None

    # --- per-decision entry point -------------------------------------------------------

    def choose(self, obs, objectives, zone_goal, squad=False):
        """Return the point to walk to for a pickup, or None to keep the zone objective.
        squad=True applies the practice-mode wishes and seek ranges (squad-fire)."""
        me, now = obs["self"], obs["t"]
        pos = me["pos"][:2]
        self.squad = squad
        self.remember(obs, prune=squad)
        if not self.seeking(me):
            if self.target is not None:
                self.acquired += 1
            self.target = self.pending = None
            return None
        if squad and self.target is not None and not self.wanted(me, self.target.get("kind")):
            # Slot 1 changed under a pursuit (we took this kind, or something better).
            self.acquired += 1
            self.target = self.pending = None
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
        if self.squad:
            # Practice mode: followed while remembered, however long it has been out of view.
            if target["id"] not in self.memory:
                return self.drop(FOREVER, "disappeared")
            target["seen"] = self.memory[target["id"]]["seen"]
        elif any(pickup["id"] == target["id"] for pickup in obs["pickups"]):
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
        options.sort(key=lambda item: (item[1] != searching, item[0], item[1]))
        for _, key, pickup, at in options:
            if self.pressure(obs, pos, at):
                continue
            cost = self.route_cost(pos, at)
            if cost is None:
                # The planner expands a bounded number of cells per decision.
                if searching != key:
                    self.pending = [key, 0]
                self.pending[1] += 1
                # squad-fire: a far pickup needs more planner decisions (1000 cells each).
                ticks = (max(self.ROUTE_TICKS, math.ceil(self.reach_for(pickup["kind"]) / 20.0))
                         if self.squad else self.ROUTE_TICKS)
                if self.pending[1] >= ticks:
                    self.pending = None
                    self.skip[key] = now + 10
                return
            if searching == key:
                self.pending = searching = None
            extra = cost + math.dist(at, zone_goal) - math.dist(pos, zone_goal)
            route_limit = self.reach_for(pickup["kind"]) if self.squad else self.MAX_ROUTE
            # squad-fire: no cap on the added trip; the zone-timing check below decides.
            extra_limit = FOREVER if self.squad else self.MAX_EXTRA
            if cost > route_limit or extra > extra_limit:
                self.skip[key] = FOREVER if cost == FOREVER else now + 10
                continue
            if not self.zone_allows(obs, at, cost):
                self.skip[key] = now + 20
                continue
            self.pending = None
            self.target = dict(id=key, pos=pickup["pos"], at=at, since=now, seen=now,
                               initial=cost, best=cost, closest=math.dist(pos, at), best_at=now,
                               kind=pickup["kind"])
            if key not in self.pursued:
                self.pursued.append(key)
            return
        self.pending = None
