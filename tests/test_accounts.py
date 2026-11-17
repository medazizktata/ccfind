"""Other Claude accounts: found as ~/.claude-<name>, saved once, limited with -a, resumed by name."""

import json
import os
import stat
import tempfile
import unittest

from load_agsearch import load_agsearch


class AccountTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = d.name
        self.ag = ag = load_agsearch()
        ag.HOME = self.home
        ag.CONFIG_PATH = os.path.join(self.home, "config", "accounts.json")

    def account(self, name, projects=True, launcher=False):
        d = os.path.join(self.home, ".claude-" + name)
        os.makedirs(os.path.join(d, "projects") if projects else d)
        if launcher:
            path = os.path.join(d, "mcp-launch.sh")
            with open(path, "w") as fh:
                fh.write("#!/bin/sh\n")
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return d

    def use(self, accounts, ask=None):
        """Make the module act as if it had loaded this account table."""
        self.ag.ACCOUNT_DIRS = accounts
        self.ag.ACCOUNT_PROJECTS = {n: os.path.join(d, "projects") for n, d in accounts.items()}
        self.ag.ASK_ACCOUNT = ask

    def test_finds_only_folders_that_have_projects_and_a_free_name(self):
        a = self.account("alpha")
        self.account("empty", projects=False)
        self.account("All")                         # "all" already means every account
        self.assertEqual(self.ag._find_accounts(), {"alpha": a})

    def test_names_are_lowercase_so_that_the_lowercased_flag_matches(self):
        d = self.account("Mixed")
        self.assertEqual(self.ag._find_accounts(), {"mixed": d})

    def test_first_run_saves_what_it_found_and_later_runs_read_the_file(self):
        self.account("alpha")
        accounts, ask = self.ag._load_accounts()
        self.assertEqual(list(accounts), ["alpha"])
        self.assertIsNone(ask)
        with open(self.ag.CONFIG_PATH) as fh:
            saved = json.load(fh)
        self.assertEqual(saved["accounts"], {"alpha": "~/.claude-alpha"})
        self.account("beta")                        # appears later: not picked up unasked
        self.assertEqual(list(self.ag._load_accounts()[0]), ["alpha"])

    def test_editing_the_file_drops_an_account_and_sets_the_ask_account(self):
        self.account("alpha")
        self.account("beta")
        self.ag._load_accounts()
        with open(self.ag.CONFIG_PATH, "w") as fh:
            json.dump({"accounts": {"beta": "~/.claude-beta"}, "ask": "beta"}, fh)
        accounts, ask = self.ag._load_accounts()
        self.assertEqual(accounts, {"beta": os.path.join(self.home, ".claude-beta")})
        self.assertEqual(ask, "beta")

    def test_a_broken_file_is_searched_around_and_left_alone(self):
        self.account("alpha")
        os.makedirs(os.path.dirname(self.ag.CONFIG_PATH))
        with open(self.ag.CONFIG_PATH, "w") as fh:
            fh.write("{not json")
        self.assertEqual(list(self.ag._load_accounts()[0]), ["alpha"])
        with open(self.ag.CONFIG_PATH) as fh:       # a half-written or hand-broken file is not
            self.assertEqual(fh.read(), "{not json")  # replaced: that would lose "ask" and edits

    def test_an_unwritable_config_location_does_not_stop_the_search(self):
        self.account("alpha")
        with open(os.path.join(self.home, "f"), "w"):
            pass
        self.ag.CONFIG_PATH = os.path.join(self.home, "f", "accounts.json")   # parent is a file
        self.assertEqual(list(self.ag._load_accounts()[0]), ["alpha"])

    def test_resume_goes_through_the_accounts_own_launcher(self):
        d = self.account("alpha", launcher=True)
        self.use({"alpha": d})
        path = os.path.join(d, "projects", "slug", "s1.jsonl")
        self.assertEqual(self.ag._account_launch(path), [os.path.join(d, "mcp-launch.sh")])
        line = self.ag.resume_command("/repo", self.ag._account_launch(path) + ["--resume", "s1"])
        self.assertEqual(line, "cd /repo && claude-alpha --resume s1")

    def test_without_a_launcher_resume_names_the_config_dir(self):
        d = self.account("beta")
        self.use({"beta": d})
        path = os.path.join(d, "projects", "slug", "s1.jsonl")
        self.assertEqual(self.ag._account_launch(path),
                         ["env", "CLAUDE_CONFIG_DIR=" + d, "claude"])

    def test_the_default_account_and_other_paths_use_plain_claude(self):
        self.use({"alpha": self.account("alpha", launcher=True)})
        self.assertIsNone(self.ag._account_launch(
            os.path.join(self.home, ".claude", "projects", "slug", "s1.jsonl")))

    def test_a_path_that_only_starts_with_the_same_letters_is_not_that_account(self):
        d = self.account("alpha", launcher=True)
        self.use({"alpha": d})
        self.assertIsNone(self.ag._account_launch(os.path.join(d, "projects-two", "s1.jsonl")))


if __name__ == "__main__":
    unittest.main()
