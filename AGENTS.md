# AGENTS.md — ccfind

How an agent should use and maintain `ccfind`. Usage for people is in `README.md`.

## Finding a session for the user

1. `ccfind -n "<distinctive words>"`. Use names, file names, error text or exact phrases the
   user remembers. Generic words ("fix", "setup") match hundreds of sessions.
2. Skip the session you are running in. It contains the query, so it often ranks first.
3. Treat the top 3–5 as candidates, not the first hit as the answer. The search is lexical
   (BM25, stemming, typo fallback), not semantic.
4. Confirm with `ccfind read <id-prefix>`, which prints a session without resuming it.
5. Give the user the line printed under the result. It is already correct:
   `cd <launch dir> && claude --resume <id>`, or `claude-<name> --resume <id>` for
   sessions under another account's folder `~/.claude-<name>`.

`ccfind -p <path-substring> "<words>"` limits the search to matching project paths.
`ccfind -a <default>|<key>|all` limits it to one account's transcripts (`claude`, `codex`,
`gemini`, `cursor`, `opencode` are the default accounts). Accounts are found per service
(`ACCOUNT_HOMES`, one entry each): `~/.claude-<name>` with a `projects/` folder is the Claude
account `<name>`, `~/.codex-<name>` the Codex account `codex-<name>`, and the home a tool's own
variable points at counts too (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
`GEMINI_CLI_HOME`, `XDG_DATA_HOME`; the last two name the folder that contains the home, see
`env_parent`). Gemini and OpenCode have no sibling-folder convention, so their accounts come from
the variable or the saved file. Cursor has one account: run for real, `cursor-agent` with
`CURSOR_CONFIG_DIR` set moves its config and `chats/` there but still writes the transcripts
(`projects/`) to `~/.cursor`, so the variable separates nothing ccfind reads.

To add a tool: put its session format in `SOURCES` (an adapter needs a real session folder to
read it from, so it cannot be written from a description) and one entry in `ACCOUNT_HOMES`. Tools
seen on the machine without an adapter are listed in `NOT_INDEXED` and named by `-v` and `setup`.
`ccfind -v` prints to stderr only, so results stay clean. `ccask` ends with
`via account <name> (<dir>)` and, with `-v`, says whether that came from `CCASK_ACCOUNT`, the
saved `"ask"` or the environment. The default is all. The accounts are
found on the first run and saved in `~/.config/ccfind/accounts.json`. `ccfind setup` is the
interactive way to change it (`cmd_setup`; `--accounts`, `--ask NAME|claude|none` and `--yes` skip
the questions; `ccfind setup docker` is still a search, see `_is_setup`). Editing the file also
works, and deleting it looks again. A file that cannot be parsed is searched around, never replaced. Unknown options, `-a` with a bad value and `-p` with no value exit 2 rather than being
searched for as words. Use `--` before a query that starts with a dash.

## Agent mode and the clipboard

Agent mode turns on with `--agent`, with `CCFIND_AGENT=1`, or when the shell has any of
`CLAUDECODE AI_AGENT OPENCODE CURSOR_AGENT CODEX_SANDBOX`. Those were verified 2026-10-17 for
claude, opencode and cursor-agent; `CODEX_SANDBOX` is unverified because codex could not run.
`CCFIND_AGENT=0` forces human mode.

- Agent mode never copies to the clipboard. It also drops the calling session
  (`CLAUDE_CODE_SESSION_ID`, `OPENCODE_SESSION_ID`, `CURSOR_CONVERSATION_ID`) from results.
- In human mode, `-n` copies the top resume line and `ccask` copies the BEST line.
  `--copy` and `--no-copy` override either way. ccask's own internal ccfind call never copies.
- The variable list exists twice, in ccfind's `AGENT_VARS` and in ccask's. test.sh runs every
  variable through both and fails if they disagree, so update both.
- test.sh uses a stub `pbcopy` and `CCFIND_AGENT=0`. It runs inside agents, which would
  otherwise make every run an agent run.

## How the index updates

There is no daemon, file watcher or hook. Each `ccfind` run (search box or `-n`) calls
`build_index()` once before searching:

1. It walks `~/.claude/projects` and every saved account's `projects` folder (`SOURCES["cc"]["roots"]`)
   and stats every `.jsonl`, subagent transcripts included.
2. It compares each mtime with `~/.cache/ccfind/meta.json`:
   - unchanged: reuse the cached fragment in `~/.cache/ccfind/frag/` without reading it
     (`filesids.json` says which sessions it holds; rows are read only for changed sessions
     and for the sessions a search prints)
   - new, changed, or fragment missing: re-parse the **whole** file
   - deleted: drop its fragment
3. It writes `sessions.tsv` (one row per session; a session whose files are unchanged keeps
   its row, tracked in `sessions.sig.json`) and ranks against it. `forkfam.json` caches fork
   detection the same way.

Consequences:
- A transcript written a moment ago is searchable on the next run.
- The open search box does not update. Each keystroke runs `ccfind _filter`, which re-ranks the
  `sessions.tsv` snapshot taken at launch. Reopen `ccfind` to see newer sessions.
- A changed file is re-read in full, so a large transcript that is still being written adds
  seconds to every search.
- `ccfind --reindex` discards the cache and rebuilds everything (~50s over ~7 GB, 2026-10-17).

## Files, fork and upstream

This folder is a git fork of github.com/devcodes9/agsearch (MIT). Branch `ccfind` is v0.2.0
plus our commits (`git log --oneline v0.2.0..ccfind`); remote `upstream` is the original.
- `agsearch`: the tool, kept under upstream's file name so merges stay simple.
  `~/.local/bin/ccfind` links here, so do not move this folder.
- `ask/`: `ccfind ask` (ccask, ccask-guard, ccask-system.md). Run logs `ask/.ccask-last-*`
  are git-ignored.
- `harness/test.sh`: end-to-end checks. `tests/`: upstream's pytest suite.
- `benchmarks/`: warm and cold search timings plus a row-level cache check, on real transcripts.
  `benchmarks/README.md` has the method, results and calibration.
- `docs/UPSTREAM-README.md`: upstream's README, unchanged.
- `.archive/`: the pre-fork layout (the patch script, the built copy). Git-ignored, kept
  because nothing here is deleted.

What the fork changes (`git log v0.2.0..ccfind` lists the commits):
- index every `~/.claude-<name>/projects` too (found once, saved in `~/.config/ccfind/accounts.json`),
  and resume those sessions with `claude-<name>` (its `mcp-launch.sh`, a `claude-<name>` on PATH, or
  `env CLAUDE_CONFIG_DIR=... claude` when neither exists)
- `-a/--account`, `--`, errors for unknown options and missing values
- a cd/resume line under each `-n` result; humans get the top one copied
- agent mode (see above); cache dir `~/.cache/ccfind`
- no deletes: upstream's one pruning call is removed. Stale fragments are never read.
- `ask` subcommand, `ask/`, `harness/`
- cherry-picked upstream #58 (crash fix)

Deliberately not taken: upstream #59 (keeps deleted transcripts searchable for 180 days).
It adds its own pruning deletes, and transcripts here are kept 365 days anyway. Revisit if
`cleanupPeriodDays` drops.

Taking upstream changes:
    git fetch upstream
    git log --oneline ccfind..upstream/main      # read them; check each for delete calls
    git cherry-pick <sha>                        # or merge, then resolve
    uvx pytest -q tests && ./harness/test.sh && ./harness/test.sh --calibrate
Upstream tests that assert old output (id shown once, "agsearch read") were adapted in one
commit that keeps each test's intent. Do the same for new ones.

## Verified and not verified (2026-10-17)

Verified by running it:
- A new transcript, an appended line and a moved-away transcript each show up correctly on
  the next search (tested in a throwaway `HOME`).
- Resume lines route correctly: unpatched agsearch sends another account's sessions to plain
  `claude`, which cannot open them.
- A message `cwd` in a subdirectory resolves back to the launch dir.

Not verified:
- Search quality beyond two real queries.
- Codex, Cursor, Gemini and opencode sources (built into upstream, untested here).
- That the code makes no network calls. The source was grepped, not audited line by line.

Transcripts are kept for 365 days (`cleanupPeriodDays` in both `settings.json` files). A
shorter setting would make old sessions unsearchable.

## ccask (AI fallback)

`ccask "<words>"` runs `ccfind -n`, then hands the candidates to `claude -p --model haiku`
with `ccask-system.md` as the system prompt. It runs under `CCASK_ACCOUNT=<name>` if set, else
the account named by `"ask"` in `~/.config/ccfind/accounts.json`, else the one the environment
already selects (`CLAUDE_CONFIG_DIR`, default `~/.claude`), and bills that account. The agent is
always the `claude` CLI (`claude -p`, with its flags); another tool would need its own command.

Guard rails, enforced outside the model (three layers):
- `ccask-guard`, a PreToolUse hook passed with `--settings`, runs before every tool call:
  - a budget of `CCASK_MAX_TOOLS` calls (default 15)
  - Bash: exactly one plain `ccfind -n …` or `ccfind read …`; no `; & | ` $ < > ( ) { } \`
    or newlines
  - Read, Grep and Glob: only inside the transcript folders
  - every other tool is blocked, except `StructuredOutput`, the final answer. That is always
    allowed and never counted, so a budget-stopped agent can still answer.
  The guard must not use bash here-strings (`<<<`). Under the sandbox, bash 3.2 cannot
  create their temp file in /tmp, so every call failed and was denied. That is how the
  answer tool got blocked once.
- `agent-fence --read-only` (~/Desktop/agent-fence) wraps the whole claude process tree
  (`ccask.sb` is retired). It adds `--allow-write ~/.cache/ccfind` and `--protect` for both
  transcript folders.
- Former `ccask.sb` rules, now done by agent-fence: Writes (and so deletes and
  moves) are allowed only in the ask account's config folder, ~/.cache/ccfind, $TMPDIR,
  ~/Library/Caches, /private/tmp/claude-<uid> and bash here-doc files. Both transcript
  folders are write-protected even inside those. Reads and network stay open (claude needs
  the API).
- ccask fails closed: it refuses to run if agent-fence or the guard is missing
  (`AGENT_FENCE` overrides the binary; tests use it).
- Every run keeps `.ccask-last-stream.jsonl` (every event: tool calls, results, answer) and
  `.ccask-last-output.json` (the result event), overwritten each time. Read the stream
  first when a run misbehaves.
- If the schema'd answer is missing, ccask accepts JSON written as text, then a
  `best_id: <id>` in prose. Either way the id is validated and the resume line is built by
  the script.
- `-a claude|<name>|all` is passed to the first ccfind call and to the model, and any
  returned id outside that account is rejected.
- Tools are `ccfind -n`, `ccfind read`, Read, Grep and Glob only. A test `ls /tmp` was denied.
- No MCP servers, no user settings, plugins or hooks, and no saved session, so its runs never
  show up in searches.
- Capped by `CCASK_BUDGET` (default $0.25) and `CCASK_TIMEOUT` (default 300s).
- The model answers through a JSON schema. The script resolves each id against
  `~/.cache/ccfind/index.json` and prints the resume line itself. Unknown or ambiguous ids
  produce a warning and exit 1.
- On a model error, timeout or budget stop, it prints the plain ccfind ranking and exits 1.
  Usage errors exit 2.

Do not read `sessions.tsv` for lookups. It holds only the last search's rows, narrowed by
`-p`. This broke the first resolver.

Measured on 2026-10-17, one query about an invoice page, with one known session as the answer:

| run | answer | turns | cost |
|---|---|---|---|
| 1 | NOT FOUND (right session only mentioned in prose) | 22 | $0.21 |
| 2 | correct BEST | 12 | $0.14 |
| 3 | wrong BEST; the right one under ALSO | 24 | $0.19 |

| 4 | `-a <account>`: no structured answer, fallback ranking shown (cost not printed then) | ? | ? |
| 5 | `-a <account>`: timed out at 300s, nothing returned | ? | ? |

Plain `ccfind -n` had it 3rd for free in ~10s. Untested: `CCASK_MODEL=sonnet`. The cause of
run 4 is unknown. `.ccask-last-output.json` now keeps the raw response for next time (a
timeout leaves it empty).

## Tests

Run `./harness/test.sh` and `uvx pytest -q tests` after every change; both must pass.

- Default: 76 offline checks (agent mode, clipboard and `ccfind ask` included): guard verdicts, sandbox write probe, fail-closed with no
  guard and no agent-fence, prose recovery, and an ast-grep scan for delete calls
  (`nodelete-scan`, calibrated on samples in the agent-fence harness). in a throwaway HOME (left in $TMPDIR, never deleted), with
  fixture transcripts for both accounts and a stub `claude`. They cover ccfind ranking,
  routing, launch dir, `-a`, option errors, index updates and no deletes, plus every ccask
  path: answer, invented id, wrong account, JSON as text, no answer, budget, error, crash,
  timeout, and the locked-down flags.
- `--calibrate`: re-runs the suite against a do-nothing ccfind and sabotaged builds (no
  routing, no account filter, no agent detection, no CCFIND_EXCLUDE, ccask accepting invented
  ids, ccask not passing or not hiding the caller's session). Each must produce failures.
  It also tries an allow-all guard and an allow-all sandbox.
  2026-10-20: all 10 caught; the unmodified build passes.
- Calling session: in agent mode ccask passes the caller's session id to its agent as
  `CCFIND_EXCLUDE` and hides its transcript with `agent-fence --hide`. Without that, the agent
  found the calling session with Grep and cited it (2 of 12 benchmark runs, 2026-10-20).
  The open-sandbox run writes `harness/.sbprobe` (2 bytes). That file is expected
  and gets overwritten each time.
- `--real`: free checks on your own transcripts. Set `CCFIND_REAL_QUERY` and `CCFIND_REAL_SID`
  (and `CCFIND_REAL_ACCOUNT` for a session outside `~/.claude`); the session must be in the top 3.
- `--live`: one paid Haiku run. It is a quality check and currently fails.
- Fixture paths must be normalised. `$TMPDIR`'s trailing `/` once produced `//`, which broke
  slug matching in the fixtures only.
