"""squad_fire: what to shoot and how, the fire part of the practice-mode design.

In practice the 15 house bots hunt us as one squad and only our kills score. While practice
mode is on (practice.py: after the first 20 s, while every death so far is one of our kills)
`SquadFire` replaces the v6 choice of opponent and the trigger handling for every slot, the
weapon wishes (loot.py) and the upgrade order. squad_move.py decides where we stand in a fight
and fights this part's target. The dodges and the farming rules stay the parent's.

Distances here are horizontal unless a comment says otherwise. Angles are radians.
"""
import math

INF = math.inf

# Upgrade order while practice mode is active: survival first, then the laser, then the rest.
UPGRADES = ("plating", "armor", "laser_damage", "laser_charge", "nanites", "gun_damage", "gun_rate",
            "lightning_efficiency", "lightning_range", "servos", "gun_mag", "gun_velocity", "gyros",
            "lightning_chain", "reactor", "capacitor", "mortar_reload", "mortar_splash",
            "mortar_velocity", "sensors", "jets", "laser_pierce")


def wrap(angle):
    return (angle + math.pi) % math.tau - math.pi


def is_mech_id(key):
    """Mech ids are 0-15; drones start at 100."""
    return isinstance(key, (int, float)) and not isinstance(key, bool) and 0 <= key < 100


def pick_upgrade(offer):
    """Index of the offered choice that comes first in UPGRADES; unknown ids rank last and a
    tie keeps the earlier choice."""
    choices = offer.get("choices") or []
    if not choices:
        return None
    rank = {name: k for k, name in enumerate(UPGRADES)}
    return min(range(len(choices)), key=lambda i: (rank.get(choices[i].get("id"), len(UPGRADES)), i))


class SquadFire:
    """Practice-mode choice of what to shoot and how each slot's trigger is held.

    Engagement: a listed mech is engaged when it is close, hit us recently, the match is late,
    it is closing on us, it is badly hurt, or it aims at us (each with its own range). Every
    other mech is ignored: never shot, never looked at.

    Target: the engaged mech with a line of fire within MAX_TARGET_M that has the lowest
    distance + HP_WEIGHT x HP, lowered for low HP, for being the target a moment ago, for
    hitting us and for closing. With no target the torso faces the nearest engaged mech (or the
    bearing of the last hit) and no mech is shot. Drones are shot only in self-defence here; the
    parent's farming decisions (passive drones, crates) are kept as they are.

    Triggers: the gun fires when its lead point is within reach of the torso this tick; the
    laser is held while a target is in reach and let go early when the charge already kills,
    or at full charge once the torso is on the body; lightning fires only inside its range and
    cone with energy for the shot. A held mortar is never fired in practice mode.
    """
    # engagement
    NEAR_M = 60.0
    HIT_MEMORY_S = 6.0
    LATE_RADIUS_M = 70.0
    LATE_ALIVE = 3
    CLOSING_MPS = 3.0
    CLOSING_RANGE_M = 180.0
    WEAK_FRACTION = 0.40
    WEAK_RANGE_M = 160.0
    AIMED_RAD = 0.22
    AIMED_RANGE_M = 190.0
    # target score (lower is better)
    MAX_TARGET_M = 240.0
    HP_WEIGHT = 0.2
    LOW_HP_FRACTION = 0.30
    LOW_HP_BONUS = 100.0
    STICKY_S = 2.0
    STICKY_BONUS = 120.0
    HIT_BONUS_S = 4.0
    HIT_BONUS = 40.0
    CLOSING_BONUS = 15.0
    # facing and threat memory
    SEEN_S = 2.5            # a mech that left the list this recently can still be faced
    HURT_FACE_S = 2.5       # face the bearing of a hit this recent
    DANGER_HIT_S = 4.0
    DAMAGED_S = 3.0
    CALM_S = 3.0            # no threat for this long allows an early reload
    # drone self-defence
    DRONE_DEFENCE_S = 3.0
    DRONE_RANGE_M = 150.0
    DRONE_ANGLE = 0.7
    # weapons
    GUN_REACH = 0.96
    LASER_REACH = 0.97
    FULL_MARGIN_S = 0.051   # a charge this close to full counts as full
    DIRECT_AFTER = 0.45     # past this fraction of a full charge the torso goes to the direct point
    DECISION_S = 0.1        # charge gained by the next decision while the trigger is held
    LETHAL_MARGIN = 0.8     # armour and rear hits are not modelled; this is the safety factor
    LASER_YAW_FACTOR = 0.9
    DIRECT_LEAD_S = 0.125   # target motion added to the direct aim point
    OWN_LEAD_S = 0.075      # our own motion added to the muzzle for the direct aim
    SLEW_S = 0.05           # the torso turns this long before a shot leaves
    LIGHTNING_MARGIN_M = 1.5
    LIGHTNING_CONE_MARGIN = 0.05
    RELOAD_FRACTION = 0.6
    HIGH_AIM = 0.85         # fraction of body height aimed at when the centre is behind low cover

    def __init__(self, hello, engagement):
        config = hello["config"]
        self.engagement = engagement            # the parent's v6 engagement: cover, lead, lines
        self.cover = engagement.cover
        mech = config.get("mech", {})
        self.radius = mech.get("radius", 2.5)
        self.height = mech.get("height", 9)
        cubes = config.get("cubes", {})
        self.size_per_cube = cubes.get("size_per_cube", 0.05)
        self.damage_per_cube = cubes.get("damage_per_cube", 0.04)
        self.cube_cap = cubes.get("stat_cap", 10)
        npc = config.get("npc", {})
        self.npc_radius = npc.get("radius", 1.8)
        self.npc_height = npc.get("height", 3.5)
        self.defaults = config.get("weapons", {})
        self.hit_by = {}          # attacker id -> last time it damaged us
        self.hurt = None          # (time, bearing) of the last damage with a usable bearing
        self.drone_hurt = None    # (time, bearing or None) of the last damage from a drone
        self.damaged_at = -INF    # last damage from a mech or drone
        self.seen = {}            # mech id -> (time last listed, position)
        self.sticky = (None, -INF)
        self.last_threat = -INF
        self.decision = {}
        self.counts = {}          # decision reason -> count, for local reports
        self.early = 0            # lethal early laser releases commanded, for local reports

    # --- memory ------------------------------------------------------------------------------

    def observe(self, obs):
        now = obs["t"]
        for event in obs.get("events") or ():
            kind = event.get("type")
            if kind == "damaged":
                by, weapon = event.get("by"), event.get("weapon")
                if by is None or weapon == "zone":
                    continue
                self.hit_by[by] = now
                self.damaged_at = now
                drone = weapon == "npc" or not is_mech_id(by)
                # A mortar's bearing points at the blast, not at the shooter.
                bearing = None if weapon == "mortar" else event.get("bearing")
                if bearing is not None:
                    self.hurt = (now, bearing)
                if drone:
                    self.drone_hurt = (now, bearing)
            elif kind == "kill":
                key = event.get("target")
                self.hit_by.pop(key, None)
                self.seen.pop(key, None)
                if self.sticky[0] == key:
                    self.sticky = (None, -INF)
        for other in obs.get("mechs") or ():
            if other.get("kind") == "mech":
                self.seen[other.get("id")] = (now, other["pos"])
        self.seen = {k: v for k, v in self.seen.items() if now - v[0] <= self.SEEN_S + 1e-9}
        self.hit_by = {k: v for k, v in self.hit_by.items() if now - v <= self.HIT_MEMORY_S + 1e-9}

    def hit_within(self, key, now, seconds):
        return now - self.hit_by.get(key, -INF) <= seconds + 1e-9

    # --- geometry ----------------------------------------------------------------------------

    def body(self, other):
        """(radius, height) of a mech scaled by its cubes, or of a drone."""
        if other.get("kind") == "npc":
            return self.npc_radius, self.npc_height
        scale = 1 + self.size_per_cube * (other.get("cubes") or 0)
        return self.radius * scale, self.height * scale

    def sight(self, other, muzzle):
        """Height to aim at with a clear line from the muzzle (the body centre, else high on the
        body over low cover), or None when there is no line of fire."""
        x, y, z = other["pos"]
        _, height = self.body(other)
        centre = z + height / 2
        known = getattr(self.engagement, "lines", {}).get(other.get("id"))
        if known if known is not None else self.cover.clear(muzzle, [x, y, centre]):
            return centre
        if other.get("kind") != "npc":
            high = z + self.HIGH_AIM * height
            if self.cover.clear(muzzle, [x, y, high]):
                return high
        return None

    def engaged(self, other, me, now, late):
        """Why a listed mech is engaged, or None when it is ignored."""
        pos, vel = me["pos"], me.get("vel") or [0, 0, 0]
        ox, oy = other["pos"][0], other["pos"][1]
        dx, dy = pos[0] - ox, pos[1] - oy
        distance = math.hypot(dx, dy)
        if distance < self.NEAR_M:
            return "near"
        if self.hit_within(other.get("id"), now, self.HIT_MEMORY_S):
            return "hit us"
        if late:
            return "late"
        if self.closing(other, me) > self.CLOSING_MPS and distance < self.CLOSING_RANGE_M:
            return "closing"
        hp, max_hp = self.health(other)
        if hp < self.WEAK_FRACTION * max_hp and distance < self.WEAK_RANGE_M:
            return "weak"
        aim = (other.get("aim") or [None])[0]
        if (aim is not None and distance < self.AIMED_RANGE_M
                and abs(wrap(aim - math.atan2(dy, dx))) <= self.AIMED_RAD):
            return "aimed"
        return None

    @staticmethod
    def health(other):
        max_hp = other.get("max_hp") or 1400
        hp = other.get("hp")
        return (max_hp if hp is None else hp), max_hp

    @staticmethod
    def closing(other, me):
        """Speed at which the gap to us shrinks, m/s (positive when approaching)."""
        pos, vel = me["pos"], me.get("vel") or [0, 0, 0]
        dx, dy = pos[0] - other["pos"][0], pos[1] - other["pos"][1]
        distance = math.hypot(dx, dy)
        if distance < 1e-6:
            return 0.0
        ovx, ovy = (other.get("vel") or [0, 0, 0])[:2]
        return ((ovx - vel[0]) * dx + (ovy - vel[1]) * dy) / distance

    def score(self, fact, now):
        other, distance = fact["other"], fact["distance"]
        hp, max_hp = self.health(other)
        value = distance + self.HP_WEIGHT * hp
        if hp <= self.LOW_HP_FRACTION * max_hp:
            value -= self.LOW_HP_BONUS
        key = other.get("id")
        if self.sticky[0] == key and now - self.sticky[1] <= self.STICKY_S + 1e-9:
            value -= self.STICKY_BONUS
        if self.hit_within(key, now, self.HIT_BONUS_S):
            value -= self.HIT_BONUS
        if fact["closing"] > self.CLOSING_MPS:
            value -= self.CLOSING_BONUS
        return value

    def gun_aim(self, other, aim_z, me, muzzle, gun):
        """[yaw, pitch] to the lead-shots intercept point (or straight at a slow target)."""
        lead = self.engagement.lead_point(other, muzzle, [gun]) if gun else None
        tx, ty = lead if lead is not None else other["pos"][:2]
        flat = max(math.hypot(tx - me["pos"][0], ty - me["pos"][1]), 1e-6)
        return [math.atan2(ty - me["pos"][1], tx - me["pos"][0]), math.atan2(aim_z - muzzle[2], flat)]

    def direct_aim(self, other, aim_z, me, muzzle_height):
        """[yaw, pitch] for an instant shot: target point a little ahead along its motion, seen
        from where our muzzle will be when the command applies."""
        pos, vel = me["pos"], me.get("vel") or [0, 0, 0]
        px, py = pos[0] + vel[0] * self.OWN_LEAD_S, pos[1] + vel[1] * self.OWN_LEAD_S
        pz = pos[2] + muzzle_height
        ovx, ovy = (other.get("vel") or [0, 0, 0])[:2]
        tx, ty = other["pos"][0] + ovx * self.DIRECT_LEAD_S, other["pos"][1] + ovy * self.DIRECT_LEAD_S
        flat = max(math.hypot(tx - px, ty - py), 1e-6)
        return [math.atan2(ty - py, tx - px), math.atan2(aim_z - pz, flat)]

    def tolerances(self, other, distance):
        radius, height = self.body(other)
        d = max(distance, 1.0)
        return math.atan(0.75 * radius / d), math.atan(0.4 * height / d)

    # --- weapons -----------------------------------------------------------------------------

    def stats(self, weapon):
        stats = dict(self.defaults.get(weapon.get("kind"), {}))
        stats.update(weapon.get("stats") or {})
        return stats

    def gun_fires(self, gun, distance, aim, actual, tol, me_stats):
        """Gun trigger: in reach, rounds loaded, and the torso reaches the lead point this tick."""
        if gun is None or actual is None:
            return False
        stats = self.stats(gun)
        if distance > self.GUN_REACH * stats.get("range", 230):
            return False
        if (gun.get("ammo") if gun.get("ammo") is not None else 1) <= 0 or (gun.get("reload") or 0) > 0:
            return False
        yaw_error = max(0.0, abs(wrap(aim[0] - actual[0])) - me_stats.get("turn_rate", 4) * self.SLEW_S)
        pitch_error = max(0.0, abs(aim[1] - actual[1]) - me_stats.get("pitch_rate", 3) * self.SLEW_S)
        return yaw_error < tol[0] and pitch_error < tol[1]

    def lightning_fires(self, weapon, distance, direct_yaw, actual, energy):
        if weapon is None or actual is None:
            return False
        stats = self.stats(weapon)
        cone = math.radians(stats.get("cone_deg", 30)) / 2 - self.LIGHTNING_CONE_MARGIN
        return (distance < stats.get("range", 45) - self.LIGHTNING_MARGIN_M
                and abs(wrap(direct_yaw - actual[0])) < cone
                and energy >= stats.get("energy", 3))

    def lethal(self, stats, charge, target, cubes):
        """True when a beam released at `charge` seconds kills `target` by the lethal-release
        rule (the minimum charge reached, LETHAL_MARGIN x predicted damage >= its HP)."""
        if charge < stats.get("min_charge", 0.15):
            return False
        full = stats.get("charge", 0.75)
        low = stats.get("min_frac", 0.35)
        damage = stats.get("damage", 315) * (low + (1 - low) * min(charge, full) / full)
        damage *= 1 + self.damage_per_cube * min(cubes, self.cube_cap)
        if "mortar" in (target.get("weapons") or ()):
            damage *= 1 + stats.get("cookoff", 0.6)
        hp, _ = self.health(target)
        return self.LETHAL_MARGIN * damage >= hp

    def laser_plan(self, laser, target, distance, direct, actual, cubes):
        """(hold the trigger, aim at the direct point, lethal early release) for a mech target.
        The torso moves to the direct point past DIRECT_AFTER of a full charge, or as soon as
        the charge on the next decision would already be lethal, so it is on the body by then."""
        stats = self.stats(laser)
        full = stats.get("charge", 0.75)
        if distance > self.LASER_REACH * stats.get("range", 280):
            return False, False, False
        charge = laser.get("charge") or 0.0
        tol_yaw, tol_pitch = self.tolerances(target, distance)
        aligned = (actual is not None
                   and abs(wrap(direct[0] - actual[0])) < self.LASER_YAW_FACTOR * tol_yaw
                   and abs(direct[1] - actual[1]) < tol_pitch)
        if charge >= full - self.FULL_MARGIN_S:
            return not aligned, True, False
        if aligned and self.lethal(stats, charge, target, cubes):
            return False, True, True
        soon = self.lethal(stats, charge + self.DECISION_S, target, cubes)
        return True, soon or charge > self.DIRECT_AFTER * full, False

    # --- decision ----------------------------------------------------------------------------

    def decide(self, obs, parent, pickup=None):
        """Return {target, reason, aim, fire, reload}. `parent` is the v6 engagement's decision for
        this observation (its farming shots are kept); `pickup` is the pickup detour's point.
        aim None keeps the aim already in the action. nearest is the closest engaged listed mech,
        for local reports: squad_move.py fights only the target (a line of fire within
        MAX_TARGET_M), and with no target the idle aim faces the engaged mech instead. observe()
        must have seen this observation (bot.py calls it on every decision, so hits from before
        the mode started count)."""
        now, me = obs["t"], obs["self"]
        pos = me["pos"]
        me_stats = me.get("stats") or {}
        muzzle_height = me_stats.get("muzzle_height", 7)
        muzzle = [pos[0], pos[1], pos[2] + muzzle_height]
        actual = me.get("aim") if len(me.get("aim") or ()) >= 2 else None
        slots = (list(me.get("weapons") or []) + [None, None])[:2]
        kinds = [w.get("kind") if w else None for w in slots]
        gun = next((w for w in slots if w and w.get("kind") == "gun"), None)
        zone = obs.get("zone") or {}
        late = zone.get("next_radius", INF) <= self.LATE_RADIUS_M or obs.get("alive", 16) <= self.LATE_ALIVE
        listed = [o for o in obs.get("mechs") or () if o.get("kind") == "mech"]

        facts, ignored = [], []
        for other in listed:
            reason = self.engaged(other, me, now, late)
            distance = math.hypot(other["pos"][0] - pos[0], other["pos"][1] - pos[1])
            if reason is None:
                ignored.append(other.get("id"))
                continue
            aim_z = self.sight(other, muzzle) if distance <= self.MAX_TARGET_M else None
            facts.append(dict(other=other, distance=distance, reason=reason, aim_z=aim_z,
                              closing=self.closing(other, me)))
        scored = [(self.score(f, now), f["other"].get("id"), f) for f in facts if f["aim_z"] is not None]
        best = min(scored, key=lambda item: item[:2], default=None)
        target = best[2] if best else None
        if target is not None:
            self.sticky = (target["other"].get("id"), now)
        danger = bool(facts) or any(now - t <= self.DANGER_HIT_S + 1e-9 for t in self.hit_by.values())
        if danger or now - self.damaged_at <= self.DAMAGED_S + 1e-9:
            self.last_threat = now

        fire = [False, False]
        aim, subject, reason = None, None, None
        if target is not None:
            subject, reason = "mech", "target: " + target["reason"]
            aim, fire = self.shoot_mech(target, me, muzzle, muzzle_height, actual, slots, gun, me_stats)
        else:
            drone = self.defend(obs, me, muzzle, now)
            if drone is not None:
                subject, reason = "drone", "drone self-defence"
                aim, fire = self.shoot_drone(drone, me, muzzle, muzzle_height, actual, slots, gun, me_stats)
            elif parent.get("reason") in ("drone hunt", "crate shoot"):
                subject, reason = ("drone" if parent["reason"] == "drone hunt" else "crate"), parent["reason"]
                aim, fire = self.farm(obs, parent, me, actual, slots, pickup)
            else:
                aim, reason = self.idle(obs, facts, me, pickup)
            # Never start the laser at anything but a mech target. A charge already in progress
            # stays held while a mech is listed, so it is not spent into cover or empty ground.
            for slot, weapon in enumerate(slots):
                if weapon and weapon.get("kind") == "laser":
                    fire[slot] = bool(listed) and (weapon.get("charge") or 0) > 0
        for slot in (0, 1):
            if slots[slot] is None:
                fire[slot] = fire[1 - slot] if kinds[1 - slot] == "gun" else False

        reload = False
        if gun is not None and subject is None and (gun.get("reload") or 0) <= 0:
            mag = self.stats(gun).get("mag", 12)
            ammo = gun.get("ammo") if gun.get("ammo") is not None else mag
            if ammo < mag and (ammo <= self.RELOAD_FRACTION * mag or now - self.last_threat > self.CALM_S):
                reload = True
        if aim is not None:
            aim = [aim[0], max(me_stats.get("min_pitch", -0.7), min(me_stats.get("max_pitch", 1.3), aim[1]))]
        self.counts[reason] = self.counts.get(reason, 0) + 1
        nearest = min(facts, key=lambda f: (f["distance"], str(f["other"].get("id"))), default=None)
        self.decision = dict(target=target["other"].get("id") if target else None, reason=reason,
                             subject=subject, aim=aim, fire=fire, reload=reload,
                             nearest=nearest["other"].get("id") if nearest else None,
                             engaged={f["other"].get("id"): f["reason"] for f in facts},
                             ignored=ignored, scores={key: round(s, 1) for s, key, _ in scored})
        return self.decision

    def shoot_mech(self, target, me, muzzle, muzzle_height, actual, slots, gun, me_stats):
        other, distance, aim_z = target["other"], target["distance"], target["aim_z"]
        lead = self.gun_aim(other, aim_z, me, muzzle, gun)
        direct = self.direct_aim(other, aim_z, me, muzzle_height)
        tol = self.tolerances(other, distance)
        gun_on = self.gun_fires(gun, distance, lead, actual, tol, me_stats)
        aim = lead if gun is not None else direct
        fire = [False, False]
        for slot, weapon in enumerate(slots):
            kind = weapon.get("kind") if weapon else None
            # A held mortar is never fired: its shell would follow the gun's flat aim, and close
            # in the splash catches us as well. It stays False like an empty slot.
            if kind == "gun":
                fire[slot] = gun_on
            elif kind == "lightning":
                fire[slot] = self.lightning_fires(weapon, distance, direct[0], actual, me.get("energy", 0))
            elif kind == "laser":
                hold, straight, lethal = self.laser_plan(weapon, other, distance, direct, actual,
                                                         me.get("cubes") or 0)
                fire[slot] = hold
                if straight:
                    aim = direct
                if lethal:
                    self.early += 1
        return aim, fire

    def defend(self, obs, me, muzzle, now):
        """The drone to shoot back at: hit us in the last DRONE_DEFENCE_S, or the visible drone
        closest to the bearing of the last drone hit; None when no drone qualifies."""
        if self.drone_hurt is None or now - self.drone_hurt[0] > self.DRONE_DEFENCE_S + 1e-9:
            return None
        pos = me["pos"]
        best = None
        for other in obs.get("mechs") or ():
            if other.get("kind") != "npc":
                continue
            distance = math.hypot(other["pos"][0] - pos[0], other["pos"][1] - pos[1])
            if distance > self.DRONE_RANGE_M:
                continue
            if self.hit_within(other.get("id"), now, self.DRONE_DEFENCE_S):
                angle = 0.0
            elif self.drone_hurt[1] is not None:
                bearing = math.atan2(other["pos"][1] - pos[1], other["pos"][0] - pos[0])
                angle = abs(wrap(bearing - self.drone_hurt[1]))
            else:
                continue
            if angle >= self.DRONE_ANGLE:
                continue
            if best is not None and (angle, distance) >= best[:2]:
                continue
            aim_z = self.sight(other, muzzle)
            if aim_z is None:
                continue
            best = (angle, distance, other, aim_z)
        return None if best is None else dict(other=best[2], distance=best[1], aim_z=best[3])

    def shoot_drone(self, drone, me, muzzle, muzzle_height, actual, slots, gun, me_stats):
        other, distance, aim_z = drone["other"], drone["distance"], drone["aim_z"]
        lead = self.gun_aim(other, aim_z, me, muzzle, gun)
        direct = self.direct_aim(other, aim_z, me, muzzle_height)
        gun_on = self.gun_fires(gun, distance, lead, actual, self.tolerances(other, distance), me_stats)
        fire = [False, False]
        for slot, weapon in enumerate(slots):
            kind = weapon.get("kind") if weapon else None
            if kind == "gun":
                fire[slot] = gun_on
            elif kind == "lightning":
                fire[slot] = self.lightning_fires(weapon, distance, direct[0], actual, me.get("energy", 0))
        return (lead if gun is not None else direct), fire

    def farm(self, obs, parent, me, actual, slots, pickup):
        """The parent's farming shot (a passive drone or a crate): its aim and its gun trigger;
        lightning only inside its range and cone."""
        pos = me["pos"]
        aim = parent.get("aim")
        if pickup is not None and parent.get("target") is None:
            aim = None   # a crate shot never turns the torso away from a pickup detour
        centre = parent.get("centre") or pos
        distance = math.hypot(centre[0] - pos[0], centre[1] - pos[1])
        direct_yaw = math.atan2(centre[1] - pos[1], centre[0] - pos[0])
        fire = [False, False]
        for slot, weapon in enumerate(slots):
            kind = weapon.get("kind") if weapon else None
            if kind == "gun":
                fire[slot] = bool(parent.get("fire"))
            elif kind == "lightning":
                fire[slot] = bool(parent.get("fire")) and self.lightning_fires(
                    weapon, distance, direct_yaw, actual, me.get("energy", 0))
        return aim, fire

    def idle(self, obs, facts, me, pickup):
        """Where to look with nothing to shoot: the nearest engaged mech (or one that hit us in the
        last HIT_MEMORY_S and was listed in the last SEEN_S), else the bearing of a recent drone
        hit, else of any recent hit. With none of those and a mech listed, look where we would
        with nobody listed: at the pickup during a detour, else toward the zone goal."""
        now, pos = obs["t"], me["pos"]
        options = [(f["distance"], f["other"]["pos"]) for f in facts]
        listed = {f["other"].get("id") for f in facts}
        for key, (_, where) in self.seen.items():
            if key not in listed and self.hit_within(key, now, self.HIT_MEMORY_S):
                options.append((math.hypot(where[0] - pos[0], where[1] - pos[1]), where))
        if options:
            where = min(options, key=lambda item: item[0])[1]
            return [math.atan2(where[1] - pos[1], where[0] - pos[0]), 0.0], "face engaged mech"
        if pickup is None:
            for memory, why in ((self.drone_hurt, "face drone hit"), (self.hurt, "face last hit")):
                if memory and memory[1] is not None and now - memory[0] <= self.HURT_FACE_S + 1e-9:
                    return [memory[1], 0.0], why
        if not any(o.get("kind") == "mech" for o in obs.get("mechs") or ()):
            return None, "no subject"
        if pickup is not None and math.dist(pickup[:2], pos[:2]) > 1:
            return [math.atan2(pickup[1] - pos[1], pickup[0] - pos[0]), 0.0], "ignore unengaged: face pickup"
        goal = (obs.get("zone") or {}).get("next_center") or pos[:2]
        return [math.atan2(goal[1] - pos[1], goal[0] - pos[0]), 0.0], "ignore unengaged: face zone goal"
