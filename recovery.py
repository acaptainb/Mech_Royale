"""v9: one recovery attempt when the zone return stops making progress toward safety."""
import math
from collections import deque


class ReturnRecovery:
    """Progress is the remaining walking distance to the zone centre, measured with the same
    planner that steers the return: the straight line when it is clear, otherwise the length
    of the planner's path. While the planner has not reached us yet, progress is not judged.

    When the remaining distance has shrunk by less than MIN_PROGRESS_M over STALL_S, one
    recovery attempt runs: the existing obstacle-recovery manoeuvre (a sideways step with a
    jump, as first_run does outside zone returns) for RECOVER_S, to the side of the planner's
    direction whose step is clear on the ground grid. Attempts keep the same side twice before
    switching (A, A, B, B, ...), so a long obstacle is rounded rather than paced back and forth.
    A mech that moved MOVE_M or more during the window is sliding round something on its own,
    slowly but successfully, and is left alone.
    Another attempt is allowed only COOLDOWN_S after the previous one ends.
    """
    STALL_S = 2.0
    MIN_PROGRESS_M = 2.0
    RECOVER_S = 1.5
    COOLDOWN_S = 3.0
    STEP_M = 6.0
    MOVE_M = 3.0              # a mech that moved this far in the window is sliding, not stuck

    def __init__(self, nav):
        self.nav = nav
        self.history = deque()   # (time, remaining distance, position)
        self.until = -1.0        # end of the attempt under way
        self.allowed = -1.0      # earliest start of the next attempt
        self.side = None
        self.turn = 1
        self.counts = {}         # outcome -> count, for local reports only

    def remaining(self, pos, goal):
        nav = self.nav
        if nav.clear_segment(pos, goal):
            return math.dist(pos[:2], goal[:2])
        node = nav.snap(pos)
        if nav.goal != list(goal) or node not in nav.toward:
            return None
        steps = 0
        while nav.toward[node] != node and steps < 5000:
            node = nav.toward[node]
            steps += 1
        return steps * nav.step + math.dist(pos[:2], nav.point(nav.snap(pos)))

    def steer(self, obs, returning, goal, waypoint, action):
        """Call after the return's move is set. Returns True while an attempt steers."""
        me, now = obs["self"], obs["t"]
        pos = me["pos"]
        if not returning:
            self.history.clear()
            self.until = -1.0
            return False
        if now < self.until - 1e-9:
            self.apply(action, me)
            return True
        remaining = self.remaining(pos, goal)
        if remaining is None:
            self.history.clear()
            return False
        self.history.append((now, remaining, (pos[0], pos[1])))
        while self.history and self.history[0][0] < now - self.STALL_S - 1e-9:
            self.history.popleft()
        started, before, then = self.history[0]
        if now - started < self.STALL_S - 1e-9 or before - remaining >= self.MIN_PROGRESS_M:
            return False
        if math.dist(then, pos[:2]) >= self.MOVE_M:
            return False  # sliding round something: slow, but still getting there
        if now < self.allowed - 1e-9:
            return False
        dx, dy = waypoint[0] - pos[0], waypoint[1] - pos[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            dx, dy = goal[0] - pos[0], goal[1] - pos[1]
            length = math.hypot(dx, dy) or 1.0
        dx, dy = dx / length, dy / length
        self.history.clear()
        turn = self.turn
        for side in ((-turn * dy, turn * dx), (turn * dy, -turn * dx)):
            if self.nav.clear_segment(pos, (pos[0] + side[0] * self.STEP_M, pos[1] + side[1] * self.STEP_M)):
                self.side = side
                self.until = now + self.RECOVER_S
                self.allowed = self.until + self.COOLDOWN_S
                self.counts["retry"] = self.counts.get("retry", 0) + 1
                if self.counts["retry"] % 2 == 0:
                    self.turn *= -1
                self.apply(action, me)
                return True
        self.allowed = now + self.COOLDOWN_S
        self.counts["skipped: both sides blocked"] = self.counts.get("skipped: both sides blocked", 0) + 1
        return False

    def apply(self, action, me):
        action["move"] = [self.side[0], self.side[1]]
        action["jump"] = bool(me.get("grounded"))
