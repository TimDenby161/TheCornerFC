// The list pages' own script (Clubs, Leagues, Nations, Players; web/src/lib/actions.ts and the
// Svelte FilterMenu, ExcludeChips, Clubs and Players pages). Everything here adds to a page the
// server has already drawn whole: without it the menu, Exclude, sorting and search still work as
// ordinary links and forms.
(() => {
	const canHover = matchMedia('(hover: hover)');

	// ---- Column explanations: hover a heading (or reach it with the keyboard) that carries data-tip.
	// `cellTip` adds tips over cells marked tip-cell: it says what to show now, and `then` when
	// something it is fetching arrives (the tip is drawn again if it is still up).
	function columnTips(wrap, cellTip) {
		const tip = Object.assign(document.createElement('div'), { className: 'col-tip', hidden: true });
		tip.setAttribute('role', 'tooltip');
		document.body.appendChild(tip);
		const sel = cellTip ? 'th[data-tip], td.tip-cell' : 'th[data-tip]';
		let on = null;
		const draw = (h, text) => {
			tip.textContent = text;
			if (!text) return;
			tip.hidden = false;
			on = h;
			const b = h.getBoundingClientRect(), w = tip.offsetWidth;
			tip.style.left = `${Math.max(8, Math.min(b.left + b.width / 2 - w / 2, innerWidth - w - 8))}px`;
			tip.style.top = `${b.bottom + 6}px`;
		};
		const show = (e) => {
			// (not on touch screens: a tap sends mouseover too, and the tip would stay up)
			if (e.type === 'mouseover' && !canHover.matches) return;
			const h = e.target.closest(sel);
			if (!h) return;
			if (h.dataset.tip) { draw(h, h.dataset.tip); return; }
			if (!cellTip || h.tagName !== 'TD') return;
			const said = cellTip(h);
			draw(h, said.text);
			// "Loading…" until it's in, then the text if the tip is still on this cell
			said.then?.then(() => { if (!tip.hidden && on === h && h.isConnected) draw(h, cellTip(h).text); });
		};
		const hide = () => { tip.hidden = true; on = null; };
		wrap.addEventListener('mouseover', show);
		wrap.addEventListener('mouseout', (e) => {
			const from = e.target.closest(sel);
			if (from && e.relatedTarget?.closest?.(sel) !== from) hide();
		});
		wrap.addEventListener('focusin', (e) => { if (e.target.matches?.(':focus-visible')) show(e); });
		wrap.addEventListener('focusout', hide);
		wrap.addEventListener('scroll', hide, true);
	}

	// ---- The Players table's tip over a season's rank: his age that season, then each club he
	// played for with his rank there, minutes, goals and assists (seasonTipText in players.ts).
	// His clubs come from /players/seasons, fetched on the first hover over his row.
	function seasonTipText(age, back, estimated, spells, loaded) {
		if (!loaded) return 'Loading…';
		const ageLine = age != null ? `Age ${age - back}\n` : '';
		if (estimated) {
			const club = spells?.[0] ? `${spells[0][0]} – ${spells[0][1] ?? '–'}\n` : '';
			return `${ageLine}${club}Not in a covered league this season\nEstimated from his other seasons and age`;
		}
		if (!spells?.length) return `${ageLine}No minutes`;
		return ageLine + spells.map(([club, rank, minutes, goals, assists]) => `${club} – ${rank ?? '–'}\n${minutes.toLocaleString('en-GB')} mins – ${goals} G, ${assists} A`).join('\n\n');
	}
	const seasonFiles = new Map();
	function seasonTip(cell) {
		const id = cell.dataset.player, back = Number(cell.dataset.back);
		let f = seasonFiles.get(id);
		if (!f) {
			f = {};
			f.asked = fetch(`/players/seasons?id=${id}`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})).then((d) => { f.data = d; });
			seasonFiles.set(id, f);
		}
		const ageText = cell.closest('tr').querySelector('.col-age')?.textContent.trim() ?? '';
		const age = /^\d+$/.test(ageText) ? Number(ageText) : null;
		const year = (cell.closest('table').dataset.seasons || '').split(',')[back];
		return { text: seasonTipText(age, back, !!cell.querySelector('.est'), f.data?.[year], !!f.data), then: f.data ? undefined : f.asked };
	}

	// ---- The club tables: each club one line. Where a name would be cut short, drop the league and
	// keep just the flag; where it still would be, use the club's short name (data-short); past that
	// it ends in "…" with the full name on hover. A list that spans leagues ("capped") sits in a box
	// no taller than the window, never showing fewer than its first ten rows.
	const TOP_ROWS = 10;
	function fitTable(wrap) {
		const capped = () => wrap.dataset.fitTable === 'capped';
		function fitNames() {
			const names = [...wrap.querySelectorAll('table.clubs .club-cell > .team-link')];
			for (const a of names) {
				a.parentElement.classList.remove('flag-only');
				if (a.dataset.full) { a.textContent = a.dataset.full; delete a.dataset.full; }
				a.removeAttribute('title');
			}
			const cutShort = (a) => a.scrollWidth > a.clientWidth;
			const cut = names.filter(cutShort);
			for (const a of cut) a.parentElement.classList.add('flag-only');
			for (const a of cut.filter(cutShort)) {
				const full = a.textContent || '';
				if (a.dataset.short) { a.dataset.full = full; a.textContent = a.dataset.short; }
				a.title = full;
			}
		}
		function fitRows() {
			const box = wrap.querySelector('.table-scroll');
			if (!box) return;
			const rows = box.querySelectorAll('tbody tr');
			if (!capped() || rows.length <= TOP_ROWS) { box.style.maxHeight = 'none'; return; }
			let minH = box.querySelector('thead').offsetHeight;
			for (let i = 0; i < TOP_ROWS; i++) minH += rows[i].offsetHeight;
			const room = innerHeight - box.getBoundingClientRect().top - 12;
			box.style.maxHeight = `${Math.max(minH + 2, room)}px`;
		}
		// again whenever the table's width changes, not only the window's
		let width = -1;
		const seen = new ResizeObserver((entries) => {
			const w = Math.round(entries[0].contentRect.width);
			if (w === width) return;
			width = w;
			fitNames();
		});
		const again = () => { width = -1; fitNames(); fitRows(); const box = wrap.querySelector('.table-scroll'); seen.disconnect(); if (box) seen.observe(box); };
		again();
		addEventListener('resize', fitRows);
		wrap.fitAgain = again;
	}

	// ---- The country / league menu: on a narrow screen behind a button naming the selection; on a
	// wide one a group opens after a short hover. Picking a group keeps the menu open to go further
	// in; anything else closes it (the form then loads the choice).
	function filterMenu(wrap) {
		const trigger = wrap.querySelector('.menu-trigger'), groups = wrap.querySelector('.cgroups');
		const setOpen = (open) => { wrap.classList.toggle('menu-open', open); trigger.setAttribute('aria-expanded', String(open)); };
		trigger.addEventListener('click', () => setOpen(!wrap.classList.contains('menu-open')));
		document.addEventListener('click', (e) => { if (wrap.classList.contains('menu-open') && !wrap.contains(e.target)) setOpen(false); });
		wrap.querySelectorAll('button[name]').forEach((b) => b.addEventListener('click', () => { if (!b.dataset.group) setOpen(false); }));
		let timer;
		wrap.querySelectorAll('.cgroup').forEach((g) => g.addEventListener('mouseenter', () => {
			if (!canHover.matches) return;
			clearTimeout(timer);
			timer = setTimeout(() => g.classList.add('hover-open'), 150);
		}));
		groups.addEventListener('mouseleave', () => {
			clearTimeout(timer);
			timer = setTimeout(() => wrap.querySelectorAll('.hover-open').forEach((g) => g.classList.remove('hover-open')), 300);
		});
	}

	// ---- Exclude: its chips open under the menu
	const more = document.getElementById('more-filters'), side = document.getElementById('table-side');
	more?.addEventListener('click', () => {
		const open = !side.classList.contains('filters-open');
		side.classList.toggle('filters-open', open);
		more.setAttribute('aria-expanded', String(open));
	});

	// ---- A row opens its club's page, wherever on it the click lands
	document.addEventListener('click', (e) => {
		const row = e.target.closest('tr[data-href]');
		if (row && !e.target.closest('a')) location.href = row.dataset.href;
	});

	// ---- The rest of a long list's rows arrive 100 at a time as its bottom scrolls into view, so
	// thousands of rows are never drawn at once: the server sends them as table rows, for the
	// page's own address with ?offset=
	function moreRows(wrap) {
		const sentinel = wrap.querySelector('[data-more-rows]');
		if (!sentinel) return;
		const box = sentinel.closest('.table-scroll'), body = box.querySelector('tbody'), total = Number(sentinel.dataset.total);
		let busy = false;
		const seen = new IntersectionObserver(async (entries) => {
			if (busy || !entries.some((e) => e.isIntersecting)) return;
			busy = true;
			const key = location.search, at = body.rows.length;
			try {
				const q = new URLSearchParams(location.search);
				q.set('offset', String(at));
				const r = await fetch(`${sentinel.dataset.moreRows}?${q}`);
				if (!r.ok) return;
				const rows = document.createElement('template');
				rows.innerHTML = await r.text();
				// (a list that has changed meanwhile keeps its own rows)
				if (location.search !== key || body.rows.length !== at || !sentinel.isConnected) return;
				const got = rows.content.querySelectorAll('tr').length;
				body.append(rows.content);
				if (!got || body.rows.length >= total) { seen.disconnect(); sentinel.remove(); return; }
			} catch { /* the list stays as it is; scrolling again asks again */ } finally { busy = false; }
			seen.unobserve(sentinel); seen.observe(sentinel); // still in view: load again
		}, { root: getComputedStyle(box).maxHeight === 'none' ? null : box, rootMargin: '0px 0px 600px 0px' });
		seen.observe(sentinel);
	}

	// ---- A new choice: the server draws the page for it (the same as following the link) and its
	// list, and the parts the section names in data-swap, are swapped in place, with the address
	// following. The React parts are handed their new props. The rest of the page (an open menu, a
	// box being typed in, where it is scrolled to) stays as it is.
	const section = document.querySelector('section[data-swap]');
	let asked = 0;
	async function swapTo(url, { target = '#table-wrap', history: how = 'replace' } = {}) {
		const mine = ++asked;
		try {
			const r = await fetch(url, { headers: { accept: 'text/html' } });
			if (!r.ok) throw new Error(String(r.status));
			const page = new DOMParser().parseFromString(await r.text(), 'text/html');
			if (mine !== asked) return;
			const wrap = document.querySelector(target), fresh = page.querySelector(target);
			if (!wrap || !fresh) throw new Error('no list');
			wrap.innerHTML = fresh.innerHTML;
			wrap.dataset.fitTable = fresh.dataset.fitTable ?? '';
			for (const id of (section?.dataset.swap || '').split(' ').filter(Boolean)) {
				const old = document.getElementById(id), now = page.getElementById(id);
				if (!old || !now) continue;
				old.replaceWith(now);
				if (now.matches('[data-filter-menu]')) filterMenu(now);
			}
			for (const el of page.querySelectorAll('[data-island][id]')) {
				const props = el.querySelector(':scope > script[type="application/json"]');
				if (props) document.getElementById(el.id)?.dispatchEvent(new CustomEvent('island-props', { detail: JSON.parse(props.textContent || '{}') }));
			}
			const search = document.getElementById('table-search'), typed = page.getElementById('table-search');
			if (search && typed && document.activeElement !== search) search.value = typed.value;
			document.title = page.title;
			if (how === 'push') history.pushState({ swapped: true }, '', url);
			else if (how === 'replace') history.replaceState({ swapped: true }, '', url);
			wrap.fitAgain?.();
			moreRows(wrap);
		} catch {
			location.assign(url);
		}
	}
	const address = (q) => { for (const [k, v] of [...q]) if (!v) q.delete(k); return `${location.pathname}${q.size ? `?${q}` : ''}`; };

	// The search narrows the list as it is typed
	document.querySelectorAll('input[data-live-search]').forEach((input) => {
		let typing;
		input.addEventListener('input', () => {
			clearTimeout(typing);
			typing = setTimeout(() => {
				const form = input.form, q = new URLSearchParams(new FormData(form));
				if (!input.value.trim()) q.delete('q');
				swapTo(`${form.getAttribute('action')}${q.size ? `?${q}` : ''}`, { target: input.dataset.liveSearch });
			}, 200);
		});
	});
	if (section?.matches('[data-swap-forms]')) {
		// the menu, Exclude and the position pitch: forms whose button carries the choice
		section.addEventListener('submit', (e) => {
			const form = e.target;
			if (form.method !== 'get') return;
			e.preventDefault();
			swapTo(address(new URLSearchParams(new FormData(form, e.submitter))), { history: 'push' });
		});
		// a choice made in a React part ({key: value}, null to drop it), as the address has it
		document.addEventListener('choose', (e) => {
			const q = new URLSearchParams(location.search);
			for (const [k, v] of Object.entries(e.detail)) if (v == null || v === '') q.delete(k); else q.set(k, v);
			swapTo(address(q));
		});
		addEventListener('popstate', () => swapTo(location.href, { history: 'none' }));
	}

	// ---- The Matches page: a competition's (or a day's) matches fold away under its name
	document.querySelectorAll('.comp-group-header').forEach((h) => {
		const fold = () => {
			const closed = h.parentElement.classList.toggle('collapsed');
			h.setAttribute('aria-expanded', String(!closed));
			h.querySelector('.comp-group-caret').textContent = closed ? '▸' : '▾';
		};
		h.addEventListener('click', fold);
		h.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fold(); } });
	});

	document.querySelectorAll('[data-column-tips]').forEach((wrap) => columnTips(wrap, wrap.matches('[data-season-tips]') ? seasonTip : undefined));
	document.querySelectorAll('[data-fit-table]').forEach(fitTable);
	document.querySelectorAll('[data-filter-menu]').forEach(filterMenu);
	document.querySelectorAll('#table-wrap').forEach(moreRows);
})();
