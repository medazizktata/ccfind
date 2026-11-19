# ccfind — find any past agent session and get the command to reopen it

**For:** one person running many agent sessions across many folders and more than one Claude
config directory, who no longer remembers where a session was started.
**Job:** type what you remember and get the session plus a paste-ready
`cd <folder> && <tool> --resume <id>`, in about 10 seconds, free and offline.
**Not:** semantic search, a transcript backup, a team or cloud tool.

```
ccfind                         search box: type, Enter resumes, Ctrl-Y copies cd + resume
ccfind -n "gated invoice"      ranked list with a resume line under each; the top one is copied
ccfind -a <account> "…"        one Claude config directory only (default: all of them)
ccfind -p <folder> "…"         only sessions started in folders whose path contains <folder>
ccfind read <id>               print a session without reopening it
ccfind ask "…"                 AI fallback when your words don't match (costs money, see below)
```

Covers Claude Code (`~/.claude` and any other account folder, see Accounts), Codex, Cursor CLI,
opencode and Gemini CLI. New sessions are picked up on every search.

**Tips:** use rare words (names, file names, error text), look at the top 3–5, and skip `-p`
unless you know where the session was started.

## Accounts

ccfind finds more than one account of the same service, for Claude, Codex, Gemini CLI and
OpenCode. Another account is a sibling folder (`~/.claude-<name>`, `~/.codex-<name>`) that holds
sessions, or the home the tool's own variable points at when it is somewhere else:
`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `GEMINI_CLI_HOME`, `XDG_DATA_HOME` (OpenCode). Cursor CLI is one
account: it keeps its transcripts in `~/.cursor` whatever `CURSOR_CONFIG_DIR` says. It finds them on the first run and saves the list in
`~/.config/ccfind/accounts.json`. **`ccfind setup`** walks you through it: which accounts to
search, and which one `ccfind ask` runs under and bills (`ccfind setup --accounts a,b --ask a
--yes` answers it without a terminal). To change it by hand: edit that file to drop one, or to set `"ask"`, the account
`ccfind ask` runs under and bills (`CCASK_ACCOUNT=<name>` overrides it for one run); delete it to
look again. `ccfind -a <name>` limits a search to one account: `-a claude` is `~/.claude`,
`-a codex` is `~/.codex`, a Claude account is its `<name>` and every other service's is
`<service>-<name>` (`codex-work`, `gemini-work`, `opencode-work`).
A session of another account resumes with `claude-<name>` or `codex-<name>` when you have such a
command, otherwise with `env CLAUDE_CONFIG_DIR=... claude` or `env CODEX_HOME=... codex`.
`ccfind -v` (or `--verbose`) says which accounts were searched, how many sessions each holds and how
long it took, and names agent CLIs it found on the machine but cannot read yet (Antigravity,
Muse Code, Copilot, Qwen, Kiro, Droid, Goose, Crush, Aider and Amp are on that list). `ccfind ask`
ends with a note naming the account that ran the agent, e.g. `via account work (~/.claude-work)`;
`ccask -v` also says where that choice came from.

## Install

```
sh install.sh                     ccfind only, in ~/.local/bin
sh install.sh --skill             also the Claude Code skill, globally (user scope, ~/.claude)
sh install.sh --account NAME      also the skill, under one account only (~/.claude-NAME)
```

## The suite: one job per part

| Part | Job | Cost | Status |
|---|---|---|---|
| **ccfind** (this repo) | find and resume | free, ~10 s | the everyday tool |
| **ccfind ask** (`ask/`) | Haiku agent for vague memories | ~$0.003 per question, capped at $0.25 | 11/12 right, 0 wrong on a 12-question benchmark (2026-10-20); Sonnet also 11/12 at ~$0.06 |
| **[agent-fence](https://github.com/medazizktata/agent-fence)** | macOS sandbox for any agent CLI | free | separate project; `ccfind ask` requires it |

Reach for `ask` only when `ccfind -n` fails. Its agent is fenced from outside: a guard hook
allows only `ccfind` and transcript reads (15 calls at most), and agent-fence blocks file
writes. Resume lines are always built by ccfind, never by the model.

When an agent runs ccfind (detected automatically, or `--agent`), the output stays plain,
your clipboard is left alone, and the agent's own session is left out of the results.

## Fork of agsearch

A fork of [devcodes9/agsearch](https://github.com/devcodes9/agsearch) (MIT, by Dev Dalia),
branch `ccfind` = upstream plus our commits. Upstream's README is in `docs/UPSTREAM-README.md`.
What changed, and how to take upstream updates: `AGENTS.md`.

## Tests
    uvx pytest -q tests               upstream's suite plus ours, adapted where our output differs
    ./harness/test.sh                 end-to-end checks, free (stub claude, fake HOME)
    ./harness/test.sh --calibrate     proves the checks can fail
    ./harness/test.sh --real|--live   + your transcripts (free, set CCFIND_REAL_QUERY/_SID) | + one paid Haiku run
