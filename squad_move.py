"""squad_move: where to stand in a fight, the movement part of the practice-mode design.

In practice matches the 15 house mechs hunt us together, and only our kills before we die
count. While practice mode is on (practice.py: from 20 s of match time, while every death so far
is one of our kills) bot.py asks this part for the move whenever the zone return is not urgent
and neither the stuck recovery nor zone must (squad_econ.py) is moving us:

- FightMove: while there is a mech to fight (squad_fire.py's target, or the nearest engaged mech
  when no target has a line of fire), score staying put and 16 walkable points 6 m away (range to
  the foe, a line of fire when we can shoot, not being seen by the other hunters, the zone,
  nearby cubes, walls, a strafe that flips at random) and walk to the best. A cube within 40 m
  (22.8 m when hurt) is collected instead.
- LoseRule: outnumbered and hurt, or losing the HP race, starts a retreat that lasts 1.5 s
  after the last losing decision, unless the kill is close or the match is late.
- CoverSearch: during a retreat, walk to the nearest grid cell hidden from up to 4 hunters;
  without one, fight on with a line of fire wanted, and with no foe, head for the zone goal.
- Laser sidestep: a mech charging a laser aimed at us adds a sidestep along the strafe side.

When none of it applies the lower rules of squad_econ.py move us. None of it acts during the
urgent zone return, and the bullet Dodge and ShellDodge in bot.py keep the final word. Outside
practice mode nothing here touches the action.
"""
import copy
import math
import random
import sys
import traceback
from collections import deque

from cover import NONE
from navigation import Navigator

TAU = math.tau


def flat(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def zone_penalty(x, y, zone, now):
    """Cost of standing at (x, y): steep near the current edge, milder near the next one and
    only as its shrink approaches."""
    penalty = 0.0
    edge = math.hypot(x - zone["center"][0], y - zone["center"][1]) - zone["radius"]
    if edge > -5:
        penalty += 150 + 5 * (edge + 5)
    edge = math.hypot(x - zone["next_center"][0], y - zone["next_center"][1]) - zone["next_radius"]
    if edge > -5:
        soon = min(1.0, max(0.1, 1 - (zone["shrink_start"] - now) / 25))
        penalty += soon * (25 + 0.8 * (edge + 5))
    return penalty


class Sight:
    """Line tests on the cover raster with the same rule as Cover.clear (blocked by MIN_SOLID_M
    of solid matter along the line, or by crossing any raised deck), sampled every STEP_M and
    written as one tight loop. `samples` counts the points tested so callers can cap the work
    done per decision."""
    STEP_M = 2.0

    def __init__(self, cover):
        self.ground, self.top = cover.ground, cover.top
        self.low, self.high = cover.lift_low, cover.lift_high
        self.nx, self.ny = cover.nx, cover.ny
        self.ox, self.oy, self.cell = cover.ox, cover.oy, cover.cell
        self.min_solid = cover.MIN_SOLID_M
        self.samples = 0

    def index(self, x, y):
        i = int((x - self.ox) / self.cell)
        j = int((y - self.oy) / self.cell)
        if 0 <= i < self.nx and 0 <= j < self.ny:
            return j * self.nx + i
        return None

    def floor(self, x, y):
        k = self.index(x, y)
        return 0.0 if k is None else self.ground[k] / 100

    def clear(self, start, end, skip_start=1.0, skip_end=1.0):
        sx, sy, sz = start
        dx, dy, dz = end[0] - sx, end[1] - sy, end[2] - sz
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        span = length - skip_start - skip_end
        if span <= 0:
            return True
        steps = int(span / self.STEP_M) + 1
        spacing = span / steps
        limit = max(1, round(self.min_solid / spacing))
        f = skip_start / length
        df = spacing / length
        x, y, z = sx + f * dx, sy + f * dy, (sz + f * dz) * 100.0
        ddx, ddy, ddz = df * dx, df * dy, df * dz * 100.0
        ox, oy, inv = self.ox, self.oy, 1.0 / self.cell
        nx, ny = self.nx, self.ny
        ground, top, low, high = self.ground, self.top, self.low, self.high
        blocked = 0
        self.samples += steps + 1
        for _ in range(steps + 1):
            i = int((x - ox) * inv)
            j = int((y - oy) * inv)
            if 0 <= i < nx and 0 <= j < ny:
                k = j * nx + i
                if z < ground[k] or z <= top[k]:
                    blocked += 1
                    if blocked >= limit:
                        return False
                else:
                    lo = low[k]
                    if lo != NONE and lo <= z <= high[k]:
                        return False
            else:
                blocked += 1  # the map edge is a wall
                if blocked >= limit:
                    return False
            x += ddx
            y += ddy
            z += ddz
        return True

    def wall(self, i, j, floor_cm):
        """A wall taller than a step, or a deck lower than our head, fills raster cell (i, j)."""
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return True
        k = j * self.nx + i
        top = self.top[k]
        if top != NONE and top > floor_cm + 120:
            return True
        low = self.low[k]
        return low != NONE and low < floor_cm + 900 and self.high[k] > floor_cm + 120

    def clearance(self, x, y, floor):
        """Distance to the nearest wall cell in 2 m steps, counted up to 4 m (4-neighbour)."""
        i = int((x - self.ox) / self.cell)
        j = int((y - self.oy) / self.cell)
        floor_cm = floor * 100
        if self.wall(i, j, floor_cm):
            return 0.0
        if (self.wall(i + 1, j, floor_cm) or self.wall(i - 1, j, floor_cm)
                or self.wall(i, j + 1, floor_cm) or self.wall(i, j - 1, floor_cm)):
            return self.cell
        return 2 * self.cell


class FightMove:
    """Score staying put and DIRECTIONS points RING_M away; return the unit direction to the
    best (or no move to stay). Points whose straight line is not walkable on the navigation
    grid are dropped. Exact best: candidates are visited in order of their cheap terms and the
    line tests are skipped once they cannot beat the best so far."""
    RING_M = 6.0
    DIRECTIONS = 16
    RANGE_W = 1.1          # per metre off the preferred range
    TRAVEL_W = 0.4         # per metre of step
    LOS_W = 45.0           # times w, for a clear shot line from the point to the foe
    SEEN_COST = 30.0       # per other hunter whose eye can see the point
    SEEN_RANGE_M = 170.0
    MAX_OTHERS = 3         # the nearest other hunters tested, to cap the line tests
    CUBE_W = 1.5           # per metre closer to a nearby cube
    CLEAR_M = 4.0
    CLEAR_W = 2.5          # per metre of wall clearance short of CLEAR_M
    STRAFE_W = 9.0
    STAY_COST = 8.0
    STAY_HIDDEN = 14.0     # back to the stay candidate when w < 0 and we are out of sight
    FLIP_P = 0.6
    FLIP_S = (0.3, 1.0)
    BLOCKED_HOLD_S = 0.5
    BLOCKED_DOT = 0.9

    def __init__(self, seed, nav, coarse, sight):
        self.rng = random.Random(seed)
        self.nav, self.coarse, self.sight = nav, coarse, sight
        self.sign = 1
        self.until = -1.0
        self.ring = [(math.cos(k * TAU / self.DIRECTIONS), math.sin(k * TAU / self.DIRECTIONS))
                     for k in range(self.DIRECTIONS)]
        self.last = {}     # the last choice, for tests

    def strafe(self, pos, foe_pos):
        b = math.atan2(foe_pos[1] - pos[1], foe_pos[0] - pos[0])
        return (-math.sin(b) * self.sign, math.cos(b) * self.sign)

    def tick_strafe(self, now, blocked):
        if blocked:
            self.sign = -self.sign
            self.until = now + self.BLOCKED_HOLD_S
        elif now >= self.until - 1e-9:
            if self.rng.random() < self.FLIP_P:
                self.sign = -self.sign
            self.until = now + self.rng.uniform(*self.FLIP_S)

    def choose(self, obs, foe, centre, others, w, pref, cube):
        """foe: the target mech; centre: its body centre; others: [(eye xyz, (x, y))] of other
        recent hunters; cube: (x, y) of a nearby cube or None. Returns the move [mx, my]."""
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        stats = me.get("stats") or {}
        muzzle = stats.get("muzzle_height", 7.0)
        body = 0.6 * stats.get("height", 9.0)
        x, y, z = me["pos"]
        sight = self.sight
        raised = z - sight.floor(x, y) > 1.5
        fx, fy = foe["pos"][0], foe["pos"][1]
        sx, sy = self.strafe((x, y), (fx, fy))
        cube_here = math.hypot(cube[0] - x, cube[1] - y) if cube is not None else 0.0
        blocked = False
        options = []
        for k in range(-1, self.DIRECTIONS):
            if k < 0:
                dx = dy = 0.0
                px, py, pz, radius = x, y, z, 0.0
            else:
                dx, dy = self.ring[k]
                px, py = x + self.RING_M * dx, y + self.RING_M * dy
                if not self.nav.clear_segment((x, y), (px, py)):
                    if dx * sx + dy * sy > self.BLOCKED_DOT:
                        blocked = True
                    continue
                pz = z if raised else sight.floor(px, py)
                radius = self.RING_M
            cheap = -self.RANGE_W * abs(math.hypot(fx - px, fy - py) - pref) - self.TRAVEL_W * radius
            cheap -= zone_penalty(px, py, zone, now)
            if cube is not None:
                cheap += self.CUBE_W * (cube_here - math.hypot(cube[0] - px, cube[1] - py))
            clearance = sight.clearance(px, py, pz)
            if clearance < self.CLEAR_M:
                cheap -= (self.CLEAR_M - clearance) * self.CLEAR_W
            if w > 0:
                cheap += self.STRAFE_W * (dx * sx + dy * sy)
            if k < 0:
                cheap -= self.STAY_COST
            options.append((-cheap, k, px, py, pz))
        options.sort()
        best, choice, best_los = -math.inf, None, None
        rays = 0
        for negative, k, px, py, pz in options:
            cheap = -negative
            hide = self.STAY_HIDDEN if (k < 0 and w < 0) else 0.0
            if cheap + max(0.0, self.LOS_W * w) + hide <= best:
                continue
            los = self.coarse.clear([px, py, pz + muzzle], centre)
            rays += 1
            score = cheap + (self.LOS_W * w if los else 0.0) + (0.0 if los else hide)
            if score <= best:
                continue
            for eye, at in others:
                if math.hypot(at[0] - px, at[1] - py) > self.SEEN_RANGE_M:
                    continue
                rays += 1
                if sight.clear(eye, (px, py, pz + body)):
                    score -= self.SEEN_COST
                    if score <= best:
                        break
            if score > best:
                best, choice, best_los = score, (k, px, py), los
        self.tick_strafe(now, blocked)
        k, px, py = choice
        self.last = dict(k=k, point=(px, py), los=best_los, score=best, rays=rays, blocked=blocked,
                         w=w, pref=pref)
        if k < 0:
            return [0.0, 0.0]
        return [self.ring[k][0], self.ring[k][1]]


class LoseRule:
    """Retreat while losing and for PULSE_S after the last losing decision.

    near = mechs listed within NEAR_M. Losing: near >= 2 and HP < 55%, near >= 3 and HP < 80%,
    or (with a target) HP < 35% while the target's HP fraction is more than 0.10 above ours.
    Not losing when the target is under 25%, we are over 20% and near <= 2."""
    NEAR_M = 160.0
    PULSE_S = 1.5

    def __init__(self):
        self.lose_time = -math.inf
        self.losing = False

    def update(self, now, own, near, target):
        losing = (near >= 2 and own < 0.55) or (near >= 3 and own < 0.80)
        if target is not None:
            if own < 0.35 and target > own + 0.10:
                losing = True
            if target < 0.25 and own > 0.20 and near <= 2:
                losing = False
        self.losing = losing
        if losing:
            self.lose_time = now
        return now - self.lose_time < self.PULSE_S - 1e-9


class CoverSearch:
    """Breadth-first search outward over the 2 m cover raster (cells passable where the 4 m
    navigation grid is free; 8 neighbours, no corner cutting, rises of at most 2.2 m straight or
    3.1 m diagonal) for a cell hidden from every threat: both the line from a threat's eye to
    our head and the one to our mid-body there are blocked. Every second cell (checkerboard) at
    least one step out is tested, up to MAX_TESTS per search and TESTS_PER_DECISION (or
    SAMPLES_PER_DECISION ray samples) per decision, so a search runs over a few decisions.
    Score (lower wins) = 2 x steps + zone penalty - 0.25 x min(distance to the nearest threat, 80).
    A found goal is kept for CACHE_S before searching again; a failed search waits as long."""
    MAX_STEPS = 50
    MAX_TESTS = 350
    TESTS_PER_DECISION = 60
    SAMPLES_PER_DECISION = 4000
    CACHE_S = 0.4
    INTERIM_S = 1.5        # a goal this recent is followed while a new search runs
    RESTART_M = 6.0        # a running search restarts when we are this far from its origin
    MARGIN = 30.0          # stop once 2 x steps exceeds the best score by this much
    RISE_CM = (220, 310)   # straight, diagonal

    def __init__(self, nav, sight):
        self.nav, self.sight = nav, sight
        nx, ny, cell = sight.nx, sight.ny, sight.cell
        self.nav_i = [min(nav.width - 1, max(0, int(math.floor((sight.ox + (i + 0.5) * cell - nav.ox) / nav.step + 0.5))))
                      for i in range(nx)]
        self.nav_j = [min(nav.height - 1, max(0, int(math.floor((sight.oy + (j + 0.5) * cell - nav.oy) / nav.step + 0.5))))
                      for j in range(ny)]
        self.goal = None
        self.goal_time = -math.inf
        self.failed_time = -math.inf
        self.state = None
        self.tests = 0         # cells tested, for local reports
        self.searches = 0

    def passable(self, k):
        nx = self.sight.nx
        i, j = k % nx, k // nx
        return bool(self.nav.free[self.nav_j[j] * self.nav.width + self.nav_i[i]])

    def centre(self, k):
        s = self.sight
        return s.ox + (k % s.nx + 0.5) * s.cell, s.oy + (k // s.nx + 0.5) * s.cell

    def seen_by(self, x, y, floor, height, threats, order):
        """Index into threats of one that sees the spot, or None when it is hidden from all."""
        head, mid = (x, y, floor + height), (x, y, floor + 0.5 * height)
        for n in order:
            eye = threats[n][0]
            if self.sight.clear(head, eye) or self.sight.clear(mid, eye):
                return n
        return None

    def start_cell(self, pos):
        s = self.sight
        i = int((pos[0] - s.ox) / s.cell)
        j = int((pos[1] - s.oy) / s.cell)
        best = None
        for r in range(0, 5):
            for jj in range(j - r, j + r + 1):
                for ii in range(i - r, i + r + 1):
                    if max(abs(ii - i), abs(jj - j)) != r or not (0 <= ii < s.nx and 0 <= jj < s.ny):
                        continue
                    k = jj * s.nx + ii
                    if self.passable(k):
                        d = flat(self.centre(k), pos)
                        if best is None or d < best[0]:
                            best = (d, k)
            if best is not None:
                return best[1]
        return None

    def begin(self, pos, threats, now):
        start = self.start_cell(pos)
        self.searches += 1
        self.state = dict(origin=(pos[0], pos[1]), ids=sorted(str(t[2]) for t in threats), threats=threats,
                          order=list(range(len(threats))), steps={start: 0} if start is not None else {},
                          queue=deque([start]) if start is not None else deque(), tests=0, best=None,
                          started=now)

    def advance(self, zone, now, height):
        """Run the search within this decision's budget; True once it is finished."""
        st = self.state
        s = self.sight
        nx, ny = s.nx, s.ny
        ground = s.ground
        steps, queue, threats, order = st["steps"], st["queue"], st["threats"], st["order"]
        budget_tests = self.TESTS_PER_DECISION
        samples0 = s.samples
        while queue:
            if budget_tests <= 0 or s.samples - samples0 >= self.SAMPLES_PER_DECISION:
                return False
            k = queue[0]
            n = steps[k]
            best = st["best"]
            if n > self.MAX_STEPS or st["tests"] >= self.MAX_TESTS or (best is not None and 2 * n > best[0] + self.MARGIN):
                queue.clear()
                break
            queue.popleft()
            i, j = k % nx, k // nx
            if n >= 1 and (i + j) % 2 == 0:
                st["tests"] += 1
                self.tests += 1
                budget_tests -= 1
                x, y = self.centre(k)
                floor = ground[k] / 100
                seer = self.seen_by(x, y, floor, height, threats, order)
                if seer is None:
                    nearest = min(flat(t[1], (x, y)) for t in threats)
                    score = 2 * n + zone_penalty(x, y, zone, now) - 0.25 * min(nearest, 80.0)
                    if best is None or score < best[0]:
                        st["best"] = (score, k)
                elif order[0] != seer:
                    order.remove(seer)
                    order.insert(0, seer)
            if n + 1 > self.MAX_STEPS:
                continue
            g = ground[k]
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                ii, jj = i + di, j + dj
                if not (0 <= ii < nx and 0 <= jj < ny):
                    continue
                m = jj * nx + ii
                if m in steps or not self.passable(m):
                    continue
                diagonal = di != 0 and dj != 0
                if ground[m] - g > self.RISE_CM[diagonal]:
                    continue
                if diagonal and not (self.passable(j * nx + ii) and self.passable(jj * nx + i)):
                    continue
                steps[m] = n + 1
                queue.append(m)
        return True

    def find(self, obs, threats, height):
        """threats: [(eye xyz, (x, y), id)]. Returns a goal (x, y) or None."""
        now, pos, zone = obs["t"], obs["self"]["pos"], obs["zone"]
        if self.goal is not None and now - self.goal_time < self.CACHE_S - 1e-9:
            return self.goal
        if not threats:
            return None
        floor = self.sight.floor(pos[0], pos[1])
        z = pos[2] if pos[2] - floor > 1.5 else floor
        if (zone_penalty(pos[0], pos[1], zone, now) == 0
                and self.seen_by(pos[0], pos[1], z, height, threats, range(len(threats))) is None):
            self.goal, self.goal_time, self.state = [pos[0], pos[1]], now, None
            return self.goal
        st = self.state
        ids = sorted(str(t[2]) for t in threats)
        if st is None or flat(st["origin"], pos) > self.RESTART_M or st["ids"] != ids:
            if st is None and now - self.failed_time < self.CACHE_S - 1e-9:
                return None
            self.begin(pos, threats, now)
            st = self.state
        if self.advance(zone, now, height):
            self.state = None
            if st["best"] is not None:
                self.goal, self.goal_time = list(self.centre(st["best"][1])), now
                return self.goal
            self.failed_time = now
            self.goal = None
            return None
        if st["best"] is not None:
            return list(self.centre(st["best"][1]))
        if self.goal is not None and now - self.goal_time < self.INTERIM_S:
            return self.goal
        return None




class SquadMove:
    """Practice-mode fight movement: see the module docstring. bot.py calls remember() on every
    decision, and in practice mode assess() once per decision (the LoseRule pulse runs even while
    a higher rule moves us), then plan() when the stuck recovery and zone must (squad_econ.py) have
    passed and the zone return is not urgent, and sidestep() on whatever move was chosen below
    zone must."""
    SEEN_S = 2.5           # a hunter listed this recently still counts
    THREAT_M = 230.0       # cover is sought from hunters this close
    MAX_THREATS = 4
    CUBE_MEMORY_S = 10.0
    CUBE_GONE_M = 8.0      # a remembered cube this close that is not listed is gone
    CUBE_PULL_M = 40.0
    CUBE_HEIGHT_M = 4.0
    GRAB_M = 40.0
    GRAB_HURT_M = 22.8     # when our HP is at most GRAB_HURT_FRAC
    GRAB_HURT_FRAC = 0.5
    CROWD_M = 150.0
    FINISH_FOE_FRAC = 0.38
    FINISH_OWN_FRAC = 0.42
    FINISH_CROWD = 2
    FINISH_M = 20.0
    FINISHING_M = 120.0    # a foe this close with HP < 200 or under half ours blocks retreat
    FINISHING_HP = 200.0
    LATE_RADIUS = 70.0
    LATE_ALIVE = 3
    LIGHTNING_M, LASER_M, GUN_M = 28.0, 120.0, 85.0
    LIGHTNING_ENERGY = 12.0
    VS_LIGHTNING_M, VS_MORTAR_M = 64.0, 80.0
    READY_RELOAD_S = 0.25
    READY_MARGIN_M = 10.0
    COVER_ARRIVE_M = 1.5
    COVER_BOOST_ENERGY = 10.0
    LASER_AIM_RAD = 0.15
    LASER_STEP = 1.5
    PLAN_W, DODGE_W = 0.4, 0.9
    LASER_BOOST_ENERGY = 25.0

    def __init__(self, hello, cover, centre):
        config = hello["config"]
        mech = config.get("mech", {})
        self.eye_height = mech.get("eye_height", 8.0)
        self.size_per_cube = config.get("cubes", {}).get("size_per_cube", 0.05)
        self.centre = centre               # the engagement's body-centre rule
        self.sight = Sight(cover)
        self.coarse = copy.copy(cover)     # Cover.clear sampled every 2 m for the line of fire
        self.coarse.STEP_M = 2.0
        self.nav = Navigator()             # its own planner, so the zone route stays intact
        seed = hello.get("seed", 0)
        self.fight = FightMove((seed if isinstance(seed, int) else 0) ^ 0x5157, self.nav, self.coarse, self.sight)
        self.lose = LoseRule()
        self.cover = CoverSearch(self.nav, self.sight)
        self.seen = {}                     # id -> (time last listed, mech)
        self.cubes = {}                    # id -> (time last seen, pos)
        self.foe = None                    # the listed mech fought this decision, or None
        self.mode = None                   # what set the move this decision, for tests
        self.retreat = False
        self.side = None                   # the laser sidestep direction this decision, or None
        self.counts = {}
        self.errors = 0

    # --- memory ------------------------------------------------------------------------------

    def remember(self, obs):
        now, pos = obs["t"], obs["self"]["pos"]
        for event in obs.get("events") or ():
            if event.get("type") == "kill":
                self.seen.pop(event.get("target"), None)
        for other in obs.get("mechs") or ():
            if other.get("kind") == "mech":
                self.seen[other.get("id")] = (now, other)
        self.seen = {key: v for key, v in self.seen.items() if now - v[0] <= self.SEEN_S + 1e-9}
        listed = set()
        for cube in obs.get("cubes") or ():
            listed.add(cube.get("id"))
            self.cubes[cube.get("id")] = (now, cube["pos"])
        self.cubes = {key: v for key, v in self.cubes.items()
                      if key in listed or (now - v[0] <= self.CUBE_MEMORY_S and flat(v[1], pos) > self.CUBE_GONE_M)}

    def nearest_cube(self, pos, radius):
        best = None
        for _, at in self.cubes.values():
            d = flat(at, pos)
            if d <= radius and abs(at[2] - pos[2]) <= self.CUBE_HEIGHT_M and (best is None or d < best[0]):
                best = (d, at)
        return None if best is None else best[1]

    def eye(self, other):
        x, y, z = other["pos"]
        return (x, y, z + self.eye_height * (1 + self.size_per_cube * other.get("cubes", 0)))

    # --- rules -------------------------------------------------------------------------------

    def preferred(self, me, foe, finish):
        kinds = {w.get("kind") for w in me.get("weapons") or () if w}
        if "lightning" in kinds and me.get("energy", 0) > self.LIGHTNING_ENERGY:
            pref = self.LIGHTNING_M
        elif "laser" in kinds:
            pref = self.LASER_M
        else:
            pref = self.GUN_M
        if finish:
            pref = self.FINISH_M
        if "lightning" not in kinds:
            theirs = set(foe.get("weapons") or ())
            if "lightning" in theirs:
                pref = max(pref, self.VS_LIGHTNING_M)
            if "mortar" in theirs:
                pref = max(pref, self.VS_MORTAR_M)
        return pref

    def wanted(self, me, distance):
        """+1 when a shot is ready (laser or lightning held, or the gun loaded, not reloading for
        more than READY_RELOAD_S and in range), -1 to step out of sight while it is not."""
        weapons = [w for w in me.get("weapons") or () if w]
        if any(w.get("kind") in ("laser", "lightning") for w in weapons):
            return 1
        for w in weapons:
            if w.get("kind") == "gun":
                reach = (w.get("stats") or {}).get("range", 230.0)
                if (w.get("ammo", 0) > 0 and w.get("reload", 0) <= self.READY_RELOAD_S
                        and distance <= reach - self.READY_MARGIN_M):
                    return 1
        return -1

    def travel(self, pos, goal, stop):
        if flat(pos, goal) <= stop:
            return [0.0, 0.0]
        waypoint = self.nav.waypoint(pos, [goal[0], goal[1]])
        dx, dy = waypoint[0] - pos[0], waypoint[1] - pos[1]
        length = math.hypot(dx, dy)
        if length < 0.3:
            dx, dy = goal[0] - pos[0], goal[1] - pos[1]
            length = math.hypot(dx, dy)
        return [dx / length, dy / length]

    def laser_side(self, obs, mechs):
        """Unit sidestep along the strafe side from every listed mech charging a laser aimed at us."""
        x, y = obs["self"]["pos"][:2]
        sx = sy = 0.0
        for other in mechs:
            if not other.get("charging"):
                continue
            aim = (other.get("aim") or [None])[0]
            if aim is None:
                continue
            bearing = math.atan2(y - other["pos"][1], x - other["pos"][0])
            if abs((aim - bearing + math.pi) % TAU - math.pi) > self.LASER_AIM_RAD:
                continue
            a = bearing + self.fight.sign * math.pi / 2
            sx += self.LASER_STEP * math.cos(a)
            sy += self.LASER_STEP * math.sin(a)
        length = math.hypot(sx, sy)
        return None if length < 1e-9 else (sx / length, sy / length)

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def guarded(self, rule, obs, *args):
        """Run one rule; an error is reported and counted, and the rule gives way (None), so the
        lower movement rules decide as if it did not apply."""
        try:
            return rule(obs, *args)
        except Exception:
            self.errors += 1
            self.mode = "error"
            if self.errors <= 3:
                sys.stderr.write(f"squad_move failed at t={obs.get('t')}:\n{traceback.format_exc()}")
            return None

    # --- decision ----------------------------------------------------------------------------

    def assess(self, obs, foe_id):
        """Every practice decision: the mech to fight (listed, or None) and the LoseRule pulse."""
        self.mode, self.side, self.foe, self.retreat = None, None, None, False
        return self.guarded(self._assess, obs, foe_id)

    def _assess(self, obs, foe_id):
        me = obs["self"]
        pos = me["pos"]
        own = me["hp"] / max(1.0, me.get("max_hp") or 1.0)
        mechs = [m for m in obs.get("mechs") or () if m.get("kind") == "mech"]
        foe = None if foe_id is None else next((m for m in mechs if m.get("id") == foe_id), None)
        foe_frac = None
        if foe is not None:
            foe_frac = foe.get("hp", foe.get("max_hp", 1400)) / max(1.0, foe.get("max_hp") or 1400)
        near = sum(1 for m in mechs if flat(m["pos"], pos) <= LoseRule.NEAR_M)
        self.foe = foe
        self.retreat = self.lose.update(obs["t"], own, near, foe_frac)
        return self.retreat

    def plan(self, obs, goal):
        """The LoseRule retreat (unless finishing or late) or, with a foe, the fight move and the
        mid-fight cube grab: {mode, move, boost}, or None to leave the move to the other rules.
        goal is the zone goal, walked to when retreating with neither cover nor a foe."""
        return self.guarded(self._plan, obs, goal)

    def _plan(self, obs, goal):
        me, zone = obs["self"], obs["zone"]
        pos = me["pos"]
        own = me["hp"] / max(1.0, me.get("max_hp") or 1.0)
        foe = self.foe
        late = zone["next_radius"] <= self.LATE_RADIUS or obs.get("alive", 16) <= self.LATE_ALIVE
        finishing = (foe is not None and flat(foe["pos"], pos) < self.FINISHING_M
                     and (foe.get("hp", 1e9) < self.FINISHING_HP or foe.get("hp", 1e9) < 0.5 * me["hp"]))
        height = (me.get("stats") or {}).get("height", 9.0)
        step = None
        if self.retreat and not finishing and not late:
            threats = sorted(((flat(m["pos"], pos), key, m) for key, (_, m) in self.seen.items()
                              if flat(m["pos"], pos) <= self.THREAT_M), key=lambda t: (t[0], str(t[1])))
            threats = [(self.eye(m), (m["pos"][0], m["pos"][1]), key) for _, key, m in threats[:self.MAX_THREATS]]
            cover = self.cover.find(obs, threats, height)
            if cover is not None:
                step = dict(mode="cover", move=self.travel(pos, cover, self.COVER_ARRIVE_M),
                            boost=me.get("energy", 0) > self.COVER_BOOST_ENERGY)
            elif foe is not None:
                step = dict(mode="cornered", move=self.fight_move(obs, foe, w=1), boost=False)
            else:
                step = dict(mode="flee", move=self.travel(pos, goal, 0.8), boost=False)
        elif foe is not None:
            hurt = own <= self.GRAB_HURT_FRAC
            cube = self.nearest_cube(pos, self.GRAB_HURT_M if hurt else self.GRAB_M)
            if cube is not None:
                step = dict(mode="grab", move=self.travel(pos, cube, 0.3), boost=False)
            else:
                step = dict(mode="fight", move=self.fight_move(obs, foe), boost=False)
        if step is not None:
            self.mode = step["mode"]
            self.count(self.mode)
        return step

    def sidestep(self, obs, move):
        """Blend a sidestep from aimed laser charges into `move`: (move, boost), or None."""
        return self.guarded(self._sidestep, obs, move)

    def _sidestep(self, obs, move):
        me = obs["self"]
        mechs = [m for m in obs.get("mechs") or () if m.get("kind") == "mech"]
        side = self.laser_side(obs, mechs)
        if side is None:
            return None
        plan = move or [0.0, 0.0]
        mx = self.PLAN_W * plan[0] + self.DODGE_W * side[0]
        my = self.PLAN_W * plan[1] + self.DODGE_W * side[1]
        length = math.hypot(mx, my)
        if length > 1:
            mx, my = mx / length, my / length
        self.side = side
        self.count("laser sidestep")
        return [mx, my], me.get("energy", 0) > self.LASER_BOOST_ENERGY

    def fight_move(self, obs, foe, w=None):
        me, pos = obs["self"], obs["self"]["pos"]
        distance = flat(foe["pos"], pos)
        mechs = [m for m in obs.get("mechs") or () if m.get("kind") == "mech"]
        crowd = sum(1 for m in mechs if flat(m["pos"], pos) <= self.CROWD_M)
        own = me["hp"] / max(1.0, me.get("max_hp") or 1.0)
        foe_frac = foe.get("hp", foe.get("max_hp", 1400)) / max(1.0, foe.get("max_hp") or 1400)
        finish = foe_frac < self.FINISH_FOE_FRAC and own > self.FINISH_OWN_FRAC and crowd <= self.FINISH_CROWD
        pref = self.preferred(me, foe, finish)
        if w is None:
            w = self.wanted(me, distance)
        others = sorted(((flat(m["pos"], pos), str(key), m) for key, (_, m) in self.seen.items()
                         if key != foe.get("id")), key=lambda t: (t[0], t[1]))
        others = [(self.eye(m), (m["pos"][0], m["pos"][1])) for d, _, m in others[:FightMove.MAX_OTHERS]
                  if d <= FightMove.SEEN_RANGE_M + FightMove.RING_M]
        cube = self.nearest_cube(pos, self.CUBE_PULL_M)
        return self.fight.choose(obs, foe, self.centre(foe), others, w, pref, cube)
