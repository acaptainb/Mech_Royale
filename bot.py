"""Zone navigation, resource decisions, an early weapon detour and selective engagement for Mech Royale.

Practice mode (practice.py: after 20 s, while every death so far is one of our kills) hands every
decision to the practice design, in three parts: squad_fire.py (what to face and shoot, how each
trigger is pulled, the weapon wishes and the upgrade order), squad_move.py (where to stand in a
fight) and squad_econ.py (loot all match, zone camping, the idle aim and the stuck rule).
In practice mode the zone only takes over the movement on a deadline: squad_econ.py's zone must.
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
from squad_econ import Squad as SquadEcon
from squad_fire import SquadFire, pick_upgrade
from squad_move import SquadMove
from targeting import Engagement


class Bot(FirstRun):
    name = "zone-runner-squad-all-zone"

    def __init__(self, hello):
        super().__init__(hello)
        self.nav = Navigator()
        self.objectives = Objectives()
        self.engagement = Engagement(hello, Cover())
        # The cover raster lets the practice-mode pickup memory tell when a pickup should be in view.
        self.loot = PickupDetour(hello, self.engagement.cover)
        self.dodge = Dodge(hello, self.nav)
        self.shell_dodge = ShellDodge(hello, self.nav, self.engagement.cover)
        self.farm = CubeFarm(hello)
        # Practice mode: one detector, read by the three parts of the practice design.
        self.practice = PracticeMode()
        self.squad_fire = SquadFire(hello, self.engagement)
        self.squad_move = SquadMove(hello, self.engagement.cover, self.engagement.centre)
        self.squad_econ = SquadEcon(hello, self.engagement.cover, self.engagement.lead_point)
        # The mid-fight cube grab only goes for cubes the loot rules could reach.
        self.squad_move.cube_check = self.squad_econ.economy.cube_reachable

    def act(self, obs):
        action = super().act(obs)
        practice = self.practice.update(obs)
        # The fire and move parts keep their memory on every decision, so hits and hunters seen
        # before the mode starts count; outside practice mode they never touch the action.
        self.squad_fire.observe(obs)
        self.squad_move.remember(obs)
        me, zone = obs["self"], obs["zone"]
        x, y, z = me["pos"]
        # Practice mode skips the supply-drop and relocate objectives (objectives.py).
        goal = self.objectives.choose(obs, self.nav, practice=practice)
        mode = self.objectives.mode
        waypoint = self.nav.waypoint(me["pos"], goal)
        # Zone return, supply drops and relocation keep priority: a pickup is only
        # considered while the plain zone objective is active.
        pickup = self.loot.choose(obs, self.objectives, goal, squad=practice)
        if pickup is not None:
            mode = "loot"
            waypoint = self.loot.nav.waypoint(me["pos"], pickup)
            if (math.dist(pickup, (x,y)) > 1
                    and not any(other["kind"] == "mech" for other in obs["mechs"])):
                # Face the pickup so it stays inside the vision wedge.
                action["aim"] = [math.atan2(pickup[1]-y, pickup[0]-x), 0.0]
        if practice:
            return self.practice_act(obs, action, mode, waypoint, pickup)
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
        return action

    def practice_act(self, obs, action, mode, waypoint, pickup):
        """Practice mode. squad_fire.py decides first (it only reads the observation), so the
        movement knows the target. Movement, highest first: the stuck recovery (squad_econ.py);
        the bullet and shell dodges, which keep the final word; zone must; the LoseRule retreat,
        unless finishing or late; the fight move against the target with the mid-fight cube grab
        (both squad_move.py); a laser pickup detour; zone should; the detour to any other wanted
        weapon (squad_fire.py's wishes); loot (cubes only under threat); camp or walk to the zone
        goal. Supply drops and the relocate hop after damage are not used here. The laser
        sidestep is blended into any move below zone must. Aim and triggers are squad_fire.py's;
        the loot shot applies only with nothing to shoot, the idle aim only with no target and
        no engaged enemy to face.

        squad-zone: the zone takes the movement only on a deadline, squad_econ.py's zone plan:
        - zone must (outside the zone, or the walk to the zone goal ends within 3 s of the
          deadline at our spot): no fight move, retreat or laser sidestep; the shell dodge still
          steps out of a blast and the bullet dodge blends into the walk,
          normalise(0.4 x walk + 0.9 x step), so the walk keeps making progress;
        - hurry (outside the current circle, or the walk ends at or after that deadline, which
          covers the last 3 s before it): straight to the goal with boost and no dodge at all;
        - otherwise, even outside the next circle or in the last phase, everything works as in
          the rest of practice play."""
        me = obs["self"]
        x, y, _ = me["pos"]
        # Asked on every decision so its memory and line-of-fire cache stay current; its farming
        # shots are off because loot (crates, drones, cubes) belongs to squad_econ.py here.
        engage = self.engagement.decide(obs, farm=False)
        plan = self.squad_fire.decide(obs, engage, pickup)
        fighter, econ = self.squad_move, self.squad_econ
        # The mech to fight is the target only: engaged, with a line of fire, within 240 m. An
        # engaged mech without one is faced by the idle aim, never walked to.
        fighter.assess(obs, plan["target"])
        laser = pickup is not None and (self.loot.target or {}).get("kind") == "laser"
        # Zone must outranks the fight part inside econ.plan, so the fight part is always offered.
        step = econ.plan(obs, plan["target"] is not None, waypoint if pickup is not None else None,
                         fight=lambda goal: fighter.plan(obs, goal), laser=laser)
        deadline = econ.zone.state
        must, hurry = bool(deadline.get("must")), bool(deadline.get("hurry"))
        action["move"], action["jump"], action["boost"] = step["move"], step["jump"], step["boost"]
        if not must and econ.mode not in ("unstuck", "zone must"):
            side = fighter.sidestep(obs, action["move"])
            if side is not None:
                action["move"] = side[0]
                action["boost"] = action["boost"] or side[1]
        self.dodge.steer(obs, action, urgent=hurry, blend=must)
        self.shell_dodge.steer(obs, action, urgent=hurry)
        # Aim and triggers. With nothing to face (no subject; only unengaged mechs listed) we
        # look where we would with nobody listed: the pickup during its detour, else the idle aim.
        idle = plan["subject"] is None and (plan["reason"] == "no subject"
                                            or plan["reason"].startswith("ignore unengaged"))
        if plan["aim"] is not None and not idle:
            action["aim"] = plan["aim"]
        action["fire"] = list(plan["fire"])
        reload = plan["reload"]
        if plan["subject"] is None and econ.shot is not None:
            econ.apply_shot(obs, action)
            reload = False   # no early reload between loot shots
        elif idle:
            if econ.mode == "pickup" and math.dist(pickup[:2], (x, y)) > 1:
                action["aim"] = [math.atan2(pickup[1]-y, pickup[0]-x), 0.0]
            else:
                action["aim"] = econ.idle_aim(obs, action.get("move"))
        action.pop("reload", None)
        if reload:
            action["reload"] = True
        # Weapon pickups: squad_fire.py's take and swap rule.
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
        econ.check_stuck(obs, action.get("move"), navs=(fighter.nav,))
        # Debug only (never read by the server): what set the move this decision.
        text = ("squad " + econ.mode + (f" {econ.target[1]}" if econ.target else "")
                + (" sidestep" if fighter.side else ""))
        mf.draw.label(text)
        mf.draw.text(text)
        return action


if __name__ == "__main__":
    mf.run(Bot)
