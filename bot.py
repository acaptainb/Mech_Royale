"""Zone navigation, resource decisions, an early weapon detour and selective engagement for Mech Royale.

Practice mode (practice.py: after 20 s, while every death so far is one of our kills) hands the
fight to the practice design: squad_fire.py decides what to face and shoot, how each trigger is
pulled, the weapon wishes and the upgrade order; squad_move.py decides where to stand in a fight.
Outside practice mode every decision is farm-power's.
"""
import math

import mechfight as mf
from cover import Cover
from dodge import Dodge, ShellDodge
from farm import CubeFarm
from first_run import Bot as FirstRun
from loot import PickupDetour
from navigation import Navigator
from objectives import Objectives
from practice import PracticeMode
from squad_fire import SquadFire, pick_upgrade
from squad_move import SquadMove, zone_goal
from targeting import Engagement


class Bot(FirstRun):
    name = "zone-runner-sfm-salt-b"

    def __init__(self, hello):
        super().__init__(hello)
        self.nav = Navigator()
        self.objectives = Objectives()
        self.loot = PickupDetour(hello)
        self.engagement = Engagement(hello, Cover())
        self.dodge = Dodge(hello, self.nav)
        self.shell_dodge = ShellDodge(hello, self.nav, self.engagement.cover)
        self.farm = CubeFarm(hello)
        # Practice mode: one detector, read by both parts of the practice design.
        self.practice = PracticeMode()
        self.squad_fire = SquadFire(hello, self.engagement)
        self.squad_move = SquadMove(hello, self.engagement.cover, self.engagement.centre)

    def act(self, obs):
        action = super().act(obs)
        squad = self.practice.update(obs)
        # Both parts keep their memory on every decision, so hits and hunters seen before the mode
        # starts count; outside practice mode they never touch the action.
        self.squad_fire.observe(obs)
        self.squad_move.remember(obs)
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        goal = self.objectives.choose(obs, self.nav)
        mode = self.objectives.mode
        waypoint = self.nav.waypoint(me["pos"], goal)
        # Zone return, supply drops and relocation keep priority: a pickup is only
        # considered while the plain zone objective is active.
        pickup = self.loot.choose(obs, self.objectives, goal, squad=squad)
        if pickup is not None:
            mode = "loot"
            waypoint = self.loot.nav.waypoint(me["pos"], pickup)
            if (math.dist(pickup, (x,y)) > 1
                    and not any(other["kind"] == "mech" for other in obs["mechs"])):
                # Face the pickup so it stays inside the vision wedge.
                action["aim"] = [math.atan2(pickup[1]-y, pickup[0]-x), 0.0]
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
        action["boost"] = (late or not me["in_zone"]) and me["energy"] > 15
        # v8: one brief sideways step when a visible bullet is on course to hit us,
        # never while the zone return is urgent.
        urgent = mode == "return" or late or not me["in_zone"]
        # v6: opponent choice and the decision to shoot replace the inherited nearest-mech
        # rule. Movement, pickups and how the weapons are triggered are as in v5.
        # farm-power: in the first 180 s with nobody to fight, the engagement also shoots passive
        # drones and crates within 150 m (targeting.py); crates not during a pickup detour, which
        # keeps facing its pickup. It only reads the observation, so it is asked here, before the
        # dodges; the cube farm above still sees the previous decision's attackers.
        engage = self.engagement.decide(obs, crates=pickup is None)
        plan = None
        if squad:
            # Practice mode: squad_fire.py decides what to shoot first, so the fight movement
            # (squad_move.py) knows the mech to fight.
            plan = self.squad_fire.decide(obs, engage, pickup)
            self.squad_fight_move(obs, action, plan, urgent)
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
        if squad:
            self.squad_overrides(obs, action, plan)
        # salt-b: a -0.0005 rad yaw offset, a twentieth of the gun's spread. It changes nothing
        # systematically but re-rolls how the fixed practice matches play out (a noise sample).
        if action.get("aim") is not None:
            action["aim"] = [action["aim"][0] - 0.0005, action["aim"][1]]
        return action

    def squad_fight_move(self, obs, action, plan, urgent):
        """Practice mode, before the dodges: unless the zone return is urgent, the LoseRule retreat
        (unless finishing or late), else the fight move with the mid-fight cube grab against the
        target (or the nearest engaged mech while no target has a line of fire), then the laser
        sidestep; otherwise the parent's move stands."""
        fighter = self.squad_move
        fighter.assess(obs, plan["target"] if plan["target"] is not None else plan["nearest"])
        if urgent:
            return
        step = fighter.plan(obs, zone_goal(obs["self"]["pos"], obs["zone"]))
        if step is not None:
            action["move"], action["boost"], action["jump"] = step["move"], step["boost"], False
        side = fighter.sidestep(obs, action.get("move"))
        if side is not None:
            action["move"] = side[0]
            if side[1]:
                action["boost"] = True
        if step is not None or side is not None:
            # Debug text only (never read by the server): what set the move this decision.
            mf.draw.text(" ".join(["squad"] + ([step["mode"]] if step else []) + (["sidestep"] if side else [])))

    def squad_overrides(self, obs, action, plan):
        """Practice mode only: squad_fire.py's choice of what to face and shoot, every trigger,
        the early reload, the weapon take and swap, and the upgrade order replace the parent's."""
        me = obs["self"]
        if plan["aim"] is not None:
            action["aim"] = plan["aim"]
        action["fire"] = plan["fire"]
        action.pop("reload", None)
        if plan["reload"]:
            action["reload"] = True
        action.pop("take", None)
        action.pop("drop", None)
        take = self.loot.swap_take(me, obs.get("pickups") or ())
        if take is not None:
            action["take"] = take[0]
            if take[1] is not None:
                action["drop"] = take[1]
        if obs.get("offer"):
            choice = pick_upgrade(obs["offer"])
            if choice is not None:
                action["pick"] = choice


if __name__ == "__main__":
    mf.run(Bot)
