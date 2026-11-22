"""rooftop: jet onto a nearby flat roof inside the next zone circle and camp there.

roofs.json (tools/build_roofs.py) lists flat roofs 8-45 m above the ground beside them, each
with a camp spot well in from the edge and climb points on straight walls. During ordinary
zone movement with time to spare, nothing to fight and no pickup detour, the mech walks to the
nearest climb point's stage within RANGE_M, runs at the wall, jumps and jets until its feet
clear the roof, walks to the camp spot and holds there. It walks back off the roof at the same
wall once the camp spot stops being safely inside the zone, or the zone return becomes urgent.
Aim and fire are untouched. A climb that fails bans that roof for BAN_S.
"""
import json
import math
from pathlib import Path

from navigation import Navigator

ROOT = Path(__file__).resolve().parent


class Rooftop:
    RANGE_M = 80.0          # straight-line distance to a climb point's stage
    ZONE_MARGIN_M = 12.0    # a camp spot this far inside the next and current circles qualifies
    LEAVE_MARGIN_M = 6.0    # leave once it is less than this inside either circle
    RESERVE = 15.0          # energy kept on top of what the climb needs
    CLEAR_M = 0.8           # stop jetting once the feet are this far above the roof
    CHOOSE_EVERY_S = 0.5
    RETRY_S = 10.0          # no new trip for this long after one is given up
    BAN_S = 120.0           # a roof whose climb failed is skipped for this long
    RUN_S = 2.5
    WAIT_S = 8.0
    CLIMB_S = 6.0
    CROSS_S = 10.0
    LEAVE_S = 8.0

    def __init__(self, hello):
        mech = hello["config"]["mech"]
        self.walk = mech.get("walk_speed", 11.7)
        # Jet energy per metre climbed: jet_drain at max_rise_speed.
        self.per_m = mech.get("jet_drain", 15) / max(1.0, mech.get("max_rise_speed", 10))
        data = json.loads((ROOT / "roofs.json").read_text())
        self.ox, self.oy = data["origin"]
        self.cell, self.nx = data["cell"], data["nx"]
        self.roofs = data["roofs"]
        self.cells = {}
        for roof in self.roofs:
            for j, i0, i1 in roof["runs"]:
                for i in range(i0, i1 + 1):
                    self.cells[j * self.nx + i] = roof["id"]
        self.feet = [(roof, foot) for roof in self.roofs for foot in roof["feet"]]
        # Its own planner, so the zone route's incremental search is left intact.
        self.nav = Navigator()
        self.entry = None       # the navigation node nearest the stage point
        self.phase = "idle"
        self.roof = self.foot = None
        self.since = self.trip_start = 0.0
        self.next_choose = -1.0
        self.retry_until = -1.0
        self.banned = {}
        self.leg = 0            # leave: 0 walking to the landing point, 1 over the edge
        self.last_t = None
        # Counters for the local reports; they never influence a decision.
        self.counts = {}
        self.camp_s = 0.0
        self.roof_times = []    # seconds from the start of a trip to standing on the roof

    def count(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1

    # --- geometry ------------------------------------------------------------------------

    def roof_at(self, x, y):
        i, j = int((x - self.ox) / self.cell), int((y - self.oy) / self.cell)
        return self.cells.get(j * self.nx + i) if 0 <= i < self.nx and j >= 0 else None

    def on_roof(self, me, roof):
        x, y, z = me["pos"]
        return self.roof_at(x, y) == roof["id"] and z >= roof["top"] - 1.0

    def safe(self, zone, at, margin):
        return (math.dist(at, zone["next_center"]) + margin <= zone["next_radius"]
                and math.dist(at, zone["center"]) + margin <= zone["radius"])

    def need(self, foot):
        return self.per_m * (foot["h"] + self.CLEAR_M + 1.5) + self.RESERVE

    @staticmethod
    def toward(pos, at):
        dx, dy = at[0] - pos[0], at[1] - pos[1]
        length = math.hypot(dx, dy)
        return [dx / length, dy / length] if length > 1e-6 else [0.0, 0.0]

    # --- decisions -----------------------------------------------------------------------

    @property
    def active(self):
        return self.phase != "idle"

    @property
    def dodge_ok(self):
        """The v8 dodge may steer: never during the run, the climb or the walk off the roof."""
        return self.phase in ("idle", "approach", "cross", "camp")

    def end(self, now, reason, ban=False, retry=None):
        self.count(reason)
        if ban and self.roof is not None:
            self.banned[self.roof["id"]] = now + self.BAN_S
        self.retry_until = now + (self.RETRY_S if retry is None else retry)
        self.phase, self.roof, self.foot = "idle", None, None

    def choose(self, obs, mode, urgent, recovering, pickup):
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        if (mode != "zone" or urgent or recovering or pickup is not None or not me.get("grounded", True)
                or now < self.retry_until or now < self.next_choose
                or any(other.get("kind") == "mech" for other in obs.get("mechs") or ())):
            return False
        self.next_choose = now + self.CHOOSE_EVERY_S
        x, y, z = me["pos"]
        here = self.roof_at(x, y)
        if here is not None:
            roof = self.roofs[here]
            if z >= roof["top"] - 1.0 and self.safe(zone, roof["camp"], self.ZONE_MARGIN_M):
                # Already standing on a listed roof (a rooftop spawn): walk to its camp spot.
                self.roof = roof
                self.foot = min(roof["feet"], key=lambda f: math.dist(f["stage"], zone["next_center"]))
                self.phase, self.since, self.trip_start = "cross", now, now
                self.count("trip from on the roof")
                return True
        best = None
        for roof, foot in self.feet:
            distance = math.dist((x, y), foot["stage"])
            if (distance > self.RANGE_M or self.banned.get(roof["id"], -1) > now
                    or self.need(foot) > me.get("max_energy", 100)
                    or not self.safe(zone, roof["camp"], self.ZONE_MARGIN_M)):
                continue
            if best is None or distance < best[0]:
                best = (distance, roof, foot)
        if best is None:
            return False
        distance, self.roof, self.foot = best
        self.entry = self.nav.point(self.nav.snap(self.foot["stage"]))
        self.leg = 0
        self.phase, self.since, self.trip_start = "approach", now, now
        self.limit = now + 2 * distance / self.walk + 6
        self.count("trip started")
        return True

    def steer(self, obs, action, mode, urgent, recovering, pickup):
        """Set move, jump and boost while a rooftop trip is under way. Returns True then."""
        me, zone, now = obs["self"], obs["zone"], obs["t"]
        if self.phase == "camp" and self.last_t is not None:
            self.camp_s += now - self.last_t
        self.last_t = now
        if self.phase == "idle" and not self.choose(obs, mode, urgent, recovering, pickup):
            return False
        x, y, z = me["pos"]
        roof, foot = self.roof, self.foot
        stage, contact, land, u = foot["stage"], foot["contact"], foot["land"], foot["dir"]
        top = roof["top"]

        if self.phase == "approach":
            if urgent or mode not in ("zone",) or pickup is not None:
                self.end(now, "approach given up: objective changed")
                return False
            if any(other.get("kind") == "mech" for other in obs.get("mechs") or ()):
                self.end(now, "approach given up: opponent listed")
                return False
            if now > self.limit:
                self.end(now, "approach given up: timeout", ban=True)
                return False
            if math.dist((x, y), stage) <= 1.5:
                self.phase, self.since = "wait", now
            else:
                # The planner leads to the node nearest the stage point; the last few metres
                # to the stage point are open ground (checked when roofs.json was built).
                if self.leg == 0 and (math.dist((x, y), self.entry) <= 2.5 or self.nav.clear_segment(me["pos"], stage)):
                    self.leg = 1
                target = stage if self.leg == 1 else self.nav.waypoint(me["pos"], stage)
                action["move"] = self.toward((x, y), target)
                action["jump"] = False
                action["boost"] = False
                return True

        if self.phase == "wait":
            if urgent:
                self.end(now, "wait given up: zone")
                return False
            if me["energy"] >= self.need(foot):
                self.phase, self.since = "run", now
            elif now - self.since > self.WAIT_S:
                self.end(now, "wait given up: energy", ban=True)
                return False
            else:
                action.update(move=self.toward((x, y), stage) if math.dist((x, y), stage) > 0.6 else [0, 0],
                              jump=False, boost=False)
                return True

        if self.phase == "run":
            along = (contact[0] - x) * u[0] + (contact[1] - y) * u[1]
            vel = me.get("vel") or [0, 0, 0]
            stalled = now - self.since >= 0.4 and vel[0] * u[0] + vel[1] * u[1] < 1.5
            if now - self.since > self.RUN_S:
                self.end(now, "run given up: timeout", ban=True)
                return False
            if along <= 0.4 or stalled:
                self.phase, self.since = "climb", now
                self.count("climb started")
                action.update(move=list(u), jump=True, boost=True)
                return True
            action.update(move=list(u), jump=False, boost=False)
            return True

        if self.phase == "climb":
            grounded = me.get("grounded", False)
            if grounded and self.on_roof(me, roof):
                self.phase, self.since = "cross", now
                self.count("climb completed")
                self.roof_times.append(round(now - self.trip_start, 1))
            elif now - self.since > self.CLIMB_S:
                self.end(now, "climb aborted: timeout", ban=True)
                return False
            elif grounded and z < top - 3.0:
                if now - self.since <= 0.5:
                    action.update(move=list(u), jump=True, boost=True)   # the jump did not take
                    return True
                self.end(now, "climb aborted: fell back", ban=True)
                return False
            elif me["energy"] <= 1.0 and z < top:
                self.end(now, "climb aborted: out of energy", ban=True)
                action.update(boost=False, jump=False)
                return True
            else:
                action.update(move=list(u), jump=False, boost=z < top + self.CLEAR_M)
                return True

        if self.phase == "cross":
            if not self.on_roof(me, roof):
                if me.get("grounded", False) and z < top - 1.5:
                    self.end(now, "fell off the roof", ban=True)
                    return False
                action.update(move=list(u), jump=False, boost=False)
                return True
            if math.dist((x, y), roof["camp"]) <= 1.0 or now - self.since > self.CROSS_S:
                self.phase, self.since = "camp", now
                self.count("camp started")
            else:
                action.update(move=self.toward((x, y), roof["camp"]), jump=False, boost=False)
                return True

        if self.phase == "camp":
            if not self.on_roof(me, roof):
                self.end(now, "fell off the roof", ban=True)
                return False
            if urgent or mode == "return" or not me.get("in_zone", True) \
                    or not self.safe(zone, roof["camp"], self.LEAVE_MARGIN_M):
                self.phase, self.since, self.leg = "leave", now, 0
                self.count("left: zone")
            else:
                action.update(move=[0, 0], jump=False, boost=False)
                return True

        if self.phase == "leave":
            if me.get("grounded", False) and z < top - 3.0:
                self.end(now, "back on the ground", retry=5.0)
                return False
            if now - self.since > self.LEAVE_S:
                self.end(now, "leave timeout", retry=5.0)
                return False
            if self.leg == 0 and math.dist((x, y), land) <= 1.0:
                self.leg = 1
            target = land if self.leg == 0 else stage
            action.update(move=self.toward((x, y), target), jump=False, boost=False)
            return True
        return False
