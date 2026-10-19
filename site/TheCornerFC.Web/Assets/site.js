// Every page's own small script: the menu, the theme and kick-off time choices, the visitor's time
// zone, and the old site's #/ links. The interactive pieces with more to them are React (step by
// step, audit/csharp-rebuild-plan.md).
(() => {
	const body = document.body;
	const menuBtn = document.querySelector('.menu-btn');
	const backdrop = document.querySelector('.menu-backdrop');
	const main = document.getElementById('main');
	const setMenu = (open) => {
		body.classList.toggle('menu-open', open);
		menuBtn?.setAttribute('aria-expanded', String(open));
		if (backdrop) backdrop.hidden = !open;
		if (main) main.inert = open;
	};
	menuBtn?.addEventListener('click', () => setMenu(!body.classList.contains('menu-open')));
	backdrop?.addEventListener('click', () => setMenu(false));
	document.querySelectorAll('.menu-link').forEach((a) => a.addEventListener('click', () => setMenu(false)));
	addEventListener('keydown', (e) => { if (e.key === 'Escape') setMenu(false); });

	// Light, Dark, or the device's own (theme.js applies it before the page draws)
	const themeButtons = document.querySelectorAll('[data-theme-pick]');
	const showTheme = (to) => themeButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themePick === to)));
	let kept = '';
	try { kept = localStorage.getItem('fc.theme') || ''; } catch { /* storage blocked: follow the device */ }
	showTheme(kept === 'light' || kept === 'dark' ? kept : '');
	themeButtons.forEach((b) => b.addEventListener('click', () => {
		const to = b.dataset.themePick;
		if (to) document.documentElement.dataset.theme = to; else delete document.documentElement.dataset.theme;
		try { if (to) localStorage.setItem('fc.theme', to); else localStorage.removeItem('fc.theme'); } catch { /* lasts for this visit */ }
		showTheme(to);
	}));

	// The time zone cookie: the browser's own zone, or "off" for a visitor who chose UK time (then
	// only the choice is kept). The server writes days and times in it.
	const keepZone = (value) => {
		document.cookie = `tz=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax${location.protocol === 'https:' ? '; secure' : ''}`;
	};
	const mine = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
	const ukTime = body.dataset.ukTime === '1';
	document.querySelectorAll('[data-uk-time]').forEach((b) => {
		if (b.tagName !== 'BUTTON') return;
		b.addEventListener('click', () => {
			const uk = b.dataset.ukTime === '1';
			if (uk === ukTime) return;
			keepZone(uk ? 'off' : mine);
			location.reload();
		});
	});
	// The server wrote this page's days and times in the zone it had for this visitor. Tell it the
	// browser's own; where that is a different one, ask for the page again. Not for a visitor who
	// chose UK time.
	if (!ukTime && mine && mine !== body.dataset.tz) { keepZone(mine); location.reload(); return; }

	// A menu of choices, or a date, that loads its choice as soon as it is picked (a league's
	// rounds, the Matches page's day): a date box emptied loads nothing
	document.querySelectorAll('[data-submit-on-change]').forEach((s) => s.addEventListener('change', () => { if (s.value) s.form.requestSubmit(); }));

	// A page's tabs (a club's, a league's): on a phone the row can run wider than the screen, so
	// the tab that's open is brought into view
	document.querySelectorAll('nav.page-tabs').forEach((nav) => {
		const a = nav.querySelector('[aria-current="page"]');
		if (!a) return;
		const box = nav.getBoundingClientRect(), r = a.getBoundingClientRect();
		if (r.left < box.left || r.right > box.right) nav.scrollLeft += r.left - box.left - (box.width - r.width) / 2;
	});

	// A pitch in a club's own kit colours: they can't be classes, so they are set here
	document.querySelectorAll('.pitch[data-kit]').forEach((p) => {
		const [shirt, number] = p.dataset.kit.split(',');
		if (/^[0-9a-f]{6}$/i.test(shirt) && /^[0-9a-f]{6}$/i.test(number)) { p.style.setProperty('--kit', `#${shirt}`); p.style.setProperty('--kit2', `#${number}`); }
	});

	// A link shared from the old site (thecornerfc.com/#/club/42/matches) names its page after a #,
	// which the server never sees: go to the same address here.
	const old = /^#\/(clubs|players|leagues|nations|matches|stats|lineups|fpl|my-fpl-team|efl-fantasy|(?:club|player|league|country|nation)\/[^?#]+)(\?[^#]*)?$/.exec(location.hash);
	if (old) location.replace(`/${old[1].replace(/^((?:club|player|nation)\/[^/]+)\/overview$/, '$1')}${old[2] ?? ''}`);
})();
