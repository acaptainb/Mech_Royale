"""Parameter sweep of the v8 bullet dodge on the dodge trial's closed-loop episodes.

    py tools/dodge_sweep.py [--base <git revision>] [--heldout] [--grid '{"COOLDOWN_S": [...], ...}']

Each variant is the base revision (default: dodge-tuned dd9b731, official 3.10) with constants
of class Dodge (not ShellDodge) replaced, run as a real bot process through tools/dodge_trial.py's
reactive episodes: a gun shooter that leads every bullet at our current velocity, 12 tuning
routes or, with --heldout, the 16 held-out routes. Prints hits taken, hits per second of route,
arrival time, boost energy and zone exits for each variant. Standard library only.
"""
import concurrent.futures as cf
import itertools
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from harness import export

BASE = "dd9b7313b69aa7a9ab655d731acd3774ba4467fc"   # dodge-tuned, official 3.10
GRID = {"COOLDOWN_S": [0.35, 0.5], "MARGIN_M": [0.5, 1.5, 3.0]}


def name_of(params):
    return " ".join(f"{k}={v}" for k, v in sorted(params.items()))


def make_variant(base, out, params):
    folder = out / re.sub(r"[^A-Za-z0-9.]+", "_", name_of(params))
    shutil.copytree(base, folder)
    path = folder / "dodge.py"
    head, sep, tail = path.read_text(encoding="utf-8").partition("class ShellDodge")
    for key, value in params.items():
        head, n = re.subn(rf"(\n    {key} = )[0-9.]+", rf"\g<1>{value}", head)
        assert n == 1, f"{key} not found exactly once in class Dodge"
    path.write_text(head + sep + tail, encoding="utf-8")
    return folder


def run(args):
    folder, heldout = args
    sys.path.insert(0, str(ROOT / "tools"))
    import dodge_trial as dt
    eps = dt.heldout_episodes() if heldout else dt.episodes()
    rows = [dt.react(folder, ep) for ep in eps]
    seconds = sum(r["reached"] or 30.0 for r in rows)
    return dict(hits=sum(r["hits"] for r in rows), rate=sum(r["hits"] for r in rows) / seconds,
                arrival=seconds / len(rows), spent=sum(r["spent"] for r in rows),
                outside=sum(r["outside"] for r in rows), unreached=sum(r["reached"] is None for r in rows))


def main():
    base_rev = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else BASE
    grid = json.loads(sys.argv[sys.argv.index("--grid") + 1]) if "--grid" in sys.argv else GRID
    heldout = "--heldout" in sys.argv
    base, out = export(base_rev), Path(tempfile.mkdtemp(prefix="dodge-sweep-"))
    variants = [dict(zip(grid, combo)) for combo in itertools.product(*grid.values())]
    folders = [make_variant(base, out, v) for v in variants]
    print(f"base {base_rev[:12]}, {'16 held-out' if heldout else '12 tuning'} routes per variant\n")
    print(f"{'variant':36}{'hits':>6}{'hits/s':>8}{'arrival s':>11}{'energy':>8}{'outside':>9}{'unreached':>11}")
    with cf.ProcessPoolExecutor(max_workers=8) as pool:
        for v, r in zip(variants, pool.map(run, [(f, heldout) for f in folders])):
            print(f"{name_of(v):36}{r['hits']:>6}{r['rate']:>8.2f}{r['arrival']:>11.2f}{r['spent']:>8.0f}"
                  f"{r['outside']:>9}{r['unreached']:>11}", flush=True)


if __name__ == "__main__":
    main()
