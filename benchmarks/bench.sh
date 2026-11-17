#!/bin/bash
# End-to-end benchmark of a ccfind search, run with the tool itself on your real transcripts.
#   ./bench.sh                       cold build, warm runs, caches-blanked runs, output check
#   QUERY=migration RUNS=7 ./bench.sh | tee results/$(date +%F).md
# CCFIND_BIN points at another build (the README calibrates the checks that way).
# Uses a throwaway cache (XDG_CACHE_HOME), so your real ~/.cache/ccfind is never touched.
# Nothing is deleted: the throwaway cache stays in $BENCH_DIR and its path is printed.
set -uo pipefail

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
REPO="$(dirname "$HERE")"
CCFIND_BIN="${CCFIND_BIN:-$REPO/agsearch}"
QUERY="${QUERY:-invoice}"
RUNS="${RUNS:-5}"
BENCH_DIR="${BENCH_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/ccfind-bench.XXXXXX")}"
export XDG_CACHE_HOME="$BENCH_DIR"
C="$BENCH_DIR/ccfind"
MARK="$BENCH_DIR/run.mark"

die() { echo "bench: $*" >&2; exit 1; }
[ -x "$CCFIND_BIN" ] || die "$CCFIND_BIN is not executable"

# One timed search. --agent keeps the clipboard alone; the caller's own session id is dropped
# from the environment and excluded from the output, so a live session cannot change what is
# printed between two runs. Prints seconds; fails unless real results (a resume line) came out.
timed() {
  local out=$1 t
  touch "$MARK"
  t=$( { TIMEFORMAT=%R; time env -u CLAUDE_CODE_SESSION_ID -u OPENCODE_SESSION_ID \
           -u CURSOR_CONVERSATION_ID CCFIND_EXCLUDE="${CLAUDE_CODE_SESSION_ID:-}" \
           "$CCFIND_BIN" --agent -n "$QUERY" >"$out" 2>/dev/null; } 2>&1 )
  grep -q 'resume' "$out" || die "no results from $CCFIND_BIN for query '$QUERY' (see $out)"
  echo "$t"
}
# What the last timed run wrote of the session cache: 0 nothing, 1 only the changed rows
# (sessions.tsv.delta), 2 the whole sessions.tsv. A run writes when any session's transcript
# changed since the run before (a live session); the whole file is 150+ MB.
wrote() {
  if [ -n "$(find "$C/sessions.tsv" -newer "$MARK" 2>/dev/null)" ]; then echo 2
  elif [ -n "$(find "$C/sessions.tsv.delta" -newer "$MARK" 2>/dev/null)" ]; then echo 1
  else echo 0; fi
}
blank_caches() { echo '{}' > "$C/sessions.sig.json"; echo '{}' > "$C/forkfam.json"; }
pick() {  # seconds of the warm runs whose wrote code equals $1
  local i; for i in "${!warm[@]}"; do [ "${warm_rw[$i]}" = "$1" ] && echo "${warm[$i]}"; done
}
stats() {  # min median max of the seconds on stdin
  sort -n | awk '{a[NR]=$1} END {if (!NR) printf "n/a | n/a | n/a"; else printf "%.2f | %.2f | %.2f", a[1], a[int((NR+1)/2)], a[NR]}'
}

mkdir -p "$C"
echo "## ccfind benchmark, $(date +%F)"
echo
echo "- build: \`$CCFIND_BIN\` ($(cd "$REPO" && git rev-parse --short HEAD 2>/dev/null || echo no-git))"
echo "- machine: $(sw_vers -productVersion 2>/dev/null | sed 's/^/macOS /'), $(python3 -V), $RUNS runs per arm"
echo "- query: \`$QUERY\`; throwaway cache: \`$BENCH_DIR\`"
load() { uptime | sed 's/.*load averages*: //'; }   # 1, 5, 15 minute: a busy machine slows every arm
echo "- load average (1, 5, 15 min) at the start: $(load)"

cold=$(timed "$BENCH_DIR/cold.out") || exit 1
timed "$BENCH_DIR/prime.out" >/dev/null || exit 1          # absorbs files that changed during the cold build
warm=() warm_rw=() full=()
for ((i = 0; i < RUNS; i++)); do
  warm+=("$(timed "$BENCH_DIR/warm.out")") || exit 1
  warm_rw+=("$(wrote)")
done
for ((i = 0; i < RUNS; i++)); do blank_caches; full+=("$(timed "$BENCH_DIR/full.out")") || exit 1; done

python3 -I - "$C" <<'PY'
import json, sys
c = sys.argv[1]
print("- corpus: %d transcript files, %d sessions" % (
    len(json.load(open(c + "/meta.json"))) - 2, len(json.load(open(c + "/index.json")))))
PY
echo
echo "| arm | min s | median s | max s |"
echo "|---|---|---|---|"
echo "| cold (empty cache, parses every transcript, 1 run) | $cold | $cold | $cold |"
echo "| warm, caches on, all $RUNS runs | $(printf '%s\n' "${warm[@]}" | stats) |"
nq=$(pick 0 | grep -c .); nd=$(pick 1 | grep -c .); nr=$(pick 2 | grep -c .)
echo "|  of which quiet: nothing changed, nothing written ($nq of $RUNS) | $(pick 0 | stats) |"
echo "|  of which a live session wrote: only the changed rows, sessions.tsv.delta ($nd of $RUNS) | $(pick 1 | stats) |"
echo "|  of which sessions.tsv was rewritten whole ($nr of $RUNS) | $(pick 2 | stats) |"
echo "| warm, session and fork caches blanked | $(printf '%s\n' "${full[@]}" | stats) |"

echo
echo "Load average at the end: $(load). Timings are only comparable between runs on a similarly idle machine."
echo
if cmp -s "$BENCH_DIR/warm.out" "$BENCH_DIR/full.out"; then
  echo "Output check: cached and caches-blanked runs printed identical results ($(wc -l < "$BENCH_DIR/warm.out" | tr -d ' ') lines)."
else
  echo "Output check: FAILED, cached and caches-blanked runs differ: diff $BENCH_DIR/warm.out $BENCH_DIR/full.out"
  status=1
fi
echo
echo "Row check (every session, not just the ones this query prints):"
echo '```'
python3 -I "$HERE/oracle.py" "$CCFIND_BIN" "$C" || status=1
echo '```'
exit "${status:-0}"
