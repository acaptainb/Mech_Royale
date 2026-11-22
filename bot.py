"""Zone navigation, resource decisions, an early weapon detour and selective engagement for Mech Royale."""
import math

import mechfight as mf
from cover import Cover
from dodge import Dodge
from first_run import Bot as FirstRun
from loot import PickupDetour
from navigation import Navigator
from objectives import Objectives
from targeting import Engagement


class Bot(FirstRun):
    name = "zone-runner-reload-lull"
    LULL_AMMO = 8           # reload-lull: reload during a hold when fewer rounds than this remain
    LULL_REASONS = ("hold: behind cover", "hold: out of range",
                    "hold: passive, shots would miss", "no opponent")

    def __init__(self, hello):
        super().__init__(hello)
        self.nav = Navigator()
        self.objectives = Objectives()
        self.loot = PickupDetour(hello)
        self.engagement = Engagement(hello, Cover())
        self.dodge = Dodge(hello, self.nav)
        self.lull_reloads = 0   # reload-lull: decisions this rule asked for a reload

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
        # v8: one brief sideways step when a visible bullet is on course to hit us,
        # never while the zone return is urgent.
        self.dodge.steer(obs, action, urgent=mode == "return" or late or not me["in_zone"])
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
        # v6: opponent choice and the decision to shoot replace the inherited nearest-mech
        # rule. Movement, pickups and how the weapons are triggered are as in v5.
        engage = self.engagement.decide(obs)
        # During a pickup detour v5 faces the pickup to keep it in view; only a listed
        # opponent overrides that, never the turn toward an unseen attacker.
        if engage["aim"] is not None and not (pickup is not None and engage["target"] is None):
            action["aim"] = engage["aim"]
        fire = [bool(engage["fire"]), bool(engage["fire"])]
        if not engage["fire"] and engage["target"] is not None:
            # Letting go of a charging laser fires it along the current aim, into the cover
            # or at an opponent we chose to spare. Keep that trigger held, as v5 does while
            # an opponent is listed; a full charge only fires on its own after hold_s.
            for slot, weapon in enumerate(me["weapons"][:2]):
                if weapon and weapon.get("kind") == "laser" and weapon.get("charge", 0) > 0:
                    fire[slot] = True
        # v7: a full charge with the beam on the chosen opponent is released now instead of
        # being held until it fires on its own. The other slot's command is left as it is.
        for slot, weapon in enumerate(me["weapons"][:2]):
            if weapon and weapon.get("kind") == "laser" and self.engagement.release_laser(obs, weapon):
                fire[slot] = False
        action["fire"] = fire
        # reload-lull: top the gun up while v6 is holding fire (target behind cover, out of
        # range, a passive target unled shots would miss, or nobody to shoot), so a fight
        # that resumes starts on a full magazine. Never while the gun fires or already reloads.
        if engage["reason"] in self.LULL_REASONS and not engage["fire"] and not action.get("reload"):
            for weapon in me["weapons"][:2]:
                if (weapon and weapon.get("kind") == "gun" and weapon.get("reload", 0) <= 0
                        and weapon.get("ammo", self.LULL_AMMO) < self.LULL_AMMO):
                    action["reload"] = True
                    self.lull_reloads += 1
        return action


if __name__ == "__main__":
    mf.run(Bot)
