"""Practice mode: when the bot plays the practice match, where the 15 house bots hunt it together.

Only our kills score there, so the three parts of the practice design (squad_fire.py: what to shoot
and how; squad_move.py: where to stand in a fight; squad_econ.py: loot, zone camping, idle scan and
the stuck rule) all read this one detector. Outside practice mode the bot plays farm-power exactly.
"""


class PracticeMode:
    """Active from t > START_S while no mech has died to anything but us.

    The starting head count is the first observation's `alive`. Each decision, deaths we did not
    cause = start - alive - our kills (distinct `kill` targets). A positive count on OUTSIDE_TICKS
    decisions in a row (the wait covers a decision of lag between `alive` and our `kill` event)
    turns the mode off for the rest of the match."""
    START_S = 20.0
    OUTSIDE_TICKS = 5

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
            self.outside = self.outside + 1 if others > 0 else 0
            if self.outside >= self.OUTSIDE_TICKS:
                self.off = True
                self.switched_off_at = obs.get("t")
        self.active = not self.off and obs.get("t", 0.0) > self.START_S
        return self.active
