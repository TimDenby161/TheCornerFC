import { useLayoutEffect, useRef } from 'react';
import { rankTier } from '../../../web/src/lib/club.ts';
import type { Spot } from '../../../web/src/lib/lineups.ts';

// An eleven on a pitch (XiPitch.svelte): keeper at the top, attacking down. Each spot is the
// player's rank over his name, then his chance of starting and expected minutes (a predicted XI)
// or his position (the XI that started). A started XI marked against the prediction is ringed
// green where he was predicted and red where not, with the model's pick instead under a miss. In
// the club's home kit colours where its file has them.
// start chance colour: 80%+ green, 60-80 yellow, 40-60 orange, under 40 red
const startTier = (c: number) => (c >= 80 ? 4 : c >= 60 ? 3 : c >= 40 ? 2 : 1);
const cls = (s: Spot) => (s.predicted != null ? `xi-mark ${s.predicted ? 'xi-hit' : 'xi-miss'}` : `sq-${s.chance != null ? startTier(s.chance) : rankTier(s.rank ?? 0)}`);

export function XiPitch({ spots, kit = null, ranks = true }: { spots: Spot[]; kit?: string[] | null; ranks?: boolean }) {
	const pitch = useRef<HTMLDivElement>(null);
	// the colours are the club's own, so they can't be classes: set here (the page's rules allow it)
	useLayoutEffect(() => {
		if (!kit || !pitch.current) return;
		pitch.current.style.setProperty('--kit', `#${kit[0]}`);
		pitch.current.style.setProperty('--kit2', `#${kit[1]}`);
	}, [kit]);
	return (
		<div ref={pitch} className={`pitch pp-pitch${kit ? ' kit' : ''}`}>
			<svg viewBox="0 0 68 88" preserveAspectRatio="none" aria-hidden="true" fill="none" stroke="rgba(255,255,255,0.16)" strokeWidth="0.6">
				<rect x="3" y="3" width="62" height="82" rx="1" /><line x1="3" y1="44" x2="65" y2="44" />
				<circle cx="34" cy="44" r="7" /><rect x="17" y="3" width="34" height="12" /><rect x="26" y="3" width="16" height="5" />
				<rect x="17" y="73" width="34" height="12" /><rect x="26" y="80" width="16" height="5" /></svg>
			{spots.map((s) => (
				<a key={s.id} className={`pp-spot xi-spot ${cls(s)} sx-${s.x} sy-${s.y}`} href={`/player/${s.id}`} title={s.tip}>
					{ranks && <span className={`pp-rank rk-${rankTier(s.rank ?? 0)}`}>{s.rank == null ? '–' : Math.round(s.rank)}</span>}<span className="pp-name">{s.name}</span>
					{s.chance != null || s.mins != null
						? <span className="pp-meta">{s.chance != null && <span className={`sc-${startTier(s.chance)}`}>{s.chance}%</span>}{s.chance != null && s.mins != null ? ' · ' : ''}{s.mins != null ? `${s.mins}′` : ''}</span>
						: <span className="pp-meta">{s.label}</span>}
					{s.instead && <span className="pp-instead"><span className="pp-instead-name">{s.instead.name}</span><span className={`pp-instead-rank rk-${rankTier(s.instead.rank ?? 0)}`}>{s.instead.rank == null ? '–' : Math.round(s.instead.rank)}</span></span>}
				</a>
			))}
		</div>
	);
}
