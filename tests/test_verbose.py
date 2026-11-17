"""-v/--verbose: what ccfind searched and how long it took, on stderr only."""

import contextlib
import io
import json
import os
import tempfile
import unittest
import unittest.mock

from load_agsearch import load_agsearch


class VerboseTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = d.name
        self.ag = ag = load_agsearch()
        ag.HOME = self.home
        ag.CONFIG_PATH = os.path.join(self.home, "accounts.json")
        ag.INDEX_PATH = os.path.join(self.home, "index.json")
        beta = os.path.join(self.home, ".claude-beta")
        work = os.path.join(self.home, ".codex-work")
        ag.ACCOUNT_DIRS = {"beta": beta, "codex-work": work}
        ag.ACCOUNT_SOURCE = {"beta": "cc", "codex-work": "codex"}
        ag.ACCOUNT_PROJECTS = {"beta": os.path.join(beta, "projects"),
                               "codex-work": os.path.join(work, "sessions")}
        ag.DEFAULT_ROOTS = {"claude": os.path.join(self.home, ".claude", "projects"),
                            "codex": os.path.join(self.home, ".codex", "sessions")}
        ag.ASK_ACCOUNT = "beta"
        self.addCleanup(setattr, ag, "VERBOSE", False)
        with open(ag.INDEX_PATH, "w") as fh:
            json.dump({
                "a": {"source": "cc", "path": os.path.join(self.home, ".claude", "projects", "x", "a.jsonl")},
                "b": {"source": "cc", "path": os.path.join(beta, "projects", "x", "b.jsonl")},
                "c": {"source": "cc", "path": os.path.join(beta, "projects", "x", "c.jsonl")},
                "d": {"source": "codex", "path": os.path.join(work, "sessions", "2026", "d.jsonl")},
                "e": {"source": "cc", "path": "", "was": os.path.join(beta, "projects", "x", "e.jsonl"),
                      "expired": "2026-10-01"},
                "f": {"source": "cc", "path": "", "expired": "2026-10-01"},      # no path recorded
            }, fh)

    def report(self, verbose=True):
        self.ag.VERBOSE = verbose
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.ag._verbose_accounts()
        return err.getvalue()

    def test_sessions_are_counted_per_account_by_where_their_transcript_lives_or_lived(self):
        self.assertEqual(self.ag._account_counts(), {"claude": 1, "beta": 3, "codex-work": 1, "?": 1})

    def test_the_report_lists_every_account_with_its_count_and_who_ask_bills(self):
        out = self.report()
        self.assertIn("beta", out)
        self.assertIn("3 session(s)", out)
        self.assertIn("codex-work", out)
        self.assertIn("ask bills: beta", out)
        self.assertIn("1 session(s), kept as expired", out)

    def test_tools_that_are_here_but_not_read_are_named_not_skipped_silently(self):
        os.makedirs(os.path.join(self.home, ".kiro"))
        os.makedirs(os.path.join(self.home, ".gemini", "antigravity-cli"))
        self.ag.NOT_INDEXED = {**self.ag.NOT_INDEXED, "muse": ([], [])}     # no folder, no command
        with unittest.mock.patch.object(self.ag.shutil, "which", return_value=None):
            self.assertEqual(sorted(self.ag._unindexed_tools()), ["antigravity", "kiro"])

    def test_the_report_and_setup_mention_them(self):
        os.makedirs(os.path.join(self.home, ".qwen"))
        with unittest.mock.patch.object(self.ag.shutil, "which", return_value=None):
            self.assertIn("not indexed (no session reader yet): qwen", self.report())

    def test_nothing_is_printed_without_the_flag(self):
        self.assertEqual(self.report(verbose=False), "")

    def test_the_flag_goes_to_stderr_and_stdout_keeps_only_the_answer(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = self.ag.main(["-v", "--version"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.getvalue().startswith("agsearch "))
        self.assertTrue(self.ag.VERBOSE)

    def test_the_long_form_is_the_same_flag(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.ag.main(["--verbose", "--version"])
        self.assertTrue(self.ag.VERBOSE)


if __name__ == "__main__":
    unittest.main()
