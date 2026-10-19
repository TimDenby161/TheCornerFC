import { useEffect, useRef, useState, type ChangeEvent } from 'react';
import { handlesRange, rangeLabel, rangeText, type RangeKey } from '../../../web/src/lib/playerFilters.ts';
import { choose } from './choose.ts';

export type SliderProps = { kind: RangeKey; name: string; stops: number[]; a: number; b: number; ids?: [string, string] | null };

// A two-handled slider over a list of stops (DualRange.svelte). A handle at either end leaves that
// end open. The handles and the words beside the name move straight away; the page is told the
// range once the handle has settled (or is let go).
export function DualRange({ kind, name, stops, a: fromA, b: fromB, ids }: SliderProps) {
	// where the server drew the handles, then wherever they are dragged; new props move them
	const [a, setA] = useState(fromA), [b, setB] = useState(fromB);
	useEffect(() => { setA(fromA); setB(fromB); }, [fromA, fromB]);
	const n = stops.length - 1;
	const at = (i: number) => Math.round((i / (n || 1)) * 100);

	const settle = useRef<ReturnType<typeof setTimeout>>(undefined);
	const from = useRef<HTMLInputElement>(null), to = useRef<HTMLInputElement>(null);
	const tell = (x: number, y: number) => { clearTimeout(settle.current); choose({ [kind]: rangeText(handlesRange(stops, x, y)) }); };
	// handles can't cross
	function moved(end: 0 | 1, e: ChangeEvent<HTMLInputElement>) {
		const v = Number(e.currentTarget.value);
		const x = end === 0 ? Math.min(v, b) : a, y = end === 1 ? Math.max(v, a) : b;
		if (x === a && y === b) return; // (React also calls this on letting go, which the listener below tells)
		setA(x); setB(y);
		clearTimeout(settle.current);
		settle.current = setTimeout(() => tell(x, y), 250);
	}
	// let go: told at once
	useEffect(() => {
		const done = () => tell(Number(from.current!.value), Number(to.current!.value));
		const els = [from.current!, to.current!];
		for (const el of els) el.addEventListener('change', done);
		return () => { for (const el of els) el.removeEventListener('change', done); };
	});

	return (
		<>
			<div className="age-head"><span>{name}</span><span className="rng-val">{rangeLabel(kind, stops, a, b)}</span></div>
			<div className="age-slider">
				<div className="age-track"><div className={`age-fill sx-${at(a)} sr-${100 - at(b)}`}></div></div>
				<input ref={from} type="range" min="0" max={n} step="1" value={a} id={ids?.[0]} aria-label={`${name}: from`} onChange={(e) => moved(0, e)} />
				<input ref={to} type="range" min="0" max={n} step="1" value={b} id={ids?.[1]} aria-label={`${name}: to`} onChange={(e) => moved(1, e)} />
			</div>
		</>
	);
}

// Ability, club world rank and minutes, with a Clear for all three
export function PlayerRanges({ ranges }: { ranges: { slider: SliderProps; tip: string }[] }) {
	const on = ranges.some(({ slider: s }) => rangeText(handlesRange(s.stops, s.a, s.b)));
	return (
		<>
			<div className="pos-head"><span>Ranges</span>
				<button type="button" className="pos-clear" hidden={!on} onClick={() => choose(Object.fromEntries(ranges.map((r) => [r.slider.kind, null])))}>Clear</button></div>
			{ranges.map((r) => (
				<div className="rng-row" title={r.tip} key={r.slider.kind}><DualRange {...r.slider} /></div>
			))}
		</>
	);
}
