"""Zone navigation, resource decisions, an early weapon detour and selective engagement for Mech Royale.

squad-econ: in practice mode (after 20 s, while every death so far was our kill) squad.py plans the
movement (loot all match, zone camping, the stuck rule) and the aim when there is nothing to shoot.
Outside practice mode every decision is farm-power's."""
import math

import mechfight as mf
from cover import Cover
from dodge import Dodge, ShellDodge
from farm import CubeFarm
from first_run import Bot as FirstRun
from loot import PickupDetour
from navigation import Navigator
from objectives import Objectives
from squad import PracticeMode, Squad
from targeting import Engagement


class Bot(FirstRun):
    name = "zone-runner-squad-econ"

    def __init__(self, hello):
        super().__init__(hello)
        self.nav = Navigator()
        self.objectives = Objectives()
        self.loot = PickupDetour(hello)
        self.engagement = Engagement(hello, Cover())
        self.dodge = Dodge(hello, self.nav)
        self.shell_dodge = ShellDodge(hello, self.nav, self.engagement.cover)
        self.farm = CubeFarm(hello)
        self.practice = PracticeMode()
        self.squad = Squad(hello, self.engagement.cover, self.engagement.lead_point)

    def act(self, obs):
        action = super().act(obs)
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        practice = self.practice.update(obs)
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
        if practice:
            # squad-econ: the engagement decides first (it only reads the observation), so the
            # movement plan knows whether a mech holds our attention; its own drone hunt and crate
            # shot are off because squad.py chooses and approaches loot in this mode.
            engage = self.engagement.decide(obs, crates=pickup is None, farm=False)
            plan = self.squad.plan(obs, engage, self.objectives, waypoint,
                                   waypoint if pickup is not None else None)
            action["move"], action["jump"] = plan["move"], plan["jump"]
        else:
            # farm-power: in the first 180 s with no mech around, walk to cubes up to 120 m away
            # (see farm.py); otherwise the inherited 16 m cube rule below.
            farm = self.farm.choose(obs, self.engagement.attackers) if mode == "zone" else None
            if farm is not None:
                waypoint = farm
            elif mode == "zone" and me["in_zone"] and not obs["mechs"]:
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
        if practice:
            action["boost"] = plan["boost"]
        else:
            action["boost"] = (late or not me["in_zone"]) and me["energy"] > 15
        # v8: one brief sideways step when a visible bullet is on course to hit us,
        # never while the zone return is urgent.
        urgent = mode == "return" or late or not me["in_zone"] or (practice and plan["urgent"])
        self.dodge.steer(obs, action, urgent=urgent)
        # mortar-dodge: step out of the blast of a visible mortar shell that would land on
        # our route; it has the last word on movement, and never acts on an urgent return.
        self.shell_dodge.steer(obs, action, urgent=urgent)
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
        # farm-power: in the first 180 s with nobody to fight, the engagement also shoots passive
        # drones and crates within 150 m (targeting.py); crates not during a pickup detour, which
        # keeps facing its pickup.
        if not practice:
            engage = self.engagement.decide(obs, crates=pickup is None)
        # During a pickup detour v5 faces the pickup to keep it in view; only a listed
        # opponent overrides that, never the turn toward an unseen attacker.
        if engage["aim"] is not None and not (pickup is not None and engage["target"] is None):
            action["aim"] = engage["aim"]
        fire = [bool(engage["fire"]), bool(engage["fire"])]
        if engage.get("crate") is not None:
            # Only the gun shoots crates: a laser charge halves walking speed and leaves the
            # laser on cooldown, a mortar shell is spent, and lightning costs energy.
            fire = [bool(w and w.get("kind") == "gun") for w in (list(me["weapons"]) + [None, None])[:2]]
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
        if practice:
            # squad-econ: with nothing to face, shoot the loot target (gun only) or scan idly;
            # then the stuck rule watches the final move.
            self.squad.finish(obs, action, engage)
            mf.draw.label(f"squad {self.squad.mode}" + (f" {self.squad.target[1]}" if self.squad.target else ""))
        return action


if __name__ == "__main__":
    mf.run(Bot)
