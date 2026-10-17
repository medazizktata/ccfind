#!/bin/bash
# Test harness for ccfind + ccask.
#   ./test.sh              offline: throwaway HOME, fixture transcripts, stub `claude` (free)
#   ./test.sh --real       also: ranking on your real transcripts (free, ~1 min)
#   ./test.sh --live       also: one real ccask query through Haiku (~$0.20)
#   ./test.sh --calibrate  prove the checks can fail: re-run against broken builds and a
#                          do-nothing ccfind, and require failures from each
# CCFIND_BIN / CCASK_BIN point the harness at another build (used by --calibrate).
# Nothing is deleted: each run leaves its throwaway HOME in $TMPDIR and prints the path.
set -uo pipefail
TMPDIR="${TMPDIR:-/tmp}"   # its trailing / would put // in fixture paths, which Claude never records

HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
REPO="$(dirname "$HERE")"; ASK="$REPO/ask"
CCFIND_BIN="${CCFIND_BIN:-$REPO/agsearch}"
CCASK_BIN="${CCASK_BIN:-$ASK/ccask}"
REAL=0 LIVE=0 CALIBRATE=0
for a in "$@"; do
  case "$a" in
    --real) REAL=1 ;; --live) REAL=1; LIVE=1 ;; --calibrate) CALIBRATE=1 ;;
    *) echo "usage: test.sh [--real] [--live] [--calibrate]" >&2; exit 2 ;;
  esac
done

pass=0 fail=0 OUT="" RC=0
run() { OUT=$("$@" 2>&1); RC=$?; }
# check <name> <want-exit> [+literal-present] [-literal-absent] [~regex-present] ...
check() {
  local name=$1 want=$2 why="" c; shift 2
  [ "$RC" = "$want" ] || why="exit $RC, want $want"
  for c in "$@"; do
    case "$c" in
      +*) grep -qF -- "${c:1}" <<<"$OUT" || why="${why:+$why; }missing: ${c:1}" ;;
      -*) ! grep -qF -- "${c:1}" <<<"$OUT" || why="${why:+$why; }unexpected: ${c:1}" ;;
      '~'*) grep -qE -- "${c:1}" <<<"$OUT" || why="${why:+$why; }no match: ${c:1}" ;;
    esac
  done
  if [ -z "$why" ]; then
    pass=$((pass + 1)); echo "  ok    $name"
  else
    fail=$((fail + 1)); echo "  FAIL  $name ($why)"; sed 's/^/          /' <<<"$OUT" | head -6
  fi
}

# ---------------------------------------------------------------- calibration
if [ $CALIBRATE = 1 ]; then
  C=$(mktemp -d "${TMPDIR%/}/ccfind-calibrate.XXXXXX")
  echo "calibration builds in $C"
  printf '#!/bin/sh\nexit 0\n' > "$C/noop-ccfind"; chmod +x "$C/noop-ccfind"
  sed 's/^        argv\[0\] = PROPAGENDA_BIN$/        pass  # sabotaged/' "$CCFIND_BIN" > "$C/ccfind-no-routing"
  sed 's/^        lines = \[l for l in lines if l.split(SEP, 1)\[0\] in keep\]$/        pass  # sabotaged/' \
    "$CCFIND_BIN" > "$C/ccfind-no-account"
  sed 's/^    return any(os.environ.get(v) for v in AGENT_VARS)$/    return False  # sabotaged/' \
    "$CCFIND_BIN" > "$C/ccfind-no-agent-detect"
  chmod +x "$C/ccfind-no-agent-detect"
  for d in ask ask-openguard ask-opensb; do
    mkdir -p "$C/$d"; cp "$ASK/ccask-system.md" "$ASK/ccask-guard" "$CCASK_BIN" "$C/$d/"
  done
  sed 's/^        bad = 1$/        pass  # sabotaged/' "$CCASK_BIN" > "$C/ask/ccask"
  printf '#!/bin/sh\n# sabotaged: allows every tool call\ncat >/dev/null; exit 0\n' > "$C/ask-openguard/ccask-guard"
  printf '#!/bin/bash\n# sabotaged: no sandbox at all\nwhile [ $# -gt 0 ]; do case "$1" in --) shift; break ;; --allow-write|--protect|--workspace) shift 2 ;; -*) shift ;; *) break ;; esac; done\nexec "$@"\n' > "$C/fence-open"
  chmod +x "$C/fence-open"
  chmod +x "$C/ccfind-no-routing" "$C/ccfind-no-account" "$C"/ask*/ccask "$C"/ask*/ccask-guard
  cal_fail=0
  for spec in "do-nothing ccfind|CCFIND_BIN=$C/noop-ccfind" \
              "ccfind without propagenda routing|CCFIND_BIN=$C/ccfind-no-routing" \
              "ccfind without account filter|CCFIND_BIN=$C/ccfind-no-account" \
              "ccfind that never detects agents|CCFIND_BIN=$C/ccfind-no-agent-detect" \
              "ccask that accepts invented ids|CCASK_BIN=$C/ask/ccask" \
              "guard that allows every tool call|CCASK_BIN=$C/ask-openguard/ccask" \
              "sandbox that allows every write|AGENT_FENCE=$C/fence-open"; do
    label=${spec%%|*}; envset=${spec#*|}
    # count rows changed by the sabotage; a sed that matched nothing would test nothing
    src=${envset#*=}
    case "$label" in guard*) src="$(dirname "$src")/ccask-guard" ;; esac
    if [ "$label" != "do-nothing ccfind" ] && ! grep -q 'sabotaged' "$src"; then
      echo "  FAIL  $label: sabotage did not apply (pattern no longer matches)"; cal_fail=1; continue
    fi
    res=$(env "$envset" "$HERE/test.sh" 2>&1); rc=$?
    n=$(grep -c '^  FAIL' <<<"$res")
    if [ $rc -ne 0 ] && [ "$n" -gt 0 ]; then
      echo "  ok    $label is caught ($n failing checks), e.g.:"
      grep '^  FAIL' <<<"$res" | head -2 | sed 's/^  FAIL/          /'
    else
      echo "  FAIL  $label was NOT caught (exit $rc)"; cal_fail=1
    fi
  done
  res=$("$HERE/test.sh" 2>&1); rc=$?
  if [ $rc -eq 0 ]; then echo "  ok    unmodified build passes"; else echo "  FAIL  unmodified build fails"; cal_fail=1; fi
  exit $cal_fail
fi

# ---------------------------------------------------------------- real data (before HOME moves)
REAL_HOME=$HOME
if [ $REAL = 1 ]; then
  echo "real transcripts (known sessions; results change as transcripts do):"
  run env HOME="$REAL_HOME" "$CCFIND_BIN" -n "gated invoice page"
  top=$(grep -E '^[0-9a-f]{8}' <<<"$OUT" | head -3)
  OUT=$top; RC=0
  check "\"gated invoice page\" has 0546caa9 in the top 3" 0 "+0546caa9"
  run env HOME="$REAL_HOME" "$CCFIND_BIN" -n -a claude "gated invoice page"
  check "-a claude excludes the propagenda session 0546caa9" "$RC" "-0546caa9"
fi
if [ $LIVE = 1 ]; then
  echo "live Haiku run (costs money; Haiku picked the right best match 1 in 3 before):"
  run env HOME="$REAL_HOME" "$CCASK_BIN" -a propagenda "propagenda website invoice page addition"
  echo "$OUT" | sed 's/^/          /' | head -12
  check "ccask BEST is 0546caa9" 0 "~^BEST .*" "+0546caa9-de6b-4edb-8f38-7023d9f9ac5a"
fi

# ---------------------------------------------------------------- fixtures
T=$(mktemp -d "${TMPDIR%/}/ccfind-test.XXXXXX")
export HOME="$T" XDG_CACHE_HOME="$T/.cache" STUB_LOG="$T/stub"
mkdir -p "$T/bin"
ln -s "$CCFIND_BIN" "$T/bin/ccfind"
cat > "$T/bin/claude" <<'STUB'
#!/bin/bash
# stub claude: records how it was called, answers per $STUB_MODE
printf '%s\n' "$@" > "$STUB_LOG.args"; cat > "$STUB_LOG.stdin"
head='"type":"result","num_turns":3,"total_cost_usd":0.0123'
case "${STUB_MODE:-ok}" in
  ok)       printf '{%s,"subtype":"success","is_error":false,"result":"","structured_output":{"status":"found","best_id":"%s","why":"stub","also":[]}}' "$head" "$STUB_ID" ;;
  textjson) printf '{%s,"subtype":"success","is_error":false,"result":"```json\\n{\\"status\\":\\"found\\",\\"best_id\\":\\"%s\\",\\"why\\":\\"stub\\",\\"also\\":[]}\\n```"}' "$head" "$STUB_ID" ;;
  prose)    printf '{%s,"subtype":"success","is_error":false,"result":"I could not decide."}' "$head" ;;
  proseid)  printf '{"type":"system","subtype":"init"}\n{%s,"subtype":"success","is_error":false,"result":"I called it above. **best_id**: \\"%s\\" is the one."}\n' "$head" "$STUB_ID" ;;
  budget)   printf '{%s,"subtype":"error_max_budget_usd","is_error":true,"result":""}' "$head" ;;
  error)    printf '{%s,"subtype":"error_during_execution","is_error":true,"result":""}' "$head" ;;
  garbage)  echo "stub: simulated crash" >&2; echo "not json"; exit 3 ;;
  sleep)    sleep 30 ;;
  probe)    # try writes; the sandbox must block the first two and allow the last
            for f in "$PROBE_OUTSIDE" "$HOME/.claude-propagenda/projects/.sbprobe" "$HOME/.cache/ccfind/.sbprobe"; do
              if (echo x > "$f") 2>/dev/null; then echo "written $f"; else echo "blocked $f"; fi
            done > "$STUB_LOG.probe"
            printf '{%s,"subtype":"success","is_error":false,"result":"","structured_output":{"status":"not_found","best_id":"","why":"probe","also":[]}}' "$head" ;;
esac
STUB
chmod +x "$T/bin/claude"
# stub clipboard: one line per pbcopy call, so tests never touch the real clipboard
printf '#!/bin/bash\n{ cat; echo; } >> "$CLIP_LOG"\n' > "$T/bin/pbcopy"; chmod +x "$T/bin/pbcopy"
export PATH="$T/bin:$PATH" CLIP_LOG="$T/clipboard.log"
export CCFIND_AGENT=0   # human mode unless a test says otherwise (this harness runs inside agents)
AGENT_VARS=(CLAUDECODE AI_AGENT OPENCODE CURSOR_AGENT CODEX_SANDBOX)
no_agent_env=(env -u CCFIND_AGENT); for v in "${AGENT_VARS[@]}"; do no_agent_env+=(-u "$v"); done
clip() { cat "$CLIP_LOG" 2>/dev/null; }

slug() { sed 's/[^A-Za-z0-9]/-/g' <<<"$1"; }
# mk <claude|propagenda> <session-id> <launch-dir> <cwd> <title> <text>
mk() {
  local base=".claude"; [ "$1" = propagenda ] && base=".claude-propagenda"
  local d="$T/$base/projects/$(slug "$3")"; mkdir -p "$d" "$4"
  printf '{"type":"user","sessionId":"%s","cwd":"%s","timestamp":"2026-10-01T10:00:00Z","uuid":"%s-u1","message":{"role":"user","content":"%s"}}\n{"type":"ai-title","aiTitle":"%s","sessionId":"%s"}\n' \
    "$2" "$4" "$2" "$6" "$5" "$2" > "$d/$2.jsonl"
  echo "$d/$2.jsonl"
}
A=aaaaaaaa-0000-4000-8000-000000000001
B=bbbbbbbb-0000-4000-8000-000000000002
C=cccccccc-0000-4000-8000-000000000003
D=dddddddd-0000-4000-8000-000000000004
FA=$(mk claude     $A "$T/work/alpha" "$T/work/alpha"     "Alpha zebrafinch" "zebrafinch invoice alpha")
mk propagenda $B "$T/work/beta"  "$T/work/beta/sub" "Beta quokka"      "quokka invoice beta" >/dev/null
mk propagenda $C "$T/work/gamma" "$T/work/gamma"    "Gamma marmoset"   "marmoset gamma --frobnicate" >/dev/null
echo "offline tests (throwaway HOME: $T)"

# ---------------------------------------------------------------- ccfind
run ccfind -n zebrafinch
check "finds a ~/.claude session"                0 "+$A" "+cd $T/work/alpha && claude --resume $A"
run ccfind -n quokka
check "propagenda session resumes via claude-propagenda from its launch dir (not the subdir)" \
      0 "+cd $T/work/beta && claude-propagenda --resume $B" "-$T/work/beta/sub &&"
run ccfind -n invoice
check "no account filter returns both accounts"  0 "+$A" "+$B"
run ccfind -n -a claude invoice
check "-a claude keeps only ~/.claude"           0 "+$A" "-$B"
run ccfind -n -a PROPAGENDA invoice
check "-a PROPAGENDA (any case) keeps only propagenda" 0 "+$B" "-$A"
run ccfind -n -a claude marmoset
check "account with no match says so"            1 "+No matches"
run ccfind -n -- --frobnicate
check "-- searches a word that starts with a dash" 0 "+$C"
for bad in "-a bogus x" "-a" "-p" "--zz x"; do
  run ccfind -n $bad
  check "rejects: ccfind -n $bad"                2 "+ccfind:"
done
run ccfind read aaaaaaaa
check "read <prefix> prints the session"         0 "+zebrafinch"
run ccfind -n nosuchwordanywhere
check "no matches exits 1"                       1 "+No matches"

printf '{"type":"user","sessionId":"%s","cwd":"%s","timestamp":"2026-10-01T10:05:00Z","uuid":"%s-u2","message":{"role":"user","content":"pangolin appended later"}}\n' \
  "$A" "$T/work/alpha" "$A" >> "$FA"
run ccfind -n pangolin
check "a line appended to a transcript is found on the next search" 0 "+$A"
FD=$(mk claude $D "$T/work/delta" "$T/work/delta" "Delta" "okapi brand new")
run ccfind -n okapi
check "a new transcript is found on the next search" 0 "+$D"
frags_before=$(ls "$XDG_CACHE_HOME/ccfind/frag" | wc -l)
mkdir -p "$T/moved"; mv "$FD" "$T/moved/"
run ccfind -n okapi
check "a transcript moved away drops out of results" 1 "-$D"
OUT="cached copies: before=$frags_before after=$(ls "$XDG_CACHE_HOME/ccfind/frag" | wc -l)"; RC=0
check "stale cached copy is left in place (no deletes)" 0 "~before= *([0-9]+) after= *\\1$"

# Structural scan (ast-grep, ~/Desktop/agent-fence/nodelete-scan): real calls only, so
SCAN="$(dirname "$(readlink -f "$(command -v agent-fence)")")/nodelete-scan"
run "$SCAN" "$CCFIND_BIN" "$CCASK_BIN" "$ASK/ccask-guard" "$HERE/test.sh"
check "no delete calls in ccfind, ccask, guard, test.sh (ast-grep)" 0

# ---------------------------------------------------------------- ccask (stub claude)
run "$CCASK_BIN"
check "ccask with no words: usage, exit 2"       2 "+usage:"
run ccfind ask
check "ccfind ask hands off to ask/ccask"        2 "+usage: ccask"
run ccfind ask -h
check "ccfind ask -h"                            0 "+usage: ccask"
for bad in "-a bogus x" "-a" "--zz x"; do
  run "$CCASK_BIN" $bad
  check "rejects: ccask $bad"                    2 "+ccask:"
done
run "$CCASK_BIN" -h
check "ccask -h"                                 0 "+usage:"

export STUB_ID=bbbbbbbb
STUB_MODE=ok run "$CCASK_BIN" invoice
check "answer: resume line built by the script, not the model" 0 "~^BEST " \
      "+cd $T/work/beta && claude-propagenda --resume $B" "+\$0.0123"
OUT=$(cat "$STUB_LOG.args"); RC=0
check "claude is called locked down" 0 "+haiku" "+--no-session-persistence" "+--json-schema" \
      "+--strict-mcp-config" "+Bash(ccfind -n:*)" "+Bash(ccfind read:*)" "+Bash,Read,Grep,Glob" "-default"
OUT=$(cat "$STUB_LOG.stdin"); RC=0
check "prompt carries ccfind's candidates, no account note" 0 "+$A" "+$B" "-Account filter"
STUB_MODE=ok run "$CCASK_BIN" -a propagenda invoice
OUT="$OUT
$(cat "$STUB_LOG.stdin")"
check "-a propagenda: candidates filtered and the model told" 0 "+Account filter" "+-a propagenda" "-$A"
STUB_MODE=ok run "$CCASK_BIN" -a claude invoice
check "-a claude rejects an answer from the other account" 1 "+outside the 'claude' account"
STUB_ID=deadbeef-0000-4000-8000-00000000dead STUB_MODE=ok run "$CCASK_BIN" invoice
check "an invented session id is rejected"       1 "+WARNING" "-claude-propagenda --resume deadbeef"
STUB_MODE=textjson run "$CCASK_BIN" invoice
check "JSON written as text is still accepted"   0 "~^BEST " "+$B"
STUB_MODE=proseid run "$CCASK_BIN" invoice
check "answer only in prose: id recovered, still validated" 0 "~^BEST " "+recovered from the model" \
      "+cd $T/work/beta && claude-propagenda --resume $B"
STUB_ID=deadbeef-0000-4000-8000-00000000dead STUB_MODE=proseid run "$CCASK_BIN" invoice
check "prose with an invented id is still rejected" 1 "+WARNING" "-claude-propagenda --resume deadbeef"
STUB_MODE=prose run "$CCASK_BIN" invoice
check "no usable answer: falls back to the ranking" 1 "+no structured answer" "+$A" "+\$0.0123"
STUB_MODE=budget run "$CCASK_BIN" invoice
check "budget stop is reported, ranking shown"   1 "+hit the" "+$A"
STUB_MODE=error run "$CCASK_BIN" invoice
check "model error is reported, ranking shown"   1 "+reported an error" "+$A"
STUB_MODE=garbage run "$CCASK_BIN" invoice
check "crash with non-JSON output is reported"   1 "+claude failed" "+simulated crash"
STUB_MODE=sleep CCASK_TIMEOUT=1 run "$CCASK_BIN" invoice
check "timeout is reported, ranking shown"       1 "+timed out" "+$A"

# ---------------------------------------------------------------- agent mode + clipboard
: > "$CLIP_LOG"; run ccfind -n zebrafinch
OUT="$OUT
clipboard=[$(clip)]"
check "human: -n copies the top resume line" 0 "+copied to clipboard" "+clipboard=[cd $T/work/alpha && claude --resume $A"
for v in "${AGENT_VARS[@]}"; do
  : > "$CLIP_LOG"; run "${no_agent_env[@]}" "$v=1" ccfind -n zebrafinch
  OUT="$OUT
clipboard=[$(clip)]"
  check "ccfind: $v=1 is an agent: plain list, no clipboard" 0 "+claude --resume $A" "-copied" "+clipboard=[]"
  : > "$CLIP_LOG"; STUB_MODE=ok run "${no_agent_env[@]}" "$v=1" "$CCASK_BIN" invoice
  OUT="$OUT
clipboard=[$(clip)]"
  check "ccask: $v=1 is an agent too (lists agree)" 0 "~^BEST " "-copied" "+clipboard=[]"
done
: > "$CLIP_LOG"; run ccfind --agent zebrafinch
OUT="$OUT
clipboard=[$(clip)]"
check "--agent forces agent mode (and -n)" 0 "+claude --resume $A" "+clipboard=[]"
: > "$CLIP_LOG"; run "${no_agent_env[@]}" CLAUDECODE=1 ccfind -n --copy zebrafinch
OUT="$OUT
clipboard=[$(clip)]"
check "--copy copies even for agents" 0 "+clipboard=[cd $T/work/alpha"
: > "$CLIP_LOG"; run ccfind -n --no-copy zebrafinch
OUT="$OUT
clipboard=[$(clip)]"
check "--no-copy stops the human copy" 0 "-copied" "+clipboard=[]"
run "${no_agent_env[@]}" CLAUDECODE=1 CLAUDE_CODE_SESSION_ID=$A ccfind -n invoice
check "agent mode skips the calling session" 0 "+skipped the session you are calling from" "-$A" "+$B"
run ccfind -n invoice
check "human mode keeps every session" 0 "+$A" "+$B" "-skipped"
: > "$CLIP_LOG"; STUB_MODE=ok run "$CCASK_BIN" invoice
OUT="$OUT
pbcopy-calls=$(grep -c . "$CLIP_LOG")
clipboard=[$(clip)]"
check "ccask (human): copies BEST once, its own ccfind call does not copy" 0 \
      "+copied to clipboard" "+pbcopy-calls=1" "+clipboard=[cd $T/work/beta && claude-propagenda --resume $B"

# ---------------------------------------------------------------- guard + sandbox
GUARD="$(dirname "$(readlink -f "$CCASK_BIN")")/ccask-guard"
GC="$T/guard-count"
g() {  # g <want-exit> <tool-call json> <label>
  : > "$GC"
  OUT=$(printf '%s' "$2" | CCASK_GUARD_COUNT="$GC" CCASK_MAX_TOOLS=5 CCASK_DIR="$HERE" "$GUARD" 2>&1); RC=$?
  check "guard: $3" "$1"
}
P="$HOME/.claude-propagenda/projects"
g 0 '{"tool_name":"Bash","tool_input":{"command":"ccfind -n \"gated invoice\""}}' "allows ccfind -n"
g 0 '{"tool_name":"Bash","tool_input":{"command":"ccfind read 0546caa9"}}'          "allows ccfind read"
g 2 '{"tool_name":"Bash","tool_input":{"command":"ls /tmp"}}'                       "blocks other commands"
g 2 '{"tool_name":"Bash","tool_input":{"command":"ccfind -n x; touch y"}}'          "blocks ; chaining"
g 2 '{"tool_name":"Bash","tool_input":{"command":"ccfind -n $(id)"}}'               "blocks \$( ) substitution"
g 2 '{"tool_name":"Bash","tool_input":{"command":"ccfind -n x > out"}}'             "blocks > redirection"
g 2 '{"tool_name":"Bash","tool_input":{"command":"ccfind -n x\ntouch y"}}'         "blocks newlines"
g 2 '{"tool_name":"Bash","tool_input":{"command":"ccfind --reindex"}}'              "blocks other ccfind options"
g 0 '{"tool_name":"Grep","tool_input":{"pattern":"x","path":"'"$P"'"}}'             "allows Grep in transcripts"
g 2 '{"tool_name":"Grep","tool_input":{"pattern":"x","path":"'"$HOME"'/.ssh"}}'     "blocks Grep outside"
g 2 '{"tool_name":"Read","tool_input":{"file_path":"'"$P"'/../../.ssh/id_rsa"}}'    "blocks ../ escapes"
g 2 '{"tool_name":"Glob","tool_input":{"pattern":"/etc/*"}}'                        "blocks absolute Glob outside"
g 2 '{"tool_name":"Write","tool_input":{"file_path":"/tmp/x"}}'                     "blocks unlisted tools"
g 0 '{"tool_name":"StructuredOutput","tool_input":{}}'                              "always allows the final answer"
: > "$GC"; for i in 1 2 3; do printf '{"tool_name":"Bash","tool_input":{"command":"ccfind read a"}}' \
  | CCASK_GUARD_COUNT="$GC" CCASK_MAX_TOOLS=2 "$GUARD" >/dev/null 2>&1; done
OUT=$(printf '{"tool_name":"Bash","tool_input":{"command":"ccfind read a"}}' | CCASK_GUARD_COUNT="$GC" CCASK_MAX_TOOLS=2 "$GUARD" 2>&1); RC=$?
check "guard: budget of 2 blocks later calls" 2 "+tool limit"
OUT=$(printf '{"tool_name":"StructuredOutput","tool_input":{}}' | CCASK_GUARD_COUNT="$GC" CCASK_MAX_TOOLS=2 "$GUARD" 2>&1); RC=$?
check "guard: the answer still gets through after the budget" 0

STUB_MODE=ok run "$CCASK_BIN" invoice
OUT=$(cat "$STUB_LOG.args"); RC=0
check "claude gets the guard hook" 0 "+PreToolUse" "+ccask-guard"
# probe target outside every allowed folder; only created if the sandbox fails
export PROBE_OUTSIDE="$HERE/.sbprobe"
STUB_MODE=probe run "$CCASK_BIN" invoice
OUT=$(cat "$STUB_LOG.probe" 2>&1); RC=0
check "sandbox blocks writes outside, and to transcripts; allows the cache" 0 \
      "+blocked $PROBE_OUTSIDE" "+blocked $HOME/.claude-propagenda/projects/.sbprobe" "+written $HOME/.cache/ccfind/.sbprobe"
mkdir -p "$T/noguard"; cp "$CCASK_BIN" "$(dirname "$(readlink -f "$CCASK_BIN")")/ccask-system.md" "$T/noguard/"
run "$T/noguard/ccask" invoice
check "ccask refuses to run without its guard (fails closed)" 1 "+missing or not executable"
AGENT_FENCE=/nonexistent/agent-fence run "$CCASK_BIN" invoice
check "ccask refuses to run without agent-fence (fails closed)" 1 "+not found on PATH"

echo
echo "$pass passed, $fail failed"
[ $fail -eq 0 ]
