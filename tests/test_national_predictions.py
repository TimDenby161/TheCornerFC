import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

from thecornerfc.publish import export
from thecornerfc.pipeline import matchday
from thecornerfc.models import national_predictions as np_, nations
from thecornerfc.models.nations import Result

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

    def test_each_projection_is_stored_as_a_snapshot_of_its_own_match_model(self):
        # what a paper bet on the match points to (paper_evidence.record_decision)
        row = (1, KICKOFF, 5, 10, 770, 1950.0, 1800.0, False, *np_.predict_match(1950.0, 1800.0))
        conn = conn_with([])
        with writable(), patch.object(np_.match_snapshots, "append_snapshots") as append, \
                patch.object(np_, "register_model_version", return_value="mv_national") as register:
            np_.capture_snapshots(conn, [row], NOW)
        self.assertEqual(register.call_args.args[1:], (np_.ModelType.MATCH, "national-match-prediction"))
        (snap,) = append.call_args.args[1]
        self.assertEqual((snap["fixture_id"], snap["league_id"], snap["model_version_id"], snap["source"]),
                         (1, 5, "mv_national", "prospective"))
        self.assertEqual((snap["p_home"], snap["home_xg"], snap["p_btts"]), (row[11], row[9], row[16]))
        self.assertIn('"neutral": false', snap["inputs"])
        # nothing before the snapshot table exists
        with patch.object(np_.match_snapshots, "append_snapshots") as append:
            np_.capture_snapshots(conn_with([], table=False), [row], NOW)
        append.assert_not_called()

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

    def test_market_chances_go_on_the_card_where_odds_were_collected(self):
        row = (*self.BASE, 0.5, 0.3, 0.2, 1.6, 0.9, "1-0", 1950.0, 1800.0, False, 0.7, 0.5, 0.5, NOW,
               None, None, None, None, None, None)
        m = dict(zip(export.SITE_MATCH_FIELDS, export.national_match(row, (0.61234, 0.25, 0.13766))[0]))
        self.assertEqual((m["m_home"], m["m_draw"], m["home_missing"], m["p_over25"]), (0.612, 0.25, None, 0.5))

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


class StatsTests(unittest.TestCase):
    """The Stats tab counts national team matches with the club ones, under their own competitions."""
    CLUB = (KICKOFF, 39, 0.5, 0.3, 0.2, 1.6, 0.9, "1-0", 2, 1, "live", 4, 5, 4, 3, 4, 3, 100)
    NATIONAL = (KICKOFF, 5, 0.6, 0.25, 0.15, 1.8, 0.8, "2-0", 0, 0, "backfill", 2, 1, 2, 3, 2, 3, 7)

    def conn(self, tables=True, odds=False):
        def execute(sql, params=None):
            rows = []
            if "to_regclass" in sql:
                return Mock(fetchone=lambda: ("x" if tables else None,))
            if "from national_fixture_predictions p join national_fixtures f" in sql and "p.likely_score" in sql:
                self.assertIn("case when p.updated_at > f.kickoff then 'backfill' else 'live' end", sql)
                rows = [self.NATIONAL]
            elif "from national_fixture_predictions p join national_fixtures f" in sql:
                self.assertIn("f.status_short = 'FT'", sql)       # not one that went to extra time
                rows = [(7, 0.6, 0.25, 0.15, 0.4, 1.8, 0.8, 0, 0)]
            elif "from fixture_predictions p join fixtures f" in sql and "p.likely_score" in sql:
                rows = [self.CLUB]
            elif "from odds where bet_id = 1" in sql:
                rows = [(7, 8, "Home", 2.0), (7, 8, "Draw", 4.0), (7, 8, "Away", 4.0)] if odds else []
            elif "with o as" in sql:
                self.assertEqual("union all select fixture_id, status_short, kickoff from national_fixtures" in sql, tables)
                rows = [(7, 1, "", "Home", 0.5, None), (7, 1, "", "Draw", 0.25, None), (7, 1, "", "Away", 0.25, None)] if odds else []
            result = MagicMock(fetchall=lambda: rows)
            result.__iter__.side_effect = lambda: iter(rows)
            return result
        conn = Mock()
        conn.execute.side_effect = execute
        return conn

    def export(self, conn):
        import json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d, \
                patch.object(export, "datetime", Mock(now=lambda tz: KICKOFF + timedelta(days=1))):
            export.export_stats(conn, Path(d))
            return json.loads((Path(d) / "stats.json").read_text())["ranges"]["7d"]

    def test_a_national_match_is_in_all_and_under_its_competition(self):
        out = self.export(self.conn())
        self.assertEqual((out["all"]["n"], out["all"]["live"], out["39"]["n"], out["5"]["n"]), (2, 1, 1, 1))
        self.assertEqual((out["5"]["correct"], out["5"]["rating_avg"], out["5"]["market"]), (0.0, 2.0, None))
        self.assertEqual(out["eng"]["n"], 1)

    def test_with_odds_a_national_match_is_compared_with_the_market(self):
        out = self.export(self.conn(odds=True))
        self.assertEqual((out["5"]["market"]["n"], out["all"]["market"]["n"], out["39"]["market"]), (1, 1, None))
        self.assertEqual(out["5"]["market"]["market_correct"], 0.0)          # a 0-0 draw; the market had the home side
        self.assertEqual((out["5"]["markets"]["1X2"]["n"], out["5"]["markets"]["1X2"]["open_n"]), (1, 0))

    def test_before_the_national_tables_exist_only_clubs_count(self):
        out = self.export(self.conn(tables=False))
        self.assertEqual((out["all"]["n"], "5" in out), (1, False))


class BetsExportTests(unittest.TestCase):
    def test_a_bet_on_a_national_match_is_listed_with_the_fixture_s_names(self):
        import json, tempfile
        from pathlib import Path
        early = KICKOFF - timedelta(days=1)
        bet = lambda bet_id, fid, kickoff, league, home, away, hid, aid: (
            bet_id, "early", fid, kickoff, league, "1X2", "Home", 0.6, 0.45, 2.0, "Bet365", 0.2, None, None,
            None, None, NOW, None, home, away, None, None, ["x"], hid, aid)
        def execute(sql, params=None):
            if "to_regclass" in sql:
                return Mock(fetchone=lambda: ("x",))
            if "information_schema" in sql:
                return Mock(fetchone=lambda: None)
            rows = [bet(2, 7, KICKOFF, 5, "Bosnia &amp; Herzegovina", "England", 1113, 10)] \
                if "join national_fixtures f" in sql else [bet(1, 100, early, 39, "Arsenal", "Chelsea", 42, 49)]
            return Mock(fetchall=lambda: rows)
        conn = Mock()
        conn.execute.side_effect = execute
        with tempfile.TemporaryDirectory() as d:
            export.export_bets(conn, Path(d))
            bets = json.loads((Path(d) / "bets.json").read_text())["bets"]
        self.assertEqual([b["id"] for b in bets], [2, 1])                # latest kickoff first
        self.assertEqual((bets[0]["home"], bets[0]["league"], bets[0]["home_id"], bets[0]["intl"]),
                         ("Bosnia & Herzegovina", 5, 1113, 1))
        self.assertNotIn("intl", bets[1])


class MatchdayTests(unittest.TestCase):
    def test_national_matches_with_odds_have_them_refreshed_near_kickoff(self):
        conn = MagicMock()
        def execute(sql, params=None):
            if "to_regclass" in sql:
                return Mock(fetchone=lambda: ("national_fixtures",))
            self.assertIn("exists (select 1 from odds o where o.fixture_id = nf.fixture_id)", sql)
            self.assertEqual(params[1] - params[0], timedelta(hours=matchday.WINDOW_HOURS))
            return [(7,), (8,)]
        conn.execute.side_effect = execute
        self.assertEqual(matchday.national_with_odds(conn, NOW), [7, 8])
        conn.execute.side_effect = lambda sql, params=None: Mock(fetchone=lambda: (None,))
        self.assertEqual(matchday.national_with_odds(conn, NOW), [])        # before the migration

    def test_the_ninety_minute_score_is_stored_once_its_columns_exist(self):
        from thecornerfc.pipeline import ingest
        item = {"fixture": {"id": 7, "date": KICKOFF.isoformat(), "status": {"short": "AET"}},
                "league": {"id": 1, "season": 2026, "name": "World Cup", "round": "Final"},
                "teams": {"home": {"id": 10, "name": "England"}, "away": {"id": 2, "name": "France"}},
                "goals": {"home": 2, "away": 1}, "score": {"fulltime": {"home": 1, "away": 1}}}
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (1,)
        (row,) = ingest._national_rows(conn, [item])
        self.assertEqual((row["home_goals"], row["away_goals"], row["ft_home"], row["ft_away"]), (2, 1, 1, 1))
        conn.execute.return_value.fetchone.return_value = None          # before the migration
        self.assertNotIn("ft_home", ingest._national_rows(conn, [item])[0])

    def test_nightly_odds_only_for_competitions_with_a_match_coming(self):
        from thecornerfc.pipeline import ingest
        conn, api = MagicMock(), Mock()
        conn.execute.return_value = [(5, 2026), (32, 2024)]
        with patch.object(ingest, "sync_odds") as sync:
            ingest.sync_national_odds(api, conn)
        sync.assert_called_once_with(api, conn, [(5, 2026), (32, 2024)])
        conn.execute.return_value = []
        with patch.object(ingest, "sync_odds") as sync:
            ingest.sync_national_odds(api, conn)
        sync.assert_not_called()

    def test_recent_national_results_are_refreshed_twenty_a_call(self):
        conn, api = MagicMock(), Mock()
        def execute(sql, params=None):
            return Mock(fetchone=lambda: ("national_fixtures",)) if "to_regclass" in sql else [(i,) for i in range(1, 26)]
        conn.execute.side_effect = execute
        api.get.side_effect = lambda endpoint, ids: [{"id": int(x)} for x in ids.split("-")]
        with patch.object(matchday, "_national_rows", side_effect=lambda conn, items: [{"fixture_id": f["id"]} for f in items]), \
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
