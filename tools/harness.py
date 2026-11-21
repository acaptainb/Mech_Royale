"""Run a bot as a real process speaking mechfight/1, and export a baseline from git.

Shared by the per-version trials: the candidate is `bot.py` in this working tree, the
baseline is `git archive <revision>` unpacked to a temp folder. Standard library only.
"""
import io
import json
import queue
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "1a0ca394d26fe5e97c60dbac2ded343a2694b114"  # zone-runner-v6, official 2.08


class BotProcess:
    def __init__(self, folder, hello):
        self.process = subprocess.Popen([sys.executable, "-u", "bot.py"], cwd=folder, text=True,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.send(hello)
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


def export(revision=BASELINE):
    folder = Path(tempfile.mkdtemp(prefix="mech-baseline-"))
    archive = subprocess.run(["git", "archive", "--format=tar", revision], cwd=ROOT,
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(folder, filter="data")
    return folder


def plain(action):
    """An action without its tick and debug drawing, for comparing two bots."""
    return {key: value for key, value in action.items() if key not in ("tick", "debug")}
