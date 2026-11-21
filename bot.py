"""Zone navigation, resource decisions and an early weapon detour for the Mech Royale simulation."""
import math

import mechfight as mf
from first_run import Bot as FirstRun
from loot import PickupDetour
from navigation import Navigator
from objectives import Objectives


class Bot(FirstRun):
    name = "zone-runner-v6"

    def __init__(self, hello):
        super().__init__(hello)
        self.nav = Navigator()
        # v6 experiment: no voluntary supply-drop pursuit. Zone return, relocation after
        # damage, ordinary movement and passive health regeneration are as in v5.
        self.objectives = Objectives(pursue_drops=False)
        self.loot = PickupDetour(hello)

    def act(self, obs):
        action = super().act(obs)
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        goal = self.objectives.choose(obs, self.nav)
        mode = self.objectives.mode
        waypoint = self.nav.waypoint(me["pos"], goal)
        # Zone return, supply drops and relocation keep priority: a pickup is only
        # considered while the plain zone objective is active.
        pickup = self.loot.choose(obs, self.objectives, goal)
        if pickup is not None:
            mode = "loot"
            waypoint = self.loot.nav.waypoint(me["pos"], pickup)
            if (math.dist(pickup, (x,y)) > 1
                    and not any(other["kind"] == "mech" for other in obs["mechs"])):
                # Face the pickup so it stays inside the vision wedge.
                action["aim"] = [math.atan2(pickup[1]-y, pickup[0]-x), 0.0]
        if mode == "zone" and me["in_zone"] and not obs["mechs"]:
            nearby = sorted(obs["cubes"], key=lambda item: math.dist(item["pos"], me["pos"]))
            for cube in nearby:
                at = cube["pos"]
                if (abs(at[2]-z) <= 4 and math.dist(at[:2], (x,y)) <= 16
                        and math.dist(at[:2], zone["next_center"]) + 4 < zone["next_radius"]
                        and self.nav.clear_segment(me["pos"], at)):
                    waypoint = at[:2]
                    break
        dx, dy = waypoint[0]-x, waypoint[1]-y
        length = math.hypot(dx, dy)
        recovering = obs["t"] < self.detour_until
        if not recovering or mode != "zone":
            action["move"] = [dx/length, dy/length] if length > 0.6 else [0,0]
            action["jump"] = False
        distance_to_safe = math.dist((x,y),zone["next_center"]) - zone["next_radius"]
        walk_time = max(0,distance_to_safe) / max(1,me["stats"]["walk_speed"])
        late = distance_to_safe > 0 and obs["t"] + walk_time + 4 > zone["shrink_start"]
        action["boost"] = (late or not me["in_zone"]) and me["energy"] > 15
        if obs["offer"]:
            priorities = ("armor","plating","nanites","servos","gun_rate","sensors")
            choices = obs["offer"]["choices"]
            action["pick"] = min(range(len(choices)),key=lambda i:
                priorities.index(choices[i]["id"]) if choices[i]["id"] in priorities else len(priorities))
        # Pick the closest eligible item, including the height requirement.
        action.pop("take",None)
        if me["weapons"][1] is None:
            eligible = [p for p in obs["pickups"] if p["kind"] != "gun"
                        and abs(p["pos"][2]-z) <= 4 and math.dist(p["pos"][:2],(x,y)) <= self.reach]
            if eligible:
                action["take"] = min(eligible,key=lambda p: math.dist(p["pos"],me["pos"]))["id"]
        if not obs["mechs"]:
            for weapon in me["weapons"]:
                if weapon and weapon["kind"] == "gun" and weapon.get("ammo",12) <= 5:
                    action["reload"] = True
        return action


if __name__ == "__main__":
    mf.run(Bot)
