"""stealth: stay hidden and out of fights until the endgame, then fight.

The plan comes from live play: wander hidden, avoid fights, and only fight when few mechs are
left. In practice the house bots share vision and hunt us, so every mech that sees us can bring
the squad; placement is the death order, so outliving them is worth more than early kills.
"""
import math

from breaksight import BreakSight


class Stealth(BreakSight):
    """Before the endgame (more than ENDGAME_ALIVE mechs alive and the next circle wider than
    ENDGAME_RADIUS_M):

    - Out of sight: whenever a game mech is listed (we see it, so it may see us) and no game
      mech has damaged us in the last ATTACK_S, move to the nearest reachable point hidden by
      solid cover from every listed mech and recent attacker (BreakSight's search, inside both
      circles), boosting while energy stays above ENERGY_RESERVE, and stand there. The episode
      ends once no mech has been listed for CLEAR_S, when a mech damages us (then we fight
      back as before), in the endgame, or when the zone return becomes urgent.
    - Fire discipline (applied in bot.py through `hold_fire`): the gun only fires at a mech
      that has hit us, that aims at us (it has seen us already, and waiting would only hand it
      the first shots), that we are already fighting, or that is inside the close range; it
      holds fire on passive mechs, so gunfire does not give us away.
    - The hide spot (hide.py) is the zone goal, as on the hide-spot candidate.

    In the endgame all of this switches off and the bot fights exactly as dodge-tuned does.
    The bullet and shell dodges run after this rule in every phase and keep the last word.
    """
    ENDGAME_ALIVE = 4          # alive counts us too: 4 means three opponents left
    ENDGAME_RADIUS_M = 25.0    # the last two circles (25 m and 0 m): nowhere left to hide
    ATTACK_S = 5.0             # a game mech that damaged us this recently is fought, not hidden from
    CLEAR_S = 2.0              # end an episode once no mech has been listed for this long
    FIRE_REASONS = ("attacker", "aiming at us", "committed", "close")

    def __init__(self, hello, nav, cover):
        super().__init__(hello, nav, cover)
        self.last_seen = -1e9   # last time a game mech was listed
        self.held = 0           # decisions the fire discipline turned a shot into a hold

    def endgame(self, obs):
        return (obs.get("alive", 16) <= self.ENDGAME_ALIVE
                or obs["zone"]["next_radius"] <= self.ENDGAME_RADIUS_M)

    def hold_fire(self, obs, engage):
        """True when the engagement wants to shoot but stealth holds the shot."""
        if self.endgame(obs) or not engage.get("fire"):
            return False
        if engage.get("reason") in self.FIRE_REASONS:
            return False
        self.held += 1
        return True

    def steer(self, obs, action, urgent):
        """Call after the move and boost are set, before the dodges. True while it steers."""
        self.active = False
        self.observe(obs)
        now, me = obs["t"], obs["self"]
        if any(other.get("kind") == "mech" for other in obs.get("mechs") or ()):
            self.last_seen = now
        reason = ("ended: endgame" if self.endgame(obs)
                  else "ended: attacked, fighting back" if now - self.last_damage <= self.ATTACK_S + 1e-9
                  else "ended: zone return urgent" if urgent or not me.get("in_zone")
                  else "ended: nobody in sight" if now - self.last_seen > self.CLEAR_S + 1e-9
                  else None)
        if reason is not None:
            if self.started is not None:
                self.end(reason)
            return False
        if self.started is None:
            self.started = now
            self.point, self.reached, self.resume = None, False, 0
            self.count("episodes")
        eyes = self.observers(obs)
        pos = me["pos"]
        if self.hidden(pos[:2], eyes):
            target = (pos[0], pos[1])
            self.point = None
        else:
            if self.point is None or not self.hidden(self.point, eyes) or not self.usable(obs, self.point):
                self.point = None
                if now < self.retry - 1e-9:
                    return False
                found = self.search(obs, eyes)
                if found is False:
                    self.count("search continues next decision")
                    return False
                if found is None:
                    self.retry = now + self.RETRY_S
                    self.count("no cover found")
                    return False
                self.point, self.reached = found, False
                self.count("cover moves started")
            target = self.point
        dx, dy = target[0] - pos[0], target[1] - pos[1]
        length = math.hypot(dx, dy)
        if length < 1.0:
            action["move"], action["boost"] = [0, 0], False
            if not self.reached:
                self.reached = True
                self.count("hidden")
        else:
            action["move"] = [dx / length, dy / length]
            action["boost"] = me.get("energy", 0) > self.ENERGY_RESERVE
        action["jump"] = False
        self.active = True
        self.count("decisions steered")
        return True
