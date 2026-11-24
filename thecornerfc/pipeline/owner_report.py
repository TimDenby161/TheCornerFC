"""The owner's morning email: yesterday's visits, new accounts and paid subscribers.

    python -m thecornerfc report            # read the figures and email them
    python -m thecornerfc report --dry-run  # read them and print the email, send nothing

Runs from .github/workflows/daily-report.yml on main. The repository and its Actions logs are
public, so the figures go only into the email: a real run prints nothing but whether it was sent.
It reads production (one connection, read-only statements), asks Cloudflare's Web Analytics for
yesterday's visits, and sends one email through Resend. It writes nothing and calls no feed.
"""
import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

UK = ZoneInfo("Europe/London")
CLOUDFLARE_GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
RESEND_EMAILS = "https://api.resend.com/emails"
SENDER = "TheCorner FC <reports@thecornerfc.com>"

# A subscription counts while paid up, with 3 days' grace for a failed renewal: the same test
# as site.subscriber() in db/schema.sql
PAID = ("b.status IN ('active', 'trialing', 'past_due') "
        "AND (b.current_period_end IS NULL OR b.current_period_end + interval '3 days' > now())")

ACCOUNTS_SQL = """
SELECT count(*) FILTER (WHERE u.created_at >= %(start)s AND u.created_at < %(end)s),
       count(*) FILTER (WHERE u.created_at >= %(start)s AND u.created_at < %(end)s
                          AND u.email_confirmed_at IS NOT NULL),
       count(*)
FROM auth.users u
"""

SUBSCRIBERS_SQL = f"""
SELECT count(*) FILTER (WHERE {PAID}),
       count(*) FILTER (WHERE {PAID} AND b.plan = 'monthly'),
       count(*) FILTER (WHERE {PAID} AND b.plan = 'yearly'),
       count(*) FILTER (WHERE {PAID} AND b.cancel_at_period_end),
       count(*) FILTER (WHERE {PAID} AND b.updated_at >= %(start)s AND b.updated_at < %(end)s)
FROM public.subscriptions b
"""

VISITS_QUERY = """
query ($account: String!, $site: String!, $start: Time!, $end: Time!) {
  viewer {
    accounts(filter: {accountTag: $account}) {
      rumPageloadEventsAdaptiveGroups(limit: 1, filter: {AND: [
        {datetime_geq: $start}, {datetime_lt: $end}, {siteTag: $site}]}) {
        count
        sum { visits }
      }
    }
  }
}
"""


def yesterday(now=None):
    """Yesterday as a UK day: its date and its start and end in UTC."""
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(UK).date() - timedelta(days=1)
    start = datetime.combine(day, time(0), UK)
    end = datetime.combine(day + timedelta(days=1), time(0), UK)
    return day, start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def database_figures(conn, start, end):
    params = {"start": start, "end": end}
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        new, confirmed, accounts = conn.execute(ACCOUNTS_SQL, params).fetchone()
        paid, monthly, yearly, cancelling, changed = conn.execute(SUBSCRIBERS_SQL, params).fetchone()
    return {"new_accounts": new, "new_confirmed": confirmed, "accounts": accounts,
            "paid": paid, "monthly": monthly, "yearly": yearly, "cancelling": cancelling,
            "paid_changed": changed}


def visits(start, end, *, token, account, site, post=requests.post):
    """Yesterday's Web Analytics figures, or None when Cloudflare can't be read."""
    if not (token and account and site):
        return None
    variables = {"account": account, "site": site,
                 "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        response = post(CLOUDFLARE_GRAPHQL, json={"query": VISITS_QUERY, "variables": variables},
                        headers={"Authorization": f"Bearer {token}"}, timeout=30)
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            return None
        groups = body["data"]["viewer"]["accounts"][0]["rumPageloadEventsAdaptiveGroups"]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None
    if not groups:
        return {"visits": 0, "page_views": 0}
    return {"visits": groups[0]["sum"]["visits"], "page_views": groups[0]["count"]}


def _plural(n, word):
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def compose(day, figures, web):
    when = f"{day:%A} {day.day} {day:%B %Y}"
    visits_short = "visits unknown" if web is None else _plural(web["visits"], "visit")
    subject = (f"TheCorner FC, {day.day} {day:%b}: {visits_short}, "
               f"{_plural(figures['new_accounts'], 'new account')}, {figures['paid']:,} paid")
    if web is None:
        web_lines = ["Visits: Cloudflare couldn't be read this morning."]
    else:
        web_lines = [f"Visits: {web['visits']:,} (people arriving from outside the site)",
                     f"Page views: {web['page_views']:,}"]
    lines = [
        f"Yesterday, {when} (UK time)",
        "",
        *web_lines,
        "",
        f"New accounts: {figures['new_accounts']:,} ({figures['new_confirmed']:,} confirmed their email)",
        f"All accounts: {figures['accounts']:,}",
        "",
        f"Paid subscribers now: {figures['paid']:,} ({figures['monthly']:,} monthly, {figures['yearly']:,} yearly)",
        f"Of those, set to cancel at the period end: {figures['cancelling']:,}",
        f"Subscriptions started, renewed or changed yesterday: {figures['paid_changed']:,}",
        "",
        "Visits and page views are Cloudflare Web Analytics' figures (sampled). Your own visits",
        "count too. Your own account isn't a paid subscriber, so it isn't in that number.",
    ]
    return subject, "\n".join(lines) + "\n"


def send(subject, text, *, api_key, to, post=requests.post):
    response = post(RESEND_EMAILS, json={"from": SENDER, "to": [to], "subject": subject, "text": text},
                    headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
    if response.status_code >= 300:
        raise RuntimeError(f"Resend refused the email (HTTP {response.status_code})")


def run(dry_run=False):
    from .db import connect

    to = (os.getenv("REPORT_TO") or "").strip()
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not dry_run and not (to and api_key):
        raise RuntimeError("REPORT_TO and RESEND_API_KEY must be set to send the report")
    day, start, end = yesterday()
    conn = connect()
    try:
        figures = database_figures(conn, start, end)
    finally:
        conn.close()
    web = visits(start, end, token=(os.getenv("CLOUDFLARE_ANALYTICS_TOKEN") or "").strip(),
                 account=(os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip(),
                 site=(os.getenv("CLOUDFLARE_SITE_TAG") or "").strip())
    subject, text = compose(day, figures, web)
    if dry_run:
        print(subject, text, sep="\n\n")
        return
    send(subject, text, api_key=api_key, to=to)
    # Nothing else: the logs are public
    print("Report sent" + ("" if web else " (without visits: Cloudflare couldn't be read)"))
