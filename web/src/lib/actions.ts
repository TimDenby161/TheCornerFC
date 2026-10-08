// Things a table does once it is on the page, which need measuring or the pointer.

// A page's tabs (a club's, a player's, a league's, a nation's): on a phone the row can run wider
// than the screen, so the tab that's open is brought into view, on arrival and on each move
// between tabs. `_path`: the address, so the action runs again when it changes.
export function currentInView(nav: HTMLElement, _path: string) {
	const show = () => {
		const a = nav.querySelector<HTMLElement>('[aria-current="page"]');
		if (!a) return;
		const box = nav.getBoundingClientRect(), r = a.getBoundingClientRect();
		if (r.left < box.left || r.right > box.right) nav.scrollLeft += r.left - box.left - (box.width - r.width) / 2;
	};
	show();
	return { update() { requestAnimationFrame(show); } };
}

// Column explanations: hover a heading (or reach it with the keyboard) that carries data-tip.
// `cellTip`: for a table whose cells have tips too (td.tip-cell): what one says, and, where that
// has to be fetched first, a promise that ends when it can be asked again.
export type CellTip = (cell: HTMLElement) => { text: string; then?: Promise<unknown> };
export function columnTips(wrap: HTMLElement, cellTip?: CellTip) {
	const tip = Object.assign(document.createElement('div'), { className: 'col-tip', hidden: true });
	tip.setAttribute('role', 'tooltip');
	document.body.appendChild(tip);
	const canHover = matchMedia('(hover: hover)');
	const sel = cellTip ? 'th[data-tip], td.tip-cell' : 'th[data-tip]';
	let on: HTMLElement | null = null;
	const draw = (h: HTMLElement, text: string) => {
		tip.textContent = text;
		if (!text) return;
		tip.hidden = false;
		on = h;
		const b = h.getBoundingClientRect(), w = tip.offsetWidth;
		tip.style.left = `${Math.max(8, Math.min(b.left + b.width / 2 - w / 2, innerWidth - w - 8))}px`;
		tip.style.top = `${b.bottom + 6}px`;
	};
	const show = (e: Event) => {
		// (not on touch screens: a tap sends mouseover too, and the tip would stay up)
		if (e.type === 'mouseover' && !canHover.matches) return;
		const h = (e.target as HTMLElement).closest<HTMLElement>(sel);
		if (!h) return;
		if (h.dataset.tip) { draw(h, h.dataset.tip); return; }
		if (!cellTip || h.tagName !== 'TD') return;
		const said = cellTip(h);
		draw(h, said.text);
		// "Loading…" until it's in, then the text if the tip is still on this cell
		said.then?.then(() => { if (!tip.hidden && on === h && h.isConnected) draw(h, cellTip(h).text); });
	};
	const hide = () => { tip.hidden = true; on = null; };
	const out = (e: MouseEvent) => {
		const from = (e.target as HTMLElement).closest(sel);
		if (from && (e.relatedTarget as HTMLElement | null)?.closest?.(sel) !== from) hide();
	};
	const focus = (e: FocusEvent) => { if ((e.target as HTMLElement).matches?.(':focus-visible')) show(e); };
	wrap.addEventListener('mouseover', show);
	wrap.addEventListener('mouseout', out);
	wrap.addEventListener('focusin', focus);
	wrap.addEventListener('focusout', hide);
	wrap.addEventListener('scroll', hide, true);
	return { destroy() { tip.remove(); } };
}

// The Clubs and Players tables. On Clubs, each club is one line (name, flag, league), so every row is the same height:
// where the name would be cut short, drop the league and keep just the flag; where it still would
// be, use the club's short name if it has one (data-short); past that it ends in "…" (the full
// name on hover). And a list that spans leagues sits in a box no taller than the window, never
// showing fewer than its first ten rows. `capped`: whether the list is one of those.
const TOP_ROWS = 10;
export function fitTable(wrap: HTMLElement, capped: boolean) {
	function fitNames() {
		const names = [...wrap.querySelectorAll<HTMLElement>('table.clubs .club-cell > .team-link')];
		for (const a of names) {
			a.parentElement!.classList.remove('flag-only');
			if (a.dataset.full) { a.textContent = a.dataset.full; delete a.dataset.full; }
			a.removeAttribute('title');
		}
		const cutShort = (a: HTMLElement) => a.scrollWidth > a.clientWidth;
		const cut = names.filter(cutShort);
		for (const a of cut) a.parentElement!.classList.add('flag-only');
		for (const a of cut.filter(cutShort)) {
			const full = a.textContent || '';
			if (a.dataset.short) { a.dataset.full = full; a.textContent = a.dataset.short; }
			a.title = full;
		}
	}
	function fitRows() {
		const box = wrap.querySelector<HTMLElement>('.table-scroll');
		if (!box) return;
		const rows = box.querySelectorAll<HTMLElement>('tbody tr');
		if (!capped || rows.length <= TOP_ROWS) { box.style.maxHeight = 'none'; return; }
		let minH = box.querySelector('thead')!.offsetHeight;
		for (let i = 0; i < TOP_ROWS; i++) minH += rows[i].offsetHeight;
		const room = window.innerHeight - box.getBoundingClientRect().top - 12;
		box.style.maxHeight = `${Math.max(minH + 2, room)}px`;
	}
	// again whenever the table's width changes, not only the window's (a scrollbar appearing once
	// the rows are in, the side menu, a split-screen pane)
	let width = -1;
	const seen = new ResizeObserver((entries) => {
		const w = Math.round(entries[0].contentRect.width);
		if (w === width) return; // only its height changed
		width = w;
		fitNames();
	});
	// Players with the other seasons open: the box widens to the right, as far as the window allows
	// (16px short of its edge), to fit the extra columns, and the search box above widens with it;
	// their left edges and the page don't move
	function fitYears() {
		const box = wrap.querySelector<HTMLElement>('.table-scroll'), search = document.querySelector<HTMLElement>('#table-search');
		if (search) search.style.width = '';
		if (!box) return;
		box.style.width = '';
		const table = box.querySelector<HTMLTableElement>('table.players.years');
		if (!table) return;
		const room = document.documentElement.clientWidth - box.getBoundingClientRect().left - 16;
		const need = table.scrollWidth + box.offsetWidth - box.clientWidth; // plus its borders
		if (need > box.offsetWidth) { box.style.width = `${Math.max(box.offsetWidth, Math.min(need, room))}px`; if (search) search.style.width = box.style.width; }
		// #, Player, Pos and Age stay put when it scrolls sideways: each column's left edge, for the
		// stylesheet (summed widths: a sticky cell's offsetLeft moves as it sticks)
		let left = 0;
		[...table.tHead!.rows[0].cells].slice(0, 4).forEach((c, i) => {
			table.style.setProperty(`--fz${i + 1}`, `${left}px`);
			left += c.getBoundingClientRect().width;
		});
	}
	const again = () => { fitNames(); fitRows(); fitYears(); const box = wrap.querySelector('.table-scroll'); seen.disconnect(); if (box) seen.observe(box); };
	again();
	const resized = () => { fitRows(); fitYears(); };
	window.addEventListener('resize', resized);
	return {
		update(now: boolean) { capped = now; width = -1; again(); },
		destroy() { seen.disconnect(); window.removeEventListener('resize', resized); }
	};
}

// A fantasy table over several gameweeks: # and Player stay put when it scrolls sideways, and
// Player's left edge is #'s width (--fz2 in the stylesheet), measured once the table is drawn.
export function frozenColumns(table: HTMLTableElement) {
	const set = () => { const first = table.tHead?.rows[0]?.cells[0]; if (first) table.style.setProperty('--fz2', `${first.getBoundingClientRect().width}px`); };
	set();
	const watch = new ResizeObserver(set);
	watch.observe(table);
	return { destroy: () => watch.disconnect() };
}
