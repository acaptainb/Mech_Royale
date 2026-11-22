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
    name = "zone-runner-vision-scan"
    SCAN_HALF_DEG = 60.0   # vision-scan: sweep this far either side of v5's aim
    SCAN_PERIOD_S = 3.0    # one full sweep, centre -> left -> right -> centre
    SCAN_RATE_FRAC = 0.5   # never ask the torso for more than this share of its turn rate

    def __init__(self, hello):
        super().__init__(hello)
        self.nav = Navigator()
        self.objectives = Objectives()
        self.loot = PickupDetour(hello)
        self.engagement = Engagement(hello, Cover())
        self.dodge = Dodge(hello, self.nav)
        self.turn_rate = hello["config"]["mech"]["turn_rate"]
        self.scan_since = None   # vision-scan: when the current sweep started
        self.scanning = False    # vision-scan: this decision's aim is the sweep
        self.scans = 0           # vision-scan: decisions whose aim was the sweep

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
        # vision-scan: beyond 45 m we only see inside a 120 deg wedge around the torso aim.
        # During ordinary zone movement with nothing listed, nothing to face (no pickup detour,
        # no turn toward an unseen attacker), sweep the aim yaw +-60 deg around v5's aim so
        # opponents to the side are seen sooner. Pitch, movement and triggers are unchanged;
        # the sweep yields the moment anything is listed or the engagement sets an aim.
        self.scanning = (mode == "zone" and pickup is None and not obs["mechs"]
                         and engage["aim"] is None and action.get("aim") is not None)
        if self.scanning:
            if self.scan_since is None:
                self.scan_since = obs["t"]
            half = math.radians(self.SCAN_HALF_DEG)
            rate = self.SCAN_RATE_FRAC * (me["stats"].get("turn_rate") or self.turn_rate)
            period = max(self.SCAN_PERIOD_S, 4 * half / rate)
            u = ((obs["t"] - self.scan_since) / period) % 1.0
            offset = half * (4 * u if u < 0.25 else 2 - 4 * u if u < 0.75 else 4 * u - 4)
            yaw, pitch = action["aim"]
            action["aim"] = [(yaw + offset + math.pi) % math.tau - math.pi, pitch]
            self.scans += 1
        else:
            self.scan_since = None
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
        return action


if __name__ == "__main__":
    mf.run(Bot)
