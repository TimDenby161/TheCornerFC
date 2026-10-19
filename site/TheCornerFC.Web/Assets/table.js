// The list pages' own script (Clubs, Leagues, Nations; web/src/lib/actions.ts and the Svelte
// FilterMenu, ExcludeChips and Clubs page). Everything here adds to a page the server has already
// drawn whole: without it the menu, Exclude, sorting and search still work as ordinary links and
// forms.
(() => {
	const canHover = matchMedia('(hover: hover)');

	// ---- Column explanations: hover a heading (or reach it with the keyboard) that carries data-tip
	function columnTips(wrap) {
		const tip = Object.assign(document.createElement('div'), { className: 'col-tip', hidden: true });
		tip.setAttribute('role', 'tooltip');
		document.body.appendChild(tip);
		const draw = (h) => {
			tip.textContent = h.dataset.tip;
			tip.hidden = false;
			const b = h.getBoundingClientRect(), w = tip.offsetWidth;
			tip.style.left = `${Math.max(8, Math.min(b.left + b.width / 2 - w / 2, innerWidth - w - 8))}px`;
			tip.style.top = `${b.bottom + 6}px`;
		};
		const show = (e) => {
			// (not on touch screens: a tap sends mouseover too, and the tip would stay up)
			if (e.type === 'mouseover' && !canHover.matches) return;
			const h = e.target.closest('th[data-tip]');
			if (h) draw(h);
		};
		const hide = () => { tip.hidden = true; };
		wrap.addEventListener('mouseover', show);
		wrap.addEventListener('mouseout', (e) => {
			const from = e.target.closest('th[data-tip]');
			if (from && e.relatedTarget?.closest?.('th[data-tip]') !== from) hide();
		});
		wrap.addEventListener('focusin', (e) => { if (e.target.matches?.(':focus-visible')) show(e); });
		wrap.addEventListener('focusout', hide);
		wrap.addEventListener('scroll', hide, true);
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

	// ---- The search narrows the list as it is typed: the server works out the rows (the same as
	// when the form is sent) and the list is swapped in place, with the address following
	document.querySelectorAll('input[data-live-search]').forEach((input) => {
		const form = input.form, target = document.querySelector(input.dataset.liveSearch);
		let typing, asked = 0;
		input.addEventListener('input', () => {
			clearTimeout(typing);
			typing = setTimeout(async () => {
				const q = new URLSearchParams(new FormData(form));
				if (!input.value.trim()) q.delete('q');
				const url = `${form.getAttribute('action')}${q.size ? `?${q}` : ''}`;
				const mine = ++asked;
				try {
					const r = await fetch(url, { headers: { accept: 'text/html' } });
					if (!r.ok) throw new Error(String(r.status));
					const page = new DOMParser().parseFromString(await r.text(), 'text/html');
					if (mine !== asked) return;
					const fresh = page.querySelector(input.dataset.liveSearch);
					if (!fresh) throw new Error('no list');
					target.innerHTML = fresh.innerHTML;
					target.dataset.fitTable = fresh.dataset.fitTable ?? '';
					document.title = page.title;
					history.replaceState(history.state, '', url);
					target.fitAgain?.();
				} catch {
					location.replace(url);
				}
			}, 200);
		});
	});

	document.querySelectorAll('[data-column-tips]').forEach(columnTips);
	document.querySelectorAll('[data-fit-table]').forEach(fitTable);
	document.querySelectorAll('[data-filter-menu]').forEach(filterMenu);
})();
