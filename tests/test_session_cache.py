"""build_sessions keeps the row of a session whose source files did not change.

build_index hands over `lines` plus a signature (files and mtimes) per session. A warm search
used to regroup and lowercase every session's full text each run, which was most of its time.
"""

import json
import os
import tempfile
import unittest

from load_agsearch import load_agsearch

ag = load_agsearch()
SEP = ag.SEP


def line(sid, text, ts="2026-08-19T10:00:00"):
    return SEP.join([sid, "/repo", "", ts, "user", "0", "", text, "cli"])


class SessionCacheTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for name in ("INDEX_PATH", "SESSIONS_PATH", "SESSSIG_PATH"):
            self.addCleanup(setattr, ag, name, getattr(ag, name))
            setattr(ag, name, os.path.join(d.name, name))
        json.dump({}, open(ag.INDEX_PATH, "w"))
        self.addCleanup(ag._FRESH.clear)
        self.grouped = []
        real = ag.group_sessions
        self.addCleanup(setattr, ag, "group_sessions", real)
        ag.group_sessions = lambda ls: (self.grouped.append(len(ls)), real(ls))[1]

    def _build(self, lines, sigs, force=False, scoped=None):
        ag._FRESH.clear()
        ag._FRESH.update(lines=lines, force=force, sigs=sigs)
        return ag.build_sessions(scoped if scoped is not None else lines)

    def test_an_unchanged_session_is_not_regrouped_and_the_output_is_the_same(self):
        lines = [line("a", "alpha"), line("b", "beta", "2026-08-18T10:00:00")]
        sigs = {"a": "f1:1", "b": "f2:1"}
        first = self._build(lines, sigs)
        self.assertEqual(self.grouped, [2])
        again = self._build(lines, sigs)
        self.assertEqual(self.grouped, [2, 0])
        self.assertEqual(again, first)

    def test_a_changed_signature_regroups_only_that_session(self):
        self._build([line("a", "alpha"), line("b", "beta")], {"a": "f1:1", "b": "f2:1"})
        rows = self._build([line("a", "alpha"), line("b", "beta and gamma")],
                           {"a": "f1:1", "b": "f2:2"})
        self.assertEqual(self.grouped[-1], 1)
        self.assertIn("gamma", {r[0]: r for r in rows}["b"][ag.C_BLOB])

    def test_force_and_a_scoped_run_do_not_reuse_the_rows(self):
        lines = [line("a", "alpha"), line("b", "beta")]
        sigs = {"a": "f1:1", "b": "f2:1"}
        self._build(lines, sigs)
        self._build(lines, sigs, force=True)
        self.assertEqual(self.grouped[-1], 2)
        # a scoped list is a different object: full rebuild, and the cache is emptied
        self._build(lines, sigs, scoped=[line("a", "alpha")])
        self.assertEqual(self.grouped[-1], 1)
        self.assertEqual(json.load(open(ag.SESSSIG_PATH)), {})
        self._build(lines, sigs)
        self.assertEqual(self.grouped[-1], 2)


if __name__ == "__main__":
    unittest.main()
