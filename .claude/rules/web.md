---
paths:
  - "site/**"
  - "web/**"
---

# The site (`site/`, with what it shares from `web/`)

The live site is the C# app in `site/` (since 2026-10-20). `web/` was the SvelteKit site; it
stays as the source of the stylesheets, icons, text pages, `tabInfo.json`, `names.json` and the
logic in `web/src/lib` that the React parts import, so a change there changes the C# site too.

- No back buttons on any page. Navigation is the menu and the browser.
- Logic goes in tested `Site/*.cs` (or `web/src/lib/*.ts` when a React part needs it); database
  reads go through `Data/Database.cs`; Razor pages stay thin.
- React only where it earns it (the sign-in box, filters with sliders, the match card's panels,
  the rank chart, the fantasy pages); small touches are plain JavaScript in `Assets/` (edit
  there, never `wwwroot/`).
- A page's choices live in its address, through GET forms. No inline styles: computed positions
  are classes from `placed.css` (the security policy in `Site/Gate.cs` forbids inline styles).
- Each page's intro and key come from `tabInfo.json` (`TabHead.For`). Kick-off times go through
  `Markup.LocalTime` (`LocalTime.tsx` in React).
- Keep `#ad-top` and `#ad-rail` free when laying out a page. Adverts never go on Home, the two
  betting pages, the fantasy pages or the text pages.
- **No added cost** (`guide/costs.md`): count the database calls a page adds; keep what every
  visitor shares in `KeptDoc`/`KeptAsk` and don't turn off Cloudflare's caching. The site runs
  on one B1 plan with the staging app: no second instance or bigger plan without the owner.
- Secrets are the Azure web app's settings. None in the code.
- A signed-in visitor's requests go through `AskAs(token, ...)` with their own token, never
  `KeptAsk`, and their pages answer `private, no-store`.
- Fantasy data never goes into a page the server writes: the owner's browser asks for it.
- Lists behind the paywall keep the subscriber's order with the ranks hidden.
- No fault text on any page: faults go to the logs only.

## Checks

From `site/`: `dotnet test`. From `site/client`: `npm test`, `npm run check`. From `web/`
(its shared logic): `npm test`, `npm run check`. Then run the site (`dotnet run --urls
http://127.0.0.1:5280` from `site/TheCornerFC.Web`) and `node web/scripts/browser-check.mjs
http://127.0.0.1:5280`; `node web/scripts/fantasy-check.mjs "" http://127.0.0.1:5280` for the
fantasy pages. `site/e2e` drives the site as visitors on phone and desktop sizes, with accessibility
checks, on staging's data (`npx playwright test` from there; the Visitors workflow runs it on
staging): add to it for each new page or interactive piece. The deploy workflow runs the React and C# tests first, so a failing test stops a
deploy. Add a step to `browser-check.mjs` for each new interactive piece, and wait with its
`until()`, not a fixed sleep.
