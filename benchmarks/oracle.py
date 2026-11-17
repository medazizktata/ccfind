"""Row-level check: the cached build_sessions must give the same rows as a full rebuild.

usage: oracle.py <agsearch> <cache dir>     (the cache dir bench.sh filled; it is not modified
beyond rewriting its own sessions.tsv with the same rows; one session's row and signature
are damaged first, and the delta file then holds its correct row)

Compares every session, which a single query's printed results cannot. Exits 1 if the two
builds disagree on which rows exist or what is in them. Different order of sessions with an
identical timestamp is reported but is not a failure (a full rebuild orders ties by file-walk
order, so there was no stable order to keep).
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

path, cache = sys.argv[1], sys.argv[2]
os.environ["XDG_CACHE_HOME"] = os.path.dirname(cache.rstrip("/"))
loader = importlib.machinery.SourceFileLoader("ags", path)
m = importlib.util.module_from_spec(importlib.util.spec_from_loader("ags", loader))
loader.exec_module(m)

grouped = []
real = m.group_sessions
def counted(ls):
    ls = list(ls)                             # build_index returns a lazy object, not a list
    grouped.append(len(ls))
    return real(ls)
m.group_sessions = counted

lines = m.build_index()
m.build_sessions(lines)                       # primes the session cache if the build has one
grouped.clear()
# Make exactly one session look changed, so the run under test exercises the changed-row path
# (a build with a delta file writes only that row) whatever the live sessions happen to be
# doing. Its stored row is also damaged: the regrouped row is the same bytes as the old one,
# so without that a reader that ignored the delta file would still pass.
sig_path = getattr(m, "SESSSIG_PATH", "")
try:
    sigs = json.load(open(sig_path))
    sid = sorted(sigs)[0]
    sigs[sid][0] += "-tampered"
    rows = open(m.SESSIONS_PATH, errors="replace").read().split("\n")
    i = next(i for i, l in enumerate(rows) if l.startswith(sid + m.SEP))
    rows[i] = m.SEP.join(rows[i].split(m.SEP)[:-1] + ["damaged on purpose by oracle.py"])
    open(m.SESSIONS_PATH, "w").write("\n".join(rows))
    json.dump(sigs, open(sig_path, "w"))
except (OSError, ValueError, IndexError, StopIteration):
    pass
cached = m.build_sessions(lines)              # the run under test: unchanged sessions reused
regrouped = sum(grouped)
# What a later process reads from disk, which is what a search after this one ranks.
persisted = m._read_session_rows() if hasattr(m, "_read_session_rows") else cached
delta = os.path.getsize(m.SESSIONS_PATH + ".delta") if os.path.exists(m.SESSIONS_PATH + ".delta") else 0
getattr(m, "_FRESH", {}).clear()              # no build_index record: build_sessions does everything
m.SESSIONS_PATH = os.path.join(cache, "sessions.full.tsv")
full = m.build_sessions(lines)

same = sorted(map(tuple, cached)) == sorted(map(tuple, full)) and persisted == cached
moved = sum(1 for a, b in zip(cached, full) if a != b)
print("sessions: cached %d, full %d; rows identical as a set: %s" % (len(cached), len(full), same))
print("changed rows kept in the delta file: %d bytes; rows read back from disk equal the build: %s" % (
    delta, persisted == cached))
print("regrouped %d of %d rows on the cached run; %d positions differ in order (ties)" % (
    regrouped, sum(1 for _ in lines), moved))
sys.exit(0 if same else 1)
