"""Time several builds of a search while one session looks changed before every run.

usage: compare_builds.py <runs> <name>=<binary>=<cache home> ...

Each build needs its own cache home (the directory that holds `ccfind/`): builds that disagree
on the cache format would otherwise rebuild each other's cache every run. Fill each once by
running the build, twice, with XDG_CACHE_HOME set to its cache home.

Before each run one session's signature is edited in that build's own cache, so the run has
exactly one changed session whatever the live sessions are doing. Runs rotate through the
builds so none always goes first. Two times per run: when the last byte of output arrived, and
when the process exited. Prints median and min over the runs, and whether every build printed
the same bytes. Only the caches named on the command line are modified.
"""
import json
import os
import statistics
import subprocess
import sys
import time

runs = int(sys.argv[1])
builds = [a.split("=", 2) for a in sys.argv[2:]]
base = {k: v for k, v in os.environ.items()
        if k not in ("CLAUDE_CODE_SESSION_ID", "OPENCODE_SESSION_ID", "CURSOR_CONVERSATION_ID")}
base["CCFIND_EXCLUDE"] = os.environ.get("CLAUDE_CODE_SESSION_ID", "")


def dirty_one(cache_home):
    path = os.path.join(cache_home, "ccfind", "sessions.sig.json")
    sigs = json.load(open(path))
    if not sigs:
        sys.exit("no session signatures in %s: run the build on it twice first" % path)
    sid = sorted(sigs)[0]
    sigs[sid][0] = "tampered-%f" % time.time()
    json.dump(sigs, open(path, "w"))


def run(binary, cache_home):
    t0 = time.time()
    p = subprocess.Popen([binary, "--agent", "-n", "invoice"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=dict(base, XDG_CACHE_HOME=cache_home))
    last, got = t0, b""
    while True:
        chunk = os.read(p.stdout.fileno(), 65536)
        if not chunk:
            break
        got += chunk
        last = time.time()
    p.wait()
    return last - t0, time.time() - t0, got


res = {name: [] for name, _b, _c in builds}
outs = {}
for i in range(runs):
    k = i % len(builds)
    for name, binary, home in builds[k:] + builds[:k]:
        dirty_one(home)
        last, exit_, outs[name] = run(binary, home)
        res[name].append((last, exit_))
print("load average (1, 5, 15 min) at the end:", ", ".join("%.1f" % x for x in os.getloadavg()))
for name, rs in res.items():
    print("%-8s last byte median %.2f s (min %.2f) | exit median %.2f s (min %.2f) | %d runs" % (
        name, statistics.median(r[0] for r in rs), min(r[0] for r in rs),
        statistics.median(r[1] for r in rs), min(r[1] for r in rs), len(rs)))
print("every build printed the same %d bytes: %s" % (
    len(next(iter(outs.values()))), len(set(outs.values())) == 1))
