// Home's carousel (the Svelte site's +page.svelte): a slide for each part of the site, turning every
// ten seconds, by swipe or by its name under the slides. The server drew every slide; this turns
// them, adds the example line-up once it arrives (/home/xi), and counts the headline's number up.
(() => {
	const hero = document.querySelector('.home-hero');
	if (!hero) return;
	const box = hero.querySelector('.home-slides'), turn = hero.querySelector('.home-turn'), list = hero.querySelector('.home-turn-list');
	const slides = () => [...box.children];
	const buttons = () => [...list.children];
	let upKey = 'clubs'; // the slide that's up, by name (a slide that arrives late can join to its left)
	const up = () => Math.max(0, slides().findIndex((s) => s.dataset.slide === upKey));
	const left = (i) => slides()[i].offsetLeft - box.firstElementChild.offsetLeft;
	const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

	// the slide that's up is the only one that can be reached, and its name carries the rule that fills
	function mark() {
		const i = up();
		slides().forEach((s, k) => { s.inert = k !== i; });
		buttons().forEach((b, k) => { if (k === i) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current'); });
	}
	function slideTo(i, slid = !still()) {
		upKey = slides()[i].dataset.slide;
		mark();
		if (slid) box.scrollTo({ left: left(i), behavior: 'smooth' }); else box.scrollLeft = left(i);
	}
	list.addEventListener('click', (e) => {
		const b = e.target.closest('button');
		if (b) slideTo(buttons().indexOf(b));
	});
	// the rule over the name of the slide that's up fills as its ten seconds pass (the stylesheet's
	// home-fill is the clock): when it ends, the next slide comes up
	list.addEventListener('animationend', (e) => { if (e.animationName === 'home-fill') slideTo((up() + 1) % slides().length); });
	// a swipe (or any scroll of the slides) that comes to rest on another slide makes that one the one that's up
	let rest;
	box.addEventListener('scroll', () => {
		clearTimeout(rest);
		rest = setTimeout(() => {
			const x = box.scrollLeft;
			let near = 0;
			for (let i = 1; i < slides().length; i++) if (Math.abs(left(i) - x) < Math.abs(left(near) - x)) near = i;
			if (near !== up()) { upKey = slides()[near].dataset.slide; mark(); }
		}, 120);
	});
	// on a phone or a tablet the clock stops while the slides' rules are scrolled off the screen
	new IntersectionObserver(([e]) => hero.classList.toggle('home-turn-away', !e.isIntersecting)).observe(turn);

	// the example line-up, which the server doesn't wait for: in its place after Matches
	fetch('/home/xi').then((r) => (r.ok && r.status !== 204 ? r.text() : '')).then((html) => {
		if (!html) return;
		const slide = new DOMParser().parseFromString(html, 'text/html').body.firstElementChild;
		if (!slide) return;
		const after = slides().find((s) => s.dataset.slide === 'stats' || s.dataset.slide === 'leagues' || s.dataset.slide === 'nations');
		box.insertBefore(slide, after ?? null);
		const b = Object.assign(document.createElement('button'), { type: 'button' });
		b.dataset.slide = 'lineups';
		b.append(Object.assign(document.createElement('span'), { textContent: 'Line-ups' }));
		list.insertBefore(b, buttons()[slides().indexOf(slide)] ?? null);
		turn.hidden = slides().length < 2;
		mark();
		box.scrollLeft = left(up());
		// its pitch in the club's colours, as the page's script does for the pitches it drew
		slide.querySelectorAll('.pitch[data-kit]').forEach((p) => {
			const [shirt, number] = p.dataset.kit.split(',');
			if (/^[0-9a-f]{6}$/i.test(shirt) && /^[0-9a-f]{6}$/i.test(number)) { p.style.setProperty('--kit', `#${shirt}`); p.style.setProperty('--kit2', `#${number}`); }
		});
	}).catch(() => {});

	// the headline's number, counted up to once; left as the server wrote it where motion is turned down
	const count = hero.querySelector('[data-count-to]');
	if (count && !still()) {
		const n = Number(count.dataset.countTo), from = performance.now();
		requestAnimationFrame(function step(now) {
			const t = Math.min(1, (now - from) / 1100);
			count.textContent = Math.round(n * (1 - (1 - t) ** 3)).toLocaleString('en-GB');
			if (t < 1) requestAnimationFrame(step);
		});
	}
})();
