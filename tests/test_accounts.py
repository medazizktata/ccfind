"""Other accounts of a service (Claude, Codex): found beside the default, saved once, limited with
-a, and resumed through their own home."""

import json
import os
import stat
import tempfile
import unittest
from unittest import mock

from load_agsearch import load_agsearch


class AccountTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = d.name
        self.ag = ag = load_agsearch()
        ag.HOME = self.home
        ag.CONFIG_PATH = os.path.join(self.home, "config", "accounts.json")
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for var in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):    # the developer's own must not leak in
            os.environ.pop(var, None)

    def account(self, prefix, name, sub, launcher=False):
        d = os.path.join(self.home, f".{prefix}-{name}")
        os.makedirs(os.path.join(d, sub))
        if launcher:
            path = os.path.join(d, "mcp-launch.sh")
            with open(path, "w") as fh:
                fh.write("#!/bin/sh\n")
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return d

    def claude(self, name, **kw):
        return self.account("claude", name, "projects", **kw)

    def codex(self, name, **kw):
        return self.account("codex", name, "sessions", **kw)

    def use(self, accounts, ask=None):
        """Make the module act as if it had loaded this account table: {key: (source, dir)}."""
        ag = self.ag
        ag._ACCOUNTS = accounts
        ag.ACCOUNT_DIRS = {k: d for k, (_s, d) in accounts.items()}
        ag.ACCOUNT_SOURCE = {k: s for k, (s, _d) in accounts.items()}
        ag.ACCOUNT_PROJECTS = {k: os.path.join(d, ag.ACCOUNT_HOMES[s]["sub"])
                               for k, (s, d) in accounts.items()}
        ag.ASK_ACCOUNT = ask

    # -- finding them

    def test_finds_only_folders_that_have_the_sessions_folder_and_a_free_name(self):
        a = self.claude("alpha")
        os.makedirs(os.path.join(self.home, ".claude-empty"))
        self.claude("All")                          # "all" already means every account
        self.assertEqual(self.ag._find_accounts(), {"alpha": ("cc", a)})

    def test_a_claude_account_is_named_by_its_suffix_and_the_name_is_lowercase(self):
        d = self.claude("Mixed")
        self.assertEqual(self.ag._find_accounts(), {"mixed": ("cc", d)})

    def test_several_accounts_of_a_second_service_are_found_with_the_service_in_the_name(self):
        w, p = self.codex("work"), self.codex("personal")
        c = self.claude("work")                     # same suffix, other service: no clash
        self.assertEqual(self.ag._find_accounts(), {
            "codex-personal": ("codex", p), "codex-work": ("codex", w), "work": ("cc", c)})

    def test_a_codex_folder_without_sessions_is_not_an_account(self):
        os.makedirs(os.path.join(self.home, ".codex-bare"))
        self.assertEqual(self.ag._find_accounts(), {})

    def test_the_home_the_tool_is_pointed_at_by_its_variable_counts_even_if_oddly_named(self):
        odd = os.path.join(self.home, "elsewhere", "cfg")
        os.makedirs(os.path.join(odd, "sessions"))
        os.environ["CODEX_HOME"] = odd
        self.assertEqual(self.ag._find_accounts(), {"codex-cfg": ("codex", odd)})

    def test_the_variable_pointing_at_the_default_or_at_a_found_account_adds_nothing(self):
        d = self.claude("alpha")
        os.makedirs(os.path.join(self.home, ".claude", "projects"))
        os.environ["CLAUDE_CONFIG_DIR"] = d
        self.assertEqual(list(self.ag._find_accounts()), ["alpha"])
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.home, ".claude")
        self.assertEqual(list(self.ag._find_accounts()), ["alpha"])

    # -- saving them

    def test_first_run_saves_what_it_found_and_later_runs_read_the_file(self):
        self.claude("alpha")
        self.codex("work")
        accounts, ask = self.ag._load_accounts()
        self.assertEqual(sorted(accounts), ["alpha", "codex-work"])
        self.assertIsNone(ask)
        with open(self.ag.CONFIG_PATH) as fh:
            saved = json.load(fh)
        self.assertEqual(saved["accounts"], {
            "alpha": "~/.claude-alpha", "codex-work": {"source": "codex", "dir": "~/.codex-work"}})
        self.claude("beta")                         # appears later: not picked up unasked
        self.assertEqual(sorted(self.ag._load_accounts()[0]), ["alpha", "codex-work"])

    def test_a_file_saved_before_other_services_existed_still_loads(self):
        os.makedirs(os.path.dirname(self.ag.CONFIG_PATH))
        with open(self.ag.CONFIG_PATH, "w") as fh:
            json.dump({"accounts": {"alpha": "~/.claude-alpha"}, "ask": "alpha"}, fh)
        accounts, ask = self.ag._load_accounts()
        self.assertEqual(accounts, {"alpha": ("cc", os.path.join(self.home, ".claude-alpha"))})
        self.assertEqual(ask, "alpha")

    def test_an_entry_with_an_unknown_service_is_ignored_not_fatal(self):
        os.makedirs(os.path.dirname(self.ag.CONFIG_PATH))
        with open(self.ag.CONFIG_PATH, "w") as fh:
            json.dump({"accounts": {"x": {"source": "nope", "dir": "~/x"},
                                    "codex-w": {"source": "codex", "dir": "~/.codex-w"}}}, fh)
        self.assertEqual(list(self.ag._load_accounts()[0]), ["codex-w"])

    def test_editing_the_file_drops_an_account_and_sets_the_ask_account(self):
        self.claude("alpha")
        self.claude("beta")
        self.ag._load_accounts()
        with open(self.ag.CONFIG_PATH, "w") as fh:
            json.dump({"accounts": {"beta": "~/.claude-beta"}, "ask": "beta"}, fh)
        accounts, ask = self.ag._load_accounts()
        self.assertEqual(accounts, {"beta": ("cc", os.path.join(self.home, ".claude-beta"))})
        self.assertEqual(ask, "beta")

    def test_a_broken_file_is_searched_around_and_left_alone(self):
        self.claude("alpha")
        os.makedirs(os.path.dirname(self.ag.CONFIG_PATH))
        with open(self.ag.CONFIG_PATH, "w") as fh:
            fh.write("{not json")
        self.assertEqual(list(self.ag._load_accounts()[0]), ["alpha"])
        with open(self.ag.CONFIG_PATH) as fh:       # a half-written or hand-broken file is not
            self.assertEqual(fh.read(), "{not json")  # replaced: that would lose "ask" and edits

    def test_an_unwritable_config_location_does_not_stop_the_search(self):
        self.claude("alpha")
        with open(os.path.join(self.home, "f"), "w"):
            pass
        self.ag.CONFIG_PATH = os.path.join(self.home, "f", "accounts.json")   # parent is a file
        self.assertEqual(list(self.ag._load_accounts()[0]), ["alpha"])

    # -- using them

    def test_each_services_sessions_are_searched_in_its_default_folder_then_the_others(self):
        self.use({"alpha": ("cc", self.claude("alpha")),
                  "codex-work": ("codex", self.codex("work"))})
        self.assertEqual(self.ag.account_roots("cc"), [
            os.path.join(self.home, ".claude", "projects"),
            os.path.join(self.home, ".claude-alpha", "projects")])
        self.assertEqual(self.ag.account_roots("codex"), [
            os.path.join(self.home, ".codex", "sessions"),
            os.path.join(self.home, ".codex-work", "sessions")])

    def test_resume_goes_through_the_accounts_own_launcher(self):
        d = self.claude("alpha", launcher=True)
        self.use({"alpha": ("cc", d)})
        path = os.path.join(d, "projects", "slug", "s1.jsonl")
        self.assertEqual(self.ag._account_launch(path), [os.path.join(d, "mcp-launch.sh")])
        line = self.ag.resume_command("/repo", self.ag._account_launch(path) + ["--resume", "s1"])
        self.assertEqual(line, "cd /repo && claude-alpha --resume s1")

    def test_without_a_launcher_resume_names_the_config_dir(self):
        d = self.claude("beta")
        self.use({"beta": ("cc", d)})
        path = os.path.join(d, "projects", "slug", "s1.jsonl")
        self.assertEqual(self.ag._account_launch(path),
                         ["env", "CLAUDE_CONFIG_DIR=" + d, "claude"])

    def test_a_codex_account_resumes_with_its_own_codex_home(self):
        d = self.codex("work")
        self.use({"codex-work": ("codex", d)})
        path = os.path.join(d, "sessions", "2026", "11", "17", "rollout-x.jsonl")
        self.assertEqual(self.ag._account_launch(path), ["env", "CODEX_HOME=" + d, "codex"])

    def test_a_codex_account_with_a_command_on_path_is_shown_by_that_name(self):
        d = self.codex("work")
        self.use({"codex-work": ("codex", d)})
        bin_ = os.path.join(self.home, "bin")
        os.makedirs(bin_)
        launcher = os.path.join(bin_, "codex-work")
        with open(launcher, "w") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(launcher, 0o755)
        with mock.patch.dict(os.environ, {"PATH": bin_ + os.pathsep + os.environ["PATH"]}):
            path = os.path.join(d, "sessions", "x.jsonl")
            self.assertEqual(self.ag._account_launch(path), [launcher])
            argv = self.ag._account_launch(path) + ["resume", "s1"]
            self.assertEqual(self.ag.resume_command("", argv), "codex-work resume s1")

    def test_the_default_accounts_and_other_paths_use_the_plain_tool(self):
        self.use({"alpha": ("cc", self.claude("alpha", launcher=True))})
        for default in (".claude/projects", ".codex/sessions"):
            self.assertIsNone(self.ag._account_launch(os.path.join(self.home, default, "s1.jsonl")))

    def test_a_path_that_only_starts_with_the_same_letters_is_not_that_account(self):
        d = self.claude("alpha", launcher=True)
        self.use({"alpha": ("cc", d)})
        self.assertIsNone(self.ag._account_launch(os.path.join(d, "projects-two", "s1.jsonl")))

    def test_dash_a_knows_the_default_codex_account(self):
        self.assertEqual(self.ag.ACCOUNTS["codex"], self.ag.CODEX_DIR)


if __name__ == "__main__":
    unittest.main()
