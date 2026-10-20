# Running costs

The owner's rule: **no change may add cost.** Every change is checked against each paid or
metered service it touches before it is built, and a change that would push one onto a higher
plan, past its allowance or into overage is put to the owner first, as one plain question,
with the cost. The answer is usually a cheaper design, not a bigger bill.

## What is paid today

$54 a month, as the owner confirmed on 14 October 2026:

| Service | Plan | Price | Allowance to stay within |
|---|---|---|---|
| **API-Football** | Ultra | $29 a month | 75,000 calls a day, reset daily; the jobs keep `API_DAILY_RESERVE` (200) back |
| **Supabase** (production) | Pro | $25 a month | Its included disk, egress and the smallest compute (the credit covers it); Disk IO is the tightest limit. Anything above is billed as overage or needs a bigger compute size |

**The aim is to step API-Football down to Pro** ($19 a month, 7,500 calls a day), the owner's
wish on 14 October 2026. So a change should bring the calls a day down, never up, and every
day's total, backfills included, should be heading under 7,500 less the reserve. Once it fits,
the owner changes the plan.

**Azure App Service B1** (Linux, UK South) runs the site, live and staging on one plan: about
$13 (£10) a month, the owner's yes on 2026-10-18; a budget emails at US$16 and a policy refuses
anything but that one plan.

Everything else is free: the staging Supabase project, Cloudflare (DNS, Access, the timer
Worker, and the old site's Workers until about 2026-11-03) and GitHub (public repository). Check the providers' pages for the current figures before
relying on a number here.

## The services and what to watch

| Service | What it runs | What costs money | What to check |
|---|---|---|---|
| **API-Football** | Every fetch, in the GitHub jobs only | A bigger plan if the calls outgrow 75,000 a day; staying on Ultra if they don't fit under Pro's 7,500 | New calls a run makes (per night, per match day, per backfill), whether an existing response already holds the data, `API_DAILY_RESERVE`, a backfill's `call_budget`. [API usage](api-usage.md) |
| **Supabase** (production) | The database the jobs write and the site reads | Overage above Pro's included disk and egress; a bigger compute size or add-ons if Disk IO or CPU run out | Rows and bytes a new table or column adds a season, indexes, how often a job rewrites a table whole, how much each page request reads (a function's joins, `limit`), egress from exports. It warned on Disk IO on 2026-10-05 |
| **Supabase** (staging) | Its own free project | Moving it to a paid project (about $10–25 a month) | Stays under 500 MB; it holds a few leagues, not everything. [Production and staging](environments.md#what-it-costs) |
| **Azure** | The site: web apps `thecornerfc` and `thecornerfc-staging` on one B1 plan | A second instance or a bigger plan (the policy refuses both); outbound data beyond the free allowance | Memory and CPU on the one B1 (1.75 GB, one core) shared by both apps, the budget's emails |
| **Cloudflare** | DNS, the proxy and cache in front of the site, Access, the timer Worker | Workers Paid ($5 a month) if the timer's free limits are passed | Caching that a change would turn off, Access up to 50 people |
| **GitHub** | The scheduled jobs and the tests | Nothing while the repository is public | A new workflow or a longer schedule is free only while the repository stays public |

Not yet in use: Stripe and AdSense (parked, [Paid tier](paid-tier.md)).

## Before building a change

1. Name each service the change touches.
2. For each, say what it adds: API calls a day, rows and megabytes a season, reads per page
   view, the server's CPU and memory, build minutes.
3. Prefer the design that adds nothing: reuse a response or table already there, ask for one
   item rather than a list, cache, run heavy sums in the browser, store less.
4. If anything would still raise a bill or move a plan, stop and ask the owner before building.

A change that saves cost is welcome and worth saying so.
