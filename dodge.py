"""v8: one brief sideways step away from a visible bullet that is on course to hit us."""
import math


class Dodge:
    BULLETS = ("gun", "npc")  # straight-flying bullets; mortar shells arc and splash
    HORIZON_S = 1.0           # only bullets that would arrive within this time
    MARGIN_M = 0.5            # extra clearance around our body when judging a hit
    STEP_M = 4.0              # sideways step that must be clear on the ground grid
    ZONE_MARGIN_M = 3.0       # the step must end this far inside the current circle
    DODGE_S = 0.2             # how long one dodge steers sideways (2 decisions; tuned from 0.3)
    COOLDOWN_S = 0.25         # at most one dodge per this long (tuned from 2.0 by tools/dodge_sweep.py)
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
            self.count("skipped: inside the dodge cooldown")
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


class ShellDodge:
    """mortar-dodge: step out of the blast of a visible mortar shell that will land on us.

    Each decision, every visible shell's flight is integrated (gravity from the hello config)
    until it meets terrain, a wall or a deck on the cover raster, or passes through our body.
    If following the route would leave us inside a blast, the move is replaced by the clear
    direction that cuts the predicted damage most, preferring the one closest to the route."""
    HORIZON_S = 2.5        # only shells that land, or reach us, within this time
    DT = 0.025             # integration step for the shell's flight and for our own movement
    MARGIN_M = 1.0         # extra clearance on top of the splash radius and our body radius
    MIN_GAIN_HP = 10.0     # a step must cut the predicted damage by at least this much
    PROBE_M = 12.0         # this much of the step (at most) must be clear on the ground grid
    ZONE_MARGIN_M = 3.0    # the probed step must end this far inside the current circle
    COOLDOWN_S = 1.0       # after a shell dodge ends, no dodge for a new shell for this long
    ENERGY_RESERVE = 20.0  # boost the step only while this much energy stays in hand
    DIRECTIONS = 16
    NEARBY_M = 25.0        # steps are judged against shells landing this close to our route

    def __init__(self, hello, nav, cover):
        mortar = hello["config"].get("weapons", {}).get("mortar", {})
        self.gravity = mortar.get("gravity", 22.0)
        self.direct = mortar.get("damage", 200.0)
        self.splash = mortar.get("splash", 160.0)
        self.splash_radius = mortar.get("splash_radius", 7.0)
        self.splash_edge = mortar.get("splash_edge", 0.3)
        self.nav, self.cover = nav, cover
        self.active = False   # a shell dodge steered the last decision
        self.ended = -1e9     # when the last shell dodge ended
        self.answered = set() # shell ids a dodge has already answered
        self.decisions = 0    # decisions steered by this rule, for the local reports only
        self.counts = {}      # outcome -> count, for the local reports only

    def count(self, outcome):
        self.counts[outcome] = self.counts.get(outcome, 0) + 1

    def flight(self, shell):
        """Samples (x, y, z) every DT until the shell meets solid matter or HORIZON_S passes;
        returns (samples, landed)."""
        (x, y, z), (vx, vy, vz) = shell["pos"], shell["vel"]
        dt, g = self.DT, self.gravity
        samples = [(x, y, z)]
        for _ in range(int(self.HORIZON_S / dt)):
            x, y = x + vx * dt, y + vy * dt
            z += vz * dt - 0.5 * g * dt * dt
            vz -= g * dt
            samples.append((x, y, z))
            if self.cover.solid(x, y, z):
                return samples, True
        return samples, False

    def path(self, me, direction, boost, steps):
        """Our horizontal positions every DT when steering `direction` from the current velocity."""
        stats = me.get("stats") or {}
        accel = stats.get("ground_accel", 58.5)
        cap = stats.get("boost_speed", 19.5) if boost else stats.get("walk_speed", 11.7)
        x, y = me["pos"][:2]
        vx, vy = (me.get("vel") or [0, 0])[:2]
        tx, ty = direction[0] * cap, direction[1] * cap
        limit, dt = accel * self.DT, self.DT
        out = [(x, y)]
        for _ in range(steps):
            dvx, dvy = tx - vx, ty - vy
            dv = math.hypot(dvx, dvy)
            if dv > limit:
                dvx, dvy = dvx * limit / dv, dvy * limit / dv
            vx, vy = vx + dvx, vy + dvy
            x, y = x + vx * dt, y + vy * dt
            out.append((x, y))
        return out

    def harm(self, samples, landed, ours, floor, radius, height):
        """Predicted damage from one shell to a mech moving along `ours`."""
        for k in range(1, len(samples)):
            (sx0, sy0, sz0), (sx1, sy1, sz1) = samples[k - 1], samples[k]
            (qx0, qy0), (qx1, qy1) = ours[k - 1], ours[k]
            rx, ry = sx0 - qx0, sy0 - qy0
            wx, wy = (sx1 - sx0) - (qx1 - qx0), (sy1 - sy0) - (qy1 - qy0)
            w2 = wx * wx + wy * wy
            f = 0.0 if w2 < 1e-12 else max(0.0, min(1.0, -(rx * wx + ry * wy) / w2))
            if math.hypot(rx + f * wx, ry + f * wy) <= radius and floor <= sz0 + f * (sz1 - sz0) <= floor + height:
                return self.direct + self.splash  # passes through our body
        if not landed:
            return 0.0
        bx, by, bz = samples[-1]
        qx, qy = ours[len(samples) - 1]
        across = max(0.0, math.hypot(bx - qx, by - qy) - radius)
        up = max(0.0, bz - (floor + height), floor - bz)
        d = max(0.0, math.hypot(across, up) - self.MARGIN_M)
        if d > self.splash_radius:
            return 0.0
        return self.splash * (1 - (1 - self.splash_edge) * d / self.splash_radius)

    def stop(self, now):
        if self.active:
            self.active = False
            self.ended = now
        return False

    def steer(self, obs, action, urgent):
        """Override move and boost when a visible shell would land on our route.
        Returns True while a shell dodge is steering this decision."""
        me, now, zone = obs["self"], obs["t"], obs["zone"]
        shells = [s for s in obs.get("projectiles") or () if s.get("kind") == "mortar"]
        if not shells:
            return self.stop(now)
        stats = me.get("stats") or {}
        radius, height = stats.get("radius", 2.5), stats.get("height", 9)
        floor = me["pos"][2]
        flights = [(shell, *self.flight(shell)) for shell in shells]
        steps = max(len(samples) for _, samples, _ in flights) - 1
        move = action.get("move") or [0.0, 0.0]
        length = math.hypot(move[0], move[1])
        route = (move[0] / length, move[1] / length) if length > 1 else (move[0], move[1])
        ours = self.path(me, route, bool(action.get("boost")) and me.get("energy", 0) > 0, steps)
        threats, nearby = {}, []
        for shell, samples, landed in flights:
            damage = self.harm(samples, landed, ours, floor, radius, height)
            if damage > 0:
                threats[shell["id"]] = damage
            # Steps are judged against the shells that threaten the route or land near it.
            if damage > 0 or (landed and math.dist(samples[-1][:2], ours[len(samples) - 1]) <= self.NEARBY_M):
                nearby.append((samples, landed))
        if not threats:
            return self.stop(now)
        base = sum(threats.values())
        if urgent:
            self.count("skipped: urgent zone return")
            return self.stop(now)
        known = any(key in self.answered for key in threats)
        if not self.active and not known and now - self.ended < self.COOLDOWN_S - 1e-9:
            self.count("skipped: a shell dodge ended less than 1 s ago")
            return False
        boost = me.get("energy", 0) > self.ENERGY_RESERVE
        pos = me["pos"]
        heading = math.hypot(*route)
        options = []
        for k in range(self.DIRECTIONS):
            a = math.tau * k / self.DIRECTIONS
            side = (math.cos(a), math.sin(a))
            track = self.path(me, side, boost, steps)
            probe = max(4.0, min(self.PROBE_M, math.dist(track[0], track[-1])))
            end = (pos[0] + side[0] * probe, pos[1] + side[1] * probe)
            if not self.nav.clear_segment(pos, end):
                continue
            if math.dist(end, zone["center"]) + self.ZONE_MARGIN_M > zone["radius"]:
                continue
            damage = sum(self.harm(samples, landed, track, floor, radius, height)
                         for samples, landed in nearby)
            along = (side[0] * route[0] + side[1] * route[1]) / heading if heading > 1e-9 else 0.0
            options.append((damage, along, side))
        if not options:
            self.count("skipped: every step blocked or outside the zone")
            return self.stop(now)
        least = min(damage for damage, _, _ in options)
        if least > base - self.MIN_GAIN_HP:
            self.count("skipped: no clear step cuts the damage")
            return self.stop(now)
        _, _, side = max((o for o in options if o[0] <= least + 1.0), key=lambda o: o[1])
        self.count("dodged" if self.active else "started")
        self.active = True
        self.answered.update(threats)
        self.decisions += 1
        action["move"] = [side[0], side[1]]
        action["boost"] = boost
        action["jump"] = False
        return True
