import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("already_ran", ROOT / "scripts/already_ran.py")
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)

T = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class Slots(unittest.TestCase):
    def test_the_nightly_has_one_slot_a_day(self):
        self.assertEqual(ar.slot_start("nightly.yml", T("2026-10-16T05:53:00")), T("2026-10-16T00:00:00"))

    def test_match_day_has_one_each_half_hour(self):
        self.assertEqual(ar.slot_start("matchday.yml", T("2026-10-16T12:07:00")), T("2026-10-16T12:00:00"))
        self.assertEqual(ar.slot_start("matchday.yml", T("2026-10-16T12:31:00")), T("2026-10-16T12:30:00"))

    def test_fpl_has_three_a_day(self):
        self.assertEqual(ar.slot_start("fpl.yml", T("2026-10-16T13:40:00")), T("2026-10-16T13:00:00"))
        self.assertEqual(ar.slot_start("fpl.yml", T("2026-10-16T23:10:00")), T("2026-10-16T19:00:00"))
        # before 07:00 the slot is the previous evening's
        self.assertEqual(ar.slot_start("fpl.yml", T("2026-10-16T05:00:00")), T("2026-10-15T19:00:00"))


class ShouldRun(unittest.TestCase):
    slot = T("2026-10-16T12:00:00")

    def test_a_run_by_hand_always_works(self):
        self.assertTrue(ar.should_run("workflow_dispatch", "", self.slot, [T("2026-10-16T12:01:00")]))

    def test_the_timer_and_the_schedule_skip_once_the_slot_is_done(self):
        for event, source in [("workflow_dispatch", "timer"), ("schedule", "")]:
            with self.subTest(event=event):
                self.assertFalse(ar.should_run(event, source, self.slot, [T("2026-10-16T12:00:30")]))
                self.assertTrue(ar.should_run(event, source, self.slot, [T("2026-10-16T11:30:20")]))
                self.assertTrue(ar.should_run(event, source, self.slot, []))


class WorkDone(unittest.TestCase):
    slot = T("2026-10-16T12:00:00")

    def github(self, runs, jobs):
        def get(path):
            if path.startswith("actions/workflows/"):
                return {"workflow_runs": runs}
            return {"jobs": jobs[int(path.split("/")[2])]}
        return get

    def test_only_a_work_job_that_succeeded_counts(self):
        runs = [{"id": 1, "updated_at": "2026-10-16T12:05:00Z"},   # did the work
                {"id": 2, "updated_at": "2026-10-16T12:06:00Z"},   # only skipped: its work job was skipped
                {"id": 3, "updated_at": "2026-10-16T12:07:00Z"},   # its work failed
                {"id": 4, "updated_at": "2026-10-16T11:45:00Z"},   # finished before the slot
                {"id": 9, "updated_at": "2026-10-16T12:08:00Z"}]   # this run
        jobs = {1: [{"name": "check", "conclusion": "success", "started_at": "2026-10-16T12:00:10Z"},
                    {"name": "matchday", "conclusion": "success", "started_at": "2026-10-16T12:00:40Z"}],
                2: [{"name": "check", "conclusion": "success", "started_at": "2026-10-16T12:06:00Z"},
                    {"name": "matchday", "conclusion": "skipped", "started_at": None}],
                3: [{"name": "matchday", "conclusion": "failure", "started_at": "2026-10-16T12:06:30Z"}],
                4: [{"name": "matchday", "conclusion": "success", "started_at": "2026-10-16T11:30:40Z"}],
                9: [{"name": "matchday", "conclusion": "success", "started_at": "2026-10-16T12:08:00Z"}]}
        done = ar.work_done(self.github(runs, jobs), "matchday.yml", self.slot, this_run=9)
        self.assertEqual(done, [T("2026-10-16T12:00:40")])

    def test_a_skip_never_makes_the_next_slot_skip(self):
        # 12:00 worked, 12:05 skipped; at 12:30 nothing in the new slot has worked, so it works
        runs = [{"id": 1, "updated_at": "2026-10-16T12:02:00Z"}, {"id": 2, "updated_at": "2026-10-16T12:05:30Z"}]
        jobs = {1: [{"name": "matchday", "conclusion": "success", "started_at": "2026-10-16T12:00:40Z"}],
                2: [{"name": "matchday", "conclusion": "skipped", "started_at": None}]}
        slot = T("2026-10-16T12:30:00")
        done = ar.work_done(self.github(runs, jobs), "matchday.yml", slot, this_run=5)
        self.assertTrue(ar.should_run("workflow_dispatch", "timer", slot, done))


if __name__ == "__main__":
    unittest.main()
