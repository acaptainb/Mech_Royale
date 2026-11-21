"""Prove the bot that actually runs (natively or in the match container) uses v6 engagement.

    python tools/engagement_probe.py              # runs: python -u bot.py
    python tools/engagement_probe.py --docker     # runs the image verify.py --docker built

Speaks mechfight/1 over stdin/stdout like the server: the recorded hello, then crafted
observations with a passive mech at 30 m and an attacker at 45 m that hit us. The nearest-mech
rule (v5) aims at the passive mech; v6 must aim at the attacker. Standard library only.
"""
import copy
import gzip
import json
import math
import queue
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NAME = "zone-runner-v6"


def main():
    with gzip.open(ROOT / "check/stream.jsonl.gz", "rt") as f:
        hello = json.loads(next(f))
        template = next(json.loads(line) for line in f if '"obs"' in line)
    if "--docker" in sys.argv:
        command = ["docker", "run", "--platform", "linux/amd64", "--rm", "-i", "--network", "none",
                   "--cpus", "1", "--memory", "512m", "--read-only", "--tmpfs", "/tmp:rw,size=64m",
                   "--user", "65534:65534", "mech-first-run"]
    else:
        command = [sys.executable, "-u", str(ROOT / "bot.py")]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               text=True, bufsize=1, cwd=ROOT)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout] and lines.put(None),
                     daemon=True).start()

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def receive():
        line = lines.get(timeout=30)
        if line is None:
            raise SystemExit("bot closed stdout")
        return json.loads(line)

    send(hello)
    ready = receive()
    print("ready:", ready)
    # The open lawn west of the Oval: flat, with clear lines of fire east and north.
    me = [-353.0, -158.0, -5.47]
    template["self"].update(pos=me, in_zone=True)
    template["zone"].update(center=me[:2], radius=400, next_center=me[:2], next_radius=250,
                            shrink_start=200, shrink_end=250)
    passive = [me[0] + 30, me[1], me[2]]           # east, 30 m
    attacker = [me[0], me[1] + 45, me[2]]          # north, 45 m
    results = []
    for k in range(5):
        obs = copy.deepcopy(template)
        obs.update(tick=1000 + 2 * k, t=50 + 0.1 * k, pickups=[], cubes=[], drops=[], offer=None,
                   events=[dict(type="damaged", amount=45, weapon="gun", by=5,
                                bearing=math.pi / 2)] if k == 0 else [],
                   mechs=[dict(id=3, kind="mech", pos=passive, vel=[0, 0, 0], aim=[math.pi / 2, 0],
                               hp=1400, max_hp=1400, cubes=0, weapons=["gun"], charging=False),
                          dict(id=5, kind="mech", pos=attacker, vel=[0, 0, 0], aim=[-math.pi / 2, 0],
                               hp=1400, max_hp=1400, cubes=0, weapons=["gun"], charging=False)])
        send(obs)
        action = receive()
        yaw = action.get("aim", [None])[0]
        results.append((action.get("tick") == obs["tick"], yaw, action.get("fire")))
        print(f"tick {obs['tick']}: aim yaw {yaw}, fire {action.get('fire')}")
    send({"type": "end", "place": 1, "kills": 0})
    process.stdin.close()
    process.wait(timeout=30)
    checks = [
        ("ready name is " + EXPECTED_NAME, ready.get("name") == EXPECTED_NAME),
        ("every action echoes its tick", all(ok for ok, _, _ in results)),
        ("aims at the attacker (north), not the closer passive mech (east)",
         all(yaw is not None and abs(yaw - math.pi / 2) < 0.05 for _, yaw, _ in results)),
        ("fires at it", all(fire and any(fire) for _, _, fire in results)),
        ("exits cleanly after end", process.returncode == 0),
    ]
    for text, ok in checks:
        print(("  ok    " if ok else "  FAIL  ") + text)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


if __name__ == "__main__":
    main()
