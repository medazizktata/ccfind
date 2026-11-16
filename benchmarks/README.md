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
| warm, caches on | the normal case: fragments, fork map and session rows cached. Reported for all runs, then split by whether the run rewrote `sessions.tsv` (see "Live sessions" below) |
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

## Results (2,076 transcript files, 446 sessions, macOS 26.5.1, Python 3.14.8, 2026-11-16)

Median seconds of a warm `-n` search, same corpus and query, 5 runs each:

| build | warm, caches on | warm, caches blanked | cold |
|---|---|---|---|
| fork and session caches (`c64ccf0`) | 4.22 | 12.08 | 68.6 |
| plus lazy rows (the build in `results/2026-11-16-lazy-rows.md`) | 1.79 | 12.41 | 68.5 |

"Caches blanked" empties the fork and session caches only, so a search rebuilds both from the
cached fragments. Before `c64ccf0` a warm search always paid that (about 12 s). The cold
column is one run. Both checks passed on both builds. Raw output: `results/`.

One machine, one corpus, one query: the absolute numbers will differ on yours, compare the
ratios.

### The 1.79 s is the best case: live sessions and machine load move it

Re-running the same build (`df3969d`, `agsearch` byte-identical to the one behind 1.79 s) on
2026-11-16 gave a warm median of 3.01 s. Nothing in ccfind had changed; two things did:

- **A live session wrote.** A session counts as changed when any of its transcript files
  changes, subagent files included. Any changed session makes `build_sessions` rewrite the
  whole 158 MB `sessions.tsv`, not just that row. Calling `build_index` and `build_sessions`
  directly, one run found 3 changed sessions (another repo's session and its subagent, and
  the conversation running the benchmark) and the run right after found 0. Per stage
  (in-process, 4 runs, machine busy): `build_index` 0.34 s, loading the session cache 1.15 s,
  rewriting `sessions.tsv` 0.84 s. A run with nothing changed is the first two plus
  startup, about 1.8 s; a run that rewrites adds the third, and re-reading the changed
  sessions' fragments, which was not measured on its own (about 0.4 s is unaccounted for).
  In practice a person always has some session open, so about 3 s is the typical warm search
  and 1.8 s is what you get when nothing has written since the last one.
- **The machine was busy.** Load average was 6 to 20 during these runs. Every arm slowed,
  the quiet warm runs included (4.9 s in the run in `results/2026-11-16-live-sessions.md`,
  cold 97 s against 68.5 s). The bench now prints the load average at the start and end;
  compare timings only between runs on a similarly idle machine.

The bench splits the warm runs by whether each one rewrote `sessions.tsv`, so a live session
is visible instead of being averaged in. It cannot make a session stop writing, so on a busy
machine the "quiet" group can be small or empty. An attempt to force the comparison (a clean
run against one deliberately dirty session, interleaved) failed: live sessions dirtied the
clean arm too, so both arms rewrote the file and the two medians meant nothing.

What the lazy-rows step changed: `build_index` used to read every fragment (about 458k rows)
into a list on every run, so a search could print a dozen sessions. It now returns a lazy
object that knows which sessions each fragment holds (`filesids.json`, valid while the
source file's mtime is unchanged) and reads only the fragments of changed sessions and of
the sessions it prints. Anything that needs every row (a scoped search with `-a`, `-p` or
`--here`) still iterates all of them, as before. Where the remaining time goes is profiled
below.

### Other queries and scoped searches (single runs, 2026-11-16, lazy-rows build)

Warm, unscoped: `invoice` 2.14 s, `sandbox` 1.90, `fork` 2.03, `agent fence` 2.69,
`p2p quote` 2.18, no query 1.47, and 3.37 for a nonsense word (it falls through to the
typo tier, which ranks slowest). So "about 2 s" is typical and the range is 1.5 to 3.4 s.

Scoped searches iterate every row to apply the filter, and do not reuse the session cache:
`-a second` 5.30 s (the account holds about half the sessions, so they are all
regrouped), `-p Second` 1.93 s and `--here` 1.69 s (few sessions survive the filter).
The first unscoped search after any scoped one rebuilds the session rows once: 7.51 s, then
1.75 s again.

Where a warm search spends its time (cProfile, one run, 1.96 s profiled): reading the
157 MB `sessions.tsv` about 1.0 s (every row carries its session's whole lowercased text),
`build_index` 0.4 s (mostly walking the directories), ranking 0.2 s.

## Calibration: the checks can fail

Each was run and had to fail (2026-11-16):

| broken input | result |
|---|---|
| `CCFIND_BIN=/bin/echo` (does nothing) | exit 1: "no results from /bin/echo" |
| a build that corrupts every reused row (title replaced with `X`) | exit 1: output check and row check both failed |
| the real build, same cache, afterwards | exit 0 |
| `CCFIND_BIN` stub that never writes `sessions.tsv`, 4 warm runs | the "quiet" row counts 4 of 4, the "rewritten" row 0 |
| `CCFIND_BIN` stub that always writes `sessions.tsv`, 4 warm runs | the "quiet" row counts 0 of 4, the "rewritten" row 4 |

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
