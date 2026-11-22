"""v12: hold position while comfortably safe beside cover with nothing else to do."""
import math

NONE = -32768


class Hold:
    """Hold (move [0, 0], no boost) while every condition below is true. The first decision
    any of them fails, the normal move for that decision stands.

    - objective: the plain zone objective, so no zone return, supply drop, relocation after
      damage or pickup detour; no cube being chased; not in the obstacle recovery
    - safety: inside the current circle by NOW_MARGIN_M and inside the next circle by
      max(NEXT_MARGIN_M, NEXT_MARGIN_FRAC * next radius). The next circle lies inside every
      circle the zone passes through while shrinking toward it, so this stays safe until the
      zone announces a new next circle, which releases the hold
    - cover: a building, stadium or other ground-anchored solid at least COVER_HEIGHT_M tall
      within COVER_RADIUS_M, from the line-of-fire raster (cover.i16). That raster holds what
      stops shots; the navigation grid also blocks slopes and clearance and is not cover
    - quiet: no game mech listed, no damage from a mech or drone this decision, and no recent
      attacker evidence in v6's engagement memory
    """
    NOW_MARGIN_M = 5.0
    NEXT_MARGIN_M = 8.0
    NEXT_MARGIN_FRAC = 0.15
    COVER_RADIUS_M = 8.0
    COVER_HEIGHT_M = 4.5   # at least a mech's centre height

    def __init__(self, cover):
        self.cover = cover
        self.holding = False
        self.started = 0      # holds started
        self.decisions = 0    # decisions spent holding
        self.releases = {}    # reason -> count

    def near_cover(self, pos):
        c = self.cover
        ci = int((pos[0] - c.ox) / c.cell)
        cj = int((pos[1] - c.oy) / c.cell)
        if not (0 <= ci < c.nx and 0 <= cj < c.ny):
            return False
        floor = c.ground[cj * c.nx + ci] + self.COVER_HEIGHT_M * 100
        reach = int(self.COVER_RADIUS_M / c.cell) + 1
        for j in range(max(0, cj - reach), min(c.ny, cj + reach + 1)):
            for i in range(max(0, ci - reach), min(c.nx, ci + reach + 1)):
                top = c.top[j * c.nx + i]
                if top == NONE or top < floor:
                    continue
                x, y = c.ox + (i + 0.5) * c.cell, c.oy + (j + 0.5) * c.cell
                if math.dist((x, y), pos[:2]) <= self.COVER_RADIUS_M + c.cell / 2:
                    return True
        return False

    def blocker(self, obs, mode, chasing_cube, recovering, loot, engagement):
        """The first condition that rules out holding, or None."""
        me, zone = obs["self"], obs["zone"]
        pos = me["pos"]
        if mode != "zone" or loot.target is not None or loot.pending is not None:
            return "objective"
        if chasing_cube:
            return "cube"
        if recovering:
            return "recovery"
        if not me.get("in_zone"):
            return "zone"
        if math.dist(pos[:2], zone["center"]) + self.NOW_MARGIN_M > zone["radius"]:
            return "zone"
        margin = max(self.NEXT_MARGIN_M, self.NEXT_MARGIN_FRAC * zone["next_radius"])
        if math.dist(pos[:2], zone["next_center"]) + margin > zone["next_radius"]:
            return "next circle"
        if any(other.get("kind") == "mech" for other in obs.get("mechs") or ()):
            return "opponent"
        if any(e.get("type") == "damaged" and e.get("by") is not None for e in obs.get("events") or ()):
            return "opponent"
        if engagement.attackers:
            return "opponent"
        if not self.near_cover(pos):
            return "no cover"
        return None

    def steer(self, obs, action, **state):
        """Call after the decision's move and boost are set. Returns True while holding."""
        reason = self.blocker(obs, **state)
        moving = math.hypot(*(action.get("move") or [0, 0])) > 0
        if reason is None and moving:
            if not self.holding:
                self.started += 1
            self.holding = True
            self.decisions += 1
            action["move"] = [0, 0]
            action["boost"] = False
            action["jump"] = False
            return True
        if self.holding:
            key = reason or "arrived"
            self.releases[key] = self.releases.get(key, 0) + 1
        self.holding = False
        return False
