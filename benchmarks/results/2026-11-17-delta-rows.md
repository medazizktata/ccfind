# Changed sessions go to a delta file (2026-11-17)

Question: a search that finds one changed session rewrote the whole 158 MB `sessions.tsv`
(about 0.8 s, measured on 2026-11-16). Two changes, measured separately:

1. `-n` prints its results, flushes, and only then writes the cache (commit `1b5efb3`).
2. The write itself shrinks: changed rows go to `sessions.tsv.delta`; `sessions.tsv` is
   rewritten whole only on a first or scoped build, or when the changed rows exceed
   `DELTA_MAX` (16 MB). Readers lay the delta over `sessions.tsv`.

Method: `benchmarks/compare_builds.py`. One session's signature is edited before every run, so
each run has exactly one changed session; the builds run in rotation, each with its own cache
(cold build, then settled with two runs); query `invoice`, `-n --agent`. Last byte = when the
last output byte reached the reader; exit = when the process ended.

| build | last byte, median (min) | exit, median (min) |
|---|---|---|
| before (`a939175`) | 2.83 s (2.16) | 2.85 s (2.18) |
| print first (`1b5efb3`) | 2.32 s (1.72) | 2.76 s (2.13) |
| delta file | 2.17 s (1.97) | 2.24 s (2.03) |

8 runs per build, load average 9.0 / 14.0 / 24.7 at the end. Two earlier runs with a one-off
script (6 and 8 runs, load 10 to 30) gave the same order: exit 2.39 / 2.34 / 1.93 s and
2.37 / 2.34 / 1.97 s. Every build printed the same 7,226 bytes.

Reading: the delta file takes about 0.4 to 0.6 s off the process exit, and printing first takes
about 0.5 s off the time the last byte arrives (it does nothing for a caller that waits for
exit). The delta file does not touch the other costs of a warm search: reading the 158 MB
`sessions.tsv` (about 1.1 s in the earlier profile) and ranking it are unchanged.

Checks, each run on 2026-11-17:

- 204 unit tests and the 80-check offline harness pass. 10 new tests cover the delta; 8
  deliberate breakages (never use the delta, reader ignores it, trusts it with empty
  signatures, drops earlier delta rows, returns vanished sessions, no size cap, no early
  return, delta left behind by a full write) each turned the intended test red; the source
  was restored byte for byte. One breakage (the reader ignoring dates) was first not caught
  and needed a test where the changed session becomes the newest.
- `oracle.py` (rows from the cached build, the rows read back from disk, and a full rebuild
  must agree): exit 0. It first passed a reader that ignores the delta, because its tamper
  only changed a signature and the regrouped row had the same bytes; it now also damages that
  session's stored row, and a build that ignores the delta exits 1 (then 0 again for the real
  build).
- `bench.sh` write classes (nothing / delta only / whole file), calibrated with three stubs:
  each lands in its own row, 4 of 4.
- The repo's no-delete scan failed on my first version (`os.replace`); the delta is written in
  place, like `sessions.tsv`.

Not verified:

- No idle-machine timing; every number above was taken at load 9 to 30.
- Not run against the real `~/.cache/ccfind`, only throwaway caches. The format number
  changed (`SESS_FMT` 1 to 2), so the first real search regroups every session once from the
  cached fragments (the earlier measurement for a full regroup was about 7 s).
- A reader that starts while a build is writing the delta can see a torn delta (written in
  place). The signatures are emptied first, so a reader that checks them first ignores the
  delta; one that read them just before is not covered. Not tested.
- An older build pointed at a newer cache is protected only by the `SESS_FMT` bump (its
  signatures no longer match, so it regroups everything and rewrites `sessions.tsv`). Reasoned
  from the code, not run.
- The interactive fzf list was exercised only through the harness, not by hand.
