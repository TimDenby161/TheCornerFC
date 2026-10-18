"""The Admin area's data: the model change record (thecornerfc/evidence/model_changes.py), the
paper bets leaving the public rows, and the migration that shuts both to everyone but an
administrator. No database: a stand-in keeps the tables as lists."""
import copy
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from thecornerfc import config
from thecornerfc.evidence import model_changes as mc
from thecornerfc.publish import export, site_files, site_record

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'db/migrations/20261013_admin_area.sql'
NOW = datetime(2027, 3, 1, tzinfo=timezone.utc)


def change(cid='MC-0001', kind='experiment', events=(), **registration):
    reg = {"recorded": "2026-10-13", "retrospective": False, "date": "2026-10-12", "title": "A change", "component": "Match probabilities",
           "model": "match", "kind": kind, "what": "w", "why": "y", "how": "h", "hypothesis": "it helps",
           "expected": {"improves": None, "metrics": [], "betting": None, "confidence": None, "evidence": None},
           "success_criteria": "0.002", "code": {"commit": None, "experiment": None, "model_version": None}, **registration}
    return {"id": cid, "registration": reg, "events": list(events)}


def result(date='2026-10-12', evaluation='backtest', **more):
    return {"date": date, "type": "result", "evaluation": evaluation, "unseen": "partly", "label": "Test", "metric": "log_loss",
            "delta": -0.001, "n": 1000, "period": None, "baseline": None, "after": None, "interval": None, "interval_level": None,
            "vs_market": None, "meaningful": "Small", "source": "experiments/x/REPORT.md", **more}


decision = lambda status, date='2026-10-12': {"date": date, "type": "decision", "status": status, "reason": "because"}
deployed = lambda date, **more: {"date": date, "type": "deployed", "commit": None, **more}


class Conn:
    """model_changes, model_change_events, admin_docs and site.docs as lists, refusing what the
    real tables' triggers refuse, with every statement kept."""
    def __init__(self, environment='staging', live=(), months=()):
        self.changes, self.events, self.admin, self.site_docs = {}, {}, {}, {'bets': 'public', 'stats': 'x'}
        self.environment, self.live, self.months = environment, list(live), list(months)
        self.live_count = {}
        self.sql, self.commits, self.rollbacks = [], 0, 0

    def execute(self, sql, params=None):
        text = ' '.join(sql.split()).lower()
        self.sql.append(text)
        if re.match(r'(update|delete from|truncate) model_change', text):
            raise RuntimeError('The model change record is append only')
        if text.startswith('insert into model_changes'):
            cid, registration, sha = params
            if cid in self.changes:
                raise RuntimeError('duplicate key')
            self.changes[cid] = (json.loads(registration), sha, NOW)
        elif text.startswith('insert into model_change_events'):
            cid, seq, body, sha = params
            if (cid, seq) in self.events:
                raise RuntimeError('duplicate key')
            self.events[(cid, seq)] = (json.loads(body), sha, NOW)
        elif text.startswith('insert into admin_docs'):
            self.admin[params[0]] = json.loads(params[1])
        elif text.startswith("delete from site.docs where key = 'bets'"):
            self.site_docs.pop('bets', None)
        rows = []
        if text.startswith('select change_id, sha256 from model_changes'):
            rows = [(c, v[1]) for c, v in self.changes.items()]
        elif text.startswith('select change_id, seq, sha256 from model_change_events'):
            rows = [(c, s, v[1]) for (c, s), v in self.events.items()]
        elif text.startswith('select change_id, registration, recorded_at from model_changes'):
            rows = [(c, v[0], v[2]) for c, v in sorted(self.changes.items())]
        elif text.startswith('select change_id, body, recorded_at from model_change_events'):
            rows = [(c, v[0], v[2]) for (c, s), v in sorted(self.events.items())]
        elif text.startswith('select count(*) from fixtures f'):
            rows = [(self.live_count.get((params[1], tuple(params[0])), 0),)]
        elif text.startswith('select site.environment()'):
            rows = [(self.environment,)]
        elif 'group by 1, 2' in text and 'fixture_predictions' in text:
            rows = self.months
        elif 'from fixture_predictions' in text:
            start, end = params
            rows = [r[:5] for r in self.live if start <= r[5] < end]
        return mock.Mock(fetchall=lambda: rows, fetchone=lambda: rows[0] if rows else None)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def writable():
    return mock.patch.object(config, 'require_db_write', lambda action: None)


def read_only():
    def refuse(action):
        raise config.SafetyError(f'{action}: read-only')
    return mock.patch.object(config, 'require_db_write', refuse)


class RegisterTests(unittest.TestCase):
    """experiments/changes as it is in the repository."""
    @classmethod
    def setUpClass(cls):
        cls.changes = mc.load()

    def test_every_file_can_be_recorded_and_is_numbered_in_order(self):
        self.assertGreaterEqual(len(self.changes), 27)
        self.assertEqual([c['id'] for c in self.changes], [f'MC-{i:04d}' for i in range(1, len(self.changes) + 1)])

    def test_the_recent_rejected_experiments_are_kept(self):
        by_title = {c['registration']['title']: mc.standing(c['events']) for c in self.changes}
        for title in ('Sharpening the result probabilities', 'Refitting the draw boost', 'Wider gaps between leagues in cup ties'):
            self.assertEqual(by_title[title]['stage'], 'Tested and rejected', title)

    def test_no_experiment_is_shown_as_deployed(self):
        for c in self.changes:
            where = mc.standing(c['events'])
            if c['registration']['kind'] == 'experiment':
                self.assertFalse(where['deployed'], c['id'])
                self.assertNotEqual(where['stage'], 'Deployed to production', c['id'])
            if where['deployed']:
                self.assertEqual(c['registration']['kind'], 'production change', c['id'])

    def test_no_expectation_is_given_without_the_source_that_recorded_it(self):
        numbered = 0
        for c in self.changes:
            for m in c['registration']['expected']['metrics']:
                numbered += 1
                self.assertTrue((ROOT / m['source'].split(':')[0].split(' (')[0]).exists(), f"{c['id']}: {m['source']}")
        self.assertLess(numbered, len(self.changes))          # most recorded none, and say so

    def test_every_result_names_a_file_in_the_repository(self):
        for c in self.changes:
            folder = c['registration']['code']['experiment']
            if folder:
                self.assertTrue((ROOT / folder).is_dir(), f"{c['id']}: {folder}")
            for e in c['events']:
                if e['type'] == 'result':
                    self.assertTrue((ROOT / e['source']).exists(), f"{c['id']}: {e['source']}")

    def test_an_entry_written_after_its_test_says_so(self):
        for c in self.changes:
            tested = any(e['type'] == 'result' and e['evaluation'] != 'development' for e in c['events'])
            if tested:
                self.assertTrue(c['registration']['retrospective'], c['id'])


class RulesTests(unittest.TestCase):
    def test_a_plain_change_is_recordable(self):
        self.assertEqual(mc.problems(change()), [])
        self.assertEqual(mc.problems(change(events=[{"date": "2026-10-12", "type": "status", "status": "Testing"}, result(), decision('Rejected')])), [])

    def test_a_forward_record_can_not_be_typed_in(self):
        found = mc.problems(change(events=[result(evaluation='forward')]))
        self.assertTrue(any('never written by hand' in p for p in found), found)
        self.assertNotIn('forward', mc.EVALUATIONS)
        self.assertNotIn('production', mc.EVALUATIONS)

    def test_an_experiment_can_not_be_deployed(self):
        found = mc.problems(change(events=[decision('Accepted'), deployed('2026-10-20')]))
        self.assertTrue(any('only a production change is deployed' in p for p in found), found)
        self.assertEqual(mc.problems(change(kind='production change', events=[decision('Accepted'), deployed('2026-10-20')])), [])

    def test_acceptance_and_rejection_are_decisions_with_a_reason(self):
        for status in ('Accepted', 'Rejected', 'Inconclusive'):
            found = mc.problems(change(events=[{"date": "2026-10-12", "type": "status", "status": status}]))
            self.assertTrue(any('is a decision' in p for p in found), status)
        found = mc.problems(change(events=[{"date": "2026-10-12", "type": "decision", "status": "Rejected", "reason": " "}]))
        self.assertTrue(any('gives its reason' in p for p in found))

    def test_events_are_added_at_the_end_and_corrections_point_back(self):
        found = mc.problems(change(events=[result(date='2026-10-14'), decision('Rejected', date='2026-10-13')]))
        self.assertTrue(any('added at the end' in p for p in found), found)
        ok = change(events=[result(), {"date": "2026-10-13", "type": "correction", "of": 1, "text": "n was 999"}])
        self.assertEqual(mc.problems(ok), [])
        bad = change(events=[{"date": "2026-10-13", "type": "correction", "of": 1, "text": "itself"}])
        self.assertTrue(any('earlier event' in p for p in mc.problems(bad)))

    def test_an_expected_number_needs_the_source_that_recorded_it(self):
        expected = {"improves": "log loss", "metrics": [{"metric": "log_loss", "delta": -0.002}], "betting": None, "confidence": None, "evidence": None}
        self.assertTrue(any('source that recorded it' in p for p in mc.problems(change(expected=expected))))
        expected["metrics"][0]["source"] = "experiments/x/DESIGN.md"
        self.assertEqual(mc.problems(change(expected=expected)), [])

    def test_only_a_deployed_change_can_be_reverted(self):
        gone = {"date": "2026-11-01", "type": "reverted", "reason": "worse live"}
        self.assertTrue(any('only a deployed change' in p for p in mc.problems(change(kind='production change', events=[gone]))))
        self.assertEqual(mc.problems(change(kind='production change', events=[decision('Accepted'), deployed('2026-10-20'), gone])), [])

    def test_where_a_change_stands(self):
        stand = lambda *events: mc.standing(list(events))
        self.assertEqual(stand()['stage'], 'Proposed')
        self.assertEqual((stand(decision('Accepted'))['stage'], stand(decision('Accepted'))['deployed']), ('Tested, not deployed', False))
        live = stand(decision('Accepted'), deployed('2026-10-20'))
        self.assertEqual((live['stage'], live['deployed'], live['deployed_on'], live['deployed_day_known']), ('Deployed to production', True, '2026-10-20', True))
        self.assertFalse(stand(deployed('2026-09-01', date_known_to='month'))['deployed_day_known'])
        back = stand(decision('Accepted'), deployed('2026-10-20'), {"date": "2026-11-01", "type": "reverted", "reason": "r"})
        self.assertEqual((back['status'], back['stage'], back['deployed'], back['deployed_on']), ('Reverted', 'Reverted', False, None))


released = lambda as_='MC-0002', date='2026-10-21': {"date": date, "type": "released", "as": as_, "note": "went in at its setting"}


class ReleaseTests(unittest.TestCase):
    """An experiment whose idea went live inside a production change."""
    def write(self, *changes):
        folder = Path(tempfile.mkdtemp())
        for c in changes:
            (folder / f"{c['id']}.json").write_text(json.dumps(c))
        return folder

    def test_only_an_experiment_is_released_and_it_names_the_change_and_how(self):
        self.assertEqual(mc.problems(change(events=[decision('Accepted'), released()])), [])
        self.assertTrue(any('only an experiment' in p for p in mc.problems(change(kind='production change', events=[released()]))))
        self.assertTrue(any('names the production change' in p for p in mc.problems(change(events=[released('MC-0001')]))))
        self.assertTrue(any('says how' in p for p in mc.problems(change(events=[{**released(), "note": " "}]))))

    def test_the_change_it_names_was_deployed_by_then(self):
        idea = change('MC-0001', events=[decision('Accepted'), released(date='2026-10-21')])
        carrier = lambda on: change('MC-0002', kind='production change', events=[deployed(on)] if on else [])
        mc.load(self.write(idea, carrier('2026-10-20')))
        for later in ('2026-10-22', None):
            with self.assertRaisesRegex(ValueError, 'MC-0002 is not a production change deployed by 2026-10-21'):
                mc.load(self.write(idea, carrier(later)))

    def test_it_is_in_production_while_the_change_that_carried_it_is(self):
        idea = change('MC-0001', events=[decision('Accepted'), released()])
        carrier = change('MC-0002', kind='production change', events=[deployed('2026-10-20')])
        doc = mc.document(mc.from_files([idea, carrier]), environment='staging', generated_at='t')
        first = doc['changes'][0]
        self.assertEqual((first['released_in'], first['stage'], first['deployed'], first['status']),
                         ('MC-0002', 'In production through MC-0002', False, 'Accepted'))
        self.assertIsNone(doc['changes'][1]['released_in'])
        gone = {**carrier, "events": carrier['events'] + [{"date": "2026-11-01", "type": "reverted", "reason": "worse"}]}
        back = mc.document(mc.from_files([idea, gone]), environment='staging', generated_at='t')['changes'][0]
        self.assertEqual((back['released_in'], back['stage']), (None, 'Tested, not deployed'))

    def test_the_register_marks_a16_and_a24_and_their_parts_as_live_in_mc_0028(self):
        doc = mc.document(mc.from_files(mc.load()), environment='staging', generated_at='t')
        live = {c['id'] for c in doc['changes'] if c['released_in'] == 'MC-0028'}
        self.assertEqual(live, {'MC-0013', 'MC-0014', 'MC-0016', 'MC-0024'})

class RecordTests(unittest.TestCase):
    """What was recorded stays as it was recorded."""
    def setUp(self):
        self.files = [change('MC-0001', events=[result()]), change('MC-0002')]
        self.conn = Conn()
        with writable():
            self.first = mc.sync(self.conn, self.files)

    def test_the_first_run_records_everything_and_the_second_nothing(self):
        self.assertEqual(self.first, {"added": ['MC-0001', 'MC-0001 event 1', 'MC-0002'], "differs": []})
        with writable():
            self.assertEqual(mc.sync(self.conn, self.files), {"added": [], "differs": []})

    def test_an_edited_registration_is_reported_and_the_record_stands(self):
        edited = copy.deepcopy(self.files)
        edited[0]['registration']['hypothesis'] = 'it always worked'
        edited[0]['registration']['expected']['metrics'] = [{"metric": "log_loss", "delta": -0.001, "source": "hindsight"}]
        with writable():
            again = mc.sync(self.conn, edited)
            kept = mc.recorded(self.conn)[0]
        self.assertEqual(again, {"added": [], "differs": ['MC-0001: the registration in the file is not the one recorded']})
        self.assertEqual(kept['registration']['hypothesis'], 'it helps')
        self.assertEqual(kept['registration']['expected']['metrics'], [])

    def test_an_edited_or_removed_result_is_reported_and_the_record_stands(self):
        edited = copy.deepcopy(self.files)
        edited[0]['events'][0]['delta'] = -0.009
        with writable():
            self.assertEqual(mc.sync(self.conn, edited)['differs'], ['MC-0001: event 1 in the file is not the one recorded'])
            edited[0]['events'] = []
            self.assertEqual(mc.sync(self.conn, edited)['differs'], ['MC-0001: the file has fewer events than the record'])
            self.assertEqual(mc.recorded(self.conn)[0]['events'][0]['delta'], -0.001)
            self.assertEqual(mc.sync(self.conn, self.files[:1])['differs'], ['MC-0002: recorded, but its file has gone'])

    def test_a_new_event_is_added_and_a_correction_is_one(self):
        more = copy.deepcopy(self.files)
        more[0]['events'].append({"date": "2026-10-13", "type": "correction", "of": 1, "text": "n was 999"})
        with writable():
            self.assertEqual(mc.sync(self.conn, more), {"added": ['MC-0001 event 2'], "differs": []})
            events = mc.recorded(self.conn)[0]['events']
        self.assertEqual([e['type'] for e in events], ['result', 'correction'])
        self.assertEqual(events[0]['n'], 1000)                    # the corrected event is left as it was

    def test_nothing_recorded_is_ever_updated_or_deleted(self):
        with writable():
            mc.sync(self.conn, self.files)
        self.assertFalse([s for s in self.conn.sql if re.match(r'(update|delete|truncate)', s)])
        self.assertEqual(mc.digest({"a": 1, "b": [1, 2]}), mc.digest({"b": [1, 2], "a": 1}))    # a file's layout is not its content

    def test_a_run_that_may_not_write_records_nothing(self):
        conn = Conn()
        with read_only(), self.assertRaises(config.SafetyError):
            mc.sync(conn, self.files)
        self.assertEqual((conn.changes, conn.sql), ({}, []))


def live(fixture, day, outcome=0, p=(0.5, 0.25, 0.25)):
    return (fixture, *p, outcome, datetime.fromisoformat(day).replace(tzinfo=timezone.utc))


class ForwardTests(unittest.TestCase):
    def production(self, cid, on, **more):
        return {**change(cid, kind='production change', events=[decision('Accepted'), deployed(on, **more)]), "recorded_at": None}

    def test_an_experiment_never_has_a_forward_record(self):
        conn = Conn(live=[live(i, '2026-12-01') for i in range(50)])
        self.assertEqual(mc.forward(conn, [change('MC-0001', events=[result(), decision('Accepted')])], NOW), {})
        self.assertFalse([s for s in conn.sql if 'fixture_predictions' in s])

    def test_a_change_s_window_ends_where_the_next_deployment_begins(self):
        rows = [live(1, '2026-10-25'), live(2, '2026-11-20'), live(3, '2026-12-20'), live(4, '2027-02-10')]
        out = mc.forward(Conn(live=rows), [self.production('MC-0001', '2026-11-01'), self.production('MC-0002', '2027-01-01')], NOW)
        self.assertEqual((out['MC-0001']['from'], out['MC-0001']['to'], out['MC-0001']['after']['n']), ('2026-11-01', '2027-01-01', 2))
        self.assertEqual((out['MC-0002']['from'], out['MC-0002']['to'], out['MC-0002']['after']['n']), ('2027-01-01', '2027-03-01', 1))
        self.assertEqual(out['MC-0001']['before']['n'], 1)        # set beside the 61 days just before it

    def test_changes_deployed_together_are_said_to_be_inseparable(self):
        out = mc.forward(Conn(), [self.production('MC-0001', '2026-11-01'), self.production('MC-0002', '2026-11-01')], NOW)
        self.assertEqual(out['MC-0001']['deployed_with'], ['MC-0002'])

    def test_a_deployment_known_only_to_the_month_is_not_measured(self):
        conn = Conn(live=[live(i, '2026-12-01') for i in range(50)])
        out = mc.forward(conn, [self.production('MC-0001', '2026-09-01', date_known_to='month')], NOW)
        self.assertEqual((out['MC-0001']['verdict'], out['MC-0001']['after']), ('Cannot be judged', None))
        self.assertFalse([s for s in conn.sql if 'fixture_predictions' in s])

    def test_only_predictions_stored_before_kickoff_are_scored(self):
        conn = Conn()
        mc.forward(conn, [self.production('MC-0001', '2026-11-01')], NOW)
        asked = [s for s in conn.sql if 'fixture_predictions' in s]
        self.assertTrue(asked and all("p.source = 'live'" in s for s in asked))
        self.assertTrue(all("'ft', 'aet', 'pen'" in s for s in asked))      # a tie level at 90 minutes is a draw

    def test_the_market_is_asked_once_and_only_for_a_window(self):
        asked = []
        mc.forward(Conn(), [self.production('MC-0001', '2026-11-01'), self.production('MC-0002', '2027-01-01')], NOW,
                   market_for=lambda since: asked.append(since) or {})
        self.assertEqual(len(asked), 1)

    def test_a_record_is_scored_against_the_market_on_its_own_priced_matches(self):
        rows = [(1, 0.6, 0.2, 0.2, 0), (2, 0.2, 0.3, 0.5, 0), (3, 0.3, 0.3, 0.4, 2)]
        out = mc.window_record(rows, {1: [0.7, 0.2, 0.1], 3: [0.2, 0.3, 0.5]})
        self.assertEqual((out['n'], out['vs_market']['n']), (3, 2))
        self.assertGreater(out['vs_market']['model_minus_market'], 0)
        self.assertEqual(mc.window_record([]), {"n": 0, "log_loss": None, "brier": None, "vs_market": None})

    def test_the_verdict_claims_nothing_the_record_can_not_show(self):
        side = lambda n, gap=None, priced=1000: {"n": n, "log_loss": 0.98, "brier": 0.58,
                                                 "vs_market": None if gap is None else {"n": priced, "model_minus_market": gap}}
        self.assertEqual(mc.forward_verdict(side(400, 0.01), side(5000, 0.02))[0], 'Too early to say')
        self.assertEqual(mc.forward_verdict(side(5000, 0.01), side(100, 0.02))[0], 'Cannot be judged')
        self.assertEqual(mc.forward_verdict(side(5000), side(5000, 0.02))[0], 'Cannot be judged')
        self.assertEqual(mc.forward_verdict(side(5000, 0.01, priced=100), side(5000, 0.02))[0], 'Cannot be judged')
        verdict, why = mc.forward_verdict(side(5000, 0.017), side(5000, 0.019))
        self.assertEqual(verdict, 'Still appears beneficial')
        self.assertIn('could also explain it', why)             # never credited to the change alone
        self.assertEqual(mc.forward_verdict(side(5000, 0.021), side(5000, 0.019))[0], 'No benefit visible')


class LiveTestTests(unittest.TestCase):
    """How many live matches a registered prospective test has reached."""
    P13 = {"date": "2026-10-13", "type": "live_test", "protocol": "P13", "start": "2026-10-13", "target": 9400, "extra_time": False}
    P14 = {"date": "2026-10-13", "type": "live_test", "protocol": "P14", "start": "2026-10-14", "target": 6200, "extra_time": True}

    def test_a_live_test_names_its_protocol_start_and_target(self):
        self.assertEqual(mc.problems(change(events=[self.P13, self.P14])), [])
        for missing in ("protocol", "start", "target", "extra_time"):
            self.assertTrue(mc.problems(change(events=[{k: v for k, v in self.P13.items() if k != missing}])), missing)

    def test_each_test_is_counted_from_its_own_start_and_only_counted(self):
        conn = Conn()
        conn.live_count = {("2026-10-13", ("FT",)): 310, ("2026-10-14", ("FT", "AET", "PEN")): 255}
        rows = [change('MC-0001', events=[self.P13, self.P14]), change('MC-0002', events=[self.P14]), change('MC-0003')]
        got = mc.live_tests(conn, rows)
        self.assertEqual(got, {'MC-0001': [{"protocol": "P13", "start": "2026-10-13", "target": 9400, "matches": 310},
                                           {"protocol": "P14", "start": "2026-10-14", "target": 6200, "matches": 255}],
                               'MC-0002': [{"protocol": "P14", "start": "2026-10-14", "target": 6200, "matches": 255}]})
        asked = [s for s in conn.sql if s.startswith('select count(*) from fixtures f')]
        self.assertEqual(len(asked), 2)                         # one count for each start, shared between changes
        for sql in asked:                                       # a count of matches and nothing about how they went
            for word in ('p_home', 'odds', 'goals', 'p.p_', 'ft_home >', 'ft_home ='):
                self.assertNotIn(word, sql)
            self.assertIn("s.source = 'prospective'", sql)
            self.assertIn('s.captured_at < f.kickoff', sql)

    def test_the_register_s_live_tests_are_the_registered_protocols(self):
        text = (ROOT / 'experiments/prospective/PROTOCOLS.md').read_text()
        found = {}
        for c in mc.load():
            for e in c['events']:
                if e['type'] == 'live_test':
                    found.setdefault(e['protocol'], set()).add((e['start'], e['target'], e['extra_time']))
                    self.assertIn(f"## {e['protocol']}:", text)
                    self.assertIn(f"{e['target']:,}", text)
                    self.assertIn(e['start'], text)
        self.assertEqual(found, {'P13': {('2026-10-13', 9400, False)}, 'P14': {('2026-10-14', 6200, True)},
                                 'P15': {('2026-10-14', 6200, True)},           # P15 has no target: 6,200 is where its interval is tightest
                                 'P16': {('2026-10-15', 27000, True)},          # nor P16: 27,000 is where its call is expected
                                 'P17': {('2026-10-15', 6200, True)},           # nor P17: 6,200 is where its interval is tightest
                                 'P18': {('2026-10-15', 26000, True)}})         # nor P18: 26,000 is where its call is expected

    def test_the_document_carries_the_count_for_the_changes_that_have_one(self):
        doc = mc.document(mc.from_files([change('MC-0001', events=[self.P13]), change('MC-0002')]), environment='staging', generated_at='t',
                          live={'MC-0001': [{"protocol": "P13", "start": "2026-10-13", "target": 9400, "matches": 310}]})
        self.assertEqual([c['live'] for c in doc['changes']], [[{"protocol": "P13", "start": "2026-10-13", "target": 9400, "matches": 310}], []])


class DocumentTests(unittest.TestCase):
    def test_every_result_from_a_file_is_marked_as_an_experiment_s(self):
        rows = mc.from_files([change('MC-0001', kind='production change', events=[result(), decision('Accepted'), deployed('2026-11-01')])])
        doc = mc.document(rows, environment='staging', generated_at='t', forward_record={'MC-0001': {"verdict": "Too early to say"}})
        c = doc['changes'][0]
        self.assertTrue(all(r['experimental'] for r in c['results']))
        self.assertEqual((c['stage'], c['forward']['verdict'], doc['environment'], doc['not_specified']),
                         ('Deployed to production', 'Too early to say', 'staging', 'Not specified'))

    def test_a_change_with_no_forward_record_has_none(self):
        doc = mc.document(mc.from_files([change()]), environment='production', generated_at='t')
        self.assertIsNone(doc['changes'][0]['forward'])


class ExportTests(unittest.TestCase):
    def bets_conn(self):
        conn = Conn()
        real = conn.execute

        def execute(sql, params=None, **kw):
            if 'to_regclass' in sql:
                return mock.Mock(fetchone=lambda: (None,))
            return real(sql, params)
        conn.execute = execute
        return conn

    def test_the_paper_bets_go_to_the_administrator_s_documents_and_leave_the_public_rows(self):
        conn = self.bets_conn()
        with tempfile.TemporaryDirectory() as d, writable():
            doc = export.export_bets(conn, Path(d))
            self.assertEqual(list(Path(d).iterdir()), [])              # no file, so nothing for mirror_site_docs to publish
        self.assertEqual(conn.admin['bets'], doc)
        self.assertNotIn('bets', conn.site_docs)
        self.assertIn('stats', conn.site_docs)

    def test_a_run_that_may_not_write_stores_nothing_and_writes_no_file(self):
        conn = self.bets_conn()
        with tempfile.TemporaryDirectory() as d, read_only():
            export.export_bets(conn, Path(d))
            self.assertEqual(list(Path(d).iterdir()), [])
        self.assertEqual(conn.admin, {})

    def test_the_bets_are_no_longer_a_file_the_export_must_publish(self):
        self.assertNotIn('bets.json', site_files.CRITICAL_JSON_FILES)
        main = (ROOT / 'thecornerfc/__main__.py').read_text()
        self.assertNotIn('"bets.json"', main)
        self.assertEqual(site_files.ADMIN_DOCS, ('bets', 'model_changes', 'live_tracking'))

    def test_only_the_administrator_s_two_documents_can_be_stored_there(self):
        with writable(), self.assertRaises(ValueError):
            site_files.store_admin_doc(Conn(), 'rankings', {})
        with read_only(), self.assertRaises(config.SafetyError):
            site_files.store_admin_doc(Conn(), 'bets', {})

    def test_the_tracker_s_document_is_stored_and_says_which_database_it_is(self):
        for environment in ('staging', 'production'):
            conn = Conn(environment=environment, months=[('2026-10', 'live', 700, 0.97, 0.58, 310, 170, 220)])
            with tempfile.TemporaryDirectory() as d, writable():
                (Path(d) / 'methodology.json').write_text(json.dumps({"matches": {"n": 740, "log_loss": 0.9867, "brier": 0.5885,
                                                                                  "versions": [{"name": "match-prediction", "n": 740}]}}))
                (Path(d) / 'stats.json').write_text(json.dumps({"ranges": {"365d": {"all": {"markets": {"1X2": {"n": 1147, "model_ll": 0.9739, "close_ll": 0.9536}}}}}}))
                doc = site_record.export_model_changes(conn, Path(d), NOW)
                # the same record also goes out in public for The Model page (owner, 2026-10-16)
                self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ['methodology.json', 'model.json', 'stats.json'])
                public = json.loads((Path(d) / 'model.json').read_text())
            self.assertEqual(conn.admin['model_changes'], doc)
            self.assertEqual((doc['environment'], doc['stored'], doc['differs']), (environment, True, []))
            self.assertEqual(len(doc['changes']), len(conn.changes))
            self.assertEqual((doc['current']['version'], doc['current']['n'], doc['current']['vs_market']['n']), ('match-prediction', 740, 1147))
            self.assertEqual(doc['series'][0], {"month": "2026-10", "source": "live", "n": 700, "log_loss": 0.97, "brier": 0.58,
                                                "home": 310, "draw": 170, "away": 220})
            self.assertEqual((public['current'], public['series'], len(public['changes'])), (doc['current'], doc['series'], len(doc['changes'])))
            self.assertNotIn('environment', public)
            self.assertNotIn('differs', public)

    def test_the_public_record_carries_the_live_tests_and_none_of_the_admin_notes(self):
        doc = {"generated_at": "t", "current": {"n": 1}, "series": [], "changes": [{"id": "MC-0001"}], "forward_record": {},
               "live": {}, "environment": "production", "differs": ["x"], "stored": True}
        public = site_record.public_model(doc, {"n": 5, "changes": {"MC-0018": {"called": False}}})
        self.assertEqual(sorted(public), ['changes', 'current', 'example', 'forward_record', 'generated_at', 'live', 'series', 'tracking'])
        self.assertEqual(public['tracking']['n'], 5)
        self.assertIsNone(public['example'])
        self.assertEqual(site_record.public_model(doc, None, {"match": {"id": 1}})['example'], {"match": {"id": 1}})

    def test_a_local_run_builds_the_document_from_the_files_and_stores_nothing(self):
        conn = Conn()
        with tempfile.TemporaryDirectory() as d, read_only():
            doc = site_record.export_model_changes(conn, Path(d), NOW)
        self.assertEqual((doc['stored'], conn.admin, conn.changes), (False, {}, {}))
        self.assertTrue(all(c['recorded_at'] is None for c in doc['changes']))


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text()

    def test_it_is_in_the_schema_word_for_word(self):
        self.assertIn(self.sql, (ROOT / 'db/schema.sql').read_text())

    def test_every_new_table_is_shut_to_the_public_key(self):
        for table in ('site_admins', 'admin_docs', 'model_changes', 'model_change_events'):
            self.assertIn(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;', self.sql)
        self.assertIn("REVOKE ALL ON public.site_admins, public.admin_docs, public.model_changes, public.model_change_events FROM %I", self.sql)
        self.assertNotIn('CREATE POLICY', self.sql)

    def test_only_a_signed_in_caller_can_ask_and_only_an_administrator_is_answered(self):
        grants = re.findall(r'GRANT EXECUTE ON FUNCTION (\S+) TO (\w+)', self.sql)
        self.assertEqual(sorted(grants), [('public.admin_doc(text)', 'authenticated'), ('public.am_admin()', 'authenticated')])
        self.assertNotRegex(self.sql, r'GRANT[^;]*\banon\b')
        self.assertNotRegex(self.sql, r'GRANT (SELECT|INSERT|UPDATE|DELETE|ALL)')
        body = self.sql.split('CREATE OR REPLACE FUNCTION public.admin_doc', 1)[1].split('$$;', 1)[0]
        self.assertLess(body.index('IF NOT site.is_admin() THEN'), body.index('FROM public.admin_docs'))
        check = self.sql.split('CREATE OR REPLACE FUNCTION site.is_admin()', 1)[1].split('$$;', 1)[0]
        for needed in ('auth.uid() IS NOT NULL', 'public.site_admins', 'u.email_confirmed_at IS NOT NULL', 'u.id = auth.uid()'):
            self.assertIn(needed, check)
        self.assertNotIn('fpl_team_owners', check)               # its own list: being the FPL owner is not being an administrator

    def test_every_function_has_a_pinned_search_path_and_fixed_sql(self):
        self.assertEqual(self.sql.count('CREATE OR REPLACE FUNCTION'), self.sql.count("SET search_path = ''"))
        self.assertNotIn('EXECUTE format(', self.sql.split('CREATE OR REPLACE FUNCTION site.is_admin()', 1)[1].split('REVOKE ALL', 1)[0])

    def test_the_change_record_refuses_updates_deletes_and_truncation(self):
        self.assertIn("IF TG_OP <> 'INSERT' THEN", self.sql)
        self.assertIn('BEFORE INSERT OR UPDATE OR DELETE ON public.%I', self.sql)
        self.assertIn('BEFORE TRUNCATE ON public.%I', self.sql)
        self.assertIn("ARRAY['model_changes', 'model_change_events']", self.sql)

    def test_no_address_is_kept_in_the_repository(self):
        self.assertNotRegex(self.sql, r'[\w.+-]+@[\w-]+\.[a-z]{2,}')
        self.assertNotRegex(self.sql, r'INSERT INTO (public\.)?site_admins')

    def test_the_live_tracking_document_is_let_in_by_its_own_migration(self):
        later = (ROOT / 'db/migrations/20261013_admin_live_tracking.sql').read_text()
        self.assertIn(later, (ROOT / 'db/schema.sql').read_text())
        self.assertIn("CHECK (name IN ('bets', 'model_changes', 'live_tracking'))", later)
        self.assertIn('DROP CONSTRAINT IF EXISTS admin_docs_name_check', later)
        self.assertNotRegex(later, r'(?i)\bgrant\b')              # it opens nothing: the same table, one more name

    def test_it_can_be_run_twice(self):
        self.assertEqual(self.sql.count('CREATE TABLE'), self.sql.count('CREATE TABLE IF NOT EXISTS'))
        self.assertEqual(self.sql.count('CREATE TRIGGER'), self.sql.count('DROP TRIGGER IF EXISTS'))


if __name__ == '__main__':
    unittest.main()
