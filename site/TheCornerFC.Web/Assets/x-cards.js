// The X page's cards (/admin/posts): each canvas draws the figures the server put in its data-card
// at 1200x675, saved at twice that, for the administrator to copy or download and add to a post.
(() => {
	const W = 1200, H = 675, LEFT = 72, RIGHT = W - 72;
	const C = { pitch: '#0e3b29', chalk: '#f4f5ef', t2: '#c9d4c9', t3: '#9fb3a6', line: '#2c5a46',
		home: '#3987e5', draw: '#5f7a6c', away: '#d95926', up: '#5cc08c', down: '#f07878' };

	function text(g, s, x, y, size, weight, color, align = 'left') {
		g.font = `${weight} ${size}px Archivo, sans-serif`;
		g.fillStyle = color;
		g.textAlign = align;
		g.fillText(s, x, y);
	}
	function rule(g, x1, y, x2, color, width = 1) {
		g.fillStyle = color;
		g.fillRect(x1, y, x2 - x1, width);
	}
	// words broken to fit the width, one array entry a line
	function lines(g, s, width) {
		const out = [];
		let line = '';
		for (const word of s.split(' ')) {
			const next = line ? `${line} ${word}` : word;
			if (line && g.measureText(next).width > width) { out.push(line); line = word; }
			else line = next;
		}
		return [...out, line];
	}

	// the frame every card shares; answers how far down its heading reaches
	function frame(g, card) {
		g.fillStyle = C.pitch;
		g.fillRect(0, 0, W, H);
		g.fillStyle = C.chalk;
		g.fill(new Path2D('M1171 20 1127 36l44 16z'));
		g.fillRect(1170, 20, 3, 62);
		text(g, card.kicker.toUpperCase(), LEFT, 76, 20, 700, C.t3);
		// a long heading comes down in size before it takes a second line
		const room = RIGHT - LEFT - 60;
		let size = 46;
		for (; size > 36; size -= 2) {
			g.font = `800 ${size}px Archivo, sans-serif`;
			if (g.measureText(card.title).width <= room) break;
		}
		g.font = `800 ${size}px Archivo, sans-serif`;
		let y = 130;
		for (const line of lines(g, card.title, room)) { text(g, line, LEFT, y, size, 800, C.chalk); y += size + 4; }
		rule(g, LEFT, H - 76, RIGHT, C.chalk, 2);
		text(g, 'THECORNERFC.COM', LEFT, H - 44, 18, 800, C.chalk);
		text(g, card.foot, RIGHT, H - 44, 18, 400, C.t2, 'right');
		return y - 20;
	}

	const bodies = {
		stats(g, card, top) {
			const gap = 40, width = (RIGHT - LEFT - gap * 2) / 3;
			card.stats.forEach((s, i) => {
				const x = LEFT + i * (width + gap);
				rule(g, x, top + 34, x + width, C.chalk, 2);
				text(g, s.value, x, top + 136, 88, 800, C.chalk);
				g.font = '400 21px Archivo, sans-serif';
				lines(g, s.label, width).forEach((l, k) => text(g, l, x, top + 176 + k * 28, 21, 400, C.t2));
			});
			if (card.note) text(g, card.note, LEFT, H - 104, 24, 400, C.chalk);
		},
		chances(g, card, top) {
			const key = [['Home win', C.home], ['Draw', C.draw], ['Away win', C.away]];
			let x = LEFT;
			for (const [name, color] of key) {
				g.fillStyle = color;
				g.fillRect(x, top + 4, 14, 14);
				text(g, name, x + 22, top + 17, 17, 400, C.t2);
				x += 140;
			}
			const bar = [430, 800], row = Math.min(40, (H - 96 - top - 34) / card.matches.length);
			card.matches.forEach((m, i) => {
				const y = top + 34 + i * row, mid = y + 26;
				text(g, m.when, LEFT, mid, 16, 400, C.t3);
				text(g, m.home, bar[0] - 14, mid, 20, 700, C.chalk, 'right');
				text(g, m.away, bar[1] + 14, mid, 20, 700, C.chalk);
				let at = bar[0];
				for (const [share, color] of [[m.h, C.home], [m.d, C.draw], [m.a, C.away]]) {
					const width = (bar[1] - bar[0]) * share / 100;
					g.fillStyle = color;
					g.fillRect(at, y + 7, width - 2, 28);
					if (share >= 10) text(g, `${share}%`, at + width / 2, mid, 16, 700, '#fff', 'center');
					at += width;
				}
			});
		},
		movers(g, card, top) {
			const row = (H - 96 - top - 10) / card.movers.length, zero = 640;
			const most = Math.max(...card.movers.map(m => Math.abs(m.change)), 1), reach = 300 / most;
			rule(g, zero, top + 10, zero + 1, C.t3, H - 96 - top - 10);
			card.movers.forEach((m, i) => {
				const y = top + 10 + i * row, size = Math.min(17, row - 4), mid = y + row / 2 + size / 3;
				const width = Math.abs(m.change) * reach;
				text(g, m.name, LEFT, mid, size, 700, C.chalk);
				g.fillStyle = m.change >= 0 ? C.up : C.down;
				g.fillRect(m.change >= 0 ? zero : zero - width, y + 3, width, row - 6);
				const sign = m.change > 0 ? '+' : m.change < 0 ? '−' : '';
				text(g, `${sign}${Math.abs(m.change)}`, RIGHT, mid, size, 800, C.chalk, 'right');
			});
		},
		ranked(g, card, top) {
			const row = Math.min(42, (H - 96 - top - 24) / card.clubs.length);
			const low = Math.min(...card.clubs.map(c => c.rating)), high = Math.max(...card.clubs.map(c => c.rating));
			const scale = [560, 1010], at = v => scale[0] + (v - low) / Math.max(high - low, 1) * (scale[1] - scale[0]);
			rule(g, LEFT, top + 24, RIGHT, C.chalk, 2);
			card.clubs.forEach((c, i) => {
				const y = top + 24 + i * row, mid = y + row / 2 + 7;
				text(g, String(i + 1), LEFT, mid, 20, 400, C.t3);
				text(g, c.name, LEFT + 44, mid, 22, 700, C.chalk);
				const width = g.measureText(c.name).width;
				text(g, c.comp, LEFT + 56 + width, mid, 16, 400, C.t2);
				rule(g, scale[0], y + row / 2, scale[1], C.line);
				g.fillStyle = C.home;
				g.beginPath();
				g.arc(at(c.rating), y + row / 2, 9, 0, Math.PI * 2);
				g.fill();
				text(g, c.rating.toLocaleString('en-GB'), RIGHT, mid, 26, 800, C.chalk, 'right');
				rule(g, LEFT, y + row - 1, RIGHT, C.line);
			});
		},
	};

	function draw(canvas) {
		const card = JSON.parse(canvas.dataset.card), g = canvas.getContext('2d');
		g.setTransform(2, 0, 0, 2, 0, 0);
		bodies[card.kind](g, card, frame(g, card));
	}
	const png = canvas => new Promise(done => canvas.toBlob(done, 'image/png'));

	document.querySelectorAll('.xp').forEach(post => {
		const canvas = post.querySelector('canvas'), said = post.querySelector('.xp-said');
		post.querySelector('[data-copy]').addEventListener('click', async () => {
			try {
				await navigator.clipboard.write([new ClipboardItem({ 'image/png': png(canvas) })]);
				said.textContent = 'Card copied: paste it into the post.';
			} catch { said.textContent = 'Could not copy here: use Download card.'; }
		});
		const save = post.querySelector('[data-save]');
		save.addEventListener('click', async () => {
			const link = document.createElement('a');
			link.href = URL.createObjectURL(await png(canvas));
			link.download = `thecorner-${save.dataset.save}.png`;
			link.click();
			URL.revokeObjectURL(link.href);
		});
	});
	const fonts = ['700 20px Archivo', '800 46px Archivo', '400 18px Archivo'].map(f => document.fonts.load(f));
	Promise.allSettled(fonts).then(() => document.querySelectorAll('.xp-card').forEach(draw));
})();
