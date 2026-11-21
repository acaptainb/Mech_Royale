"""First practice entry. Add short obstacle recovery to the kit's zone movement."""
import math
import mechfight as mf
from example_bot import Bot as Starter


class Bot(Starter):
    name = "zone-runner-v1"

    def __init__(self, hello):
        super().__init__(hello)
        self.sample_pos = None
        self.sample_time = 0.0
        self.detour_until = 0.0
        self.turn = 1

    def act(self, obs):
        action = super().act(obs)
        me = obs["self"]
        pos = me["pos"][:2]
        now = obs["t"]
        goal = obs["zone"]["next_center"]
        if math.dist(pos, goal) <= 2:
            action.update(move=[0, 0], boost=False, jump=False)
            self.sample_pos = None
            self.detour_until = 0.0
            return action

        if self.sample_pos is None:
            self.sample_pos, self.sample_time = pos, now
        elif now - self.sample_time >= 1.2:
            if math.dist(pos, self.sample_pos) < 1 and me["grounded"]:
                self.turn *= -1
                self.detour_until = now + 0.9
            self.sample_pos, self.sample_time = pos, now

        if now < self.detour_until:
            dx, dy = action["move"]
            action["move"] = [-self.turn * dy, self.turn * dx]
            action["jump"] = me["grounded"]
        return action


if __name__ == "__main__":
    mf.run(Bot)
