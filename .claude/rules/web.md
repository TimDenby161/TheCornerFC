---
paths:
  - "web/**"
---

# The site (`web/`)

- No back buttons on any page. Navigation is the menu and the browser.
- Logic goes in tested `src/lib/*.ts`; database reads in `src/lib/server/`; pages stay thin.
- A page's choices live in its address, through GET forms. No inline styles: computed positions
  are classes from `placed.css` (the security policy forbids inline styles).
- Each page's intro and key come from `src/lib/tabInfo.ts`. Kick-off times go through
  `LocalTime.svelte`.
- Keep `#ad-top` and `#ad-rail` free when laying out a page. Adverts never go on Home, the two
  betting pages, the fantasy pages or the text pages.
- **No added cost** (`guide/costs.md`): count the database calls and Worker CPU a page adds;
  keep requests within the free plan and don't turn off caching.
- Heavy sums run in the browser, not the Worker (the free plan allows about 10 ms of CPU a
  request).
- Redirects to another site must name it: `redirect(..., { external: [...] })`.
- Secrets are Cloudflare Worker secrets, declared in `src/env.ts`. None in the code.
- A signed-in visitor's requests go through `askAs(fetch, locals.token, ...)`, never `keptAsk`,
  and their pages answer `private, no-store`.
- Lists behind the paywall keep the subscriber's order with the ranks hidden.

## Checks

From `web/`: `npm test`, `npm run check`, `node scripts/browser-check.mjs [address]`.
`npm run build` runs the first two before it builds, and Cloudflare's build runs `npm run build`,
so a failing test or type error stops a deploy. Add a step to `browser-check.mjs` for each new
interactive piece, and wait with its `until()`, not a fixed sleep. `scripts/fantasy-check.mjs`
covers the fantasy pages.
