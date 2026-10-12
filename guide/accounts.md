# Accounts

Visitors can sign in with Google or with an email and password (Supabase Auth; **Sign in** in the
header). The only thing an account unlocks is the owner's: the FPL predictions and My FPL team
answer only the sign-in named in `fpl_team_owners` ([My FPL team](my-fpl-team.md)), and the
Admin area answers only an address in `site_admins` ([The Admin area](admin-area.md)). The code is
`web/src/lib/server/auth.ts`, `web/src/hooks.server.ts` (finishing a sign-in from an emailed link
or from Google, and reading who is signed in) and the account page,
`web/src/routes/(app)/account/`.

- **Sign-in is the server's job.** The session (Supabase Auth's access and refresh tokens) is in
  a cookie the page's scripts can't read (`HttpOnly`, `Secure`, `SameSite=Lax`); nothing is kept
  in the browser's storage. The libraries are the npm packages `@supabase/ssr` and
  `@supabase/supabase-js` in `web/package.json`, updated like any other dependency. A signed-in
  visitor's pages are answered `private, no-store`, and their database requests carry their own
  token (`askAs` in `web/src/lib/server/database.ts`).
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
  forms carry a Cloudflare Turnstile check (`web/src/lib/components/BotCheck.svelte`), whose
  token Supabase verifies before it acts. All three steps below are done. To set it up again,
  in this order:
  1. Cloudflare dashboard → Turnstile → add a widget for `thecornerfc.com` (and `localhost` for
     the local preview), mode Managed. It gives a site key (public) and a secret key.
  2. Put the site key in `BotCheck.svelte`. The security policy in `web/vite.config.ts` must
     allow `https://challenges.cloudflare.com` in `script-src` and `frame-src` (it does). The
     privacy page (`web/src/text/privacy.html`) says that the account forms load Cloudflare
     Turnstile, which sees the visitor's IP address and browser details. Deploy.
  3. Only once the site is live with the key: Supabase → Authentication → Attack Protection →
     Enable CAPTCHA protection, provider Turnstile, paste the secret key. From then Supabase
     refuses any of the three calls that comes without a token, so the other order locks
     everyone but Google sign-ins out until the site catches up.

  To turn it off, undo step 3 first, then step 2.
