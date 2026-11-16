# Warm search time with live sessions and a busy machine, 2026-11-16

Why a re-run of the same build gave 3.01 s instead of the recorded 1.79 s. See the section
"The 1.79 s is the best case" in `../README.md` for the reading; this file holds the numbers.

## Same build, repeated warm runs on one cache (5 runs, then 8, then 14)

Warm runs on the same cache swung between 1.84 s (user 1.31 s, sys 0.50 s) and about 3 s
(user 1.8 s, sys 0.95 s). The fast ones reproduce the recorded 1.79 s.
Of 14 runs in one batch, 11 rewrote `sessions.tsv` (median 4.29 s) and 3 did not (median
2.44 s). Load was not recorded for that batch; the batch before it ended at a load average
of 8.15 (1 min).

## Which sessions were dirty (build_index + build_sessions called directly)

    run A: 446 sessions, 3 dirty
       (id)  a subagent file of another project's session, mtime moved
       (id)  a session of a third project and its subagent file, mtime moved
       (id)  the conversation running the benchmark, mtime moved
    run B (immediately after): 446 sessions, 0 dirty

## Cost per stage (in-process, 4 runs; load average 6 to 7)

| stage | run 1 | run 2 | run 3 | run 4 | median |
|---|---|---|---|---|---|
| `build_index` | 0.34 | 0.22 | 0.23 | 0.60 | 0.34 s |
| load session cache (read 158 MB `sessions.tsv`) | 1.15 | 1.24 | 1.03 | 0.90 | 1.15 s |
| rewrite `sessions.tsv` (join and write 158 MB) | 0.84 | 0.93 | 0.69 | 0.60 | 0.84 s |

## An attempt that did not isolate the cost

Six pairs of runs, a clean run and then one with a single session's signature corrupted in
the throwaway cache: all 12 rewrote `sessions.tsv` because live sessions kept changing, so
medians of 3.21 s and 2.90 s compare two dirty arms. Discarded.

## Full bench run (the build after this change was not yet in; run before the load lines)

Load average read straight after the run: 18.65, 20.40, 12.97 (1, 5, 15 min).

## ccfind benchmark, 2026-11-16

- build: `~/Desktop/ccfind/agsearch` (df3969d)
- machine: macOS 26.5.1, Python 3.14.8, 5 runs per arm
- query: `invoice`; throwaway cache: `/var/folders/ff/6zbsfm7d1h383v67k783r2840000gn/T//ccfind-bench.440uYD`
- corpus: 2084 transcript files, 446 sessions

| arm | min s | median s | max s |
|---|---|---|---|
| cold (empty cache, parses every transcript, 1 run) | 97.421 | 97.421 | 97.421 |
| warm, caches on, all 5 runs | 4.33 | 5.05 | 8.38 |
|  of which quiet: nothing changed, sessions.tsv not rewritten (4 of 5) | 4.33 | 4.91 | 5.34 |
|  of which a live session wrote: sessions.tsv rewritten (1 of 5) | 8.38 | 8.38 | 8.38 |
| warm, session and fork caches blanked | 16.06 | 17.90 | 22.72 |

Output check: cached and caches-blanked runs printed identical results (61 lines).

Row check (every session, not just the ones this query prints):
```
sessions: cached 446, full 446; rows identical as a set: True
regrouped 0 of 460594 rows on the cached run; 0 positions differ in order (ties)
```
