"""v8: one brief sideways step away from a visible bullet that is on course to hit us."""
import math


class Dodge:
    BULLETS = ("gun", "npc")  # straight-flying bullets; mortar shells arc and splash
    HORIZON_S = 1.0           # only bullets that would arrive within this time
    MARGIN_M = 0.5            # extra clearance around our body when judging a hit
    STEP_M = 4.0              # sideways step that must be clear on the ground grid
    ZONE_MARGIN_M = 3.0       # the step must end this far inside the current circle
    DODGE_S = 0.3             # how long one dodge steers sideways
    COOLDOWN_S = 2.0          # at most one dodge per this long, so the route keeps progressing
    ENERGY_RESERVE = 20.0     # boost the step only while this much energy stays in hand

    def __init__(self, hello, nav):
        config = hello["config"]
        self.nav = nav
        projectile = config.get("projectile", {})
        self.bullet_radius = {"gun": projectile.get("gun_radius", 0.3),
                              "npc": projectile.get("npc_radius", 0.3)}
        self.active = None    # (until, side) while a dodge is under way
        self.last = -1e9      # when the last dodge started
        self.seen = set()     # bullet ids already answered with a dodge or a skip
        self.counts = {}      # outcome -> count, for the local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def incoming(self, obs):
        """The soonest visible bullet whose path meets our body on our current movement:
        returns (bullet, time to closest approach, horizontal miss vector) or None."""
        me = obs["self"]
        stats = me.get("stats") or {}
        radius, height = stats.get("radius", 2.5), stats.get("height", 9)
        x, y, z = me["pos"]
        ux, uy, uz = (me.get("vel") or [0, 0, 0])[:3]
        best = None
        for bullet in obs.get("projectiles") or ():
            if bullet.get("kind") not in self.BULLETS:
                continue
            (bx, by, bz), (vx, vy, vz) = bullet["pos"], bullet["vel"]
            # Relative motion of the bullet against where our current velocity takes us.
            rx, ry = bx - x, by - y
            wx, wy = vx - ux, vy - uy
            speed2 = wx * wx + wy * wy
            if speed2 < 1e-6:
                continue
            t = -(rx * wx + ry * wy) / speed2
            if t <= 0 or t > self.HORIZON_S:
                continue  # moving away, already past, or too far off to matter
            mx, my = rx + wx * t, ry + wy * t
            reach = radius + self.bullet_radius[bullet["kind"]] + self.MARGIN_M
            height_at = bz + vz * t - (z + uz * t)
            if math.hypot(mx, my) > reach or not -reach <= height_at <= height + reach:
                continue  # a near miss
            if best is None or t < best[1]:
                best = (bullet, t, (mx, my))
        return best

    def steer(self, obs, action, urgent):
        """Override move and boost with a sideways step when a bullet is on course.
        Returns True while a dodge is steering this decision."""
        me, now, zone = obs["self"], obs["t"], obs["zone"]
        pos = me["pos"]
        if self.active is not None:
            until, side = self.active
            end = (pos[0] + side[0] * self.STEP_M / 2, pos[1] + side[1] * self.STEP_M / 2)
            if now < until - 1e-9 and not urgent and self.nav.clear_segment(pos, end):
                self.apply(action, me, side)
                return True
            self.active = None
        threat = self.incoming(obs)
        if threat is None:
            return False
        bullet, arrival, (mx, my) = threat
        if bullet["id"] in self.seen:
            return False
        self.seen.add(bullet["id"])
        if urgent:
            self.count("skipped: urgent zone return")
            return False
        if now - self.last < self.COOLDOWN_S - 1e-9:
            self.count("skipped: dodged less than 2 s ago")
            return False
        vx, vy = bullet["vel"][:2]
        norm = math.hypot(vx, vy)
        nx, ny = -vy / norm, vx / norm
        # Pick the side that leaves the bullet farthest from us when it arrives, using our
        # current velocity, the ground acceleration and the speed cap for that step.
        stats = me.get("stats") or {}
        accel = stats.get("ground_accel", 58.5)
        cap = stats.get("boost_speed" if me.get("energy", 0) > self.ENERGY_RESERVE else "walk_speed", 11.7)
        u = (me.get("vel") or [0, 0])[:2]
        offset = nx * mx + ny * my

        def miss_after(sign):
            headroom = max(0.0, cap - sign * (nx * u[0] + ny * u[1]))
            ramp = headroom / accel
            shift = (0.5 * accel * arrival ** 2 if arrival <= ramp
                     else 0.5 * accel * ramp ** 2 + headroom * (arrival - ramp))
            return abs(offset - sign * shift)

        sign = 1 if miss_after(1) >= miss_after(-1) else -1
        reach = stats.get("radius", 2.5) + self.bullet_radius[bullet["kind"]]
        if miss_after(sign) <= reach:
            self.count("skipped: too close to clear in time")
            return False
        first = (sign * nx, sign * ny)
        for side in (first, (-first[0], -first[1])):
            end = (pos[0] + side[0] * self.STEP_M, pos[1] + side[1] * self.STEP_M)
            if not self.nav.clear_segment(pos, end):
                continue
            if math.dist(end, zone["center"]) + self.ZONE_MARGIN_M > zone["radius"]:
                continue
            self.active = (now + self.DODGE_S, side)
            self.last = now
            self.count("dodged" if side is first else "dodged other side")
            self.apply(action, me, side)
            return True
        self.count("skipped: both sides blocked or outside the zone")
        return False

    def apply(self, action, me, side):
        action["move"] = [side[0], side[1]]
        action["boost"] = me.get("energy", 0) > self.ENERGY_RESERVE
        action["jump"] = False
