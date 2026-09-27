# Security

## Reporting a problem

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/TimDenby161/TheCornerFC/security/advisories/new),
not in a public issue. Useful reports say what's affected (the website at thecornerfc.com, a
workflow, or the data pipeline) and how to reproduce it. This is a one-person hobby project, so
expect a reply within about a week.

Data errors (a wrong result, player or injury) aren't security issues. Report them as a normal
[issue](https://github.com/TimDenby161/TheCornerFC/issues/new). The site's privacy, corrections and
security page is [`docs/privacy.html`](docs/privacy.html).

## What there is to protect

The website is static files on GitHub Pages with no accounts, forms, cookies or analytics. The
only secrets are two GitHub Actions repository secrets. Nothing secret ships to the browser.

| Secret | Used by | Grants |
|---|---|---|
| `API_FOOTBALL_KEY` | nightly, match day, backfill workflows | API-Football requests on the paid plan (quota and billing) |
| `DATABASE_URL` | all four workflows | Write access to the Supabase Postgres database |
| `GITHUB_TOKEN` | all workflows (automatic) | Push to this repo: each job gets only `contents: write`, and the workflow default is no permissions |

Locally, `.env` holds the same names and is git-ignored. Local runs default to a read-only
database role and no API calls (README: Local development safety).

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

**If a secret was committed.** Rotate it first. Removing it from git history doesn't un-leak it.
Then check the whole history (below). The repository is public, so assume it has been copied.

## Checking for leaked secrets

On 2026-09-27 the full history (350 commits) was scanned with gitleaks 8.30 and trufflehog 3.97.
Neither found a real credential. The only matches were the placeholder URLs in `.env.example`,
README and `tests/test_db_connection.py`. To repeat the scan:

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

## Website controls

GitHub Pages can't set response headers, so what it can do is in the page:

- A Content-Security-Policy `<meta>` in `docs/index.html`: scripts only from the site itself
  (no inline script or `on…=` handlers), images only from the site, `media.api-sports.io` and
  `flagcdn.com`, and data only fetched from the site. `frame-ancestors` (clickjacking) and HSTS
  can't be set this way. They would need a host or CDN that sends headers.
- `Referrer-Policy: strict-origin-when-cross-origin`, so the image hosts see only the site's
  origin, not the page.
- API data that goes into markup is checked. Kit colours must be six-digit hex and image URLs
  are built from numeric ids or must be on API-Football's media host, both in the export
  (`thecornerfc/export.py`) and again in `docs/assets/app.js`. Text goes through `escapeHtml`.
- **Enforce HTTPS** must be on in the Pages settings.
- `docs/.well-known/security.txt` expires 2027-09-27. Renew the date before then.
