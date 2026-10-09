# Accounts

Visitors can sign in with Google or with an email and password (Supabase Auth; **Sign in** in the
header). The only thing an account unlocks is the owner's: the FPL predictions and My FPL team
answer only the sign-in named in `fpl_team_owners` (My FPL team, below). The code is the "accounts" section of `docs/assets/app.js`.

- **Library.** `docs/assets/lib/supabase-js-2.117.2.js` is `dist/umd/supabase.js` from the npm
  package `@supabase/supabase-js` 2.117.2, unchanged (the page's policy allows scripts from this
  site only). It is fetched only when the sign-in box is opened or a visitor is already signed
  in. To update it: `npm pack @supabase/supabase-js@<version>`, copy that file in under the new
  name, and change `AUTH_LIB` in `app.js` and the name and hash in `tests/test_accounts.py`.
- **Supabase settings** (Authentication): Google and Email providers on, with Confirm email;
  Site URL `https://thecornerfc.com`; Redirect URLs `https://thecornerfc.com/**` and the local
  preview address; custom SMTP for the emails. Google's OAuth client lives in the Google Cloud
  project "The Corner FC"; its secret is held by Supabase only.
- **Email links.** Supabase's default links only work in the browser that asked for them. To
  make them work anywhere, set these in Authentication → Emails → Templates:
  Confirm signup `{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=email`,
  Reset password `{{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=recovery`.
- **Deleting an account.** Account → Delete account calls `delete_my_account()`
  (`db/migrations/20261004_delete_my_account.sql`), which removes the caller's own row from
  Supabase Auth and nothing else.
- **Retention.** The nightly run deletes email sign-ups never confirmed within 7 days
  (`thecornerfc/privacy/accounts.py`; the privacy page promises the same). Confirmed accounts are kept
  until their owner deletes them.
- **Bot check (on since 2026-10-07, enforced by Supabase).** The sign-in, sign-up and reset
  forms carry a Cloudflare Turnstile check, whose token Supabase verifies before it acts. All
  three steps below are done. While `TURNSTILE_KEY` in `app.js` is empty nothing of
  Cloudflare's is loaded. To turn it on, in this order:
  1. Cloudflare dashboard → Turnstile → add a widget for `thecornerfc.com` (and `localhost` for
     the local preview), mode Managed. It gives a site key (public) and a secret key.
  2. Put the site key in `TURNSTILE_KEY`. In `docs/index.html`'s policy make `script-src 'self'`
     into `script-src 'self' https://challenges.cloudflare.com` and add
     `frame-src https://challenges.cloudflare.com;`. Say in `docs/privacy.html` that the account
     forms load Cloudflare Turnstile, which sees the visitor's IP address and browser details.
     `tests/test_accounts.py` fails until all three agree. Deploy.
  3. Only once the site is live with the key: Supabase → Authentication → Attack Protection →
     Enable CAPTCHA protection, provider Turnstile, paste the secret key. From then Supabase
     refuses any of the three calls that comes without a token, so the other order locks
     everyone but Google sign-ins out until the site catches up.

  To turn it off, undo step 3 first, then step 2.
