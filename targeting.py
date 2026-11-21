"""Opponent selection rules and a counter for how often a rule changes its mind.

Nothing here is used by bot.py yet: this is the measurement side of the stable-target
experiment. `nearest_mech` is the rule every version up to v5 inherits from the example bot.
"""
import math


def game_mechs(obs):
    return [other for other in obs["mechs"] if other["kind"] == "mech"]


def nearest_mech(obs):
    """Baseline: the id of the closest listed game mech, as in example_bot.py."""
    me = obs["self"]["pos"]
    listed = sorted(game_mechs(obs), key=lambda other: math.dist(other["pos"], me))
    return listed[0]["id"] if listed else None


class StableTarget:
    """Candidate: keep the current opponent through small distance changes.

    The current id is kept while it is still listed, unless another mech is clearly closer
    (by MARGIN_M metres or MARGIN_FRAC of the current distance, whichever is larger) or has
    been slightly closer for HOLD_S seconds without a break. When the current opponent is no
    longer listed, the closest listed mech is taken on that same decision.
    """
    MARGIN_M = 5.0
    MARGIN_FRAC = 0.10
    HOLD_S = 1.0

    def __init__(self):
        self.current = None
        self.behind_since = None

    def select(self, obs):
        me, now = obs["self"]["pos"], obs["t"]
        distance = {other["id"]: math.dist(other["pos"], me) for other in game_mechs(obs)}
        if not distance:
            self.current = self.behind_since = None
            return None
        closest = min(distance, key=lambda key: (distance[key], key))
        if self.current not in distance:
            self.current, self.behind_since = closest, None  # prompt release
        elif closest == self.current:
            self.behind_since = None
        else:
            held = distance[self.current]
            if distance[closest] < held - max(self.MARGIN_M, self.MARGIN_FRAC * held):
                self.current, self.behind_since = closest, None
            elif self.behind_since is None:
                self.behind_since = now
            elif now - self.behind_since >= self.HOLD_S - 1e-9:
                self.current, self.behind_since = closest, None
        return self.current


class SwitchCounter:
    """Counts target changes over a sequence of decisions.

    switches:  the id changed although the previous opponent was still listed.
    reversals: a switch back to the id held before the previous switch (A -> B -> A) within
               REVERSAL_S seconds of that previous switch. Reversals are also switches.
    forced:    the id changed because the previous opponent was no longer listed.
    A decision with no game mech listed ends the engagement and clears the history.
    """
    REVERSAL_S = 1.0

    def __init__(self):
        self.decisions = self.engaged = self.engagements = 0
        self.switches = self.reversals = self.forced = 0
        self.previous = None
        self.last_switch = None  # (time, id switched away from)

    def record(self, obs, target):
        self.decisions += 1
        listed = {other["id"] for other in game_mechs(obs)}
        if not listed or target is None:
            self.previous = self.last_switch = None
            return
        self.engaged += 1
        if self.previous is None:
            self.engagements += 1
        elif target != self.previous:
            if self.previous in listed:
                self.switches += 1
                if (self.last_switch is not None and self.last_switch[1] == target
                        and obs["t"] - self.last_switch[0] <= self.REVERSAL_S + 1e-9):
                    self.reversals += 1
                self.last_switch = (obs["t"], self.previous)
            else:
                self.forced += 1
                self.last_switch = None
        self.previous = target

    def summary(self):
        return dict(decisions=self.decisions, engaged=self.engaged, engagements=self.engagements,
                    switches=self.switches, reversals=self.reversals, forced=self.forced)
