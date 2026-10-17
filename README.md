# ccfind — find any past agent session and get the command to reopen it

**For:** one person running many agent sessions across many folders and two Claude accounts,
who no longer remembers where a session was started.
**Job:** type what you remember and get the session plus a paste-ready
`cd <folder> && <tool> --resume <id>`, in about 10 seconds, free and offline.
**Not:** semantic search, a transcript backup, a team or cloud tool.

```
ccfind                         search box: type, Enter resumes, Ctrl-Y copies cd + resume
ccfind -n "gated invoice"      ranked list with a resume line under each; the top one is copied
ccfind -a propagenda "…"       one Claude account (claude, propagenda, all = default)
ccfind -p Propagenda "…"       only sessions started in folders whose path contains Propagenda
ccfind read <id>               print a session without reopening it
ccfind ask "…"                 AI fallback when your words don't match (costs money, see below)
```

Covers Claude Code (`~/.claude` and `~/.claude-propagenda`), Codex, Cursor CLI, opencode and
Gemini CLI. New sessions are picked up on every search.

**Tips:** use rare words (names, file names, error text), look at the top 3–5, and skip `-p`
unless you know where the session was started.

## The suite: one job per part

| Part | Job | Cost | Status |
|---|---|---|---|
| **ccfind** (this repo) | find and resume | free, ~10 s | the everyday tool |
| **ccfind ask** (`ask/`) | Haiku agent for vague memories | ~$0.03–0.20 | experimental: right best match 1 in 3 on the hard test |
| **[agent-fence](https://github.com/medazizktata/agent-fence)** | macOS sandbox for any agent CLI | free | separate project; `ccfind ask` requires it |

Reach for `ask` only when `ccfind -n` fails. Its agent is fenced from outside: a guard hook
allows only `ccfind` and transcript reads (15 calls at most), and agent-fence blocks file
writes. Resume lines are always built by ccfind, never by the model.

When an agent runs ccfind (detected automatically, or `--agent`), the output stays plain,
your clipboard is left alone, and the agent's own session is left out of the results.

## Fork of agsearch

A fork of [devcodes9/agsearch](https://github.com/devcodes9/agsearch) (MIT, by Dev Dalia),
branch `ccfind` = v0.2.0 plus our commits. Upstream's README is in `docs/UPSTREAM-README.md`.
What changed, and how to take upstream updates: `AGENTS.md`.

## Tests
    uvx pytest -q tests               upstream's suite (182), adapted where our output differs
    ./harness/test.sh                 76 end-to-end checks, free (stub claude, fake HOME)
    ./harness/test.sh --calibrate     proves the checks can fail
    ./harness/test.sh --real|--live   + real transcripts (free) | + one paid Haiku run
