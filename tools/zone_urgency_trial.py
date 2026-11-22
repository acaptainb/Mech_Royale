"""squad-zone: the zone takes the movement only on a deadline. Parent and this tree as real bots.

    py tools/zone_urgency_trial.py [--baseline <git revision>] [--quick]

The parent (default fea757a, squad-all-fixed) treats the whole shrink window as an urgent return
once the bot is outside the next circle (and the whole last phase): no fight move, no bullet or
shell dodge, no laser sidestep. This tree hands the movement to the zone only on squad_econ.py's
deadline (zone must): there the shell dodge still acts and the bullet dodge is blended into the
walk; on hurry (outside the current circle, or the walk ends at or after the deadline) both bots
go straight home with boost and no dodge.

1. Scripted decisions in practice mode (t from 30 s, open lawn), both bots as `python -u bot.py`
   on the same frames (velocity follows each bot's own last move):
   - outside the next circle with plenty of time: a bullet on course (the candidate dodges, the
     parent walks on), an engaged hunter (the candidate fights, the parent walks), both;
   - outside the next circle with a tight deadline (zone must, not hurry): both walk home; a
     mortar shell landing on the route (only the candidate steps out), a bullet on course from
     the side and from ahead (the candidate's blended dodge keeps progress toward the goal);
   - hurry: outside the current circle, and inside it with the walk ending after the deadline,
     each with a bullet and a shell in the air: identical answers, home with boost;
   - control: the same frames before 20 s are identical.
2. Closed-loop zone run (tools/squad_move_trial.py's world with a shrinking circle and 60 HP/s
   zone damage): a gun hunter holding 100 m from us shoots while we walk 150 m to the goal in a
   new circle, with a comfortable deadline and again with a tight one (zone must from the start).
   Hits taken (before entering the circle and over 60 s), arrival in the circle and at the goal,
   decisions outside the circle, the kill and our death, for the parent and this tree.
   --quick runs two starts with one seed instead of four starts with two seeds.
Standard library only.
"""
import copy
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import dodge_trial as dt
import engagement_trial as et
import practice_trial as pt
import shell_dodge_trial as st
import squad_move_trial as smt
from harness import BotProcess, export, plain
from dodge import ShellDodge
from navigation import Navigator
from squad_econ import ZonePlan

BASELINE = "fea757a8d484bae92c488810c00f0c401a5911a5"  # squad-all-fixed
MECH = et.HELLO["config"]["mech"]
GUN = et.HELLO["config"]["weapons"]["gun"]
HOME = list(et.HOME)
FAILURES = []


def check(ok, name):
    if not ok:
        FAILURES.append(name)
    return "ok  " if ok else "FAIL"


def unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n > 1e-9 else (0.0, 0.0)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


# --- 1. scripted decisions --------------------------------------------------------------------

def scripted(folder, make, n, t0=30.0):
    """Decisions make(k, vel) for k < n through the real entrypoint; the velocity follows the
    bot's own last move and the torso its last aim. Returns [(obs, action, debug label)]."""
    bot = BotProcess(folder, et.HELLO)
    rows, last = [], {}
    for k in range(n):
        move = last.get("move") or [0.0, 0.0]
        length = math.hypot(*move)
        speed = MECH["boost_speed"] if last.get("boost") else MECH["walk_speed"]
        vel = [move[0] * speed / max(1.0, length), move[1] * speed / max(1.0, length)]
        obs = make(k, vel)
        obs["t"] = round(t0 + 0.1 * k, 2)
        obs["self"]["vel"] = [vel[0], vel[1], 0.0]
        if last.get("aim"):
            obs["self"]["aim"] = list(last["aim"])
        action = bot.act(obs)
        rows.append((obs, action, (action.get("debug") or {}).get("label", "")))
        last = action
    bot.close()
    return rows


def plan_state(zone, t, pos=HOME, in_zone=True):
    """squad_econ.ZonePlan's flags for one frame (the candidate's own rule), for the report."""
    obs = pt.pframe(0, zone=zone, in_zone=in_zone)
    obs["t"] = t
    obs["self"]["pos"] = [pos[0], pos[1], et.ground(*pos[:2])]
    plan = ZonePlan(Navigator())
    return plan.update(obs)


def pick_end(start, want, ks, z_dir, distance=120.0, radius=60.0, longest=False):
    """A shrink end time whose deadline gives the ZonePlan flags `want` on every decision in ks
    (the shortest such shrink, or the longest one)."""
    centre = pt.at(HOME, z_dir, distance)[:2]
    tenths = range(20, 1200)
    for tenth in (reversed(tenths) if longest else tenths):
        end = start + tenth / 10
        zone = dict(center=HOME, radius=400.0, next_center=centre, next_radius=radius, shrink_start=start,
                    shrink_end=end)
        states = [plan_state(zone, round(30.0 + 0.1 * k, 2)) for k in ks]
        if all(want(s) for s in states):
            return zone, states[0]
    raise RuntimeError("no shrink end gives the wanted flags")


def bullet_for(key, vel, bearing, distance=150.0):
    """A gun bullet `distance` m out on `bearing`, led to hit us on our current velocity."""
    return dt.bullet_at(key, HOME, vel, distance, bearing)


def shell_for(key, vel, bearing, flight_left=1.2):
    """A mortar shell landing on our route (where our velocity takes us) in `flight_left` s."""
    where = [HOME[0] + vel[0] * flight_left, HOME[1] + vel[1] * flight_left]
    return st.shell_at(key, where, flight_left, bearing_deg=bearing)


def blast(obs, action):
    """Predicted damage from the frame's mortar shells when following `action`'s move and boost,
    by the shell dodge's own flight and splash model (dodge.py)."""
    model = ShellDodge(et.HELLO, dt.GRID, smt.COVER)
    me = obs["self"]
    stats = me.get("stats") or {}
    flights = [model.flight(s) for s in obs["projectiles"] if s.get("kind") == "mortar"]
    steps = max(len(samples) for samples, _ in flights) - 1
    move = unit(action["move"])
    ours = model.path(me, move, bool(action.get("boost")), steps)
    return sum(model.harm(samples, landed, ours, me["pos"][2], stats.get("radius", 2.5), stats.get("height", 9))
               for samples, landed in flights)


def fmt(v):
    return f"[{v[0]:+.2f},{v[1]:+.2f}]"


def scripted_cases(folder):
    print("1. scripted decisions in practice mode (open lawn at t = 30 s; the debug label names the rule)")
    z_dir, _ = dt.clear_heading(HOME, 130)
    centre = pt.at(HOME, z_dir, 120)[:2]
    toward = unit((centre[0] - HOME[0], centre[1] - HOME[1]))
    hunter = pt.mech(5, HOME, pt.OPEN, 100, aim_at_us=True)
    N, AT = 8, 5            # decisions per case; the threat appears on decision AT

    def pair(make, n=N, t0=30.0):
        return scripted(folder, make, n, t0), scripted(ROOT, make, n, t0)

    def row(rows, k=AT):
        return rows[k][1], rows[k][2]

    plenty = dict(center=HOME, radius=400.0, next_center=centre, next_radius=60.0, shrink_start=35.0, shrink_end=95.0)
    s = plan_state(plenty, 30.0)
    print(f"   plenty of time: next circle {math.dist(HOME, centre) - 60:.0f} m away, shrink 35-95 s;"
          f" candidate plan: must {s['must']}, should {s['should']}, hurry {s['hurry']}"
          f" (deadline {s['deadline']:.1f} s, travel {s['travel']:.1f} s)")
    side = z_dir + 45       # the bullet comes in at 45 deg to the walk, so a step across it is not the walk
    base, cand = pair(lambda k, vel: pt.pframe(k, zone=plenty, projectiles=[bullet_for(9101, vel, side)] if k == AT else []))
    (a, la), (b, lb) = row(base), row(cand)
    bv = unit(cand[AT][0]["projectiles"][0]["vel"][:2])
    ok = abs(dot(unit(b["move"]), bv)) < 0.2 and dot(unit(a["move"]), toward) > 0.9 and abs(dot(unit(a["move"]), bv)) > 0.5
    print(f"   {check(ok, 'plenty: bullet dodged')} bullet on course from 45 deg off the walk: parent '{la}' {fmt(a['move'])}"
          f" (walks on), candidate {fmt(b['move'])} boost {b.get('boost')} (steps across the bullet)")
    base, cand = pair(lambda k, vel: pt.pframe(k, [hunter], zone=plenty))
    lab = lambda rows: sorted({label for _, _, label in rows})
    ok = all(l.startswith("squad fight") for _, _, l in cand) and not any(l.startswith("squad fight") for _, _, l in base)
    print(f"   {check(ok, 'plenty: hunter fought')} an engaged hunter 100 m away: parent {lab(base)},"
          f" candidate {lab(cand)}")
    base, cand = pair(lambda k, vel: pt.pframe(k, [hunter], zone=plenty,
                                               projectiles=[bullet_for(9102, vel, side)] if k == AT else []))
    (a, la), (b, lb) = row(base), row(cand)
    bv = unit(cand[AT][0]["projectiles"][0]["vel"][:2])
    ok = abs(dot(unit(b["move"]), bv)) < 0.2 and abs(dot(unit(a["move"]), bv)) > 0.5
    print(f"   {check(ok, 'plenty: hunter and bullet')} the hunter and a bullet on course: parent '{la}' {fmt(a['move'])},"
          f" candidate '{lb}' {fmt(b['move'])} (dodges)")

    ks = range(0, N)
    tight, s = pick_end(32.0, lambda s: s["must"] and not s["hurry"], ks, z_dir)
    print(f"   tight deadline: shrink 32-{tight['shrink_end']:.1f} s; candidate plan: must {s['must']}, hurry {s['hurry']}"
          f" (deadline {s['deadline']:.1f} s, travel {s['travel']:.1f} s at t = 30 s)")
    base, cand = pair(lambda k, vel: pt.pframe(k, zone=tight))
    ok = (all(l.startswith("squad zone must") for _, _, l in base + cand)
          and all(dot(unit(r[1]["move"]), toward) > 0.9 for r in base + cand)
          and all(plain(x[1]) == plain(y[1]) for x, y in zip(base, cand)))
    print(f"   {check(ok, 'tight: both head home')} nothing in the air: both walk home on every decision, identical"
          f" answers ({lab(cand)}, boost {cand[-1][1].get('boost')})")
    base, cand = pair(lambda k, vel: pt.pframe(k, zone=tight, projectiles=[shell_for(9201, vel, z_dir + 90)] if k == AT else []))
    (a, la), (b, lb) = row(base), row(cand)
    hurt_a, hurt_b = blast(cand[AT][0], a), blast(cand[AT][0], b)
    ok = (la.startswith("squad zone must") and lb.startswith("squad zone must") and dot(unit(a["move"]), toward) > 0.9
          and b["move"] != a["move"] and hurt_a > 0 and hurt_b < hurt_a - 10)
    print(f"   {check(ok, 'tight: shell dodge')} a mortar shell landing on the route in 1.2 s: parent {fmt(a['move'])}"
          f" (predicted blast damage {hurt_a:.0f}), candidate {fmt(b['move'])} boost {b.get('boost')}"
          f" (steps out: {hurt_b:.0f})")
    for name, bearing in (("from the side", z_dir + 90), ("from 30 deg off ahead", z_dir + 30)):
        base, cand = pair(lambda k, vel: pt.pframe(k, zone=tight,
                                                   projectiles=[bullet_for(9301, vel, bearing)] if k == AT else []))
        (a, la), (b, lb) = row(base), row(cand)
        bv = unit(cand[AT][0]["projectiles"][0]["vel"][:2])
        progress = dot(unit(b["move"]), toward)
        ok = ((b["move"], b.get("boost")) != (a["move"], a.get("boost")) and progress > 0.3
              and abs(math.hypot(*b["move"]) - 1) < 1e-6 and dot(unit(a["move"]), toward) > 0.9)
        print(f"   {check(ok, 'tight: blended bullet dodge ' + name)} a bullet on course {name}: parent {fmt(a['move'])}"
              f" boost {a.get('boost')},"
              f" candidate {fmt(b['move'])} boost {b.get('boost')} (progress toward the goal {progress:+.2f}, across the bullet"
              f" {abs(dot(unit(b['move']), (-bv[1], bv[0]))):.2f})")

    far = pt.at(HOME, z_dir, 300)[:2]
    outside = dict(center=far, radius=150.0, next_center=far, next_radius=100.0, shrink_start=1000.0, shrink_end=1050.0)
    out_dir = unit((far[0] - HOME[0], far[1] - HOME[1]))
    hurry, s = pick_end(31.0, lambda s: s["hurry"] and s["deadline"] < math.inf, ks, z_dir, longest=True)
    print(f"   hurry inside the current circle: shrink 31-{hurry['shrink_end']:.1f} s (deadline {s['deadline']:.1f} s,"
          f" travel {s['travel']:.1f} s)")
    for name, zone, in_zone, home in (("outside the current circle", outside, False, out_dir),
                                      ("inside it, the walk ends after the deadline", hurry, True, toward)):
        base, cand = pair(lambda k, vel: pt.pframe(k, zone=zone, in_zone=in_zone,
                                                   projectiles=[bullet_for(9401, vel, z_dir + 90),
                                                                shell_for(9402, vel, z_dir - 90)] if k >= AT - 1 else []))
        same = all(plain(x[1]) == plain(y[1]) for x, y in zip(base, cand))
        # Home is the route the planner gives (its first steps may be diagonal on the grid); the move
        # can be zero for a decision or two while the route is searched.
        homeward = (all(r[1].get("boost") for r in cand)
                    and all(dot(unit(r[1]["move"]), home) > 0.85 for r in cand[AT - 1:]))
        ok = same and homeward
        print(f"   {check(ok, 'hurry: ' + name)} {name}, a bullet and a shell on us: identical {same};"
              f" candidate straight home with boost on every decision {homeward} ({lab(cand)})")

    base, cand = pair(lambda k, vel: pt.pframe(k, [hunter], zone=plenty,
                                               projectiles=[bullet_for(9501, vel, side)] if k == AT else []), t0=5.0)
    same = all(plain(x[1]) == plain(y[1]) for x, y in zip(base, cand))
    print(f"   {check(same, 'control: before 20 s')} control: the hunter-and-bullet frames at t = 5 s (before practice"
          f" mode): identical {same}")


# --- 2. closed-loop zone run ------------------------------------------------------------------

def zone_runs_spots(count):
    """Starts with a clear, walkable straight line 190 m long and a walkable hunter start 100 m
    to one side of it, in sight of the start."""
    starts = [tuple(HOME)] + [dt.GRID.point(i) for i in range(0, len(dt.GRID.free), 89) if dt.GRID.free[i]]
    out = []
    for origin in starts:
        if any(math.dist(origin, o) < 150 for o, _, _ in out):
            continue
        for bearing in range(0, 360, 15):
            end = smt.point(origin, bearing, 190)
            if not (dt.walkable(end) and dt.GRID.clear_segment(origin, end)):
                continue
            spot = None
            for turn in (90, -90, 60, -60, 120, -120):
                p = smt.point(origin, bearing + turn, 100)
                if dt.walkable(p) and smt.sees(p, origin) and smt.sees(origin, p):
                    spot = p
                    break
            if spot is not None:
                out.append((origin, bearing, spot))
                break
        if len(out) == count:
            break
    return out


def shrinking(centre, t0, r0=260.0, r1=60.0, start=10.0, end=100.0, dps=60.0):
    """Concentric circles: r0 until t0 + start, then down to r1 by t0 + end."""
    def zone(now):
        f = min(1.0, max(0.0, (now - (t0 + start)) / (end - start)))
        return dict(center=list(centre), radius=r0 + f * (r1 - r0), next_center=list(centre), next_radius=r1,
                    shrink_start=t0 + start, shrink_end=t0 + end, dps=dps)
    return zone


def zone_run(folder, origin, bearing, spot, seed, start, end, seconds=60.0):
    t0 = smt.T0
    centre = smt.point(origin, bearing, 187.0)   # next radius 60: the goal on its inner circle is 150 m away
    zone = shrinking(centre, t0, start=start, end=end)
    shooter = smt.hunter(5, spot, mode="hunt", standoff=100.0)
    r = smt.run(folder, origin, [shooter], seconds=seconds, t0=t0, zone=zone, zone_damage=True, seed=seed)
    inside = next((row["t"] - t0 for row in r["rows"] if math.dist(row["pos"], centre) <= 60.0), None)
    goal = next((row["t"] - t0 for row in r["rows"] if math.dist(row["pos"], centre) <= 40.0), None)
    early = sum(1 for t in r["hit_times"] if inside is None or t - t0 < inside)
    out = sum(1 for row in r["rows"] if not row["in_zone"])
    modes = {}
    for row in r["rows"]:
        if inside is None or row["t"] - t0 < inside:
            key = " ".join((row["mode"] or "-").split()[:2]) if (row["mode"] or "").startswith("zone") \
                else (row["mode"] or "-").split()[0]
            modes[key] = modes.get(key, 0) + 1
    return dict(hits=r["hits"], early=early, inside=inside, goal=goal, outside=out, zone=r["zone_taken"],
                dealt=r["dealt"], kills=r["kills"], kill=r["kill_times"][0] if r["kill_times"] else None,
                died=r["died"], modes=modes)


def zone_runs(folder, quick=False):
    print("\n2. closed-loop zone run: walk 150 m to the goal of a new circle (next radius 60 m, the goal on its"
          " inner circle\n   at 37 m from the centre) while a gun hunter (1400 HP, our fire can kill it) holds 100 m"
          " from us and shoots;\n   zone damage 60 HP/s outside the circle; 60 s from t = 30 s")
    spots = zone_runs_spots(2 if quick else 4)
    seeds = (1,) if quick else (1, 2)
    show = lambda v: "-" if v is None else f"{v:.1f}"
    two = lambda a, b: f"{a} | {b}"
    mean = lambda v: sum(v) / len(v) if v else float("nan")
    totals = {}
    for start, end, title in ((10.0, 100.0, "comfortable deadline: about 40 s at the start for a 23 s walk by the"
                                            " plan's estimate (shrink 10-100 s)"),
                              (5.0, 65.0, "tight deadline: zone must from the start, not hurry (shrink 5-65 s)")):
        print(f"\n   {title}")
        print(f"   {'run':16}{'hits before':>13}{'hits':>10}{'in circle at s':>16}{'at goal at s':>15}{'outside':>9}"
              f"{'kill at s':>13}{'died at s':>13}")
        print(f"   {'':16}{'p | c':>13}{'p | c':>10}{'p | c':>16}{'p | c':>15}{'p | c':>9}{'p | c':>13}{'p | c':>13}")
        tot = {key: dict(hits=0, early=0, outside=0, kills=0, died=0, missed=0, inside=[], goal=[]) for key in "pc"}
        modes = {"p": {}, "c": {}}
        for n, (origin, bearing, spot) in enumerate(spots):
            for seed in seeds:
                p = zone_run(folder, origin, bearing, spot, seed, start, end)
                c = zone_run(ROOT, origin, bearing, spot, seed, start, end)
                for key, r in (("p", p), ("c", c)):
                    for field in ("hits", "early", "outside", "kills"):
                        tot[key][field] += r[field]
                    tot[key]["died"] += r["died"] is not None
                    tot[key]["missed"] += r["inside"] is None and r["died"] is None
                    for field in ("inside", "goal"):
                        if r[field] is not None:
                            tot[key][field].append(r[field])
                    for m, v in r["modes"].items():
                        modes[key][m] = modes[key].get(m, 0) + v
                print(f"   {'spot ' + str(n + 1) + ', seed ' + str(seed):16}{two(p['early'], c['early']):>13}"
                      f"{two(p['hits'], c['hits']):>10}{two(show(p['inside']), show(c['inside'])):>16}"
                      f"{two(show(p['goal']), show(c['goal'])):>15}{two(p['outside'], c['outside']):>9}"
                      f"{two(show(p['kill']), show(c['kill'])):>13}{two(show(p['died']), show(c['died'])):>13}")
        p, c = tot["p"], tot["c"]
        print(f"   {'total':16}{two(p['early'], c['early']):>13}{two(p['hits'], c['hits']):>10}"
              f"{two(round(mean(p['inside']), 1), round(mean(c['inside']), 1)):>16}"
              f"{two(round(mean(p['goal']), 1), round(mean(c['goal']), 1)):>15}{two(p['outside'], c['outside']):>9}"
              f"{two(p['kills'], c['kills']):>13}{two(p['died'], c['died']):>13}")
        print("   (hits before: before first entering the next circle; totals: arrival columns are means over the"
              " runs that got there, kills and deaths are counts)")
        print(f"   moves before entering the circle, parent: {dict(sorted(modes['p'].items(), key=lambda i: -i[1]))}")
        print(f"   moves before entering the circle, candidate: {dict(sorted(modes['c'].items(), key=lambda i: -i[1]))}")
        ok = c["outside"] == 0 and c["missed"] == 0
        print(f"   {check(ok, 'zone run: no candidate decision outside the circle, every run that lives arrives (' + title.split(':')[0] + ')')}"
              f" candidate: {c['outside']} decisions outside the circle, {c['missed']} living runs short of the"
              f" circle (parent {p['outside']} outside, {p['missed']} short)")
        totals[start] = tot
    return totals


def main():
    revision = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else BASELINE
    folder = export(revision)
    print(f"parent {revision[:12]} vs this working tree, both as `python -u bot.py`\n")
    scripted_cases(folder)
    zone_runs(folder, quick="--quick" in sys.argv)
    if FAILURES:
        print("\nFAIL:", "; ".join(FAILURES))
        sys.exit(1)
    print("\nPASS")


if __name__ == "__main__":
    main()
