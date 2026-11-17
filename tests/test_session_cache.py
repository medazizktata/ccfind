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


class DeltaTests(unittest.TestCase):
    """A changed session is written to sessions.tsv.delta; sessions.tsv is left alone."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for name in ("INDEX_PATH", "SESSIONS_PATH", "SESSSIG_PATH", "DELTA_MAX"):
            self.addCleanup(setattr, ag, name, getattr(ag, name))
        for name in ("INDEX_PATH", "SESSIONS_PATH", "SESSSIG_PATH"):
            setattr(ag, name, os.path.join(d.name, name))
        json.dump({}, open(ag.INDEX_PATH, "w"))
        self.addCleanup(ag._FRESH.clear)
        self.lines = [line("a", "alpha", "2026-08-19T10:00:00"),
                      line("b", "beta", "2026-08-18T10:00:00"),
                      line("c", "gamma", "2026-08-17T10:00:00")]
        self.sigs = {"a": "f1:1", "b": "f2:1", "c": "f3:1"}

    def _build(self, lines=None, sigs=None):
        lines = self.lines if lines is None else lines
        ag._FRESH.clear()
        ag._FRESH.update(lines=lines, force=False, sigs=self.sigs if sigs is None else sigs)
        return ag.build_sessions(lines)

    def _main(self):
        return open(ag.SESSIONS_PATH).read()

    def _delta_sids(self):
        return {f[ag.C_SID] for f in ag._read_rows(ag.SESSIONS_PATH + ".delta")}

    def _change(self, sid, text):
        self.lines = [line(f[0], text, f[3]) if f[0] == sid else l
                      for l, f in ((l, l.split(SEP)) for l in self.lines)]
        self.sigs = {**self.sigs, sid: self.sigs[sid] + "x"}

    def test_a_changed_session_goes_to_the_delta_and_sessions_tsv_stands(self):
        self._build()
        before = self._main()
        self._change("b", "beta rewritten")
        rows = self._build()
        self.assertEqual(self._main(), before)
        self.assertEqual(self._delta_sids(), {"b"})
        self.assertIn("rewritten", {r[0]: r for r in rows}["b"][ag.C_BLOB])

    def test_the_reader_sees_the_new_row_in_date_order_and_matches_the_build(self):
        self._build()
        self._change("b", "beta rewritten")
        rows = self._build()
        self.assertEqual(ag._read_session_rows(), rows)
        self.assertEqual([r[0] for r in rows], ["a", "b", "c"])

    def test_a_session_that_became_the_newest_is_listed_first(self):
        """The delta holds rows in no particular place: the order comes from the signatures."""
        self._build()
        self.lines[2] = line("c", "gamma again", "2026-08-25T10:00:00")
        self.sigs = {**self.sigs, "c": "f3:2"}
        rows = self._build()
        self.assertEqual([r[0] for r in rows], ["c", "a", "b"])
        self.assertEqual([r[0] for r in ag._read_session_rows()], ["c", "a", "b"])

    def _cut(self, path, keep):
        """What a reader sees while a writer is mid-row: the file ends `keep` bytes short."""
        text = open(path).read()
        with open(path, "w") as fh:
            fh.write(text[:len(text) - keep])

    def test_a_delta_cut_inside_its_blob_is_not_read_as_a_shorter_row(self):
        """The blob is the last column: a cut row still has 8 columns and used to pass."""
        self._build()
        self._change("b", "beta rewritten " + "tail " * 50)
        self._build()
        self._cut(ag.SESSIONS_PATH + ".delta", 40)
        self.assertEqual(self._delta_sids(), set())
        self.assertNotIn("rewritten", {r[0]: r for r in ag._read_session_rows()}["b"][ag.C_BLOB])

    def test_a_delta_cut_after_its_first_row_keeps_that_row(self):
        self._build()
        self._change("a", "alpha rewritten")
        self._change("b", "beta rewritten " + "tail " * 50)
        self._build()
        self._cut(ag.SESSIONS_PATH + ".delta", 40)
        self.assertEqual(len(self._delta_sids()), 1)

    def test_sessions_tsv_cut_inside_its_last_blob_drops_that_row(self):
        self._build()
        self._cut(ag.SESSIONS_PATH, 5)
        self.assertEqual(len(ag._read_rows(ag.SESSIONS_PATH)), 2)

    def test_the_cached_rows_equal_a_full_rebuild(self):
        self._build()
        self._change("c", "gamma rewritten")
        self._build()
        cached = ag._read_session_rows()
        ag._FRESH.clear()
        full = ag.build_sessions(self.lines)       # no build_index record: regroup everything
        self.assertEqual(sorted(cached), sorted(full))

    def test_a_second_changed_session_keeps_the_first_in_the_delta(self):
        self._build()
        self._change("b", "beta rewritten")
        self._build()
        self._change("c", "gamma rewritten")
        self._build()
        self.assertEqual(self._delta_sids(), {"b", "c"})
        blobs = {r[0]: r[ag.C_BLOB] for r in ag._read_session_rows()}
        self.assertIn("beta rewritten", blobs["b"])
        self.assertIn("gamma rewritten", blobs["c"])

    def test_nothing_changed_writes_nothing(self):
        self._build()
        self._change("b", "beta rewritten")
        self._build()
        mark = {p: os.stat(p).st_mtime_ns for p in (ag.SESSIONS_PATH, ag.SESSSIG_PATH,
                                                    ag.SESSIONS_PATH + ".delta")}
        self._build()
        for p, m in mark.items():
            self.assertEqual(os.stat(p).st_mtime_ns, m, p)

    def test_past_the_cap_sessions_tsv_is_rewritten_and_the_delta_emptied(self):
        self._build()
        self._change("b", "beta rewritten")
        self._build()
        ag.DELTA_MAX = 0
        self._change("c", "gamma rewritten")
        self._build()
        self.assertEqual(self._delta_sids(), set())
        self.assertIn("beta rewritten", self._main())
        self.assertIn("gamma rewritten", self._main())

    def test_a_session_that_went_away_is_not_returned(self):
        self._build()
        self.sigs = {k: v for k, v in self.sigs.items() if k != "c"}
        self.lines = [l for l in self.lines if not l.startswith("c" + SEP)]
        rows = self._build()
        self.assertEqual([r[0] for r in rows], ["a", "b"])
        self.assertEqual([r[0] for r in ag._read_session_rows()], ["a", "b"])

    def test_a_delta_is_ignored_when_the_signatures_are_empty(self):
        """A scoped or killed build empties the signatures: nothing beside sessions.tsv counts."""
        self._build()
        self._change("b", "beta rewritten")
        self._build()
        json.dump({}, open(ag.SESSSIG_PATH, "w"))
        rows = ag._read_session_rows()
        self.assertNotIn("rewritten", {r[0]: r for r in rows}["b"][ag.C_BLOB])

    def test_a_scoped_build_clears_the_delta(self):
        self._build()
        self._change("b", "beta rewritten")
        self._build()
        ag._FRESH.clear()
        ag.build_sessions([self.lines[0]])
        self.assertEqual(self._delta_sids(), set())
        self.assertEqual([r[0] for r in ag._read_session_rows()], ["a"])


class LazyLinesTests(unittest.TestCase):
    """build_index returns a lazy object: unchanged fragments are not read on a warm run."""

    PATHS = ("CACHE_DIR", "FRAG_DIR", "META_PATH", "SUBMAP_PATH", "INDEX_PATH", "FORKS_PATH",
             "FORKFAM_PATH", "SESSSIG_PATH", "SESSIONS_PATH", "FILESIDS_PATH")

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        for name in self.PATHS:
            self.addCleanup(setattr, ag, name, getattr(ag, name))
        ag.CACHE_DIR = d.name
        ag.FRAG_DIR = os.path.join(d.name, "frag")
        for name in self.PATHS[2:]:
            setattr(ag, name, os.path.join(d.name, name.lower()))
        self.src = os.path.join(d.name, "transcripts")
        os.makedirs(self.src)
        self.addCleanup(setattr, ag, "SOURCES", ag.SOURCES)
        self.parsed = []

        def parse(path, _thinking):
            self.parsed.append(os.path.basename(path))
            rows = [l.split(":", 1) for l in open(path).read().splitlines()]
            return "", [[sid, "/repo", "", "2026-08-19T10:00:00", "user", "0", "", text, "cli"]
                        for sid, text in rows]

        ag.SOURCES = {"codex": dict(ag.SOURCES["codex"], roots=[self.src], parse=parse,
                                    match=lambda p: p.endswith(".txt"))}
        ag._FRESH.clear()
        self.addCleanup(ag._FRESH.clear)

    def _write(self, name, body):
        path = os.path.join(self.src, name)
        open(path, "w").write(body)
        return path

    def _frag(self, name):
        return ag._frag_path(os.path.join(self.src, name))

    def test_a_warm_build_gives_the_same_rows_without_reading_the_fragments(self):
        self._write("a.txt", "s1:alpha\ns1:more alpha")
        self._write("b.txt", "s2:beta")
        first = list(ag.build_index())
        self.assertEqual(sorted(self.parsed), ["a.txt", "b.txt"])
        for name in ("a.txt", "b.txt"):             # a read of either now would show as garbage
            open(self._frag(name), "w").write("GARBAGE")
        self.parsed.clear()
        lines = ag.build_index()
        self.assertEqual(self.parsed, [])
        self.assertEqual(sorted(json.load(open(ag.INDEX_PATH))), ["s1", "s2"])
        self.assertEqual(lines.sid_paths.keys(), {"s1", "s2"})
        self.assertEqual(len(first), 3)

    def test_for_sids_reads_only_the_fragments_that_hold_them(self):
        self._write("a.txt", "s1:alpha")
        self._write("b.txt", "s2:beta")
        ag.build_index()
        # b's fragment now holds a row for s1; asking for s1 must not open b, which s1 is not in
        open(self._frag("b.txt"), "w").write(ag.SEP.join(["s1", "", "", "", "", "", "", "POISON", ""]))
        lines = ag.build_index()
        self.assertEqual([l.split(ag.SEP)[7] for l in lines.for_sids({"s1"})], ["alpha"])

    def test_a_changed_file_is_parsed_again_and_the_rest_are_not(self):
        a = self._write("a.txt", "s1:alpha")
        self._write("b.txt", "s2:beta")
        ag.build_index()
        self.parsed.clear()
        open(a, "w").write("s1:alpha\ns3:gamma")
        os.utime(a, (os.path.getmtime(a) + 5,) * 2)
        lines = ag.build_index()
        self.assertEqual(self.parsed, ["a.txt"])
        self.assertEqual(sorted(json.load(open(ag.INDEX_PATH))), ["s1", "s2", "s3"])
        self.assertEqual(sorted(l.split(ag.SEP)[7] for l in lines), ["alpha", "beta", "gamma"])

    def test_a_cache_from_before_filesids_still_works(self):
        self._write("a.txt", "s1:alpha")
        ag.build_index()
        open(ag.FILESIDS_PATH, "w").write("{}")     # what an older build left: no such file
        self.parsed.clear()
        lines = ag.build_index()
        self.assertEqual(self.parsed, [])
        self.assertEqual(list(lines.for_sids({"s1"}))[0].split(ag.SEP)[7], "alpha")

    def test_no_sessions_is_falsy(self):
        self.assertFalse(ag.build_index())


if __name__ == "__main__":
    unittest.main()
