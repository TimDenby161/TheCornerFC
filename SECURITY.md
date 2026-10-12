# Security

## Reporting a problem

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/TimDenby161/TheCornerFC/security/advisories/new),
not in a public issue. Useful reports say what's affected (the website at thecornerfc.com, a
workflow, or the data pipeline) and how to reproduce it. This is a one-person hobby project, so
expect a reply within about a week.

Data errors (a wrong result, player or injury) aren't security issues. Report them as a normal
[issue](https://github.com/TimDenby161/TheCornerFC/issues/new). The site's privacy, corrections and
security page is [`web/src/text/privacy.html`](web/src/text/privacy.html).

## What there is to protect

The website is a SvelteKit app running as the Cloudflare Worker `thecornerfc`. It reads the
database on the server and sends pages to the browser; the browser talks only to
thecornerfc.com. There is no analytics script. Visitors can create an optional account
([Accounts](guide/accounts.md)): Supabase Auth holds their email addresses and password hashes,
and a signed-in visitor's session is a cookie the page's scripts can't read (`HttpOnly`,
`Secure`, `SameSite=Lax`). Nothing secret is in the repository or in what the browser is sent.

| Secret | Held by | Used by | Grants |
|---|---|---|---|
| `API_FOOTBALL_KEY` | GitHub Actions secret | nightly, match day and both backfill workflows | API-Football requests on the paid plan (quota and billing) |
| `DATABASE_URL` | GitHub Actions secret | all five job workflows | Write access to the Supabase Postgres database |
| `GITHUB_TOKEN` | GitHub (automatic) | all workflows | Read the repository only: the workflow default is no permissions and each job asks for `contents: read` (the nightly check also `actions: read`). No job commits or pushes |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_MONTHLY`, `STRIPE_PRICE_YEARLY` | Cloudflare Worker secrets (declared in `web/src/env.ts`) | `web/src/lib/server/payments.ts` | Taking payment. Each may be missing; until all are set, subscriptions can't be bought |
| `SUPABASE_SERVICE_KEY` | Cloudflare Worker secret | `web/src/lib/server/payments.ts` only | Writing the `subscriptions` table. It bypasses row level security, so it is used nowhere else |
| The owner's sign-in (Google account or site password) | the owner | Sign in | Reading the owner-only FPL and EFL Fantasy pages, and saving or undoing that FPL entry's locked-in transfers. Nothing else |

The tests (`.github/workflows/tests.yml`, and the "Unit tests" step in each job) are given no
secret.

Locally, `.env` is git-ignored and should hold only a read-only database role: no write
address and no API key ([Local development safety](guide/local-safety.md);
`python db/check_local_access.py` says what each address may do without showing it). Local runs
refuse database writes and API calls in code as well.

### The Supabase publishable key

`web/src/lib/config.ts` contains the Supabase project URL and a key starting `sb_publishable_`. It is
public on purpose and is not a secret: it only identifies the project to Supabase's API, and the
database decides what it may do. Secret scanners flag it (see below); that match is expected.

What the key can do on its own, once `db/migrations/20261001_anon_grants.sql` and
`20261004_fpl_owner_login.sql` are applied (last checked against the live project on 2026-10-01,
before them):

- Sign a visitor up or in through Supabase Auth.
- Call the functions the site reads through, and nothing else: `site_doc` and the `site_*`
  queries, each with fixed SQL, which never return a row marked paid to a visitor who isn't a
  subscriber. It holds no grant on any table or view. A signed-in visitor can also call
  `delete_my_account` (their own account only) and the three FPL functions, which answer only
  the owner. (The grants are in `db/schema.sql`; this list was last checked against the live
  project before the `site_*` functions existed, so check it again there.)

Row level security is the only barrier on most tables, so **every new table or view needs it
before it exists in production**: `alter table … enable row level security`, and for a view,
revoke `anon` and `authenticated` (views skip row level security). Supabase's secret keys
(`sb_secret_…`, or the legacy `service_role` key) bypass all of this and must never go into the
repo, a workflow or anything the browser is sent. The one use is the Worker secret
`SUPABASE_SERVICE_KEY` above. The pipeline uses `DATABASE_URL` instead.

### My FPL team lock-in

"I've made these transfers" on the My FPL team page is the one place the public site writes to the
database. How it's protected:

- The two database functions behind it can be called by signed-in visitors only, and do nothing
  unless the caller's confirmed email address is the one in `fpl_team_owners` for the entry, which
  neither the publishable key nor a signed-in visitor can read.
- The functions accept only a list of at most 15 transfers (8 KB) for one entry and gameweek. The
  page uses the player ids in a lock and ignores any that don't fit the squad.
- The owner's access is as strong as that sign-in: keep two-step verification on the Google
  account, and sign out on a device that isn't yours.
- The browser never calls Supabase itself: the page posts to this site (`web/src/routes/fantasy/`),
  which passes the request on with the signed-in visitor's own token. The Content-Security-Policy's
  `connect-src` is `'self'`.

## Rotating a credential

Rotate straight away if a secret may have leaked (pasted somewhere, committed, shown in a log, or
on a lost machine). Otherwise, rotate about once a year. After each rotation, run
**Actions → Nightly sync → Run workflow** and check it goes green.

**API-Football key**
1. In the API-Football (api-sports.io) dashboard, generate a new key and revoke the old one.
2. Update the `API_FOOTBALL_KEY` repository secret (Settings → Secrets and variables → Actions)
   and your local `.env`.
3. `python -m thecornerfc status` checks the new key and shows the quota.

**Database password (`DATABASE_URL`)**
1. In Supabase: Project Settings → Database → Reset database password. Any other role in the
   URL has its password changed with `alter role … with password …` instead.
2. Copy the **Session pooler** string again (Connect → Session pooler) with the new password.
3. Update the `DATABASE_URL` repository secret and any local `.env` that has it.
4. The read-only local role (`READ_ONLY_DATABASE_URL`) is rotated the same way, in `.env` only.

**The owner's sign-in**
1. If the Google account or site password may be known to someone else, change it there first,
   then in Supabase → Authentication → Users open the owner's user and sign out all its sessions.
2. To move the owner pages to a different address, run the `INSERT INTO fpl_team_owners …`
   statement from [My FPL team](guide/my-fpl-team.md) with the new one.

**Supabase publishable key.** It isn't a secret, so a leak isn't possible. To replace it anyway
(for example to cut off a script that misuses it): Supabase → Project Settings → API Keys, create
a new publishable key, put it in `SUPABASE.key` in `web/src/lib/config.ts`, deploy, then delete the
old one.

**If a secret was committed.** Rotate it first. Removing it from git history doesn't un-leak it.
Then check the whole history (below). The repository is public, so assume it has been copied.

## Checking for leaked secrets

On 2026-10-01 the full history (426 commits) was scanned with gitleaks 8.30 and trufflehog 3.97.
Neither found a real credential. The only matches were the placeholder URLs in `.env.example`,
README and `tests/test_db_connection.py`, the empty `API_FOOTBALL_KEY=` line in `.env.example`,
and the Supabase publishable key in `web/src/lib/config.ts` (public by design, see above). To repeat
the scan:

```bash
gitleaks git --log-opts="--all" --redact -v .
trufflehog git file://. --no-update --results=verified,unverified
```

GitHub secret scanning and push protection (repo settings) catch new leaks as they're pushed.

## Dependencies

- `requirements.in` lists the direct Python dependencies. `requirements.txt` is the lock file
  (exact versions and hashes, compiled for Python 3.13 to match the workflows). To change a
  dependency, edit `requirements.in` and run:
  ```bash
  pip install pip-tools
  pip-compile --generate-hashes --strip-extras --allow-unsafe -o requirements.txt requirements.in
  ```
- Workflows use GitHub Actions pinned to full commit SHAs (the `# v4` comment is the tag).
- Dependabot (`.github/dependabot.yml`) opens weekly PRs for both. Dependabot security updates
  (repo settings) open them as soon as an advisory lands.
- On 2026-10-01 pip-audit 2.10 found no known vulnerabilities in `requirements.txt`. To repeat:
  ```bash
  pip-audit -r requirements.txt --require-hashes --disable-pip
  ```

## Website controls

The Worker sends the controls as response headers (`web/vite.config.ts`, `web/src/hooks.server.ts`):

- A Content-Security-Policy header on every page, with a one-off nonce for the one script the
  server writes into the page. Scripts only from the site itself and Cloudflare's bot check; no
  inline styles (one hashed exception, the framework's own); images only from the site and
  `flagcdn.com`; `connect-src 'self'`; `object-src 'none'`; `base-uri 'self'`;
  `frame-ancestors 'none'` (clickjacking); forms may post only to the site, the Supabase project,
  Google's sign-in and Stripe's checkout and billing pages.
- `Referrer-Policy: strict-origin-when-cross-origin` (a `<meta>` in `web/src/app.html`), so the
  flag host sees only the site's origin, not the page.
- A page differs by who asks: every response carries `Vary: Cookie`, and a signed-in visitor's
  is `Cache-Control: private, no-store`.
- `http://` and `www.` are redirected to `https://thecornerfc.com` by the Worker. HSTS is a
  Cloudflare setting (SSL/TLS → Edge Certificates), not in the repository: check it is on.
- A redirect to another site has to name it (`redirect(..., { external: [...] })`), and the
  address to return to after signing in must be a path of this site (`safePath`).
- API data that goes into a page is escaped by Svelte. Kit colours must be six-digit hex in the
  export (`_kit_colors` in `thecornerfc/publish/site_clubs.py`), and flag URLs are built from a
  fixed list of country codes.
- `web/static/.well-known/security.txt` expires 2027-09-27. Renew the date before then.
