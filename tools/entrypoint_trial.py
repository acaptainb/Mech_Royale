"""Baseline and candidate as real bot processes, from identical starting conditions.

    py tools/entrypoint_trial.py [--baseline <git revision>]

The baseline is exported from git (default: the officially scored 2.08 commit) and the
candidate is this working tree. Each runs `python -u bot.py` and speaks mechfight/1 over
stdin/stdout, exactly like a match. A small closed-loop world answers their actions: laser
charge, cooldown and the auto-fire after hold_s follow the fire commands, and the torso slews
toward the commanded aim at the configured turn and pitch rates. Opponents stand still. A beam
counts as valid when it leaves along the actual torso aim, passes through the target's body
and the line is clear by an exact test against arena/v2 geometry. Standard library only.
"""
import copy
import io
import json
import math
import queue
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import engagement_trial as et  # scenario helpers: frame(), mech(), HOME, COVER_SPOT, Exact

BASELINE = "1a0ca394d26fe5e97c60dbac2ded343a2694b114"  # zone-runner-v6, official 2.08
DT = 0.1
CONFIG = et.HELLO["config"]
LASER = CONFIG["weapons"]["laser"]
MECH = CONFIG["mech"]
EXACT = et.Exact()


class BotProcess:
    def __init__(self, folder):
        self.process = subprocess.Popen([sys.executable, "-u", "bot.py"], cwd=folder, text=True,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.send(et.HELLO)
        self.name = self.receive()["name"]
        self.times = []

    def _read(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self):
        line = self.lines.get(timeout=30)
        if line is None:
            raise RuntimeError("bot closed stdout")
        return json.loads(line)

    def act(self, obs):
        start = time.perf_counter()
        self.send(obs)
        action = self.receive()
        self.times.append(time.perf_counter() - start)
        if action.get("tick") != obs["tick"]:
            raise RuntimeError(f"tick {action.get('tick')} answered for {obs['tick']}")
        return action

    def close(self):
        self.send({"type": "end", "place": 1, "kills": 0})
        self.process.stdin.close()
        return self.process.wait(timeout=30)


def export(revision):
    folder = Path(tempfile.mkdtemp(prefix="mech-baseline-"))
    archive = subprocess.run(["git", "archive", "--format=tar", revision], cwd=ROOT,
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(folder, filter="data")
    return folder


# --- closed-loop world --------------------------------------------------------------------

def beam_hits(origin_pos, aim, target):
    """Does a beam from our muzzle along `aim` pass through the target's body, unobstructed?"""
    ox, oy, oz = origin_pos[0], origin_pos[1], origin_pos[2] + MECH["muzzle_height"]
    yaw, pitch = aim
    dx, dy, dz = math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)
    tx, ty, tz = target["pos"]
    flat = math.hypot(dx, dy)
    along = ((tx - ox) * dx + (ty - oy) * dy) / (flat * flat)
    if along <= 0 or along > LASER["range"]:
        return False
    miss = abs((tx - ox) * dy - (ty - oy) * dx) / flat
    z = oz + along * dz
    radius = MECH["radius"] * (1 + 0.05 * target.get("cubes", 0))
    height = MECH["height"] * (1 + 0.05 * target.get("cubes", 0))
    if miss > radius or not tz <= z <= tz + height:
        return False
    return EXACT.category(origin_pos[:2], target) == "clear"


def run(bot, scenario):
    """Play one scenario against one bot process; return a row per decision."""
    rows = []
    weapons = copy.deepcopy(scenario["weapons"])
    slot = next((i for i, w in enumerate(weapons) if w and w["kind"] == "laser"), None)
    target = scenario["target"]
    bearing = math.atan2(target["pos"][1] - scenario["origin"][1], target["pos"][0] - scenario["origin"][0])
    actual = [bearing + math.radians(scenario.get("aim_off_deg", 0.0)), scenario.get("pitch", 0.0)]
    commanded = list(actual)
    held_full = 0.0
    for k in range(scenario["decisions"]):
        obs = et.frame(1000 + k, [target], origin=scenario["origin"], weapons=weapons)
        obs["self"]["aim"] = [actual[0], actual[1]]
        before = copy.deepcopy(weapons)
        action = bot.act(obs)
        fire = list(action.get("fire") or [False, False])
        beams = []
        if slot is not None:
            laser = weapons[slot]
            pressed = bool(fire[slot])
            if laser["cooldown"] > 0:
                laser["cooldown"] = max(0.0, round(laser["cooldown"] - DT, 6))
            elif pressed:
                if laser["charge"] >= LASER["charge"] - 1e-9:
                    held_full += DT
                laser["charge"] = min(LASER["charge"], round(laser["charge"] + DT, 6))
                if held_full >= LASER["hold_s"] - 1e-9:
                    beams.append(("auto", 1.0, beam_hits(obs["self"]["pos"], actual, target)))
                    laser.update(charge=0.0, cooldown=LASER["cooldown"])
                    held_full = 0.0
            elif laser["charge"] > 0:
                fraction = max(LASER["min_frac"], laser["charge"] / LASER["charge"])
                beams.append(("release", round(fraction, 2), beam_hits(obs["self"]["pos"], actual, target)))
                laser.update(charge=0.0, cooldown=LASER["cooldown"])
                held_full = 0.0
        charging = slot is not None and before[slot]["cooldown"] == 0 and (before[slot]["charge"] > 0 or fire[slot])
        if "aim" in action:
            commanded = list(action["aim"])
        turn = (commanded[0] - actual[0] + math.pi) % math.tau - math.pi
        actual[0] += max(-MECH["turn_rate"] * DT, min(MECH["turn_rate"] * DT, turn))
        lift = commanded[1] - actual[1]
        actual[1] += max(-MECH["pitch_rate"] * DT, min(MECH["pitch_rate"] * DT, lift))
        actual[1] = max(MECH["min_pitch"], min(MECH["max_pitch"], actual[1]))
        rows.append(dict(t=round(k * DT, 1), fire=fire, charge=before[slot]["charge"] if slot is not None else None,
                         yaw_error=math.degrees(abs((obs["self"]["aim"][0] - bearing + math.pi) % math.tau - math.pi)),
                         beams=beams, charging=charging,
                         action={key: value for key, value in action.items() if key not in ("tick", "debug")}))
    return rows


# --- scenarios ----------------------------------------------------------------------------

def gun():
    return et.gun()


def laser(charge, cooldown=0.0):
    return dict(et.laser(charge), cooldown=cooldown)


def opponent(bearing, distance, origin=et.HOME, aim_at_us=False):
    return et.mech(3, bearing, distance, origin=origin, aim_at_us=aim_at_us)


FAR = next(b for b in range(0, 360, 5) if et.clear_from(et.HOME, b, 300))
COVER_ORIGIN, COVER_BEARING, COVER_DISTANCE, _ = et.COVER_SPOT

SCENARIOS = [
    dict(name="full charge, clear, 30 m", activates=True,
         weapons=[gun(), laser(LASER["charge"])], target=opponent(0, 30), origin=et.HOME, decisions=40),
    dict(name="partial charge (0.4 s), clear, 30 m", activates=True,
         weapons=[gun(), laser(0.4)], target=opponent(0, 30), origin=et.HOME, decisions=40),
    dict(name="full charge, blocked view", activates=False,
         weapons=[gun(), laser(LASER["charge"])], origin=COVER_ORIGIN, decisions=40,
         target=opponent(COVER_BEARING, COVER_DISTANCE, origin=COVER_ORIGIN, aim_at_us=True)),
    dict(name="full charge, torso 40 deg off", activates=True, aim_off_deg=40.0,
         weapons=[gun(), laser(LASER["charge"])], target=opponent(0, 30), origin=et.HOME, decisions=40),
    dict(name="gun-only loadout", activates=False,
         weapons=[gun(), None], target=opponent(0, 30), origin=et.HOME, decisions=40),
    dict(name="full charge, beyond laser range (300 m)", activates=False,
         weapons=[gun(), laser(LASER["charge"])], target=opponent(FAR, 300, aim_at_us=True),
         origin=et.HOME, decisions=40),
    dict(name="empty laser, torso 90 deg off, 60 m", activates=True, aim_off_deg=90.0,
         weapons=[gun(), laser(0.0)], target=opponent(0, 60, aim_at_us=True), origin=et.HOME, decisions=60),
]


def first_valid(rows):
    return next((row["t"] for row in rows if any(valid for _, _, valid in row["beams"])), None)


def releases(rows):
    return [(row["t"], b) for row in rows for b in row["beams"] if b[0] == "release"]


def check(scenario, base, cand):
    """Expectations for the v7 laser release."""
    name = scenario["name"]
    if not scenario["activates"]:
        return all(a["action"] == b["action"] for a, b in zip(base, cand)), "identical actions on every decision"
    if name.startswith("full charge, clear"):
        ok = (base[0]["fire"] == [True, True] and cand[0]["fire"] == [True, False]
              and first_valid(cand) == 0.0)
        return ok, "baseline holds both triggers; candidate releases the laser on decision 0, gun still firing"
    if name.startswith("partial charge"):
        early = [b for t, b in releases(cand) if b[1] < 1.0]
        ok = cand[0]["fire"] == base[0]["fire"] == [True, True] and not early and first_valid(cand) is not None
        return ok, "no release before the charge is full; released once it is"
    if name.startswith("full charge, torso"):
        first = releases(cand)[0] if releases(cand) else None
        ok = (cand[0]["fire"] == base[0]["fire"] and first is not None
              and all(valid for _, (_, _, valid) in releases(cand)))
        return ok, "holds while misaligned; every release lands"
    if name.startswith("empty laser"):
        ok = first_valid(cand) is not None and (first_valid(base) is None or first_valid(cand) < first_valid(base))
        return ok, "first valid beam sooner than the baseline's"
    return False, "no expectation"


def summary(rows):
    beams = [b for row in rows for b in row["beams"]]
    return (f"{sum(v for _, _, v in beams)}/{len(beams)}",
            "-" if first_valid(rows) is None else f"{first_valid(rows):.1f}",
            sum(row["charging"] for row in rows))


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    failures, traces = [], {}
    print(f"baseline {revision[:12]} (exported to a temp folder), candidate: this working tree\n")
    print(f"{'scenario':40}{'decision 0 fire':>22}{'valid/beams':>14}{'1st valid s':>13}{'charging':>10}  check")
    print(f"{'':40}{'base | cand':>22}{'base | cand':>14}{'base | cand':>13}{'base|cand':>10}")
    for scenario in SCENARIOS:
        base_bot, cand_bot = BotProcess(folder), BotProcess(ROOT)
        base, cand = run(base_bot, scenario), run(cand_bot, scenario)
        base_bot.close()
        cand_bot.close()
        ok, expectation = check(scenario, base, cand)
        (bv, bf, bc), (cv, cf, cc) = summary(base), summary(cand)
        print(f"{scenario['name']:40}{str(base[0]['fire']):>12} | {str(cand[0]['fire']):<10}{bv:>6} | {cv:<6}"
              f"{bf:>6} | {cf:<6}{bc:>4} | {cc:<4} {'ok  ' if ok else 'FAIL'} {expectation}")
        traces[scenario["name"]] = (base, cand)
        if not ok:
            failures.append(scenario["name"])
    print("\ncolumns: fire command on the first decision; beams that hit / beams fired (release or the game's"
          "\nauto-fire after hold_s); time of the first beam that hit; decisions spent charging (half speed).")

    base, cand = traces["full charge, clear, 30 m"]
    print("\ntrace, full charge with a clear opponent 30 m ahead (torso already on it):")
    print("     t  charge  torso err   baseline fire   beam        candidate fire   beam")
    for k in (0, 1, 2, 3, 17, 18, 19, 20, 21):
        b, c = base[k], cand[k]
        fmt = lambda beams: ",".join(f"{kind}{'+hit' if valid else ''}" for kind, _, valid in beams) or "-"
        print(f"  {b['t']:4.1f}  {b['charge']:.2f} | {c['charge']:.2f}  {b['yaw_error']:5.1f}   "
              f"{str(b['fire']):14}  {fmt(b['beams']):10}  {str(c['fire']):15}  {fmt(c['beams'])}")

    # Control on the standard recording: no laser is ever held, so both must answer identically.
    base_bot, cand_bot = BotProcess(folder), BotProcess(ROOT)
    differing = 0
    for obs in et.STREAM:
        a, b = base_bot.act(copy.deepcopy(obs)), cand_bot.act(copy.deepcopy(obs))
        # This trial is about the laser trigger: later versions may aim or move differently.
        differing += a.get("fire") != b.get("fire")
    p99 = sorted(cand_bot.times)[int(0.99 * len(cand_bot.times))] * 1e3
    base_bot.close()
    cand_bot.close()
    print(f"\nrecording control: fire commands differ on {differing} of {len(et.STREAM)} decisions"
          f" (candidate round trip p99 {p99:.1f} ms through stdin/stdout)")
    if differing:
        failures.append("recording control")
    if failures:
        print("\nFAIL:", ", ".join(failures))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
