"""squad_econ: everything else about movement, the economy part of the practice-mode design.

Practice points are only our kills before we die, so while practice mode is on (practice.py) the
bot keeps gathering power all match (cubes, crates and drones), camps still inside the inner zone
between fights, scans all round with its torso while there is nothing to face, and frees itself
when it stops moving against an obstacle.

- `ZonePlan` holds the zone goal (a point on an inner circle), the zone deadlines and the
  must/should flags that pull the bot back toward the goal.
- `Economy` remembers items and drones, judges danger, chooses a loot target by value per metre
  and says how to approach it (walk to it, stand off and shoot a drone, stand and shoot a crate).
- `Squad` puts them together for bot.py: one movement plan per decision with the fight part
  (squad_move.py) in its place, then the loot shot or the idle aim, and the stuck rule.

Outside practice mode bot.py does not call any of this, so the farm-power behaviour is unchanged.
"""
import math
import random

from navigation import Navigator

INF = math.inf


def wrap(angle):
    return (angle + math.pi) % math.tau - math.pi


def game_mech(key):
    return isinstance(key, int) and not isinstance(key, bool) and 0 <= key < 100


def unit_toward(pos, point, stop_m=0.6):
    """The parent's steering: a unit vector to `point`, or no move within `stop_m`."""
    dx, dy = point[0] - pos[0], point[1] - pos[1]
    length = math.hypot(dx, dy)
    return [dx / length, dy / length] if length > stop_m else [0.0, 0.0]


class ZonePlan:
    """Where to wait for the hunters, and when the zone forces a move.

    Goal: the next centre once the next radius is SMALL_M or less; otherwise the nearest point on
    an inner circle of radius next radius - clamp(0.3 x next radius, 3, 30) - 5 (our own position
    when we are already inside it). Deadline at a point: when the shrinking circle, minus a pad,
    first leaves it (sampled at SAMPLES even times over the shrink window). must: outside the zone,
    or the walk to the goal (x 1.45, + 4 s) ends within 3 s of our deadline; should: within 14 s.
    """
    BOT_PAD_M = 8.0
    LOOT_PAD_M = 6.0
    SAMPLES = 25
    SMALL_M = 30.0
    EDGE_FRAC, EDGE_MIN_M, EDGE_MAX_M, EDGE_EXTRA_M = 0.3, 3.0, 30.0, 5.0
    ROUTE_FACTOR = 1.45     # walking distance over straight distance, for the travel time
    ROUTE_EXTRA_S = 4.0
    MUST_S, SHOULD_S = 3.0, 14.0
    HOLD_DRIFT_M = 10.0     # a fresh goal this far from the held one replaces it (keeps routes stable)
    PASSABLE_SEARCH_M = 40.0

    def __init__(self, nav):
        self.nav = nav          # grid only: the goal is moved onto a walkable cell
        self.phase = None
        self.hold = None        # (x, y, radius) of the circle at this phase's shrink start
        self.goal = None        # held goal on the inner circle, or None while we are inside it
        self.next = (0.0, 0.0, 0.0)
        self.window = (0.0, 0.0)
        self.state = {}
        self.cache = {}         # (phase, key) -> loot deadline for items that do not move

    # --- circles and deadlines -----------------------------------------------------------

    def circle_at(self, when):
        (hx, hy, hr), (nx, ny, nr), (start, end) = self.hold, self.next, self.window
        if end <= start:
            return (nx, ny, nr) if when >= end else (hx, hy, hr)
        f = min(1.0, max(0.0, (when - start) / (end - start)))
        return hx + f * (nx - hx), hy + f * (ny - hy), hr + f * (nr - hr)

    def deadline(self, point, pad):
        nx, ny, nr = self.next
        if math.hypot(point[0] - nx, point[1] - ny) <= nr - pad:
            return INF
        start, end = self.window
        span = max(0.0, end - start)
        for k in range(self.SAMPLES):
            cx, cy, r = self.circle_at(start + span * k / (self.SAMPLES - 1))
            if math.hypot(point[0] - cx, point[1] - cy) > r - pad:
                return start + span * k / (self.SAMPLES - 1)
        return end

    def loot_deadline(self, key, point, moves):
        if moves:
            return self.deadline(point, self.LOOT_PAD_M)
        entry = (self.phase, key)
        if entry not in self.cache:
            self.cache[entry] = self.deadline(point, self.LOOT_PAD_M)
        return self.cache[entry]

    # --- goal ----------------------------------------------------------------------------

    def passable(self, point, toward):
        """`point`, or the first point on the walkable grid on the way to `toward`."""
        nav = self.nav
        dx, dy = toward[0] - point[0], toward[1] - point[1]
        length = math.hypot(dx, dy)
        steps = int(min(length, self.PASSABLE_SEARCH_M) / 2) + 1
        for k in range(steps):
            s = 2.0 * k
            q = (point[0] + dx / length * s, point[1] + dy / length * s) if length > 1e-9 else point
            i = round((q[0] - nav.ox) / nav.step)
            j = round((q[1] - nav.oy) / nav.step)
            if 0 <= i < nav.width and 0 <= j < nav.height and nav.free[j * nav.width + i]:
                return [q[0], q[1]]
            if length <= 1e-9:
                break
        return [point[0], point[1]]

    def update(self, obs):
        zone, now, me = obs["zone"], obs["t"], obs["self"]
        pos = me["pos"]
        centre = zone["next_center"]
        nr = zone["next_radius"]
        start, end = zone["shrink_start"], zone["shrink_end"]
        live = (zone["center"][0], zone["center"][1], zone["radius"])
        phase = (centre[0], centre[1], nr, start, end)
        self.next, self.window = (centre[0], centre[1], nr), (start, end)
        if phase != self.phase:
            if self.phase is not None:
                self.cache.clear()
            self.phase = phase
            self.goal = None
            self.hold = live
            if start < now < end:
                # Joined during a shrink: undo the interpolation to recover the starting circle.
                f = (now - start) / (end - start)
                if f < 0.98:
                    self.hold = tuple((live[k] - f * self.next[k]) / (1 - f) for k in range(3))
        elif now <= start:
            self.hold = live
        staying = False
        if nr <= self.SMALL_M:
            fresh = [centre[0], centre[1]]
            toward = pos[:2]
        else:
            margin = min(self.EDGE_MAX_M, max(self.EDGE_MIN_M, self.EDGE_FRAC * nr))
            inner = max(0.0, nr - margin - self.EDGE_EXTRA_M)
            d = math.hypot(pos[0] - centre[0], pos[1] - centre[1])
            if d <= inner:
                staying, fresh, toward = True, None, None
            else:
                fresh = [centre[0] + (pos[0] - centre[0]) * inner / d,
                         centre[1] + (pos[1] - centre[1]) * inner / d]
                toward = centre
        if staying:
            self.goal = None
            goal = [pos[0], pos[1]]
        else:
            if self.goal is None or math.dist(self.goal, fresh) > self.HOLD_DRIFT_M:
                self.goal = self.passable(fresh, toward)
            goal = self.goal
        distance = math.dist(goal, pos[:2])
        walk = max(1.0, (me.get("stats") or {}).get("walk_speed", 11.7))
        travel = distance * self.ROUTE_FACTOR / walk + self.ROUTE_EXTRA_S
        ours = self.deadline(pos, self.BOT_PAD_M)
        outside = not me.get("in_zone", True)
        self.state = dict(goal=goal, staying=staying, distance=distance, travel=travel,
                          deadline=ours,
                          must=outside or now + travel + self.MUST_S >= ours,
                          should=now + travel + self.SHOULD_S >= ours,
                          hurry=outside or now + travel >= ours)
        return self.state


class Economy:
    """Loot choice in practice mode: cubes, crates and drones, remembered and valued per metre.

    Utility = value / (distance + UTILITY_PAD_M), x HYSTERESIS for the current target; the highest
    wins. Every candidate must be within LOOT_MAX_M, inside the current circle with ZONE_EDGE_M to
    spare, reachable before its zone deadline, no more than ELEVATED_M above the terrain (no
    roofs or decks) and near a walkable grid cell.
    - cubes within CUBE_RANGE_M: value 75, or 25 once we hold CUBE_CAP cubes; always allowed,
      under threat too;
    - crates within CRATE_RANGE_M (0.6 x the cube value) and drones seen in the last DRONE_SEEN_S
      within DRONE_RANGE_M (value 85, under CUBE_CAP cubes): only above FARM_HP of our HP, with
      no danger (an engaged mech seen in the last 2.5 s, or any hit in the last 4 s) and no
      threat (Squad.plan asks for cubes only then).
    After following one item for GIVE_UP_S it is banned for BAN_S.
    """
    LOOT_MAX_M = 260.0
    CUBE_RANGE_M = 105.0
    CRATE_RANGE_M = 150.0
    DRONE_RANGE_M = 150.0
    CUBE_VALUE, CUBE_VALUE_CAPPED = 75.0, 25.0
    CRATE_SHARE = 0.6
    DRONE_VALUE = 85.0
    CUBE_CAP = 10
    UTILITY_PAD_M = 18.0
    HYSTERESIS = 1.35
    ZONE_EDGE_M = 6.0
    ELEVATED_M = 3.2
    REACH_M = 12.0          # a walkable grid cell must lie this close to the item
    FARM_HP = 0.5
    DRONE_SEEN_S = 12.0
    DRONE_FORGET_S = 120.0
    GIVE_UP_S = 30.0
    BAN_S = 60.0
    PAUSE_S = 3.0           # loot paused longer than this (a fight, a relocation) starts afresh
    LOOT_ROUTE_FACTOR, LOOT_EXTRA_S = 1.4, 5.0
    # danger and engagement (who counts as hunting us)
    DANGER_SEEN_S = 2.5
    DANGER_HIT_S = 4.0
    ENGAGED_HIT_S = 6.0
    CLOSE_M = 60.0
    CLOSING_MPS, CLOSING_M = 3.0, 180.0
    WEAK_FRAC, WEAK_M = 0.4, 160.0
    AIMED_RAD, AIMED_M = 0.22, 190.0
    LATE_RADIUS_M, LATE_ALIVE = 70.0, 3
    # approach
    DRONE_FIGHT_M = 75.0
    DRONE_FRESH_S = 1.0
    STANDOFF_M, STANDOFF_BAND_M = 58.0, 6.0
    CRATE_SHOOT_M = 50.0
    CRATE_BACKOFF_M = 12.0
    STRAIGHT_M = 12.0       # walk straight at an item this close (the grid keeps 4.6 m off walls)
    STEP_M = 4.0            # a step away must be clear on the grid this far
    RETARGET_M = 5.0        # a moving drone's route is replanned when it moves this far
    AIM_GATE_RAD = 0.2      # fire only once the torso is this close to the shot
    # forgetting items that should be in view but are not
    GONE_S = 0.35
    GONE_NEAR_M = 40.0
    GONE_VIEW_M = 80.0
    GONE_VIEW_MARGIN_RAD = math.radians(8)

    def __init__(self, hello, cover):
        config = hello.get("config", {})
        self.cover = cover
        self.nav = Navigator()  # its own planner, so the zone route and the pickup detour stay intact
        self.npc_height = config.get("npc", {}).get("height", 3.5)
        self.crate_height = config.get("crates", {}).get("height", 2.4)
        self.fov = math.radians(config.get("vision", {}).get("fov_deg", 120))
        self.items = {}         # ("cube" | "crate", id) -> {"pos", "seen"}
        self.drones = {}        # id -> {"pos", "seen", "listed"}
        self.engaged_at = {}    # mech id -> last time it was listed and engaged
        self.hit_me = {}        # attacker id -> last time it damaged us
        self.hurt_at = -INF     # last damage from anything but the zone
        self.mech_hurt_at = -INF
        self.hurt_bearing = None
        self.hurt_bearing_at = -INF
        self.engaged_now = []
        self.target = None      # (kind, id) being followed
        self.since = 0.0        # when we started following it
        self.last_run = -INF    # the last decision loot was chosen
        self.banned = {}        # (kind, id) -> time the ban ends
        self.dest = None        # destination handed to self.nav
        self.reach = {}         # (kind, id, rounded position) -> walkable cell nearby
        self.ground_cache = {}
        # counters for the local reports; they never influence a decision
        self.counts = {}

    def count(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1

    # --- perception ----------------------------------------------------------------------

    def ground(self, x, y):
        c = self.cover
        i = min(c.nx - 1, max(0, int((x - c.ox) / c.cell)))
        j = min(c.ny - 1, max(0, int((y - c.oy) / c.cell)))
        return c.ground[j * c.nx + i] / 100

    def engaged(self, other, me, now, late):
        """A listed mech that is hunting us: close, hit us lately, closing in, weak and near, or
        aiming at us. Late in the match every listed mech counts."""
        pos, at = me["pos"], other["pos"]
        dx, dy = pos[0] - at[0], pos[1] - at[1]
        d = math.hypot(dx, dy)
        if d < self.CLOSE_M or late or now - self.hit_me.get(other.get("id"), -INF) <= self.ENGAGED_HIT_S:
            return True
        if d < 1e-6:
            return True
        ov = other.get("vel") or [0.0, 0.0, 0.0]
        mv = me.get("vel") or [0.0, 0.0, 0.0]
        closing = ((ov[0] - mv[0]) * dx + (ov[1] - mv[1]) * dy) / d
        if closing > self.CLOSING_MPS and d < self.CLOSING_M:
            return True
        hp, top = other.get("hp"), other.get("max_hp")
        if hp is not None and top and hp < self.WEAK_FRAC * top and d < self.WEAK_M:
            return True
        aim = (other.get("aim") or [None])[0]
        if aim is not None and abs(wrap(aim - math.atan2(dy, dx))) <= self.AIMED_RAD and d < self.AIMED_M:
            return True
        return False

    def observe(self, obs):
        now, me = obs["t"], obs["self"]
        pos = me["pos"]
        for event in obs.get("events") or ():
            kind = event.get("type")
            if kind == "damaged":
                by = event.get("by")
                if by is None or event.get("weapon") == "zone":
                    continue
                self.hurt_at = now
                self.hit_me[by] = now
                if game_mech(by):
                    self.mech_hurt_at = now
                if event.get("bearing") is not None:
                    self.hurt_bearing, self.hurt_bearing_at = event["bearing"], now
            elif kind == "kill":
                self.engaged_at.pop(event.get("target"), None)
                self.hit_me.pop(event.get("target"), None)
        zone = obs.get("zone") or {}
        late = (zone.get("next_radius", INF) <= self.LATE_RADIUS_M
                or obs.get("alive", 16) <= self.LATE_ALIVE)
        self.engaged_now = []
        listed_drones = set()
        for other in obs.get("mechs") or ():
            kind, key = other.get("kind"), other.get("id")
            if kind == "npc":
                self.drones[key] = dict(pos=list(other["pos"]), seen=now, listed=other)
                listed_drones.add(key)
            elif kind == "mech" and self.engaged(other, me, now, late):
                self.engaged_at[key] = now
                self.engaged_now.append(other)
        for key, drone in self.drones.items():
            if key not in listed_drones:
                drone["listed"] = None
        for crate in obs.get("crates") or ():
            self.items[("crate", crate["id"])] = dict(pos=list(crate["pos"]), seen=now)
        for cube in obs.get("cubes") or ():
            self.items[("cube", cube["id"])] = dict(pos=list(cube["pos"]), seen=now)
        eye = [pos[0], pos[1], pos[2] + (me.get("stats") or {}).get("eye_height", 8)]
        facing = (me.get("aim") or [None])[0]
        for key in [k for k, item in self.items.items() if self.gone(item, eye, facing, now, 1.5)]:
            del self.items[key]
        for key in [k for k, d in self.drones.items()
                    if now - d["seen"] > self.DRONE_FORGET_S
                    or self.gone(d, eye, facing, now, self.npc_height / 2)]:
            del self.drones[key]
        self.engaged_at = {k: t for k, t in self.engaged_at.items() if now - t <= self.DANGER_SEEN_S + 1e-9}
        self.hit_me = {k: t for k, t in self.hit_me.items() if now - t <= self.ENGAGED_HIT_S + 1e-9}
        self.banned = {k: t for k, t in self.banned.items() if t > now}

    def gone(self, item, eye, facing, now, lift):
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
            off = abs(wrap(math.atan2(at[1] - eye[1], at[0] - eye[0]) - facing))
            if off > self.fov / 2 - self.GONE_VIEW_MARGIN_RAD:
                return False
        return self.cover.clear(eye, [at[0], at[1], at[2] + lift], skip_start=0.5, skip_end=0.5)

    def danger(self, now):
        return (now - self.hurt_at <= self.DANGER_HIT_S + 1e-9
                or any(now - t <= self.DANGER_SEEN_S + 1e-9 for t in self.engaged_at.values()))

    def threat(self, now):
        """A listed mech hunting us, or a mech hit in the last 4 s: only cubes are followed."""
        return bool(self.engaged_now) or now - self.mech_hurt_at <= self.DANGER_HIT_S + 1e-9

    # --- choice --------------------------------------------------------------------------

    def reachable(self, key, at):
        nav = self.nav
        entry = (key, round(at[0] / 4), round(at[1] / 4))
        if entry in self.reach:
            return self.reach[entry]
        i0 = round((at[0] - nav.ox) / nav.step)
        j0 = round((at[1] - nav.oy) / nav.step)
        rings = int(self.REACH_M / nav.step) + 1
        found = False
        for j in range(j0 - rings, j0 + rings + 1):
            for i in range(i0 - rings, i0 + rings + 1):
                if (0 <= i < nav.width and 0 <= j < nav.height and nav.free[j * nav.width + i]
                        and math.hypot(nav.ox + i * nav.step - at[0], nav.oy + j * nav.step - at[1]) <= self.REACH_M):
                    found = True
                    break
            if found:
                break
        if len(self.reach) > 4000:
            self.reach.clear()
        self.reach[entry] = found
        return found

    def elevated(self, key, at):
        entry = (key, round(at[0], 1), round(at[1], 1), round(at[2], 1))
        if entry not in self.ground_cache:
            if len(self.ground_cache) > 4000:
                self.ground_cache.clear()
            self.ground_cache[entry] = at[2] - self.ground(at[0], at[1]) > self.ELEVATED_M
        return self.ground_cache[entry]

    def release(self):
        """Nothing to follow: the next choice starts afresh."""
        self.target = None
        self.dest = None

    def cube_reachable(self, key, at):
        """The loot rules' ground checks for a cube: not on a roof or deck, and near a walkable
        grid cell. The mid-fight cube grab (squad_move.py) asks this too."""
        return not self.elevated(("cube", key), at) and self.reachable(("cube", key), at)

    def choose(self, obs, zone, cubes_only=False):
        """The (kind, id) to follow, or None. cubes_only: crates and drones are left out."""
        me, now = obs["self"], obs["t"]
        pos = me["pos"]
        live = obs["zone"]
        if now - self.last_run > self.PAUSE_S + 1e-9:
            self.release()
        self.last_run = now
        walk = max(1.0, (me.get("stats") or {}).get("walk_speed", 11.7))
        cubes = me.get("cubes", 0) or 0
        cube_value = self.CUBE_VALUE if cubes < self.CUBE_CAP else self.CUBE_VALUE_CAPPED
        top = me.get("max_hp") or 1
        farm = me.get("hp", 0) / top > self.FARM_HP and not self.danger(now) and not cubes_only
        best, best_utility = None, 0.0

        def consider(key, at, limit, value, moves):
            nonlocal best, best_utility
            if key in self.banned:
                return
            d = math.hypot(at[0] - pos[0], at[1] - pos[1])
            if d > limit or d > self.LOOT_MAX_M:
                return
            if math.hypot(at[0] - live["center"][0], at[1] - live["center"][1]) > live["radius"] - self.ZONE_EDGE_M:
                return
            if self.elevated(key, at) or not self.reachable(key, at):
                return
            if now + d * self.LOOT_ROUTE_FACTOR / walk + self.LOOT_EXTRA_S > zone.loot_deadline(key, at, moves):
                return
            utility = value / (d + self.UTILITY_PAD_M) * (self.HYSTERESIS if key == self.target else 1.0)
            if utility > best_utility or (utility == best_utility and best is not None and key < best):
                best, best_utility = key, utility

        for key, item in self.items.items():
            if key[0] == "cube":
                consider(key, item["pos"], self.CUBE_RANGE_M, cube_value, False)
            elif farm:
                consider(key, item["pos"], self.CRATE_RANGE_M, self.CRATE_SHARE * cube_value, False)
        if farm and cubes < self.CUBE_CAP:
            for key, drone in self.drones.items():
                if now - drone["seen"] <= self.DRONE_SEEN_S + 1e-9:
                    consider(("drone", key), drone["pos"], self.DRONE_RANGE_M, self.DRONE_VALUE, True)
        if best is None:
            self.release()
            return None
        if best == self.target:
            if now - self.since > self.GIVE_UP_S:
                self.banned[best] = now + self.BAN_S
                self.count("gave up")
                self.release()
                return None
        else:
            self.target, self.since, self.dest = best, now, None
            self.count("chose " + best[0])
        return best

    # --- approach ------------------------------------------------------------------------

    def position(self, key):
        if key[0] == "drone":
            return self.drones[key[1]]["pos"]
        return self.items[key]["pos"]

    def travel(self, pos, point):
        """Walk to `point`: straight when close, else along this planner's grid route."""
        if math.dist(point[:2], pos[:2]) <= self.STRAIGHT_M:
            return unit_toward(pos, point)
        if self.dest is None or math.dist(self.dest, point[:2]) > self.RETARGET_M:
            self.dest = [point[0], point[1]]
        return unit_toward(pos, self.nav.waypoint(pos, self.dest))

    def step_away(self, pos, source):
        """A unit move away from `source` whose first STEP_M are clear on the grid, else None."""
        base = math.atan2(pos[1] - source[1], pos[0] - source[0])
        for turn in (0.0, 0.8, -0.8, 1.6, -1.6):
            a = base + turn
            side = (math.cos(a), math.sin(a))
            if self.nav.clear_segment(pos, (pos[0] + side[0] * self.STEP_M, pos[1] + side[1] * self.STEP_M)):
                return [side[0], side[1]]
        return None

    def approach(self, obs, key, lead_point):
        """(move, shot) for the chosen item. shot is {aim, kind} or None; `lead_point(other,
        muzzle, weapons)` gives the gun lead for a moving drone."""
        me, now = obs["self"], obs["t"]
        pos = me["pos"]
        stats = me.get("stats") or {}
        muzzle = [pos[0], pos[1], pos[2] + stats.get("muzzle_height", 7)]
        at = self.position(key)
        d = math.hypot(at[0] - pos[0], at[1] - pos[1])
        if key[0] == "drone":
            drone = self.drones[key[1]]
            centre = [at[0], at[1], at[2] + self.npc_height / 2]
            if (now - drone["seen"] <= self.DRONE_FRESH_S + 1e-9 and d < self.DRONE_FIGHT_M
                    and self.cover.clear(muzzle, centre)):
                if d > self.STANDOFF_M + self.STANDOFF_BAND_M:
                    move = self.travel(pos, at)
                elif d < self.STANDOFF_M - self.STANDOFF_BAND_M:
                    move = self.step_away(pos, at) or [0.0, 0.0]
                else:
                    move = [0.0, 0.0]
                aim_x, aim_y = at[0], at[1]
                listed = drone.get("listed")
                if listed is not None:
                    lead = lead_point(listed, muzzle, me.get("weapons") or [])
                    if lead is not None:
                        aim_x, aim_y = lead
                flat = max(1e-6, math.hypot(aim_x - pos[0], aim_y - pos[1]))
                shot = dict(kind="drone", aim=[math.atan2(aim_y - pos[1], aim_x - pos[0]),
                                               math.atan2(centre[2] - muzzle[2], flat)])
                return move, shot
            return self.travel(pos, at), None
        if key[0] == "crate":
            centre = [at[0], at[1], at[2] + self.crate_height / 2]
            if d < self.CRATE_SHOOT_M and self.cover.clear(muzzle, centre):
                move = (self.step_away(pos, at) or [0.0, 0.0]) if d < self.CRATE_BACKOFF_M else [0.0, 0.0]
                flat = max(1e-6, d)
                shot = dict(kind="crate", aim=[math.atan2(at[1] - pos[1], at[0] - pos[0]),
                                               math.atan2(centre[2] - muzzle[2], flat)])
                return move, shot
            return self.travel(pos, at), None
        return self.travel(pos, at), None


class StuckRule:
    """A move is commanded but we stay under SLOW_MPS on the ground for WAIT_S: move in a random
    direction (seeded, so the bot stays deterministic) for RUN_S with a jump, and drop cached routes."""
    SLOW_MPS = 1.2
    WAIT_S = 0.7
    RUN_S = 0.5
    DECISION_S = 0.1

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.slow_since = None
        self.until = -INF
        self.direction = None
        self.jump_pending = False
        self.fired = 0          # for the local reports

    def active(self, now):
        return now < self.until - 1e-9

    def take_jump(self):
        jump, self.jump_pending = self.jump_pending, False
        return jump

    def check(self, obs, move):
        """Called with the final move of a decision. True when a recovery starts next decision."""
        now, me = obs["t"], obs["self"]
        if self.active(now):
            self.slow_since = None
            return False
        vel = me.get("vel") or [0.0, 0.0, 0.0]
        moving = move is not None and math.hypot(move[0], move[1]) > 0.05
        if moving and math.hypot(vel[0], vel[1]) < self.SLOW_MPS and me.get("grounded", True):
            if self.slow_since is None:
                self.slow_since = now
            elif now - self.slow_since >= self.WAIT_S - 1e-9:
                a = self.rng.uniform(-math.pi, math.pi)
                self.direction = [math.cos(a), math.sin(a)]
                self.until = now + self.DECISION_S + self.RUN_S
                self.jump_pending = True
                self.slow_since = None
                self.fired += 1
                return True
        else:
            self.slow_since = None
        return False


class Squad:
    """Practice-mode movement and the aim when there is nothing to face.

    plan() picks the first that applies: the stuck recovery; zone must (boost when it is tight);
    the fight part (squad_move.py: the LoseRule retreat, the fight move and the mid-fight cube
    grab); the pickup detour to a laser (loot.py); zone should; the detour to any other wanted
    weapon (squad_fire.py's wishes); loot (cubes only while a mech hunts us, a mech hit us in
    the last 4 s or there is a mech target); otherwise walk to the zone goal and stand still
    within ARRIVE_M of it. Supply drops and the relocate hop after damage are not followed in
    practice mode. The bullet and shell dodges still have the last word on the move in bot.py.
    """
    ARRIVE_M = 3.0
    ZONE_MOVE_M = 2.0       # zone must and should only move us when the goal is this far
    BOOST_ENERGY = 5.0
    LAST_HIT_S = 2.5        # idle aim: face the bearing of a hit this recent
    SWEEP_RAD, SWEEP_RATE = 1.15, 1.3
    SPIN_RAD = 0.35         # per decision while standing still: a full turn in about 1.8 s
    MOVING = 0.1

    def __init__(self, hello, cover, lead_point):
        self.zone = ZonePlan(Navigator())
        self.economy = Economy(hello, cover)
        self.lead = lead_point  # the engagement's gun lead for a moving drone
        self.camp_nav = Navigator()
        self.stuck = StuckRule(hello.get("seed", 0))
        self.mode = None
        self.target = None
        self.shot = None
        self.modes = {}         # mode -> decisions, for the local reports

    def plan(self, obs, busy, detour_waypoint, fight=None, laser=False):
        """Return {move, boost, jump, urgent} for this decision; remembers any loot shot.
        busy: squad_fire.py has a mech target. detour_waypoint: the next point of the weapon
        pickup detour, or None; laser: that detour is for a laser. fight(goal) is the fight part:
        {mode, move, boost} or None to fall through to the rules below it."""
        now, me = obs["t"], obs["self"]
        pos = me["pos"]
        zone = self.zone.update(obs)
        economy = self.economy
        economy.observe(obs)
        threat = economy.threat(now) or busy
        self.shot, self.target = None, None
        boost = jump = urgent = False
        if self.stuck.active(now):
            mode, move = "unstuck", list(self.stuck.direction)
            jump = self.stuck.take_jump() and bool(me.get("grounded", True))
        elif zone["must"] and zone["distance"] > self.ZONE_MOVE_M:
            mode, move = "zone must", self.walk_to_goal(pos, zone)
            boost = urgent = zone["hurry"] and me.get("energy", 0) > self.BOOST_ENERGY
        elif fight is not None and (step := fight(zone["goal"])) is not None:
            mode, move, boost = step["mode"], step["move"], step["boost"]
        elif detour_waypoint is not None and laser:
            # The laser is worth more than an early start toward the zone goal; the pickup
            # detour's own timing rule and zone must still bring us back in time.
            mode, move = "pickup", unit_toward(pos, detour_waypoint)
        elif zone["should"] and zone["distance"] > self.ZONE_MOVE_M:
            mode, move = "zone should", self.walk_to_goal(pos, zone)
        elif detour_waypoint is not None:
            mode, move = "pickup", unit_toward(pos, detour_waypoint)
        else:
            # Under threat (a mech hunting us, a mech hit in the last 4 s, or a target) only
            # cubes are worth the walk; crates and drones wait until it is calm.
            key = economy.choose(obs, self.zone, cubes_only=threat)
            if key is not None:
                self.target = key
                move, self.shot = economy.approach(obs, key, self.lead)
                mode = "loot " + key[0] + (" shoot" if self.shot else "")
            elif zone["distance"] > self.ARRIVE_M:
                mode, move = "camp walk", self.walk_to_goal(pos, zone)
            else:
                mode, move = "camp", [0.0, 0.0]
        self.mode = mode
        self.modes[mode] = self.modes.get(mode, 0) + 1
        return dict(move=move, boost=boost, jump=jump, urgent=urgent)

    def walk_to_goal(self, pos, zone):
        goal = zone["goal"]
        if math.dist(goal, pos[:2]) <= Economy.STRAIGHT_M:
            return unit_toward(pos, goal)
        return unit_toward(pos, self.camp_nav.waypoint(pos, goal))

    def apply_shot(self, obs, action):
        """The loot shot chosen by plan(): aim at it, and fire the gun once the torso is within
        AIM_GATE_RAD. Only the gun: a laser charge halves our speed and is wasted on loot, so the
        other slots keep the triggers bot.py already set."""
        me = obs["self"]
        yaw, pitch = self.shot["aim"]
        action["aim"] = [yaw, pitch]
        facing = (me.get("aim") or [yaw])[0]
        aligned = abs(wrap(yaw - facing)) <= Economy.AIM_GATE_RAD
        weapons = (list(me.get("weapons") or []) + [None, None])[:2]
        fire = list(action.get("fire") or [False, False])
        for slot, weapon in enumerate(weapons):
            if weapon and weapon.get("kind") == "gun":
                fire[slot] = bool(aligned)
        action["fire"] = fire
        self.economy.count("shot " + self.shot["kind"])

    def check_stuck(self, obs, move, navs=()):
        """With the final move of the decision: when a recovery starts, drop the cached routes
        (ours and the other planners in `navs`)."""
        if self.stuck.check(obs, move):
            for nav in (self.camp_nav, self.economy.nav) + tuple(navs):
                nav.goal, nav.toward = None, {}
                nav.queue.clear()
            self.economy.dest = None
            return True
        return False

    def idle_aim(self, obs, move):
        me, now = obs["self"], obs["t"]
        economy = self.economy
        if economy.hurt_bearing is not None and now - economy.hurt_bearing_at <= self.LAST_HIT_S + 1e-9:
            return [wrap(economy.hurt_bearing), 0.0]
        if move is not None and math.hypot(move[0], move[1]) > self.MOVING:
            heading = math.atan2(move[1], move[0])
            return [wrap(heading + self.SWEEP_RAD * math.sin(self.SWEEP_RATE * now)), 0.0]
        facing = (me.get("aim") or [0.0])[0]
        return [wrap(facing + self.SPIN_RAD), 0.0]
