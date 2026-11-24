import unittest
from datetime import date, datetime, timezone

import requests

from thecornerfc.pipeline import owner_report


class Response:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._body


class Connection:
    def __init__(self):
        self.statements = []
        self.answers = [(9, 9, 9, 3), (2, 1, 40, 0), (3, 2, 1, 1, 1), (6, 4)]

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return self

    def fetchone(self):
        return self.answers.pop(0)


FIGURES = {"new_accounts": 2, "new_confirmed": 1, "accounts": 40, "yours": 3, "paid": 3, "monthly": 2,
           "yearly": 1, "cancelling": 1, "paid_changed": 1, "week_accounts": 6, "prev_accounts": 4}


class OwnerReportTests(unittest.TestCase):
    def test_yesterday_is_a_uk_day_in_winter_and_in_summer(self):
        day, start, end = owner_report.yesterday(datetime(2026, 11, 24, 6, 30, tzinfo=timezone.utc))
        self.assertEqual(day, date(2026, 11, 23))
        self.assertEqual((start, end), (datetime(2026, 11, 23, tzinfo=timezone.utc),
                                        datetime(2026, 11, 24, tzinfo=timezone.utc)))
        day, start, end = owner_report.yesterday(datetime(2026, 7, 2, 5, 30, tzinfo=timezone.utc))
        self.assertEqual(day, date(2026, 7, 1))
        self.assertEqual(start, datetime(2026, 6, 30, 23, tzinfo=timezone.utc))

    def test_the_database_is_only_read(self):
        conn = Connection()
        end = datetime(2026, 11, 24, tzinfo=timezone.utc)
        figures = owner_report.database_figures(conn, "s", end)
        self.assertEqual(figures, FIGURES)
        self.assertEqual(conn.statements[0][0], "SET TRANSACTION READ ONLY")
        for sql, _ in conn.statements[1:]:
            self.assertTrue(sql.strip().startswith("SELECT"))

    def test_the_owners_accounts_are_left_out(self):
        for sql in (owner_report.ACCOUNTS_SQL, owner_report.SUBSCRIBERS_SQL):
            self.assertIn("LIKE 'timdenby161%%'", sql)
            self.assertIn("site_admins", sql)
            self.assertIn("fpl_team_owners", sql)

    def test_paid_means_what_the_site_means(self):
        self.assertIn("'active', 'trialing', 'past_due'", owner_report.SUBSCRIBERS_SQL)
        self.assertIn("interval '3 days'", owner_report.SUBSCRIBERS_SQL)

    def test_visits_come_from_web_analytics(self):
        sent = {}

        def post(url, json, headers, timeout):
            sent.update(url=url, variables=json["variables"], auth=headers["Authorization"])
            return Response(body={"data": {"viewer": {"accounts": [{"rumPageloadEventsAdaptiveGroups": [
                {"count": 120, "sum": {"visits": 17}}]}]}}})

        start, end = datetime(2026, 11, 23, tzinfo=timezone.utc), datetime(2026, 11, 24, tzinfo=timezone.utc)
        web = owner_report.visits(start, end, token="t", account="a", site="s", post=post)
        self.assertEqual(web, {"visits": 17, "page_views": 120})
        self.assertEqual(sent["variables"]["start"], "2026-11-23T00:00:00Z")
        self.assertEqual(sent["auth"], "Bearer t")

    def test_no_visits_when_cloudflare_cannot_be_read(self):
        def failing(*a, **k):
            raise requests.ConnectionError("down")

        self.assertIsNone(owner_report.visits(None, None, token="", account="a", site="s"))
        now = datetime(2026, 11, 23, tzinfo=timezone.utc)
        self.assertIsNone(owner_report.visits(now, now, token="t", account="a", site="s", post=failing))
        errors = lambda *a, **k: Response(body={"errors": [{"message": "no"}], "data": None})
        self.assertIsNone(owner_report.visits(now, now, token="t", account="a", site="s", post=errors))

    def test_the_email_says_each_figure(self):
        subject, text = owner_report.compose(date(2026, 11, 23), FIGURES, {"visits": 17, "page_views": 120})
        self.assertEqual(subject, "TheCorner FC, 23 Nov: 17 visits, 2 new accounts, 3 paid")
        self.assertIn("Monday 23 November 2026", text)
        self.assertIn("Visits: 17", text)
        self.assertIn("New accounts: 2 (1 confirmed their email)", text)
        self.assertIn("Paid subscribers now: 3 (2 monthly, 1 yearly)", text)
        self.assertIn("All accounts: 40 (your own 3 left out)", text)
        subject, text = owner_report.compose(date(2026, 11, 23), FIGURES, None)
        self.assertIn("visits unknown", subject)
        self.assertIn("Cloudflare couldn't be read", text)

    def test_the_week_against_the_week_before_and_where_visits_came_from(self):
        sent = {}

        def post(url, json, headers, timeout):
            sent.update(json["variables"])
            return Response(body={"data": {"viewer": {"accounts": [{
                "week": [{"count": 300, "sum": {"visits": 120}}], "prev": [{"count": 200, "sum": {"visits": 80}}],
                "refs": [{"sum": {"visits": 60}, "dimensions": {"refererHost": "www.google.com"}},
                         {"sum": {"visits": 30}, "dimensions": {"refererHost": ""}},
                         {"sum": {"visits": 12}, "dimensions": {"refererHost": "example.org"}}]}]}}})

        end = datetime(2026, 11, 24, tzinfo=timezone.utc)
        week = owner_report.week_visits(end, token="t", account="a", site="s", post=post)
        self.assertEqual((sent["weekStart"], sent["prevStart"], sent["end"]),
                         ("2026-11-17T00:00:00Z", "2026-11-10T00:00:00Z", "2026-11-24T00:00:00Z"))
        _, text = owner_report.compose(date(2026, 11, 23), FIGURES, {"visits": 17, "page_views": 120}, week)
        self.assertIn("Visits: 120, up 50% on the week before (80)", text)
        self.assertIn("Page views: 300, up 50% on the week before (200)", text)
        self.assertIn("New accounts: 6, up 50% on the week before (4)", text)
        self.assertIn("Where the last 7 days' visits came from: google.com 60, direct or unknown 30, example.org 12", text)
        _, text = owner_report.compose(date(2026, 11, 23), FIGURES, None, None)
        self.assertIn("The last 7 days, against the 7 before\nVisits: Cloudflare couldn't be read", text)

    def test_a_refused_email_fails_the_run(self):
        sent = {}

        def post(url, json, headers, timeout):
            sent.update(json)
            return Response(status=422)

        with self.assertRaises(RuntimeError):
            owner_report.send("s", "t", api_key="k", to="owner@example.com", post=post)
        self.assertEqual(sent["to"], ["owner@example.com"])
        self.assertTrue(sent["from"].endswith("@thecornerfc.com>"))


if __name__ == "__main__":
    unittest.main()
