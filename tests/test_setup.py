"""`ccfind setup`: choose which accounts are searched and which one `ask` bills, then save."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from load_agsearch import load_agsearch


class SetupTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = d.name
        self.ag = ag = load_agsearch()
        ag.HOME = self.home
        ag.CONFIG_PATH = os.path.join(self.home, "config", "accounts.json")
        ag.PROJECTS_DIR = os.path.join(self.home, ".claude", "projects")
        for name in ("alpha", "beta"):
            os.makedirs(os.path.join(self.home, ".claude-" + name, "projects"))
        ag._ACCOUNTS, ag.ACCOUNT_DIRS, ag.ACCOUNT_SOURCE, ag.ASK_ACCOUNT = {}, {}, {}, None
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for h in ag.ACCOUNT_HOMES.values():              # the developer's own must not leak in
            os.environ.pop(h["env"] or "", None)

    def run_setup(self, argv=(), answers=()):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(answers)) as asked, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = self.ag.cmd_setup(list(argv))
        return rc, out.getvalue(), asked.call_count

    def saved(self):
        with open(self.ag.CONFIG_PATH) as fh:
            return json.load(fh)

    def test_pressing_enter_everywhere_searches_everything_found_and_asks_the_environment(self):
        rc, _out, _n = self.run_setup(answers=["", "", ""])
        self.assertEqual(rc, 0)
        self.assertEqual(self.saved(), {"accounts": {"alpha": "~/.claude-alpha",
                                                     "beta": "~/.claude-beta"}, "ask": None})

    def test_numbers_choose_the_searched_accounts_and_the_billed_one(self):
        rc, _out, _n = self.run_setup(answers=["2", "2", "y"])     # beta only; 2 = beta
        self.assertEqual(rc, 0)
        self.assertEqual(self.saved(), {"accounts": {"beta": "~/.claude-beta"}, "ask": "beta"})

    def test_names_and_none_work_and_the_default_account_can_be_billed_by_name(self):
        rc, _out, _n = self.run_setup(answers=["none", "claude", "y"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.saved(), {"accounts": {}, "ask": "claude"})

    def test_answering_n_to_save_writes_nothing(self):
        rc, out, _n = self.run_setup(answers=["all", "0", "n"])
        self.assertEqual(rc, 1)
        self.assertIn("Not saved", out)
        self.assertFalse(os.path.exists(self.ag.CONFIG_PATH))

    def test_the_options_answer_everything_without_asking(self):
        rc, _out, asked = self.run_setup(["--accounts", "alpha", "--ask", "alpha", "--yes"])
        self.assertEqual((rc, asked), (0, 0))
        self.assertEqual(self.saved(), {"accounts": {"alpha": "~/.claude-alpha"}, "ask": "alpha"})

    def test_an_unknown_account_is_an_error_and_leaves_the_file_alone(self):
        os.makedirs(os.path.dirname(self.ag.CONFIG_PATH))
        with open(self.ag.CONFIG_PATH, "w") as fh:
            fh.write('{"accounts": {}, "ask": null}')
        rc, _out, _n = self.run_setup(["--accounts", "nope", "--yes"])
        self.assertEqual(rc, 2)
        with open(self.ag.CONFIG_PATH) as fh:
            self.assertEqual(fh.read(), '{"accounts": {}, "ask": null}')

    def test_asking_to_bill_an_account_that_is_not_searched_is_an_error(self):
        rc, _out, _n = self.run_setup(["--accounts", "alpha", "--ask", "beta", "--yes"])
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(self.ag.CONFIG_PATH))

    def test_end_of_input_takes_the_defaults(self):
        rc, _out, _n = self.run_setup(answers=[EOFError(), EOFError(), EOFError()])
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(self.saved()["accounts"]), ["alpha", "beta"])

    def test_the_saved_choice_is_the_default_the_next_time(self):
        os.makedirs(os.path.dirname(self.ag.CONFIG_PATH))
        with open(self.ag.CONFIG_PATH, "w") as fh:
            json.dump({"accounts": {"beta": "~/.claude-beta"}, "ask": "beta"}, fh)
        beta = os.path.join(self.home, ".claude-beta")
        self.ag._ACCOUNTS, self.ag.ACCOUNT_DIRS = {"beta": ("cc", beta)}, {"beta": beta}
        self.ag.ASK_ACCOUNT = "beta"
        rc, _out, _n = self.run_setup(answers=["", "", ""])         # Enter keeps what was saved
        self.assertEqual(rc, 0)
        self.assertEqual(self.saved(), {"accounts": {"beta": "~/.claude-beta"}, "ask": "beta"})

    def test_an_account_saved_by_hand_outside_the_usual_place_is_kept_as_a_choice(self):
        odd = os.path.join(self.home, "elsewhere", "cfg")
        os.makedirs(os.path.join(odd, "projects"))
        self.ag._ACCOUNTS, self.ag.ACCOUNT_DIRS = {"odd": ("cc", odd)}, {"odd": odd}
        rc, _out, _n = self.run_setup(["--accounts", "odd", "--ask", "none", "--yes"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.saved()["accounts"], {"odd": "~/elsewhere/cfg"})

    def test_accounts_of_another_service_are_listed_searched_and_saved_but_never_billed(self):
        os.makedirs(os.path.join(self.home, ".codex-work", "sessions"))
        rc, out, _n = self.run_setup(["--accounts", "all", "--ask", "none", "--yes"])
        self.assertEqual(rc, 0)
        self.assertIn("codex-work", out)
        self.assertEqual(self.saved()["accounts"]["codex-work"],
                         {"source": "codex", "dir": "~/.codex-work"})
        rc, _out, _n = self.run_setup(["--accounts", "all", "--ask", "codex-work", "--yes"])
        self.assertEqual(rc, 2)                                     # ask runs the claude CLI

    def test_claude_as_the_billed_account_is_reported_to_ccask(self):
        self.ag.ASK_ACCOUNT = "claude"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.ag.main(["_accounts"])
        self.assertTrue(out.getvalue().splitlines()[-1].endswith(os.path.join(self.home, ".claude")))

    def test_only_setup_alone_or_with_options_is_the_command(self):
        for argv in (["setup"], ["setup", "--yes"], ["setup", "--accounts", "a"]):
            self.assertTrue(self.ag._is_setup(argv), argv)
        for argv in ([], ["setup", "docker"], ["-n", "setup"], ["--", "setup"], ["Setup"]):
            self.assertFalse(self.ag._is_setup(argv), argv)


if __name__ == "__main__":
    unittest.main()
