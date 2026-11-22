"""Opponent selection, the decision to engage, and a counter for how often a rule changes its mind.

`nearest_mech` is the rule every version up to v5 inherits from the example bot. v6 uses
`Engagement`, which ranks opponents with `StableTarget` on a threat-adjusted distance.
"""
import math


def game_mechs(obs):
    return [other for other in obs["mechs"] if other["kind"] == "mech"]


def nearest_mech(obs):
    """Baseline: the id of the closest listed game mech, as in example_bot.py."""
    me = obs["self"]["pos"]
    listed = sorted(game_mechs(obs), key=lambda other: math.dist(other["pos"], me))
    return listed[0]["id"] if listed else None


class StableTarget:
    """Candidate: keep the current opponent through small distance changes.

    The current id is kept while it is still listed, unless another mech is clearly closer
    (by MARGIN_M metres or MARGIN_FRAC of the current distance, whichever is larger) or has
    been slightly closer for HOLD_S seconds without a break. When the current opponent is no
    longer listed, the closest listed mech is taken on that same decision.
    """
    MARGIN_M = 5.0
    MARGIN_FRAC = 0.10
    HOLD_S = 1.0

    def __init__(self):
        self.current = None
        self.behind_since = None

    def select(self, obs):
        me = obs["self"]["pos"]
        distance = {other["id"]: math.dist(other["pos"], me) for other in game_mechs(obs)}
        return self.choose(obs["t"], distance)

    def choose(self, now, distance):
        """Pick from {id: distance}; any score where lower means more urgent works."""
        if not distance:
            self.current = self.behind_since = None
            return None
        closest = min(distance, key=lambda key: (distance[key], key))
        if self.current not in distance:
            self.current, self.behind_since = closest, None  # prompt release
        elif closest == self.current:
            self.behind_since = None
        else:
            held = distance[self.current]
            if distance[closest] < held - max(self.MARGIN_M, self.MARGIN_FRAC * max(held, 0.0)):
                self.current, self.behind_since = closest, None
            elif self.behind_since is None:
                self.behind_since = now
            elif now - self.behind_since >= self.HOLD_S - 1e-9:
                self.current, self.behind_since = closest, None
        return self.current


class Engagement:
    """v6: which opponent to face, and whether to shoot at it.

    Ranking: every listed game mech, plus any listed NPC drone that hit us recently, gets a
    score of its distance, lowered for recent damage it did to us and for pointing a weapon
    at us, raised for drones and for a solid line of fire. A mech that is fighting us (hit us,
    aims at us, or we hit it) and that we can shoot ranks ahead of everything else, so a
    passive contact, a contact behind cover or a drone never holds the slot against it.
    StableTarget keeps the current choice through small score changes and drops it the
    decision it stops being listed.

    Shooting: only at the chosen opponent, only with a clear line of fire, only within
    weapon range, and only when it is fighting us or within proximity range, or when unled
    shots would land on it anyway. An opponent remembered behind cover is faced, not shot.

    Unseen attacker: when a recent attacker is not listed and the chosen opponent is neither
    fighting us nor within proximity range (or nothing is listed), the torso turns toward the
    damage bearing to
    bring it into view, and holds fire. Zone damage carries no attacker; mortar damage gives
    the blast point, not the shooter, so it is kept as evidence without a bearing.
    """
    ATTACK_MEMORY_S = 5.0     # damage evidence older than this is forgotten
    THREAT_MEMORY_S = 1.0     # a weapon pointed at us counts for this long after it moves off
    COMMIT_S = 3.0            # keep shooting at an opponent we hit this recently
    ATTACKER_BONUS_M = 35.0   # recent damage makes an opponent rank as this much closer
    THREAT_BONUS_M = 15.0     # so does a weapon pointed at us
    NPC_PENALTY_M = 60.0      # a drone that hit us ranks as this much farther than a mech
    COVER_PENALTY_M = 20.0    # an opponent behind solid cover ranks as this much farther
    SECOND_TIER_M = 1000.0    # added to everything that is not a shootable mech fighting us
    THREAT_AIM_DEG = 12.0     # its torso aim within this angle of us counts as aiming at us
    THREAT_RANGE_M = 280.0    # the longest weapon reach (laser)

    def __init__(self, hello, cover):
        config = hello["config"]
        self.cover = cover
        self.close = config.get("vision", {}).get("near_range", 45)
        self.npc_height = config.get("npc", {}).get("height", 3.5)
        mech = config.get("mech", {})
        self.radius = mech.get("radius", 2.5)
        self.height = mech.get("height", 9)
        self.size_per_cube = config.get("cubes", {}).get("size_per_cube", 0.05)
        self.laser = config.get("weapons", {}).get("laser", {})
        self.selector = StableTarget()
        self.attackers = {}   # id -> (time of last damage, bearing it came from or None)
        self.threats = {}     # id -> time it last pointed a weapon at us
        self.hits = {}        # id -> time we last damaged it
        self.decision = {}    # the last decision, for tests and debug drawing

    def observe(self, obs):
        now = obs["t"]
        for event in obs.get("events") or ():
            kind = event.get("type")
            if kind == "damaged":
                attacker = event.get("by")
                if attacker is not None and event.get("weapon") != "zone":
                    bearing = None if event.get("weapon") == "mortar" else event.get("bearing")
                    self.attackers[attacker] = (now, bearing)
            elif kind == "hit" and event.get("target") is not None:
                self.hits[event["target"]] = now
            elif kind == "kill":
                for memory in (self.attackers, self.threats, self.hits):
                    memory.pop(event.get("target"), None)
        self.attackers = {key: seen for key, seen in self.attackers.items()
                          if now - seen[0] <= self.ATTACK_MEMORY_S + 1e-9}
        self.hits = {key: seen for key, seen in self.hits.items()
                     if now - seen <= self.COMMIT_S + 1e-9}
        me = obs["self"]["pos"]
        for other in obs.get("mechs") or ():
            if self.aiming_at(other, me):
                self.threats[other.get("id")] = now
        self.threats = {key: seen for key, seen in self.threats.items()
                        if now - seen <= self.THREAT_MEMORY_S + 1e-9}

    def centre(self, other):
        x, y, z = other["pos"]
        if other.get("kind") == "npc":
            return [x, y, z + self.npc_height / 2]
        scale = 1 + self.size_per_cube * other.get("cubes", 0)
        return [x, y, z + self.height * scale / 2]

    def aiming_at(self, other, me):
        """Its torso aim points at us. A laser fires along that aim, so charging alone is not
        enough: a mech charging at someone else is not aiming at us."""
        if other.get("kind") != "mech":
            return False
        aim = (other.get("aim") or [None])[0]
        if aim is None:
            return False
        bearing = math.atan2(me[1] - other["pos"][1], me[0] - other["pos"][0])
        off = abs((aim - bearing + math.pi) % math.tau - math.pi)
        return off <= math.radians(self.THREAT_AIM_DEG)

    @staticmethod
    def reach(weapons):
        best = 0.0
        for weapon in weapons:
            stats = (weapon or {}).get("stats") or {}
            if "range" in stats:
                best = max(best, stats["range"])
            elif "speed" in stats and stats.get("gravity"):
                best = max(best, stats["speed"] ** 2 / stats["gravity"])
        return best or 230.0

    def shots_land(self, other, me, distance, weapons):
        """Unled bullets reach the target before it walks out of their path."""
        gun = next((w for w in weapons if w and w.get("kind") == "gun"), None)
        speed = ((gun or {}).get("stats") or {}).get("speed", 252.0)
        dx, dy = other["pos"][0] - me[0], other["pos"][1] - me[1]
        flat = math.hypot(dx, dy) or 1.0
        vx, vy = (other.get("vel") or [0, 0, 0])[:2]
        sideways = abs(vx * dy - vy * dx) / flat
        radius = self.radius * (1 + self.size_per_cube * other.get("cubes", 0))
        return sideways * distance / speed <= radius

    def decide(self, obs):
        """Return {target, aim, fire, reason}; aim is None when v5's aim should stand."""
        self.observe(obs)
        me_state, now = obs["self"], obs["t"]
        me = me_state["pos"]
        stats = me_state.get("stats") or {}
        muzzle = [me[0], me[1], me[2] + stats.get("muzzle_height", 7)]
        weapons = me_state.get("weapons") or []
        reach = self.reach(weapons)
        scores, facts = {}, {}
        for other in obs.get("mechs") or ():
            key, kind = other.get("id"), other.get("kind")
            if kind == "npc" and key not in self.attackers:
                continue  # leave passive drones alone
            if kind not in ("mech", "npc"):
                continue
            distance = math.dist(other["pos"], me)
            clear = self.cover.clear(muzzle, self.centre(other))
            attacker = key in self.attackers
            threat = key in self.threats and distance <= self.THREAT_RANGE_M
            committed = key in self.hits
            fighting = attacker or threat or committed
            shootable = clear and distance <= reach
            score = distance
            score -= self.ATTACKER_BONUS_M if attacker else 0.0
            score -= self.THREAT_BONUS_M if threat else 0.0
            score += self.NPC_PENALTY_M if kind == "npc" else 0.0
            score += 0.0 if clear else self.COVER_PENALTY_M
            if not (kind == "mech" and fighting and shootable):
                score += self.SECOND_TIER_M
            scores[key] = score
            facts[key] = dict(other=other, distance=distance, clear=clear, attacker=attacker,
                              threat=threat, committed=committed, fighting=fighting)
        target = self.selector.choose(now, scores)
        unseen = [seen for key, seen in self.attackers.items()
                  if key not in facts and seen[1] is not None]
        turn = max(unseen, default=None)
        engaged = target is not None and (facts[target]["fighting"]
                                          or facts[target]["distance"] <= self.close)
        if target is None or (turn is not None and not engaged):
            if turn is not None:
                self.decision = dict(target=None, aim=[turn[1], 0.0], fire=False,
                                     reason="turn toward unseen attacker")
            else:
                self.decision = dict(target=None, aim=None, fire=False, reason="no opponent")
            return self.decision
        fact = facts[target]
        other, distance = fact["other"], fact["distance"]
        tx, ty, tz = other["pos"]
        flat = math.dist((tx, ty), me[:2])
        if other.get("kind") == "npc":
            pitch = math.atan2(self.centre(other)[2] - muzzle[2], flat)
        else:
            pitch = math.atan2(tz - me[2] - 2.5, flat)  # the inherited example-bot aim point
        aim = [math.atan2(ty - me[1], tx - me[0]), pitch]
        if not fact["clear"]:
            fire, reason = False, "hold: behind cover"
        elif distance > reach:
            fire, reason = False, "hold: out of range"
        elif fact["fighting"] or distance <= self.close:
            fire = True
            reason = ("attacker" if fact["attacker"] else "aiming at us" if fact["threat"]
                      else "committed" if fact["committed"] else "close")
        elif self.shots_land(other, me, distance, weapons):
            fire, reason = True, "open fire: shots land"
        else:
            fire, reason = False, "hold: passive, shots would miss"
        scale = 1.0 if other.get("kind") == "npc" else 1 + self.size_per_cube * other.get("cubes", 0)
        radius = 1.8 if other.get("kind") == "npc" else self.radius * scale
        half_height = (self.npc_height if other.get("kind") == "npc" else self.height * scale) / 2
        self.decision = dict(target=target, aim=aim, fire=fire, reason=reason, distance=distance,
                             clear=fact["clear"], centre=self.centre(other),
                             radius=radius, half_height=half_height)
        return self.decision

    def release_laser(self, obs, weapon):
        """v7: let go of a fully charged laser on this decision when the beam would hit the
        chosen opponent: it is within laser range, the line is clear, and our actual torso aim
        (obs self.aim, not the commanded one) points inside its body."""
        decision = self.decision
        if decision.get("target") is None or not decision.get("clear"):
            return False
        stats = weapon.get("stats") or {}
        charge_time = stats.get("charge", self.laser.get("charge", 0.75))
        if weapon.get("charge", 0) < charge_time - 1e-6:
            return False
        if decision["distance"] > stats.get("range", self.laser.get("range", 280)):
            return False
        me = obs["self"]
        pos = me["pos"]
        aim = me.get("aim") or []
        if len(aim) < 2:
            return False
        muzzle_z = pos[2] + (me.get("stats") or {}).get("muzzle_height", 7)
        cx, cy, cz = decision["centre"]
        flat = max(math.dist((cx, cy), pos[:2]), 1e-6)
        yaw_error = abs((aim[0] - math.atan2(cy - pos[1], cx - pos[0]) + math.pi) % math.tau - math.pi)
        pitch_error = abs(aim[1] - math.atan2(cz - muzzle_z, flat))
        return (yaw_error <= math.atan2(decision["radius"], flat)
                and pitch_error <= math.atan2(decision["half_height"], flat))


class SwitchCounter:
    """Counts target changes over a sequence of decisions.

    switches:  the id changed although the previous opponent was still listed.
    reversals: a switch back to the id held before the previous switch (A -> B -> A) within
               REVERSAL_S seconds of that previous switch. Reversals are also switches.
    forced:    the id changed because the previous opponent was no longer listed.
    A decision with no game mech listed ends the engagement and clears the history.
    """
    REVERSAL_S = 1.0

    def __init__(self):
        self.decisions = self.engaged = self.engagements = 0
        self.switches = self.reversals = self.forced = 0
        self.previous = None
        self.last_switch = None  # (time, id switched away from)

    def record(self, obs, target):
        self.decisions += 1
        listed = {other["id"] for other in game_mechs(obs)}
        if not listed or target is None:
            self.previous = self.last_switch = None
            return
        self.engaged += 1
        if self.previous is None:
            self.engagements += 1
        elif target != self.previous:
            if self.previous in listed:
                self.switches += 1
                if (self.last_switch is not None and self.last_switch[1] == target
                        and obs["t"] - self.last_switch[0] <= self.REVERSAL_S + 1e-9):
                    self.reversals += 1
                self.last_switch = (obs["t"], self.previous)
            else:
                self.forced += 1
                self.last_switch = None
        self.previous = target

    def summary(self):
        return dict(decisions=self.decisions, engaged=self.engaged, engagements=self.engagements,
                    switches=self.switches, reversals=self.reversals, forced=self.forced)
