"""Run the official checker locally or against a freshly built match container."""
import argparse
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--docker", action="store_true")
args = parser.parse_args()
checker = [sys.executable, "check/check.py"]
bot = [sys.executable, "-u", "bot.py"]
if args.docker:
    subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t",
                    "mech-first-run", "."], cwd=root, check=True)
    checker += ["--map-dir", "/arena"]
    bot = ["docker", "run", "--platform", "linux/amd64", "--rm", "-i",
           "--network", "none", "--cpus", "1", "--memory", "512m", "--read-only",
           "--tmpfs", "/tmp:rw,size=64m", "--user", "65534:65534",
           "--mount", f"type=bind,source={root / 'arena'},target=/arena,readonly",
           "mech-first-run"]
subprocess.run(checker + ["--"] + bot, cwd=root, check=True)
