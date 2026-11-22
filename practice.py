"""Practice mode: when the bot plays the practice match, where the 15 house bots hunt it together.

Only our kills score there, so the three parts of the practice design (squad_fire.py: what to shoot
and how; squad_move.py: where to stand in a fight; squad_econ.py: loot, zone camping, idle scan and
the stuck rule) all read this one detector. Outside practice mode the bot plays farm-power exactly.
"""


class PracticeMode:
    """Active from t > START_S until OUTSIDE_DEATHS mechs have died to something other than us.

    The starting head count is the first observation's `alive`. Each decision, deaths we did not
    cause = start - alive - our kills (distinct `kill` targets). A count of at least OUTSIDE_DEATHS
    on OUTSIDE_TICKS decisions in a row (the wait covers a decision of lag between `alive` and our
    `kill` event) turns the mode off for the rest of the match.

    squad-sticky: in the practice match a house bot occasionally dies to a drone or the zone while
    the rest of the squad still hunts us; one such death no longer drops the practice design. In a
    free-for-all mechs die to each other quickly, so three outside deaths still switch it off."""
    START_S = 20.0
    OUTSIDE_TICKS = 5
    OUTSIDE_DEATHS = 3

    def __init__(self):
        self.start_alive = None
        self.kills = set()
        self.outside = 0
        self.off = False
        self.active = False
        self.switched_off_at = None   # match time the mode was turned off, for local reports

    @staticmethod
    def count(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def update(self, obs):
        alive = obs.get("alive")
        counted = self.count(alive)
        if self.start_alive is None and counted:
            self.start_alive = alive
        for event in obs.get("events") or ():
            if event.get("type") == "kill":
                key = event.get("target")
                self.kills.add(key if key is not None else ("kill", len(self.kills)))
        if counted and self.start_alive is not None and not self.off:
            others = self.start_alive - alive - len(self.kills)
            self.outside = self.outside + 1 if others >= self.OUTSIDE_DEATHS else 0
            if self.outside >= self.OUTSIDE_TICKS:
                self.off = True
                self.switched_off_at = obs.get("t")
        self.active = not self.off and obs.get("t", 0.0) > self.START_S
        return self.active
