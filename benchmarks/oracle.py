"""Row-level check: the cached build_sessions must give the same rows as a full rebuild.

usage: oracle.py <agsearch> <cache dir>     (the cache dir bench.sh filled; it is not modified
beyond rewriting its own sessions.tsv with the same rows)

Compares every session, which a single query's printed results cannot. Exits 1 if the two
builds disagree on which rows exist or what is in them. Different order of sessions with an
identical timestamp is reported but is not a failure (a full rebuild orders ties by file-walk
order, so there was no stable order to keep).
"""
import importlib.machinery
import importlib.util
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
cached = m.build_sessions(lines)              # the run under test: unchanged sessions reused
regrouped = sum(grouped)
getattr(m, "_FRESH", {}).clear()              # no build_index record: build_sessions does everything
m.SESSIONS_PATH = os.path.join(cache, "sessions.full.tsv")
full = m.build_sessions(lines)

same = sorted(map(tuple, cached)) == sorted(map(tuple, full))
moved = sum(1 for a, b in zip(cached, full) if a != b)
print("sessions: cached %d, full %d; rows identical as a set: %s" % (len(cached), len(full), same))
print("regrouped %d of %d rows on the cached run; %d positions differ in order (ties)" % (
    regrouped, sum(1 for _ in lines), moved))
sys.exit(0 if same else 1)
