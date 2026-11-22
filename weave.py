"""duel-weave: angle the normal waypoint direction 20 degrees during a clear one-on-one duel."""
import math

from strafe import DuelStrafe


class DuelWeave(DuelStrafe):
    """Same eligibility and side timer as duel-strafe. Instead of walking perpendicular to the
    opponent, the normal move (the waypoint direction) is turned ANGLE_DEG to the current
    side, at the same speed. If that heading would cross a wall on the ground grid or leave
    the safe circle within LOOKAHEAD_M, the other side is tried, then the original direction
    stands. Progress toward the zone continues at cos(20 deg) = 94% of the straight rate."""
    ANGLE_DEG = 20.0

    def steer(self, obs, action, engage, mode, urgent, recovering, reach):
        self.active = False
        reason = self.blocker(obs, engage, mode, urgent, recovering, reach)
        if reason:
            self.count("skipped: " + reason)
            return False
        move = list(action.get("move") or [0, 0])
        speed = math.hypot(*move)
        if speed < 1e-6:
            self.count("skipped: not moving")
            return False
        self.count("eligible")
        now = obs["t"]
        if now - self.last > 0.15 + 1e-9:
            self.until = -1.0  # a fresh encounter: start a new interval
        if now >= self.until - 1e-9:
            self.side = -self.side
            self.until = now + self.rng.uniform(self.MIN_S, self.MAX_S)
        pos = obs["self"]["pos"]
        base = math.atan2(move[1], move[0])
        for sign in (self.side, -self.side):
            heading = base + sign * math.radians(self.ANGLE_DEG)
            step = (speed * math.cos(heading), speed * math.sin(heading))
            end = (pos[0] + math.cos(heading) * self.LOOKAHEAD_M, pos[1] + math.sin(heading) * self.LOOKAHEAD_M)
            if not self.safe(obs, end):
                continue
            if sign != self.side:
                self.side = sign
                self.until = now + self.rng.uniform(self.MIN_S, self.MAX_S)
                self.count("switched side: lookahead blocked")
            action["move"] = [step[0], step[1]]
            self.active = True
            self.last = now
            self.count("changed movement")
            return True
        self.count("skipped: both headings unsafe")
        return False
