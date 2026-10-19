import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from 'react';
import { chartLayout, type ChartPoint } from '../../../web/src/lib/player.ts';

// Season ranks as a line, drawn to the width of its box so the text stays readable on phones (the
// server drew it 640 wide). Pointing at it shows the nearest season's rank. (RankChart.svelte.)
export function RankChart({ points, name }: { points: ChartPoint[]; name: string }) {
	const svg = useRef<SVGSVGElement>(null);
	const tip = useRef<HTMLDivElement>(null);
	const [width, setWidth] = useState(640);
	const [at, setAt] = useState<number | null>(null);
	const c = chartLayout(points, width);
	const few = points.length <= 8;

	useLayoutEffect(() => {
		const el = svg.current?.parentElement; // the server's .chart-wrap, which React now fills
		if (!el) return;
		setWidth(el.clientWidth);
		const seen = new ResizeObserver((entries) => setWidth(Math.round(entries[0].contentRect.width)));
		seen.observe(el);
		return () => seen.disconnect();
	}, []);
	// the tip sits over its point, kept inside the box
	useEffect(() => {
		const t = tip.current;
		if (at == null || !t) return;
		const cx = c.x(at), cy = c.y(points[at].v), tw = t.offsetWidth;
		t.style.left = `${Math.min(Math.max(cx - tw / 2, 0), width - tw)}px`;
		t.style.top = `${Math.max(0, cy - t.offsetHeight - 12)}px`;
	});
	function show(e: PointerEvent<SVGRectElement>) {
		const rect = e.currentTarget.getBoundingClientRect();
		const px = ((e.clientX - rect.left) / rect.width) * (c.W - c.L - c.R) + c.L;
		let i = 0;
		points.forEach((_, j) => { if (Math.abs(c.x(j) - px) < Math.abs(c.x(i) - px)) i = j; });
		setAt(i);
	}

	return (
		<>
			<svg ref={svg} viewBox={`0 0 ${c.W} ${c.H}`} height={c.H} role="img" aria-label={`${name} rank, ${Math.round(points[0].v)} to ${Math.round(points[points.length - 1].v)}`}>
				<g className="chart-grid">{c.ticks.map((v) => <line key={v} x1={c.L} x2={c.W - c.R} y1={c.y(v).toFixed(1)} y2={c.y(v).toFixed(1)} />)}</g>
				<g className="chart-axis">
					{c.ticks.map((v) => <text key={v} x={c.L - 6} y={(c.y(v) + 3).toFixed(1)} textAnchor="end">{Math.round(v)}</text>)}
					{points.map((d, i) => c.showLabel(i) && <text key={d.label} x={c.x(i).toFixed(1)} y={c.H - 6} textAnchor="middle">{d.label}</text>)}
				</g>
				<path className="chart-line" d={c.path} />
				{few && points.map((d, i) => (
					<g key={d.label}>
						<circle className={`season-dot${d.est ? ' est' : ''}`} cx={c.x(i).toFixed(1)} cy={c.y(d.v).toFixed(1)} r="4.5" />
						<text className="season-label" x={c.x(i).toFixed(1)} y={(c.y(d.v) - 9).toFixed(1)} textAnchor="middle">{Math.round(d.v)}</text>
					</g>
				))}
				{at != null && <>
					<line className="chart-cross" x1={c.x(at)} x2={c.x(at)} y1={c.T} y2={c.H - c.B} />
					<circle className="chart-dot" cx={c.x(at)} cy={c.y(points[at].v)} r="4.5" />
				</>}
				<rect x={c.L} y="0" width={c.W - c.L - c.R} height={c.H} fill="transparent" role="presentation" onPointerMove={show} onPointerDown={show} onPointerLeave={() => setAt(null)} />
			</svg>
			{at != null && <div className="chart-tip" ref={tip}>{points[at].season}<br />Rank <b>{points[at].v.toFixed(1)}</b>{points[at].est && <><br />estimated</>}</div>}
		</>
	);
}
