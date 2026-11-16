# Benchmarks

End-to-end timing and correctness of a ccfind search, run with the tool itself on your real
transcripts. Nothing here is a unit test: `tests/` and `harness/test.sh` cover those.

    ./benchmarks/bench.sh | tee benchmarks/results/$(date +%F).md
    QUERY=migration RUNS=7 ./benchmarks/bench.sh
    CCFIND_BIN=/path/to/another/agsearch ./benchmarks/bench.sh     # compare builds

It uses a throwaway cache (`XDG_CACHE_HOME`), so `~/.cache/ccfind` is never touched, and it
deletes nothing: the cache stays in `$TMPDIR/ccfind-bench.*` and the path is printed. The first
(cold) run parses every transcript, so allow about a minute on a large corpus.

## What it measures

| arm | what it is |
|---|---|
| cold | empty cache; every transcript parsed once |
| warm, caches on | the normal case: fragments, fork map and session rows cached |
| warm, caches blanked | same, but `sessions.sig.json` and `forkfam.json` emptied before each run, so the fork map and session rows are rebuilt from the cached fragments. This is what a search cost before commit `c64ccf0`, and it is also what a build without those caches does when pointed at the same files |

The script prints min, median and max seconds per arm. It sets no pass/fail speed threshold:
the numbers are for reading, not gating.

## What it checks (exit 1 if either fails)

1. **Same output.** The warm run and the caches-blanked run must print identical results.
   This only covers what the query prints, so:
2. **Same rows.** `oracle.py` compares every session row from the cached `build_sessions`
   against a full rebuild of the same lines. Rows must be identical as a set. Sessions with an
   identical timestamp may come out in a different order (a full rebuild orders them by
   file-walk order, so there was no stable order to keep); the count is reported.

The live session is left out of the output (`CCFIND_EXCLUDE`), otherwise its own growing
transcript would change what is printed between two runs.

## Result (2026-11-16, 2,076 transcript files, 446 sessions, macOS 26.5.1, Python 3.14.8)

| arm | median s |
|---|---|
| cold | 68.6 (one run) |
| warm, caches on | 4.22 (min 4.20, max 4.26, 5 runs) |
| warm, caches blanked | 12.08 (min 12.06, max 12.20, 5 runs) |

Both checks passed. Raw output: `results/2026-11-16.md`. One machine, one corpus, one query;
the absolute numbers will differ on yours, the ratio is what to compare.

Where the remaining warm time goes (cProfile, single run, approximate): `build_index` 1.6 s
(reading 2,079 fragment files and splitting 458k rows), `build_sessions` 1.8 s (reading and
rewriting the 157 MB `sessions.tsv`), `print_matches` about 1.5 s (another pass over all rows,
then ranking). No JSON parsing is left on the warm path.

## Calibration: the checks can fail

Each was run and had to fail (2026-11-16):

| broken input | result |
|---|---|
| `CCFIND_BIN=/bin/echo` (does nothing) | exit 1: "no results from /bin/echo" |
| a build that corrupts every reused row (title replaced with `X`) | exit 1: output check and row check both failed |
| the real build, same cache, afterwards | exit 0 |

A build that only *drops* a cached row would not be caught by the row check: the dropped
session has no cached signature next run, so it is regrouped and the cache heals itself. The
bench catches wrong content that persists, not a one-off loss.

## agent-fence

`ccfind ask` runs claude inside [agent-fence](https://github.com/medazizktata/agent-fence),
which allows writes only to `~/.cache/ccfind`. The dependency runs one way: ccfind needs the
fence (and `harness/test.sh` borrows its `nodelete-scan`); the fence only mentions ccfind in
its README. A warm `ccfind -n` does not involve the fence, so these benchmarks do not either.

Checked on 2026-11-16: the new build run under `agent-fence --read-only --allow-write
<cache>` exits 0, prints the same 61 result lines, and rewrites both new cache files
(`sessions.sig.json`, `forkfam.json`) inside the allowed directory. Not measured: fence startup
overhead, or `ccfind ask` timing (it needs a paid claude call; the harness covers its
behaviour with a stub).
