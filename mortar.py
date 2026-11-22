"""mortar-arc: aim the mortar on its ballistic arc instead of the gun's nearly flat line."""
import math


class MortarArc:
    """While we hold a mortar whose cooldown is 0 and v6 has decided to shoot at its chosen
    opponent (so the line of fire is clear and it is in range), the torso is pitched to the
    low-arc solution that drops the shell on the opponent's body, led by the opponent's
    horizontal velocity over the shell's flight time. The mortar trigger is pressed only once
    the actual torso aim is within PITCH_TOL / YAW_TOL of that solution; the gun trigger is
    off meanwhile. Once the shell is away (cooldown > 0) v6 and lead-shots aim as before.
    Opponents closer than MIN_M (our own splash) or beyond the arc's reach are left to the
    old behaviour."""
    MIN_M = 15.0          # keep our own splash (7 m, half damage to us) well away
    PITCH_TOL = 0.012     # rad; at 120 m one hundredth of a radian moves the impact ~4 m
    YAW_TOL = 0.03        # rad; ~3.6 m sideways at 120 m, inside the 7 m splash
    LEAD_ITERATIONS = 3

    def __init__(self, hello):
        config = hello["config"]
        self.mortar = config.get("weapons", {}).get("mortar", {})
        mech = config.get("mech", {})
        self.height = mech.get("height", 9)
        self.radius = mech.get("radius", 2.5)
        self.size_per_cube = config.get("cubes", {}).get("size_per_cube", 0.05)
        self.arcs = 0         # decisions spent aiming an arc, for local reports
        self.shells = 0       # decisions the mortar trigger was pressed on an arc

    @staticmethod
    def low_arc(speed, gravity, distance, rise):
        """Launch pitch for horizontal `distance` and height change `rise`, or None."""
        disc = speed ** 4 - gravity * (gravity * distance ** 2 + 2 * rise * speed ** 2)
        if disc < 0 or distance <= 0:
            return None
        return math.atan((speed ** 2 - math.sqrt(disc)) / (gravity * distance))

    def solve(self, tube, target):
        """Pitch, yaw and flight time from our tube to a point, allowing for the shell leaving
        3 m out along the aim (radius + 0.5)."""
        speed = self.mortar.get("speed", 72.0)
        gravity = self.mortar.get("gravity", 22.0)
        offset = self.radius + 0.5
        yaw = math.atan2(target[1] - tube[1], target[0] - tube[0])
        flat = math.dist(target[:2], tube[:2])
        pitch = 0.0
        for _ in range(3):
            distance = flat - offset * math.cos(pitch)
            rise = target[2] - (tube[2] + offset * math.sin(pitch))
            solution = self.low_arc(speed, gravity, distance, rise)
            if solution is None:
                return None
            pitch = solution
        flight = (flat - offset * math.cos(pitch)) / (speed * math.cos(pitch))
        return pitch, yaw, flight

    def plan(self, obs, engage):
        """Return {aim, fire} for this decision, or None to leave v6's aim and triggers."""
        me = obs["self"]
        weapons = me.get("weapons") or []
        slot = next((i for i, w in enumerate(weapons[:2]) if w and w.get("kind") == "mortar"), None)
        if slot is None or weapons[slot].get("cooldown", 0) > 1e-9:
            return None
        if not engage.get("fire") or engage.get("target") is None:
            return None
        other = next((m for m in obs.get("mechs") or () if m.get("id") == engage["target"]), None)
        if other is None:
            return None
        pos = me["pos"]
        if math.dist(other["pos"][:2], pos[:2]) < self.MIN_M:
            return None
        stats = me.get("stats") or {}
        tube = [pos[0], pos[1], pos[2] + stats.get("height", self.height) + 0.5]
        scale = 1 + self.size_per_cube * other.get("cubes", 0)
        body = (self.height * scale / 2) if other.get("kind") == "mech" else 1.75
        vx, vy = (other.get("vel") or [0, 0])[:2]
        point = [other["pos"][0], other["pos"][1], other["pos"][2] + body]
        solved = None
        for _ in range(self.LEAD_ITERATIONS):
            solved = self.solve(tube, point)
            if solved is None:
                return None
            flight = solved[2]
            point = [other["pos"][0] + vx * flight, other["pos"][1] + vy * flight, point[2]]
        pitch, yaw, _ = solved
        low, high = stats.get("min_pitch", -0.7), stats.get("max_pitch", 1.3)
        if not low <= pitch <= high:
            return None
        self.arcs += 1
        actual = me.get("aim") or [None, None]
        aligned = (actual[0] is not None and len(actual) > 1
                   and abs((actual[0] - yaw + math.pi) % math.tau - math.pi) <= self.YAW_TOL
                   and abs(actual[1] - pitch) <= self.PITCH_TOL)
        fire = [False, False]
        if aligned:
            fire[slot] = True
            self.shells += 1
        return dict(aim=[yaw, pitch], fire=fire)
