import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

from thecornerfc import export, matchday, national_predictions as np_, nations
from thecornerfc.nations import Result

NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(days=3)


class ModelTests(unittest.TestCase):
    def test_margin_is_the_rank_gap_plus_home_advantage(self):
        exp_diff, hx, ax, ph, pd, pa, likely, over, btts = np_.predict_match(1900.0, 1800.0)
        self.assertAlmostEqual(exp_diff, 1.0 + nations.HOME_ADVANTAGE_POINTS / 100)
        self.assertAlmostEqual(hx - ax, exp_diff)
        self.assertAlmostEqual(ph + pd + pa, 1.0)
        self.assertGreater(ph, pa)
        self.assertRegex(likely, r"^\d+-\d+$")
        self.assertTrue(0 < over < 1 and 0 < btts < 1)

    def test_no_home_advantage_at_a_neutral_ground(self):
        exp_diff, hx, ax, ph, _, pa, *_ = np_.predict_match(1800.0, 1800.0, neutral=True)
        self.assertEqual(exp_diff, 0.0)
        self.assertAlmostEqual(hx, np_.LEVEL_GOALS)
        self.assertAlmostEqual(ax, np_.LEVEL_GOALS)
        self.assertAlmostEqual(ph, pa)

    def test_neutral_is_the_stored_flag_or_a_finals_tournament(self):
        self.assertTrue(np_.is_neutral(True, 10))
        self.assertFalse(np_.is_neutral(False, 1))      # the hosts' own match, set by hand
        self.assertTrue(np_.is_neutral(None, 1))
        self.assertFalse(np_.is_neutral(None, 5))

    def test_ranks_are_the_national_ranking_s(self):
        matches = [Result("2020-01-01", "A", "B", 2, 0, "Friendly", True)]
        ranks = np_.current_ranks(matches)
        self.assertEqual(ranks, {t: h[-1] for t, h in nations.replay(matches).items()})
        self.assertGreater(ranks["A"], ranks["B"])


def writable():
    return patch.object(np_.config, "require_db_write")


def conn_with(upcoming, table=True):
    conn = MagicMock()
    def execute(sql, params=None):
        if "to_regclass" in sql:
            return Mock(fetchone=lambda: ("x" if table else None,))
        return Mock(fetchall=lambda: upcoming)
    conn.execute.side_effect = execute
    return conn


class UpdateTests(unittest.TestCase):
    MATCHES = [Result("2020-01-01", "England", "Czech Republic", 3, 0, "Friendly", True),
               Result("2020-02-01", "Republic of Ireland", "England", 0, 0, "Friendly", True)]

    def test_projects_matches_between_ranked_nations_only(self):
        upcoming = [(1, KICKOFF, 5, 10, 770, "England", "Czech Republic", None),
                    (2, KICKOFF, 10, 10, 99, "England", "England U21", None),
                    (3, KICKOFF, 10, 776, 10, "Rep. Of Ireland", "England", True)]     # API-Football's name
        conn = conn_with(upcoming)
        with writable():
            self.assertEqual(np_.update_predictions(conn, self.MATCHES), 2)
        rows = conn.cursor.return_value.__enter__.return_value.executemany.call_args.args[1]
        self.assertEqual([r[0] for r in rows], [1, 3])
        ranks = np_.current_ranks(self.MATCHES)
        self.assertEqual(rows[0][5:8], (ranks["England"], ranks["Czech Republic"], False))
        self.assertEqual(rows[0][8:], np_.predict_match(ranks["England"], ranks["Czech Republic"], False))
        self.assertEqual(rows[1][8:], np_.predict_match(ranks["Republic of Ireland"], ranks["England"], True))
        self.assertEqual(len(rows[0]), 17)
        conn.commit.assert_called_once()

    def test_nothing_before_the_migration(self):
        conn = conn_with([(1, KICKOFF, 5, 10, 770, "England", "Czech Republic", None)], table=False)
        self.assertEqual(np_.update_predictions(conn, self.MATCHES), 0)
        conn.cursor.assert_not_called()

    def test_a_failure_is_rolled_back_and_does_not_raise(self):
        conn = MagicMock()
        with patch.object(np_.nations, "load", side_effect=RuntimeError("no results file")), \
                self.assertLogs(np_.log, "ERROR"):
            np_.update_safely(conn)
        conn.rollback.assert_called_once()

    def test_nightly_step_projects_backfills_and_rates_from_one_load(self):
        conn = MagicMock()
        with patch.object(np_.nations, "load", return_value=self.MATCHES) as load, \
                patch.object(np_, "update_predictions") as update, \
                patch.object(np_, "backfill_predictions") as backfill, patch.object(np_, "rate_fixtures") as rate:
            np_.update_safely(conn)
        load.assert_called_once_with(conn)
        update.assert_called_once_with(conn, self.MATCHES)
        backfill.assert_called_once_with(conn, self.MATCHES)
        rate.assert_called_once_with(conn)


class BackfillTests(unittest.TestCase):
    PLAYED = datetime(2026, 10, 6, 18, 45, tzinfo=timezone.utc)
    MATCHES = [Result("2026-09-29", "Czech Republic", "England", 0, 2, "UEFA Nations League", False),
               Result("2026-10-06", "England", "Czech Republic", 3, 0, "UEFA Nations League", False),
               Result("2026-10-07", "England", "Jersey", 9, 0, "Island Games", True)]

    def test_finished_match_is_projected_from_the_ranks_going_into_it(self):
        finished = [(1528953, self.PLAYED, 5, 10, 770, "England", "Czech Republic"),
                    (2, self.PLAYED, 10, 10, 99, "England", "England U21"),            # not in the ranking
                    (3, self.PLAYED + timedelta(days=1), 10, 10, 98, "England", "Jersey")]   # a tournament it leaves out
        conn = conn_with(finished)
        with writable():
            self.assertEqual(np_.backfill_predictions(conn, self.MATCHES), 1)
        cur = conn.cursor.return_value.__enter__.return_value
        sql, rows = cur.executemany.call_args.args
        self.assertIn("do nothing", sql)                # never over a projection made before the match
        self.assertEqual(len(rows), 1)
        # after the first leg only: England's 2-0 away win, not the 3-0 being projected
        after_first = np_.current_ranks(self.MATCHES[:1])
        self.assertEqual(rows[0][:8], (1528953, self.PLAYED, 5, 10, 770,
                                       after_first["England"], after_first["Czech Republic"], False))
        self.assertEqual(rows[0][8:], np_.predict_match(after_first["England"], after_first["Czech Republic"], False))

    def test_dataset_day_either_side_of_the_utc_kickoff(self):
        late = datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc)       # the evening of the 6th where it was played
        conn = conn_with([(1, late, 5, 10, 770, "England", "Czech Republic")])
        with writable():
            self.assertEqual(np_.backfill_predictions(conn, self.MATCHES), 1)

    def test_nothing_to_do_makes_no_write(self):
        conn = conn_with([])
        self.assertEqual(np_.backfill_predictions(conn, self.MATCHES), 0)
        conn.cursor.assert_not_called()


class ExplanationTests(unittest.TestCase):
    def test_parts_add_up_and_reasons_are_ordered_by_size(self):
        exp_diff = np_.predict_match(1800.0, 1950.0)[0]
        why = np_.explanation(1800.0, 1950.0, False, exp_diff, NOW)
        self.assertEqual(why["margin"], {"strength": -1.5, "home_advantage": 0.5})
        self.assertAlmostEqual(sum(why["margin"].values()), why["exp_diff"])
        self.assertEqual(why["reasons"], [["strength", -1.5], ["home_advantage", 0.5]])
        self.assertEqual(why["current"], [1800, 1950])
        self.assertEqual(why["league_goals"], 2 * np_.LEVEL_GOALS)

    def test_neutral_ground_has_no_home_advantage_part(self):
        why = np_.explanation(1800.0, 1802.0, True, -0.02, NOW)
        self.assertEqual(why["margin"], {"strength": -0.02})
        self.assertEqual(why["reasons"], [])            # too small to be a key reason
        self.assertTrue(why["neutral"])


class ExportRowTests(unittest.TestCase):
    BASE = (7, KICKOFF, 5, "UEFA Nations League", "League A - 3", 10, 770, "England", "Czech Republic", "NS", None, None)

    def test_projected_match_fills_the_same_fields_as_a_club_match(self):
        exp_diff, hx, ax, ph, pd, pa, likely, over, btts = np_.predict_match(1950.0, 1800.0)
        row = (*self.BASE, ph, pd, pa, hx, ax, likely, 1950.0, 1800.0, False, exp_diff, over, btts, NOW,
               None, None, None, None, None, None)
        match, why = export.national_match(row)
        self.assertEqual(len(match), len(export.SITE_MATCH_FIELDS))
        m = dict(zip(export.SITE_MATCH_FIELDS, match))
        self.assertEqual((m["id"], m["home"], m["away"], m["intl"], m["source"]), (7, 10, 770, 1, "live"))
        self.assertEqual((m["home_rank"], m["away_rank"], m["likely"]), (1950, 1800, likely))
        self.assertAlmostEqual(m["p_home"] + m["p_draw"] + m["p_away"], 1.0, places=2)
        self.assertEqual((m["home_xg"], m["p_over25"]), (round(hx, 2), round(over, 3)))
        self.assertIsNone(m["m_home"])
        self.assertEqual(why["reasons"][0][0], "strength")
        # the paid tier blanks a national match's depth as it does a club match's
        free = dict(zip(export.SITE_MATCH_FIELDS, export.blanked(match, export.MATCH_PAID_DEPTH)))
        self.assertIsNone(free["home_xg"])
        self.assertEqual(free["p_home"], m["p_home"])

    def test_match_without_a_projection_is_as_before(self):
        match, why = export.national_match((*self.BASE, *[None] * 19))
        self.assertEqual(match, [7, KICKOFF.isoformat(), 5, "League A - 3", 10, 770, "NS", None, None, None, None,
                                 *[None] * 25, 1])
        self.assertIsNone(why)

    def test_rated_once_finished(self):
        row = (*self.BASE[:9], "FT", 2, 1, 0.5, 0.3, 0.2, 1.6, 0.9, "1-0", 1950.0, 1800.0, False, 0.7, 0.5, 0.5, NOW,
               4, 5, 4, 3, 4, 3)
        m = dict(zip(export.SITE_MATCH_FIELDS, export.national_match(row)[0]))
        self.assertEqual((m["hg"], m["ag"], m["rating"], m["r_winner"], m["r_goals"]), (2, 1, 4, 5, 3))
        self.assertEqual(m["source"], "live")           # projected before its kickoff

    def test_projection_written_after_kickoff_is_a_reconstruction(self):
        row = (*self.BASE[:9], "FT", 2, 1, 0.5, 0.3, 0.2, 1.6, 0.9, "1-0", 1950.0, 1800.0, False, 0.7, 0.5, 0.5,
               KICKOFF + timedelta(days=1), 4, 5, 4, 3, 4, 3)
        match, why = export.national_match(row)
        self.assertEqual(dict(zip(export.SITE_MATCH_FIELDS, match))["source"], "backfill")
        self.assertEqual(why["source"], "reconstruction")


class MatchdayTests(unittest.TestCase):
    def test_recent_national_results_are_refreshed_twenty_a_call(self):
        conn, api = MagicMock(), Mock()
        def execute(sql, params=None):
            return Mock(fetchone=lambda: ("national_fixtures",)) if "to_regclass" in sql else [(i,) for i in range(1, 26)]
        conn.execute.side_effect = execute
        api.get.side_effect = lambda endpoint, ids: [{"id": int(x)} for x in ids.split("-")]
        with patch.object(matchday, "_national_row", side_effect=lambda f: {"fixture_id": f["id"]}), \
                patch.object(matchday, "upsert") as upsert:
            self.assertEqual(matchday.refresh_national_results(api, conn, NOW), 25)
        self.assertEqual(api.get.call_count, 2)
        self.assertEqual([len(c.args[2]) for c in upsert.call_args_list], [20, 5])
        self.assertEqual(upsert.call_args.args[1], "national_fixtures")
        self.assertEqual(conn.commit.call_count, 2)

    def test_nothing_before_the_national_fixtures_table(self):
        conn, api = MagicMock(), Mock()
        conn.execute.return_value.fetchone.return_value = (None,)
        self.assertEqual(matchday.refresh_national_results(api, conn, NOW), 0)
        api.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
