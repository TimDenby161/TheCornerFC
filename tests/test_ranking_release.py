"""The club rank's movers, new clubs and shots for xG (MC-0028, thecornerfc/models/ranking.py).

The replay as a whole was checked against experiments/shots_proxy/run.py's on every fixture of the
research inputs before release (largest gap 2e-13 rank points); these pin each part on its own."""
import math
import unittest
from datetime import date, datetime, timezone

from thecornerfc.models import ranking
from thecornerfc.models.ranking import Match

DAY = date(2025, 8, 1).toordinal()


def league(key, home, away, hg, ag, lg, day=DAY, country="England", **more):
    return Match(key, home, away, hg, ag, league=lg, is_league=True, country=country, day=day, **more)


class ShotsTest(unittest.TestCase):
    def test_estimate_and_floor(self):
        self.assertAlmostEqual(ranking.shots_xg(5, 12, 4), 5 * 0.10846386180966687 + 7 * -0.005184228874232763
                               + 4 * 0.1091888003326247 + 0.028447322642816665)
        self.assertEqual(ranking.shots_xg(0, 40, 0), 0.0)        # many weak shots never go below nothing

    def test_xg_first_then_shots_then_goals(self):
        shots = (6, 14, 5, 2, 8, 1)
        with_xg = Match(1, 1, 2, 2, 0, home_xg=1.9, away_xg=0.4, shots=shots)
        self.assertEqual(ranking.actual_diff(with_xg)[1], ranking.K_FACTOR_XG)
        result, k = ranking.actual_diff(Match(1, 1, 2, 2, 0, shots=shots))
        self.assertEqual(k, ranking.K_FACTOR_SHOTS)
        self.assertAlmostEqual(result, 0.5 * 2 + 0.5 * (ranking.shots_xg(6, 14, 5) - ranking.shots_xg(2, 8, 1)))
        self.assertEqual(ranking.actual_diff(Match(1, 1, 2, 2, 0, shots=(6, 14, None, 2, 8, 1))), (2, ranking.K_FACTOR))
        self.assertEqual(ranking.actual_diff(Match(1, 1, 2, 2, 0, shots=shots), shots=False), (2, ranking.K_FACTOR))


class NewClubTest(unittest.TestCase):
    def test_a_new_club_moves_further_than_an_established_one(self):
        start = {1: 1000.0, 2: 1000.0, 3: 1000.0}
        # club 1 plays 40 matches against 3 first; then 1 and 2 (new) meet
        matches = [Match(k, 1, 3, 1, 1) for k in range(40)] + [Match(99, 1, 2, 0, 2)]
        rows, history = ranking.run(matches, start.get)
        last = rows[-1]
        miss = last.miss
        self.assertAlmostEqual(last[5], miss * ranking.K_FACTOR * ranking.new_club_factor(40))
        self.assertAlmostEqual(last.away_change, miss * ranking.K_FACTOR * ranking.new_club_factor(0))
        self.assertGreater(abs(last.away_change), abs(last[5]))
        self.assertAlmostEqual(ranking.new_club_factor(0), 1.5)
        self.assertAlmostEqual(ranking.new_club_factor(40), 1 + 0.5 * math.exp(-1))


class MoversTest(unittest.TestCase):
    def setUp(self):
        # division 10 (rank about 1000) and division 20 (about 700); club 1 goes up from 20 to 10
        self.start = {1: 700.0, 2: 700.0, 3: 1000.0, 4: 1000.0}
        self.before = [league(1, 1, 2, 1, 1, 20), league(2, 3, 4, 1, 1, 10)]

    def run_with(self, move):
        return ranking.run(self.before + [move], self.start.get)

    def test_a_promoted_club_moves_halfway_to_its_new_division_with_its_history(self):
        rows, history = self.run_with(league(3, 1, 3, 1, 1, 10, day=DAY + 30))
        was = rows[0][1] + rows[0][5]
        mean = (rows[1][1] + rows[1][5] + rows[1][2] - rows[1].away_change) / 2
        step = rows[-1]
        self.assertAlmostEqual(step.shift_home, 0.5 * (mean - was))
        self.assertAlmostEqual(step[1], was + step.shift_home)            # the rank it plays the match on
        self.assertAlmostEqual(history[1][0], 700.0 + step.shift_home)   # the starting rank moved too
        self.assertEqual(step.shift_away, 0.0)

    def test_no_move_from_another_country_after_a_long_gap_or_in_a_cup(self):
        far = league(3, 1, 3, 1, 1, 10, day=DAY + 401)
        self.assertEqual(self.run_with(far)[0][-1].shift_home, 0.0)
        abroad = [league(1, 1, 2, 1, 1, 20, country="Scotland"), league(2, 3, 4, 1, 1, 10),
                  league(3, 1, 3, 1, 1, 10, day=DAY + 30)]
        self.assertEqual(ranking.run(abroad, self.start.get)[0][-1].shift_home, 0.0)
        cup = Match(3, 1, 3, 1, 1, league=99, day=DAY + 30)
        self.assertEqual(self.run_with(cup)[0][-1].shift_home, 0.0)


class HistoryTest(unittest.TestCase):
    def test_the_written_history_follows_each_side_and_the_move(self):
        start = {1: 700.0, 2: 700.0, 3: 1000.0, 4: 1000.0}
        moment = lambda d: datetime.fromordinal(d).replace(hour=15, tzinfo=timezone.utc)
        fixtures = [(1, moment(DAY), 20, "League", 1, 2, 1, 1, "England"),
                    (2, moment(DAY), 10, "League", 3, 4, 1, 1, "England"),
                    (3, moment(DAY + 30), 10, "League", 1, 3, 2, 0, "England")]
        xg = {f[0]: (None, None) for f in fixtures}

        class Sink:
            def __init__(self): self.text = []
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def copy(self, sql): return self
            def write(self, text): self.text.append(text)
            def execute(self, *a): pass
            def executemany(self, *a): pass

        class Conn:
            def __init__(self): self.sink = Sink()
            def execute(self, *a): pass
            def cursor(self): return self.sink

        conn = Conn()
        history, _, vol, _ = ranking._replay(conn, fixtures, xg, start.get)
        lines = [line.split("\t") for line in "".join(conn.sink.text).splitlines()]
        third = [line for line in lines if line[0] == "3"]
        home, away = (next(line for line in third if line[4] == flag) for flag in ("t", "f"))
        rows, _ = ranking.run([Match(f[0], f[4], f[5], f[6], f[7], league=f[2], is_league=True, country=f[8],
                                     day=ranking.utc_day(f[1])) for f in fixtures], start.get)
        self.assertAlmostEqual(float(home[6]), rows[-1][1])
        self.assertAlmostEqual(float(home[10]), rows[-1][5])
        self.assertAlmostEqual(float(away[10]), -rows[-1].away_change)
        moved = rows[-1].shift_home                                       # its LT is of the moved history
        lt = ranking.summarise([700.0 + moved, rows[0][1] + rows[0][5] + moved])["lt_algo"]
        self.assertAlmostEqual(float(home[11]), lt)
        self.assertAlmostEqual(vol[1][-1], rows[-1].miss * ranking.K_FACTOR)


if __name__ == "__main__":
    unittest.main()
